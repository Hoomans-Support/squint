#!/usr/bin/env python3
"""Tier 1: Watchdog. Deterministic anomaly detection, no AI.

Reads canonical events and the Guardian report, drops sessions inside quarantine windows, then
looks for two kinds of problems:

  temporal  a screen got worse now than before (all users, or one platform)
  segment   one micro-segment does worse than everyone else on a screen, even when the
            overall numbers look fine (the "blind spot")

Per screen it tests four signals: drop-off (session ends there), median dwell, repeated focus on
one element (hesitation), and rage clicks. Every test is one-sided ("worse") and the significance
threshold is corrected for the number of tests actually run, so a flagged candidate is unlikely
to be chance. Candidates need a minimum sample and a minimum effect size as well.

It does not decide WHY. Candidates go to the Diagnostic Agent (Tier 2) with a sample of
affected and comparison sessions. Screens with a high but stable exit rate are listed separately
so the Diagnostic Agent can confirm they are natural exits.

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

NOW_DAYS = 14            # "now" window; baseline is everything before it
MIN_N = 80               # sessions at a screen needed in each group being compared
FWER = 1e-3              # family-wise false-alarm rate across all tests run
MIN_COUNT = 20           # proportions: minimum affected sessions in the group
MIN_ABS_DIFF = 0.10      # proportions: minimum absolute increase
MIN_RATIO = 1.5          # proportions: minimum relative increase (when reference > 0)
MIN_DWELL_RATIO = 1.5    # median dwell: minimum ratio
MIN_DWELL_MS = 1000      # median dwell: minimum size of the change when the baseline median is 0 (no ratio exists)
REPEAT_FOCUS = 3         # focusing the same element this many times counts as hesitation
SMALL_VIEWPORT = 360     # android with viewport <= this is treated as its own device class
PARSIMONY = 0.85         # prefer the broader of related segments if its effect is this close
HIGH_EXIT = 0.5          # a screen where this share of sessions end is a natural-exit candidate
SAMPLE = 15              # sessions per side in the evidence sample
DIMS = ("platform", "persona", "device_class")
METRICS_TEMPORAL = ("drop_off", "repeat_focus", "rage", "dwell")
METRICS_SEGMENT = ("drop_off", "repeat_focus", "rage")


def device_class(e: dict) -> str:
    os_, vw = e.get("os"), e.get("viewport_w")
    if os_ == "android" and vw is not None and vw <= SMALL_VIEWPORT:
        return "android_small"
    return os_ or "unknown"


KEEP = ("ts", "session_id", "platform", "persona", "os", "viewport_w", "screen", "event_type", "dwell_ms", "element")


def load_sessions(path: Path) -> list[dict]:
    # Group first, then process each session in timestamp order: the input may not be sorted, and an
    # event that arrives before its screen_view would otherwise be dropped.
    by_sid: dict = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            e = json.loads(line)
            by_sid[e["session_id"]].append({k: e[k] for k in KEEP if k in e})
    sessions: dict = {}
    for sid, events in by_sid.items():
        events.sort(key=lambda e: e["ts"])
        s = sessions[sid] = {"sid": sid, "start": events[0]["ts"], "last_ts": "", "last_screen": None,
                             "platform": events[0]["platform"], "persona": None, "device_class": None,
                             "screens": {}}
        for e in events:
            if e.get("persona") and not s["persona"]:
                s["persona"] = e["persona"]
            if s["device_class"] is None and e.get("os"):
                s["device_class"] = device_class(e)
            screen = e.get("screen")
            if not screen:
                continue
            if e["ts"] >= s["last_ts"]:
                s["last_ts"], s["last_screen"] = e["ts"], screen
            if e["event_type"] == "screen_view":
                s["screens"].setdefault(screen, {"dwell": None, "rage": 0, "focus": Counter()})
            st = s["screens"].get(screen)
            if st is None:
                continue
            if e["event_type"] == "screen_leave" and e.get("dwell_ms") is not None:
                st["dwell"] = (st["dwell"] or 0) + e["dwell_ms"]
            elif e["event_type"] == "rage_click":
                st["rage"] += 1
            elif e["event_type"] == "form_focus" and e.get("element"):
                st["focus"][e["element"]] += 1
    out = list(sessions.values())
    for s in out:
        s["dt"] = parse_ts(s["start"])
        s["persona"] = s["persona"] or "unknown"
        s["device_class"] = s["device_class"] or "unknown"
    return out


def session_metrics(s: dict, screen: str) -> dict:
    st = s["screens"][screen]
    return {"drop_off": s["last_screen"] == screen, "rage": st["rage"] > 0,
            "repeat_focus": max(st["focus"].values(), default=0) >= REPEAT_FOCUS, "dwell": st["dwell"]}


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


def compare(metric: str, grp: list[dict], ref: list[dict], screen: str):
    """Compare two session groups on one metric. Returns None if either group is too small."""
    g = [session_metrics(s, screen) for s in grp]
    r = [session_metrics(s, screen) for s in ref]
    if metric == "dwell":
        gv = [m["dwell"] for m in g if m["dwell"] is not None]
        rv = [m["dwell"] for m in r if m["dwell"] is not None]
        if len(gv) < MIN_N or len(rv) < MIN_N:
            return None
        mg, mr = median(gv), median(rv)
        # A zero baseline has no finite ratio (and `Infinity` is not valid JSON), so report None.
        ratio = mg / mr if mr else None
        return {"metric": metric, "value": mg, "reference": mr, "n": len(gv), "n_ref": len(rv),
                "p_value": mwu_greater_p(gv, rv), "ratio": None if ratio is None else round(ratio, 3), "diff": mg - mr,
                "effect_ok": mg >= MIN_DWELL_MS if ratio is None else ratio >= MIN_DWELL_RATIO}
    if len(g) < MIN_N or len(r) < MIN_N:
        return None
    x1, x0 = sum(m[metric] for m in g), sum(m[metric] for m in r)
    p1, p0 = x1 / len(g), x0 / len(r)
    return {"metric": metric, "value": round(p1, 4), "reference": round(p0, 4), "n": len(g), "n_ref": len(r),
            "p_value": prop_p(x1, len(g), x0, len(r)), "diff": round(p1 - p0, 4),
            "ratio": round(p1 / p0, 3) if p0 else None,
            "effect_ok": x1 >= MIN_COUNT and (p1 - p0) >= MIN_ABS_DIFF and (p0 == 0 or p1 / p0 >= MIN_RATIO)}


def label(seg: dict) -> str:
    return ",".join(f"{k}={v}" for k, v in seg.items()) if seg else "all"


def matches(s: dict, seg: dict) -> bool:
    return all(s[k] == v for k, v in seg.items())


def related(a: dict, b: dict) -> bool:
    """True if one segment is a refinement of the other (all shared dims agree, one is a subset)."""
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    return all(big.get(k) == v for k, v in small.items())


def sample_ids(rng, affected: list[dict], comparison: list[dict]) -> dict:
    a = sorted(s["sid"] for s in affected)
    c = sorted(s["sid"] for s in comparison)
    return {"affected": rng.sample(a, min(SAMPLE, len(a))), "comparison": rng.sample(c, min(SAMPLE, len(c)))}


def run_watchdog(events_path: Path, guardian_path: Path, seed: int = 42) -> dict:
    rng = random.Random(seed)
    guardian = json.loads(guardian_path.read_text(encoding="utf-8"))
    windows = guardian["quarantine_windows"]
    all_sessions = load_sessions(events_path)
    sessions = [s for s in all_sessions if not is_quarantined(s["platform"], s["dt"], windows)]

    t_end = max(s["dt"] for s in sessions) + timedelta(seconds=1)
    t_now = t_end - timedelta(days=NOW_DAYS)
    now = [s for s in sessions if s["dt"] >= t_now]
    base = [s for s in sessions if s["dt"] < t_now]
    screens = sorted({sc for s in sessions for sc in s["screens"]})

    def at(group, screen):
        return [s for s in group if screen in s["screens"]]

    # ---- run every comparison, collect results, then apply the corrected threshold ----
    results = []   # (scope, screen, segment, comparison dict, grp, ref)
    for screen in screens:
        for seg in [{}] + [{"platform": p} for p in sorted({s["platform"] for s in sessions})]:
            grp = at([s for s in now if matches(s, seg)], screen)
            ref = at([s for s in base if matches(s, seg)], screen)
            for m in METRICS_TEMPORAL:
                c = compare(m, grp, ref, screen)
                if c:
                    results.append(("temporal", screen, seg, c, grp, ref))
        now_at = at(now, screen)
        values = {d: sorted({s[d] for s in now_at}) for d in DIMS}
        for r in (1, 2, 3):
            for dims in combinations(DIMS, r):
                for combo in product(*(values[d] for d in dims)):
                    seg = dict(zip(dims, combo))
                    grp = [s for s in now_at if matches(s, seg)]
                    rest = [s for s in now_at if not matches(s, seg)]
                    for m in METRICS_SEGMENT:
                        c = compare(m, grp, rest, screen)
                        if c:
                            results.append(("segment", screen, seg, c, grp, rest))

    p_threshold = FWER / max(1, len(results))
    hits = [r for r in results if r[3]["p_value"] < p_threshold and r[3]["effect_ok"]]

    def signal(c):
        return {k: c[k] for k in ("metric", "value", "reference", "n", "n_ref", "p_value", "ratio", "diff")}

    def excess(c):
        return round(c["diff"] * c["n"]) if c["metric"] != "dwell" else 0

    # ---- group hits into candidates ----
    grouped: dict = defaultdict(list)
    for scope, screen, seg, c, grp, ref in hits:
        grouped[(scope, screen, label(seg))].append((seg, c, grp, ref))

    candidates = []
    for (scope, screen, lab), items in grouped.items():
        seg, _, grp, ref = items[0]
        sigs = [signal(c) for _, c, _, _ in items]
        drop = next((c for _, c, _, _ in items if c["metric"] == "drop_off"), None)
        # impact is measured in lost sessions, so excess counts drop-off only (0 if drop-off is not flagged)
        excess_n = excess(drop) if drop else 0
        affected = [s for s in grp if s["last_screen"] == screen] if drop else grp
        comparison = [s for s in ref if s["last_screen"] != screen]
        candidates.append({
            "id": f"{scope}:{screen}:{lab}", "scope": scope, "screen": screen, "segment": seg,
            "segment_label": lab, "signals": sigs, "n_sessions": len(grp), "excess_sessions": excess_n,
            "effect": max((c["diff"] if c["metric"] != "dwell" else 0) for _, c, _, _ in items),
            "reference": "baseline period" if scope == "temporal" else "all other sessions",
            "sample_sessions": sample_ids(rng, affected, comparison),
            "_grp": grp, "_ref": ref,
        })

    # temporal: keep the all-users candidate if there is one, else platform-level
    kept = []
    for screen in {c["screen"] for c in candidates}:
        tmp = [c for c in candidates if c["screen"] == screen and c["scope"] == "temporal"]
        if any(not c["segment"] for c in tmp):
            kept += [c for c in tmp if not c["segment"]]
        else:
            kept += tmp
    # segment: among related (nested) segments on a screen, pick one winner per cluster
    for screen in {c["screen"] for c in candidates}:
        segs = [c for c in candidates if c["screen"] == screen and c["scope"] == "segment"]
        seen = set()
        for c in sorted(segs, key=lambda c: -c["effect"]):
            if c["id"] in seen:
                continue
            cluster = [o for o in segs if o["id"] not in seen and related(c["segment"], o["segment"])]
            for o in cluster:
                seen.add(o["id"])
            ok = [o for o in cluster if o["effect"] >= PARSIMONY * c["effect"]]
            kept.append(min(ok, key=lambda o: (len(o["segment"]), -o["n_sessions"])))

    # explain away: a segment that only looks bad because it overlaps a stronger one is dropped
    final = [c for c in kept if c["scope"] == "temporal"]
    for screen in {c["screen"] for c in kept}:
        accepted = []
        for c in sorted((c for c in kept if c["scope"] == "segment" and c["screen"] == screen), key=lambda c: -c["effect"]):
            def outside(group):
                return [s for s in group if not any(matches(s, a["segment"]) for a in accepted)]
            grp, ref = outside(c["_grp"]), outside(c["_ref"])
            still = False
            for sg in c["signals"]:
                r = compare(sg["metric"], grp, ref, screen)
                if r and r["p_value"] < p_threshold and r["effect_ok"]:
                    still = True
            if still:
                accepted.append(c)
        final += accepted
    kept = sorted(final, key=lambda c: -c["excess_sessions"])
    for c in kept:
        c.pop("_grp", None)
        c.pop("_ref", None)

    # ---- screens with a high, stable exit rate: natural-exit candidates ----
    flagged_screens = {c["screen"] for c in kept}
    high_exit = []
    for screen in screens:
        grp, ref = at(now, screen), at(base, screen)
        if len(grp) < MIN_N or len(ref) < MIN_N:
            continue
        e1 = sum(s["last_screen"] == screen for s in grp) / len(grp)
        e0 = sum(s["last_screen"] == screen for s in ref) / len(ref)
        if e1 >= HIGH_EXIT and screen not in flagged_screens:
            affected = [s for s in grp if s["last_screen"] == screen]
            high_exit.append({"screen": screen, "exit_rate_now": round(e1, 4), "exit_rate_baseline": round(e0, 4),
                              "n_sessions": len(grp), "stable": abs(e1 - e0) < 0.05,
                              "sample_sessions": sample_ids(rng, affected, [s for s in grp if s["last_screen"] != screen])})

    return {
        "params": {"now_days": NOW_DAYS, "min_n": MIN_N, "fwer": FWER, "min_abs_diff": MIN_ABS_DIFF,
                   "min_ratio": MIN_RATIO, "min_count": MIN_COUNT, "min_dwell_ratio": MIN_DWELL_RATIO, "repeat_focus": REPEAT_FOCUS,
                   "small_viewport": SMALL_VIEWPORT, "seed": seed},
        "window": {"baseline_start": iso(min(s["dt"] for s in sessions)), "now_start": iso(t_now), "now_end": iso(t_end)},
        "sessions": {"total": len(all_sessions), "quarantined": len(all_sessions) - len(sessions),
                     "baseline": len(base), "now": len(now)},
        "quarantine_windows": windows,
        "tests_run": len(results), "p_threshold": p_threshold,
        "candidates": kept,
        "high_exit_screens": high_exit,
    }


def verify(report: dict, gt: dict) -> list[tuple[bool, str]]:
    out = []
    cands = report["candidates"]
    s1 = [c for c in cands if c["scope"] == "temporal" and c["screen"] == "kyc_identity" and not c["segment"]]
    out.append((bool(s1), "S1: temporal candidate on kyc_identity for all users"))
    if s1:
        metrics = {sg["metric"] for sg in s1[0]["signals"]}
        out.append(({"dwell", "drop_off"} <= metrics, f"S1: dwell and drop-off both flagged (signals: {sorted(metrics)})"))
    s2 = [c for c in cands if c["scope"] == "segment" and c["screen"] == "connect_bank"
          and c["segment"].get("persona") == "smb" and c["segment"].get("device_class") == "android_small"]
    out.append((bool(s2), "S2: segment candidate persona=smb, device_class=android_small on connect_bank"))
    if s2:
        sg = {x["metric"] for x in s2[0]["signals"]}
        out.append(({"drop_off", "rage"} <= sg, f"S2: drop-off and rage clicks both flagged (signals: {sorted(sg)})"))
        out.append((len(s2[0]["segment"]) == 2, f"S2: segment is not over- or under-specific ({s2[0]['segment_label']})"))
    out.append(("pricing" not in {c["screen"] for c in cands}, "S3: pricing is not flagged as a problem"))
    out.append(("pricing" in {h["screen"] for h in report["high_exit_screens"]}, "S3: pricing listed as high, stable exit for the Diagnostic Agent"))
    gap_screens = set()
    for w in report["quarantine_windows"]:
        gap_screens |= set(w["screens"])
    out.append((not any(c["segment"].get("platform") == "app" and c["screen"] in gap_screens for c in cands),
                "G1: nothing flagged for app on the screens hit by the outage"))
    out.append((len(cands) == 2, f"no extra candidates (found {len(cands)}, expected 2)"))
    out.append((report["sessions"]["quarantined"] > 0, f"quarantined sessions excluded ({report['sessions']['quarantined']})"))
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
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{report['sessions']['now']} sessions in the last {NOW_DAYS} days, {report['tests_run']} tests, "
          f"p<{report['p_threshold']:.1e}, {len(report['candidates'])} candidates")
    for c in report["candidates"]:
        sg = ", ".join(f"{x['metric']} {x['value']:.2f} vs {x['reference']:.2f}" if x["metric"] != "dwell"
                       else f"dwell {x['value']/1000:.0f}s vs {x['reference']/1000:.0f}s" for x in c["signals"])
        print(f"  [{c['scope']}] {c['screen']} / {c['segment_label']}: {sg}  (~{c['excess_sessions']} excess sessions)")
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
