#!/usr/bin/env python3
"""Tier 1: Watchdog. Deterministic anomaly detection, no AI. (synthetic-v2 version)

Reads canonical events and the Guardian report, drops sessions inside quarantine windows, removes
duplicated events (same event_id), then looks for three kinds of problems and one kind of pattern:

  temporal  a screen got worse in the last NOW_DAYS than before (all users)
  burst     a time window (1 to 48 hours) in which exits on one screen jump (scan statistic over hourly counts);
            this is how an outage-like problem, such as an OTP that is not delivered for a few hours, shows up
  segment   one segment (persona, device class, product, app version; up to two at once) does worse than everyone
            else on a screen, over the whole period, even when the overall numbers look fine
  pattern   a segment that behaves differently without failing (who tops up large amounts, who prefers which
            product). Reported separately and never as a problem.

Per screen it tests: drop-off (the session ends there), rage clicks, errors, and (temporal only) median dwell.
Every test is one-sided ("worse"), proportion tests use Fisher's exact test, and the significance threshold is
corrected for the number of tests actually run (family-wise), so a flagged candidate is unlikely to be chance.
Candidates also need a minimum sample and a minimum effect size. Each candidate carries a rules-based
`hint_class` for the Diagnostic Agent to confirm or overrule; the Watchdog does not decide WHY.

Screens with a high but stable exit rate are listed separately (`high_exit_screens`), terminal success
screens excluded, so the Diagnostic Agent can confirm they are natural exits.

Usage:
  python pipeline/watchdog.py --input data/synthetic/canonical_events.jsonl \
      --guardian data/synthetic/guardian_report.json --out data/synthetic/watchdog_candidates.json \
      [--ground-truth data/synthetic/ground_truth.json]
Exit code is 1 if --ground-truth is given and any expectation fails.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from itertools import combinations, product
from pathlib import Path
from statistics import median

from guardian import is_quarantined, iso, parse_ts
from schema import TERMINAL_SCREENS, journey_of

NOW_DAYS = 14            # "now" window for temporal tests; baseline is everything before it
MIN_N = 80               # temporal: sessions at a screen needed in each group being compared
MIN_N_SEG = 60           # segment: sessions needed in the segment and in the rest
FWER = 1e-3              # family-wise false-alarm rate across all tests run
MIN_COUNT = 20           # proportions: minimum affected sessions in the group
MIN_ABS_DIFF = 0.10      # proportions: minimum absolute increase
MIN_RATIO = 1.5          # proportions: minimum relative increase (when reference > 0)
MIN_DWELL_RATIO = 1.5    # median dwell: minimum ratio
MIN_DWELL_MS = 1000      # median dwell: minimum size of the change when the baseline median is 0
REPEAT_FOCUS = 3         # focusing the same element this many times counts as hesitation
PARSIMONY = 0.75         # prefer the broader of related segments if its effect is this close
HIGH_EXIT = 0.5          # a screen where this share of sessions end is a natural-exit candidate
HIGH_EXIT_MIN_N = 20
SAMPLE = 15              # sessions per side in the evidence sample
BURST_MAX_H = 48
BURST_MIN_N = 20         # sessions at the screen inside the window
BURST_MIN_COUNT = 15     # exits inside the window
BURST_MIN_DIFF = 0.20    # exit rate inside minus outside
PATTERN_MIN_N = 40
PATTERN_THRESHOLD_PHP = 5000   # top-up amounts are compared against this
DIMS = ("persona", "device_class", "product", "app_version")
SEG_MAX_DIMS = 2
METRICS_TEMPORAL = ("drop_off", "rage", "error", "dwell")
METRICS_SEGMENT = ("drop_off", "rage", "error")


KEEP = ("event_id", "ts", "session_id", "user_id", "device_id", "platform", "persona", "device_class", "app_version",
        "product", "amount_php", "screen", "event_type", "dwell_ms", "element", "error_code")


def load_sessions(path: Path) -> list[dict]:
    """Group events by session, drop duplicated event ids, and process each session in timestamp order
    (the input may not be sorted)."""
    by_sid: dict = defaultdict(list)
    seen: set = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            e = json.loads(line)
            eid = e.get("event_id")
            if eid is not None:
                if eid in seen:
                    continue
                seen.add(eid)
            by_sid[e["session_id"]].append({k: e[k] for k in KEEP if k in e})
    out = []
    for sid, events in by_sid.items():
        events.sort(key=lambda e: e["ts"])
        s = {"sid": sid, "start": events[0]["ts"], "last_ts": "", "last_screen": None, "platform": events[0]["platform"],
             "persona": None, "device_class": None, "app_version": None, "product": None, "amount": None,
             "user": None, "device": None, "screens": {}}
        for e in events:
            for k, f in (("persona", "persona"), ("device_class", "device_class"), ("app_version", "app_version"),
                         ("product", "product"), ("user", "user_id"), ("device", "device_id")):
                if s[k] is None and e.get(f):
                    s[k] = e[f]
            screen = e.get("screen")
            if not screen:
                continue
            if e["ts"] >= s["last_ts"]:
                s["last_ts"], s["last_screen"] = e["ts"], screen
            if e["event_type"] == "screen_view":
                s["screens"].setdefault(screen, {"dwell": None, "rage": 0, "dead": 0, "back": 0, "errors": 0, "view": e["ts"],
                                                 "focus": Counter()})
            st = s["screens"].get(screen)
            if st is None:
                continue
            et = e["event_type"]
            if et == "screen_leave" and e.get("dwell_ms") is not None:
                st["dwell"] = (st["dwell"] or 0) + e["dwell_ms"]
            elif et == "rage_click":
                st["rage"] += 1
            elif et == "dead_tap":
                st["dead"] += 1
            elif et == "back":
                st["back"] += 1
            elif et == "error":
                st["errors"] += 1
            elif et == "form_focus" and e.get("element"):
                st["focus"][e["element"]] += 1
            if screen == "topup_confirm" and e.get("amount_php") is not None:
                s["amount"] = e["amount_php"]
        s["dt"] = parse_ts(s["start"])
        s["persona"] = s["persona"] or "unknown"
        s["device_class"] = s["device_class"] or "unknown"
        s["journey"] = journey_of(s["screens"])
        out.append(s)
    return out


def prop_p(x1, n1, x0, n0) -> float:
    """One-sided Fisher exact p-value that rate 1 is higher than rate 0.

    Exact rather than a z-test: with small counts the normal approximation is anti-conservative
    and let a chance dip through on one test seed.
    """
    total, big_n = x1 + x0, n1 + n0
    log_den = math.lgamma(big_n + 1) - math.lgamma(n1 + 1) - math.lgamma(big_n - n1 + 1)
    p = 0.0
    for k in range(x1, min(n1, total) + 1):
        if total - k > n0:
            continue
        log_num = (math.lgamma(total + 1) - math.lgamma(k + 1) - math.lgamma(total - k + 1)
                   + math.lgamma(big_n - total + 1) - math.lgamma(n1 - k + 1) - math.lgamma(n0 - (total - k) + 1))
        p += math.exp(log_num - log_den)
    return min(1.0, p)


def mwu_greater_p(a: list, b: list) -> float:
    """One-sided Mann-Whitney U (normal approximation, tie-averaged ranks): is a larger than b?"""
    n1, n0 = len(a), len(b)
    combined = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    rank_sum, i = 0.0, 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg = (i + 1 + j) / 2
        rank_sum += avg * sum(1 for k in range(i, j) if combined[k][1] == 0)
        i = j
    u = rank_sum - n1 * (n1 + 1) / 2
    sigma = math.sqrt(n1 * n0 * (n1 + n0 + 1) / 12)
    return 0.5 * math.erfc(((u - n1 * n0 / 2 - 0.5) / sigma) / math.sqrt(2))


def count_result(metric, x1, n1, x0, n0, min_n):
    """Proportion comparison from counts. Returns None if either group is too small."""
    if n1 < min_n or n0 < min_n:
        return None
    p1, p0 = x1 / n1, x0 / n0
    return {"metric": metric, "value": round(p1, 4), "reference": round(p0, 4), "n": n1, "n_ref": n0,
            "p_value": prop_p(x1, n1, x0, n0), "diff": round(p1 - p0, 4),
            "ratio": round(p1 / p0, 3) if p0 else None,
            "effect_ok": x1 >= MIN_COUNT and (p1 - p0) >= MIN_ABS_DIFF and (p0 == 0 or p1 / p0 >= MIN_RATIO)}


def dwell_result(gv: list, rv: list):
    if len(gv) < MIN_N or len(rv) < MIN_N:
        return None
    mg, mr = median(gv), median(rv)
    # A zero baseline has no finite ratio (and `Infinity` is not valid JSON), so report None.
    ratio = mg / mr if mr else None
    return {"metric": "dwell", "value": mg, "reference": mr, "n": len(gv), "n_ref": len(rv),
            "p_value": mwu_greater_p(gv, rv), "ratio": None if ratio is None else round(ratio, 3), "diff": mg - mr,
            "effect_ok": mg >= MIN_DWELL_MS if ratio is None else ratio >= MIN_DWELL_RATIO}


def label(seg: dict) -> str:
    return ",".join(f"{k}={v}" for k, v in seg.items()) if seg else "all"


def related(a: dict, b: dict) -> bool:
    """True if one segment is a refinement of the other (all shared dims agree, one is a subset)."""
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    return all(big.get(k) == v for k, v in small.items())


def popcount(x: int) -> int:
    return x.bit_count()


class Screen:
    """Per-screen table: sessions that viewed the screen, with bitmasks for fast group counts."""

    def __init__(self, name: str, sessions: list[dict], t_now: datetime):
        self.name = name
        self.rows = [s for s in sessions if name in s["screens"]]
        self.all = (1 << len(self.rows)) - 1
        self.metric = {m: 0 for m in ("drop_off", "rage", "error", "dead")}
        self.now = self.base = 0
        self.attr: dict = defaultdict(int)
        self.dwell: list = []
        for i, s in enumerate(self.rows):
            st, bit = s["screens"][name], 1 << i
            if s["last_screen"] == name:
                self.metric["drop_off"] |= bit
            if st["rage"]:
                self.metric["rage"] |= bit
            if st["errors"]:
                self.metric["error"] |= bit
            if st["dead"]:
                self.metric["dead"] |= bit
            if s["dt"] >= t_now:
                self.now |= bit
            else:
                self.base |= bit
            for d in DIMS:
                if s[d] is not None and s[d] != "unknown" or d == "persona":
                    self.attr[(d, s[d])] |= bit
            self.dwell.append(st["dwell"])

    def count(self, mask: int, metric: str) -> tuple[int, int]:
        return popcount(mask & self.metric[metric]), popcount(mask)

    def members(self, mask: int) -> list[dict]:
        return [s for i, s in enumerate(self.rows) if mask >> i & 1]

    def seg_mask(self, seg: dict) -> int:
        m = self.all
        for d, v in seg.items():
            m &= self.attr.get((d, v), 0)
        return m


def sample_ids(rng, affected: list[dict], comparison: list[dict]) -> dict:
    a = sorted(s["sid"] for s in affected)
    c = sorted(s["sid"] for s in comparison)
    return {"affected": rng.sample(a, min(SAMPLE, len(a))), "comparison": rng.sample(c, min(SAMPLE, len(c)))}


def llr(x, n, big_x, big_n) -> float:
    """Binomial log-likelihood ratio: window (x of n) vs the same rate everywhere (big_x of big_n)."""
    def ll(k, m):
        if m == 0 or k == 0 or k == m:
            return 0.0
        p = k / m
        return k * math.log(p) + (m - k) * math.log(1 - p)
    return ll(x, n) + ll(big_x - x, big_n - n) - ll(big_x, big_n)


def scan_bursts(screen: Screen, t0: datetime, hours: int, exclude: set, skip: int = 0):
    """Best window (start hour, length) where the exit rate jumps, ignoring hours in `exclude`."""
    n, x = [0] * hours, [0] * hours
    for i, s in enumerate(screen.rows):
        if skip >> i & 1:       # sessions already explained by a flagged segment do not make a time window
            continue
        h = int((parse_ts(s["screens"][screen.name]["view"]) - t0).total_seconds() // 3600)
        if 0 <= h < hours and h not in exclude:
            n[h] += 1
            x[h] += s["last_screen"] == screen.name
    pn, px = [0], [0]
    for h in range(hours):
        pn.append(pn[-1] + n[h])
        px.append(px[-1] + x[h])
    big_n, big_x = pn[-1], px[-1]
    best, tested = None, 0
    for length in range(1, BURST_MAX_H + 1):
        for a in range(0, hours - length + 1):
            nw, xw = pn[a + length] - pn[a], px[a + length] - px[a]
            if nw < BURST_MIN_N:
                continue
            tested += 1
            if xw < BURST_MIN_COUNT or big_n - nw < BURST_MIN_N:
                continue
            rw, rc = xw / nw, (big_x - xw) / (big_n - nw)
            if rw - rc < BURST_MIN_DIFF or rw < MIN_RATIO * rc:
                continue
            score = llr(xw, nw, big_x, big_n)
            if best is None or score > best["llr"]:
                best = {"start_h": a, "hours": length, "n": nw, "x": xw, "n_out": big_n - nw, "x_out": big_x - xw, "llr": score}
    return best, tested


def hint(scope: str, seg: dict, signals: list[dict]) -> tuple[str, str]:
    """Rules-based first guess at the class. The Diagnostic Agent confirms or overrules it; it never guesses."""
    metrics = {s["metric"] for s in signals}
    if scope == "burst":
        return "technical_fault", "a short window where exits and repeated taps jump for everyone points to a fault, not to user intent"
    if seg.get("persona") == "fraudster":
        return "unclassified_needs_review", "a risk persona with failed attempts: needs a human, no confident rule"
    if scope == "segment" and metrics & {"rage", "error"} and "drop_off" in metrics:
        return "technical_bug_or_ux_friction", "drop-off together with rage taps or errors in one segment"
    if scope == "temporal" and "dwell" in metrics and "drop_off" in metrics:
        return "language_cognitive_overload", "longer time on the screen together with more exits since a date"
    return "unclassified_needs_review", "no confident rule matched"


def run_watchdog(events_path: Path, guardian_path: Path, seed: int = 42) -> dict:
    rng = random.Random(seed)
    guardian = json.loads(guardian_path.read_text(encoding="utf-8"))
    windows = guardian["quarantine_windows"]
    all_sessions = load_sessions(events_path)
    sessions = [s for s in all_sessions if not is_quarantined(s["platform"], s["dt"], windows, s["app_version"], s["journey"])]

    t_start = min(s["dt"] for s in sessions).replace(minute=0, second=0, microsecond=0)
    t_end = max(s["dt"] for s in sessions) + timedelta(seconds=1)
    t_now = t_end - timedelta(days=NOW_DAYS)
    now = [s for s in sessions if s["dt"] >= t_now]
    base = [s for s in sessions if s["dt"] < t_now]
    screens = sorted({sc for s in sessions for sc in s["screens"]} - TERMINAL_SCREENS)
    tables = {sc: Screen(sc, sessions, t_now) for sc in screens}

    # ---- every comparison is run first, then the corrected threshold is applied
    results = []   # (scope, screen, segment, comparison dict, grp mask, ref mask)
    for sc, tb in tables.items():
        gm, rm = tb.now, tb.base
        for m in METRICS_TEMPORAL:
            if m == "dwell":
                gv = [d for i, d in enumerate(tb.dwell) if gm >> i & 1 and d is not None]
                rv = [d for i, d in enumerate(tb.dwell) if rm >> i & 1 and d is not None]
                c = dwell_result(gv, rv)
            else:
                (x1, n1), (x0, n0) = tb.count(gm, m), tb.count(rm, m)
                c = count_result(m, x1, n1, x0, n0, MIN_N)
            if c:
                results.append(("temporal", sc, {}, c, gm, rm))
        values = {d: sorted(v for (dd, v) in tb.attr if dd == d) for d in DIMS}
        for r in range(1, SEG_MAX_DIMS + 1):
            for dims in combinations(DIMS, r):
                if any(len(values[d]) < 2 for d in dims):
                    continue
                for combo in product(*(values[d] for d in dims)):
                    seg = dict(zip(dims, combo))
                    gm = tb.seg_mask(seg)
                    if popcount(gm) < MIN_N_SEG:
                        continue
                    rm = tb.all & ~gm
                    for m in METRICS_SEGMENT:
                        (x1, n1), (x0, n0) = tb.count(gm, m), tb.count(rm, m)
                        c = count_result(m, x1, n1, x0, n0, MIN_N_SEG)
                        if c:
                            results.append(("segment", sc, seg, c, gm, rm))

    p_threshold = FWER / max(1, len(results))
    hits = [r for r in results if r[3]["p_value"] < p_threshold and r[3]["effect_ok"]]

    def signal(c):
        return {k: c[k] for k in ("metric", "value", "reference", "n", "n_ref", "p_value", "ratio", "diff")}

    def excess(c):
        return round(c["diff"] * c["n"]) if c["metric"] != "dwell" else 0

    grouped: dict = defaultdict(list)
    for scope, sc, seg, c, gm, rm in hits:
        grouped[(scope, sc, label(seg))].append((seg, c, gm, rm))

    candidates = []
    for (scope, sc, lab), items in grouped.items():
        tb = tables[sc]
        seg, _, gm, rm = items[0]
        sigs = [signal(c) for _, c, _, _ in items]
        drop = next((c for _, c, _, _ in items if c["metric"] == "drop_off"), None)
        excess_n = excess(drop) if drop else 0
        grp, ref = tb.members(gm), tb.members(rm)
        affected = [s for s in grp if s["last_screen"] == sc] if drop else grp
        comparison = [s for s in ref if s["last_screen"] != sc]
        hc, hr = hint(scope, seg, sigs)
        candidates.append({
            "id": f"{scope}:{sc}:{lab}", "scope": scope, "screen": sc, "segment": seg,
            "segment_label": lab, "signals": sigs, "n_sessions": popcount(gm), "excess_sessions": excess_n,
            "effect": max((c["diff"] if c["metric"] != "dwell" else 0) for _, c, _, _ in items),
            "reference": "baseline period" if scope == "temporal" else "all other sessions",
            "hint_class": hc, "hint_rule": hr,
            "sample_sessions": sample_ids(rng, affected, comparison),
            "_sc": sc, "_g": gm, "_r": rm,
        })

    kept = []
    for sc in {c["screen"] for c in candidates}:
        tmp = [c for c in candidates if c["screen"] == sc and c["scope"] == "temporal"]
        kept += tmp
        segs = [c for c in candidates if c["screen"] == sc and c["scope"] == "segment"]
        seen, picked = set(), []
        for c in sorted(segs, key=lambda c: -c["effect"]):
            if c["id"] in seen:
                continue
            cluster = [o for o in segs if o["id"] not in seen and related(c["segment"], o["segment"])]
            for o in cluster:
                seen.add(o["id"])
            ok = [o for o in cluster if o["effect"] >= PARSIMONY * c["effect"]]
            pick = min(ok, key=lambda o: (len(o["segment"]), -o["n_sessions"]))
            picked.append(pick)
        # a refinement that is not clearly worse than the rest of the broader segment it sits in is the broader segment
        tb, stands, swapped = tables[sc], [], []
        for p in picked:
            repl = None
            for q in sorted(segs, key=lambda q: len(q["segment"])):
                if q is not p and len(q["segment"]) < len(p["segment"]) and all(p["segment"].get(d) == v for d, v in q["segment"].items()):
                    m = p["signals"][0]["metric"]
                    (x1, n1), (x0, n0) = tb.count(p["_g"], m), tb.count(q["_g"] & ~p["_g"], m)
                    r = count_result(m, x1, n1, x0, n0, 20)
                    if not (r and r["p_value"] < 0.01 and r["diff"] >= MIN_ABS_DIFF):
                        repl = q
                        break
            (swapped if repl else stands).append(repl or p)
        # a broader segment brought back this way only counts if no clearly distinct refinement already covers it
        picked = list({c["id"]: c for c in stands + [q for q in swapped if not any(
            all(p["segment"].get(d) == v for d, v in q["segment"].items()) for p in stands)]}.values())
        # a refinement of another picked segment on this screen is the same cause, not a new finding
        kept += [p for p in picked if not any(q is not p and len(q["segment"]) < len(p["segment"])
                                              and all(p["segment"].get(d) == v for d, v in q["segment"].items()) for q in picked)]

    # explain away: a segment that only looks bad because it overlaps a stronger one is dropped
    final = [c for c in kept if c["scope"] == "temporal"]
    explained: dict = {}
    for sc in {c["screen"] for c in kept}:
        tb, accepted, acc_mask = tables[sc], [], 0
        for c in sorted((c for c in kept if c["scope"] == "segment" and c["screen"] == sc), key=lambda c: -c["effect"]):
            gm, rm = c["_g"] & ~acc_mask, c["_r"] & ~acc_mask
            still = False
            for sg in c["signals"]:
                (x1, n1), (x0, n0) = tb.count(gm, sg["metric"]), tb.count(rm, sg["metric"])
                r = count_result(sg["metric"], x1, n1, x0, n0, MIN_N_SEG)
                if r and r["p_value"] < p_threshold and r["effect_ok"]:
                    still = True
            if still:
                accepted.append(c)
                acc_mask |= c["_g"]
        explained[sc] = acc_mask
        final += accepted

    # ---- bursts: scan hourly exit counts for a window where the exit rate jumps
    hours = int((t_end - t_start).total_seconds() // 3600) + 1
    burst_tests, burst_found = 0, []
    for sc, tb in tables.items():
        excl: set = set()
        for _ in range(2):
            best, tested = scan_bursts(tb, t_start, hours, excl, explained.get(sc, 0))
            burst_tests += tested if not excl else 0
            if not best:
                break
            burst_found.append((sc, best))
            excl |= set(range(best["start_h"], best["start_h"] + best["hours"]))
    burst_p = FWER / max(1, burst_tests)
    for sc, b in burst_found:
        p = prop_p(b["x"], b["n"], b["x_out"], b["n_out"])
        if p >= burst_p:
            continue
        tb = tables[sc]
        ws, we = t_start + timedelta(hours=b["start_h"]), t_start + timedelta(hours=b["start_h"] + b["hours"])
        gm = rm = 0
        for i, s in enumerate(tb.rows):
            v = parse_ts(s["screens"][sc]["view"])
            if ws <= v < we:
                gm |= 1 << i
            else:
                rm |= 1 << i
        sigs = [{"metric": "drop_off", "value": round(b["x"] / b["n"], 4), "reference": round(b["x_out"] / b["n_out"], 4),
                 "n": b["n"], "n_ref": b["n_out"], "p_value": p, "ratio": round((b["x"] / b["n"]) / (b["x_out"] / b["n_out"]), 3) if b["x_out"] else None,
                 "diff": round(b["x"] / b["n"] - b["x_out"] / b["n_out"], 4)}]
        for m in ("rage", "error"):
            (x1, n1), (x0, n0) = tb.count(gm, m), tb.count(rm, m)
            r = count_result(m, x1, n1, x0, n0, BURST_MIN_N)
            if r and r["p_value"] < burst_p and r["effect_ok"]:
                sigs.append(signal(r))
        grp, ref = tb.members(gm), tb.members(rm)
        hc, hr = hint("burst", {}, sigs)
        final.append({
            "id": f"burst:{sc}:{iso(ws)[:13]}", "scope": "burst", "screen": sc, "segment": {}, "segment_label": "all",
            "window": {"start": iso(ws), "end": iso(we), "hours": b["hours"]}, "signals": sigs, "n_sessions": b["n"],
            "excess_sessions": round(sigs[0]["diff"] * b["n"]), "effect": sigs[0]["diff"],
            "reference": "the rest of the period", "hint_class": hc, "hint_rule": hr,
            "sample_sessions": sample_ids(rng, [s for s in grp if s["last_screen"] == sc], [s for s in ref if s["last_screen"] != sc]),
        })
    kept = sorted(final, key=lambda c: -c["excess_sessions"])
    for c in kept:
        for k in ("_sc", "_g", "_r"):
            c.pop(k, None)

    # ---- patterns: segments that behave differently without failing
    patterns = find_patterns(sessions)

    # ---- screens with a high, stable exit rate: natural-exit candidates
    flagged_screens = {c["screen"] for c in kept}
    high_exit = []
    for sc, tb in tables.items():
        (x1, n1), (x0, n0) = tb.count(tb.now, "drop_off"), tb.count(tb.base, "drop_off")
        if n1 < HIGH_EXIT_MIN_N or n0 < HIGH_EXIT_MIN_N:
            continue
        e1, e0 = x1 / n1, x0 / n0
        if e1 >= HIGH_EXIT and sc not in flagged_screens:
            aff = tb.members(tb.now & tb.metric["drop_off"])
            high_exit.append({"screen": sc, "exit_rate_now": round(e1, 4), "exit_rate_baseline": round(e0, 4),
                              "n_sessions": n1, "stable": abs(e1 - e0) < 0.05,
                              "sample_sessions": sample_ids(rng, aff, tb.members(tb.now & ~tb.metric["drop_off"]))})

    return {
        "params": {"now_days": NOW_DAYS, "min_n": MIN_N, "min_n_segment": MIN_N_SEG, "fwer": FWER, "min_abs_diff": MIN_ABS_DIFF,
                   "min_ratio": MIN_RATIO, "min_count": MIN_COUNT, "min_dwell_ratio": MIN_DWELL_RATIO,
                   "segment_scope": "whole period", "dims": list(DIMS), "seed": seed},
        "window": {"baseline_start": iso(min(s["dt"] for s in sessions)), "now_start": iso(t_now), "now_end": iso(t_end)},
        "sessions": {"total": len(all_sessions), "quarantined": len(all_sessions) - len(sessions),
                     "baseline": len(base), "now": len(now)},
        "quarantine_windows": windows,
        "tests_run": len(results), "p_threshold": p_threshold, "burst_windows_tested": burst_tests, "burst_p_threshold": burst_p,
        "candidates": kept,
        "patterns": patterns,
        "high_exit_screens": high_exit,
    }


def find_patterns(sessions: list[dict]) -> list[dict]:
    """Who tops up large amounts, and who prefers which product. Fisher exact, corrected; never a problem."""
    out = []
    tops = [s for s in sessions if s["journey"] == "topup" and s["amount"] is not None]
    personas = sorted({s["persona"] for s in tops})
    thr = FWER / max(1, len(personas))
    for p in personas:
        g, r = [s for s in tops if s["persona"] == p], [s for s in tops if s["persona"] != p]
        if len(g) < PATTERN_MIN_N or len(r) < PATTERN_MIN_N:
            continue
        x1, x0 = sum(s["amount"] > PATTERN_THRESHOLD_PHP for s in g), sum(s["amount"] > PATTERN_THRESHOLD_PHP for s in r)
        pv = prop_p(x1, len(g), x0, len(r))
        if pv < thr and x1 / len(g) >= 0.5 and x1 / len(g) - x0 / len(r) >= 0.3:
            out.append({"id": f"pattern:topup_amount:{p}", "kind": "topup_amount", "persona": p, "threshold_php": PATTERN_THRESHOLD_PHP,
                        "value": round(x1 / len(g), 4), "reference": round(x0 / len(r), 4), "n": len(g), "n_ref": len(r), "p_value": pv,
                        "median_php": int(median(s["amount"] for s in g)), "reference_median_php": int(median(s["amount"] for s in r)),
                        "share_above_50000": round(sum(s["amount"] > 50000 for s in g) / len(g), 4),
                        "hint_class": "behavior_pattern", "hint_rule": "a segment that differs in size, with no failure signal"})
    tx = [s for s in sessions if s["journey"] == "transaction" and s["product"]]
    products = sorted({s["product"] for s in tx})
    tx_personas = sorted({s["persona"] for s in tx})
    thr = FWER / max(1, len(tx_personas) * len(products))
    for p in tx_personas:
        for q in products:
            g, r = [s for s in tx if s["persona"] == p], [s for s in tx if s["persona"] != p]
            if len(g) < PATTERN_MIN_N or len(r) < PATTERN_MIN_N:
                continue
            x1, x0 = sum(s["product"] == q for s in g), sum(s["product"] == q for s in r)
            pv = prop_p(x1, len(g), x0, len(r))
            if pv < thr and x1 / len(g) >= 0.4 and x1 / len(g) - x0 / len(r) >= 0.25 and x1 / len(g) >= 2 * (x0 / len(r)):
                out.append({"id": f"pattern:product:{p}:{q}", "kind": "product_preference", "persona": p, "product": q,
                            "value": round(x1 / len(g), 4), "reference": round(x0 / len(r), 4), "n": len(g), "n_ref": len(r),
                            "p_value": pv, "hint_class": "behavior_pattern", "hint_rule": "a segment that prefers one product, with no failure signal"})
    return out


def verify(report: dict, gt: dict) -> list[tuple[bool, str]]:
    out = []
    cands = report["candidates"]
    m = {x["id"].split("_")[0]: x for x in gt["must_flag"]}
    pat = {x["id"].split("_")[0]: x for x in gt["must_flag_patterns"]}

    def is_p1(c):
        w = m["P1"]["window_utc"]
        ts, te = parse_ts(w[0]), parse_ts(w[1])
        if c["scope"] != "burst" or c["screen"] != "otp":
            return False
        cs, ce = parse_ts(c["window"]["start"]), parse_ts(c["window"]["end"])
        inter = max(timedelta(0), min(te, ce) - max(ts, cs))
        return inter / (max(te, ce) - min(ts, cs)) >= 0.7

    def is_p4(c):
        return c["scope"] == "segment" and c["screen"] == "txn_checkout" and c["segment"] == m["P4"]["segment"]

    def is_m1(c):
        return c["scope"] == "segment" and c["segment"] == m["M1"]["segment"]

    p1 = [c for c in cands if is_p1(c)]
    out.append((len(p1) == 1, f"P1: one burst on otp overlapping the true window (found {[(c['window']['start'], c['window']['end']) for c in cands if c['scope'] == 'burst']})"))
    if p1:
        sg = {x["metric"] for x in p1[0]["signals"]}
        out.append(({"drop_off", "rage"} <= sg, f"P1: drop-off and resend rage taps both flagged (signals {sorted(sg)})"))
        out.append((p1[0]["hint_class"] == m["P1"]["expected_class"], f"P1: hint class {p1[0]['hint_class']} (expected {m['P1']['expected_class']})"))
    p4 = [c for c in cands if is_p4(c)]
    out.append((len(p4) == 1, f"P4: segment persona=individual_trader, product=send_money flagged at txn_checkout (found {[c['segment_label'] for c in cands if c['screen'] == 'txn_checkout']})"))
    if p4:
        sg = {x["metric"] for x in p4[0]["signals"]}
        out.append(("drop_off" in sg, f"P4: drop-off flagged (signals {sorted(sg)})"))
        out.append((p4[0]["hint_class"] == m["P4"]["expected_class"], f"P4: hint class {p4[0]['hint_class']} (expected {m['P4']['expected_class']})"))
    m1 = [c for c in cands if is_m1(c)]
    out.append((len(m1) >= 1, f"M1: segment persona=fraudster flagged on {sorted(c['screen'] for c in m1)}"))
    out.append((all(c["hint_class"] == m["M1"]["expected_class"] for c in m1) and bool(m1), "M1: class is unclassified_needs_review (no confident rule)"))
    extra = [c["id"] for c in cands if not (is_p1(c) or is_p4(c) or is_m1(c))]
    out.append((not extra, f"no extra candidates (found {len(cands)}: {len(p1)} P1, {len(p4)} P4, {len(m1)} M1; extra {extra})"))
    pats = report["patterns"]
    p2 = [p for p in pats if p["kind"] == "topup_amount" and p["persona"] == pat["P2"]["persona"]]
    out.append((len(p2) == 1 and p2[0]["share_above_50000"] >= 0.8, f"P2: large_business top-up pattern found (above PHP 50,000: {p2[0]['share_above_50000'] if p2 else None})"))
    p3 = [p for p in pats if p["kind"] == "product_preference" and p["persona"] == "sari_sari" and p["product"] == "eload"]
    out.append((len(p3) == 1 and p3[0]["value"] >= 0.6, f"P3: sari_sari prefers eload as a pattern ({p3[0]['value'] if p3 else None})"))
    out.append((len(pats) == 2, f"no extra patterns (found {len(pats)}: {[p['id'] for p in pats]})"))
    out.append((not ({c["screen"] for c in cands} & {"personal_data", "tin", "prices"}), "control and M2: personal_data, tin and prices are not candidates"))
    out.append(("prices" in {h["screen"] for h in report["high_exit_screens"]}, "M2: prices listed as a high, stable exit for the Diagnostic Agent"))
    hx = next((h for h in report["high_exit_screens"] if h["screen"] == "prices"), None)
    out.append((bool(hx and hx["stable"]), "M2: the prices exit rate is stable"))
    out.append(("kyc_selfie" not in {c["screen"] for c in cands}, "G1: nothing flagged on kyc_selfie (silent tracker is not user behavior)"))
    out.append((report["sessions"]["quarantined"] > 0, f"G1: sessions inside the quarantine window excluded ({report['sessions']['quarantined']})"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True)
    ap.add_argument("--guardian", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--ground-truth")
    args = ap.parse_args()

    report = run_watchdog(Path(args.input), Path(args.guardian), args.seed)
    Path(args.out).write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"{report['sessions']['now']} sessions in the last {NOW_DAYS} days, {report['tests_run']} tests, "
          f"p<{report['p_threshold']:.1e}, {len(report['candidates'])} candidates, {len(report['patterns'])} patterns")
    for c in report["candidates"]:
        sg = ", ".join(f"{x['metric']} {x['value']:.2f} vs {x['reference']:.2f}" if x["metric"] != "dwell"
                       else f"dwell {x['value']/1000:.0f}s vs {x['reference']/1000:.0f}s" for x in c["signals"])
        print(f"  [{c['scope']}] {c['screen']} / {c['segment_label']}: {sg}  (~{c['excess_sessions']} excess sessions) -> {c['hint_class']}")
    for p in report["patterns"]:
        print(f"  [pattern] {p['id']}: {p['value']:.0%} vs {p['reference']:.0%}")
    for h in report["high_exit_screens"]:
        print(f"  high exit: {h['screen']} {h['exit_rate_now']:.0%} (baseline {h['exit_rate_baseline']:.0%}, stable={h['stable']})")
    if args.ground_truth:
        gt = json.loads(Path(args.ground_truth).read_text(encoding="utf-8"))
        ok = True
        print("ground-truth check:")
        for passed, msg in verify(report, gt):
            ok &= passed
            print(f"  {'PASS' if passed else 'FAIL'}  {msg}")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
