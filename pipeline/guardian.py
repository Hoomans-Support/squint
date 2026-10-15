#!/usr/bin/env python3
"""Tier 0: Telemetry Guardian. Deterministic pre-flight checks, no AI. (synthetic-v2 version)

Runs on canonical events before any analysis. Its job is to separate genuine behavioral shifts
from broken telemetry, so the Watchdog and the Diagnostic Agent never report a tracking fault as user
behavior. It produces:

  findings            what looks wrong with the data and why
  faults              the same, as a plain-language health list for the UI (status active | resolved)
  quarantine_windows  (platform, app_version, journeys, start, end) spans the Watchdog must exclude
  checks              pass/warn/fail per check, for the UI and the deck

Checks:
  schema         every event validates against schema.py
  duplicates     event_id repeated (an event fired twice). Reported per screen and OS with its date span;
                 "resolved" when no duplicate was seen in the last DUP_RESOLVED_DAYS
  row_loss       event ids are assigned in order by the ingestion gateway, so a gap in the sequence is a lost
                 row; days losing more than ROW_LOSS_MIN of their rows are flagged. Skipped when ids are not sequential
  unmapped       events whose raw value or raw property had no mapping (flagged for review, never ignored)
  volume_gap     hourly screen_view count per (platform, entry screen) vs the same hour-of-day on other days; a run of
                 >= MIN_RUN low hours that is also statistically implausible (Poisson tail)
  session_end    runs of hours where most sessions never log a session_end
  step_skipped   sessions that reach screen Y of a journey without ever logging the screen X that must come before
                 it, per app version. A run of those is a silent tracker, not user behavior

Usage:
  python pipeline/guardian.py --input data/synthetic/canonical_events.jsonl \
      --out data/synthetic/guardian_report.json [--ground-truth data/synthetic/ground_truth.json]
Exit code is 1 if --ground-truth is given and any expectation fails.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from schema import JOURNEYS, SCREEN_LABELS, journey_of, validate_event

UTC = timezone.utc
MIN_EXPECTED = 1.5      # ignore series too sparse to judge an hour
LOW_RATIO = 0.25        # an hour is "low" if observed <= this share of expected
MIN_RUN = 3             # consecutive low hours before flagging
FWER = 1e-3             # family-wise false-alarm rate; per-test threshold = FWER / (series x hours)
END_MISSING_RATE = 0.5  # share of sessions without session_end that makes an hour "low"
END_MIN_SESSIONS = 3
QUARANTINE_PAD = timedelta(minutes=30)
DUP_RESOLVED_DAYS = 3
NEIGHBOR_DAYS = 7       # volume_gap expectation uses this many days either side
ROW_LOSS_MIN = 0.01     # a day losing at least this share of its rows is flagged
ROW_LOSS_MIN_ROWS = 20
STEP_MIN_N = 10         # sessions in a run of skipped steps
STEP_MIN_RATE = 0.5     # share of sessions in the run that skip the step
STEP_ONGOING = timedelta(hours=6)  # a run that ended this close to the end of the data counts as ongoing
STEP_BASE_P1 = 0.75     # assumed skip rate during a silent period (scan score only)
# Volume is only judged on screens where journeys start: downstream volume depends on the steps before it (an
# OTP that is not delivered starves the screens after it), and a silent downstream tracker is caught by step_skipped.
ENTRY_SCREENS = {path[0] for path in JOURNEYS.values()}
ID_RE = re.compile(r"^(.*?)(\d+)$")


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def hour_floor(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def poisson_cdf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0
    return min(1.0, sum(math.exp(-lam + i * math.log(lam) - math.lgamma(i + 1)) for i in range(k + 1)))


def fisher_greater(x1, n1, x0, n0) -> float:
    """One-sided Fisher exact p that rate 1 is higher than rate 0 (see watchdog.prop_p)."""
    total, big_n = x1 + x0, n1 + n0
    log_den = math.lgamma(big_n + 1) - math.lgamma(n1 + 1) - math.lgamma(big_n - n1 + 1)
    p = 0.0
    for k in range(x1, min(n1, total) + 1):
        if total - k > n0:
            continue
        p += math.exp(math.lgamma(total + 1) - math.lgamma(k + 1) - math.lgamma(total - k + 1)
                      + math.lgamma(big_n - total + 1) - math.lgamma(n1 - k + 1) - math.lgamma(n0 - (total - k) + 1) - log_den)
    return min(1.0, p)


def runs(flags: list[bool]):
    """Yield (start_idx, end_idx_exclusive) for consecutive True values."""
    i = 0
    while i < len(flags):
        if flags[i]:
            j = i
            while j < len(flags) and flags[j]:
                j += 1
            yield i, j
            i = j
        else:
            i += 1


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_quarantined(platform: str, ts: datetime, windows: list[dict], app_version=None, journey=None) -> bool:
    """For the Watchdog: should a session starting at ts be excluded?

    A window may be narrowed to one `app_version` and to some `journeys` (a silent tracker only damages the
    sessions that pass through the broken screen); without those keys it covers the whole platform.
    """
    for w in windows:
        if w["platform"] != platform:
            continue
        if w.get("app_version") and w["app_version"] != app_version:
            continue
        if w.get("journeys") and journey not in w["journeys"]:
            continue
        if parse_ts(w["start"]) <= ts < parse_ts(w["end"]) + QUARANTINE_PAD:
            return True
    return False


def load(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def step_pairs() -> list[tuple[tuple, str, tuple]]:
    """(screens that can come right before Y, Y, journeys containing Y) for every non-first screen. `otp` is
    shared, so either phone screen counts as its predecessor and both register and login are affected."""
    preds: dict = defaultdict(set)
    jour: dict = defaultdict(list)
    for j, path in JOURNEYS.items():
        for a, b in zip(path, path[1:]):
            preds[b].add(a)
            if j not in jour[b]:
                jour[b].append(j)
    return [(tuple(sorted(p)), y, tuple(jour[y])) for y, p in preds.items()]


def scan_skips(seq: list[tuple[datetime, bool]]):
    """Max-scoring run of skipped steps (Kadane on a log-likelihood score). Returns (i, j) or None."""
    total_miss = sum(m for _, m in seq)
    p0 = min(0.5, max(0.005, total_miss / len(seq)))     # capped so the score stays sane when most sessions skip
    up, down = math.log(STEP_BASE_P1 / p0), math.log((1 - STEP_BASE_P1) / (1 - p0))
    best, best_ij, cur, cur_i = 0.0, None, 0.0, 0
    for k, (_, miss) in enumerate(seq):
        if cur <= 0:
            cur, cur_i = 0.0, k
        cur += up if miss else down
        if cur > best:
            best, best_ij = cur, (cur_i, k + 1)
    return best_ij


def run_guardian(path: Path) -> dict:
    n = 0
    schema_problems: Counter = Counter()
    seen_ids: set = set()
    dup_count = 0
    dups: dict = {}                                   # (screen, os) -> {count, first, last, versions}
    unmapped: Counter = Counter()
    unmapped_span: dict = {}                          # key -> [first_ts, last_ts]
    views: dict = defaultdict(Counter)                # (platform, screen) -> hour -> count
    sessions: dict = {}                               # sid -> [first_ts, platform, has_end, app_version, screens]
    ids: list = []                                    # (number, ts) for the sequence check
    prefixes: Counter = Counter()
    t_min = t_max = None

    for e in load(path):
        n += 1
        for p in validate_event(e):
            schema_problems[p] += 1
        ts = parse_ts(e["ts"])
        eid = e.get("event_id")
        if eid is not None:      # a missing id is already a schema problem; do not also call it a duplicate
            if eid in seen_ids:
                dup_count += 1
                d = dups.setdefault((e.get("screen"), e.get("os")), {"count": 0, "first": ts, "last": ts, "versions": Counter()})
                d["count"] += 1
                d["first"], d["last"] = min(d["first"], ts), max(d["last"], ts)
                d["versions"][e.get("app_version")] += 1
            else:
                seen_ids.add(eid)
                m = ID_RE.match(eid)
                if m:
                    prefixes[m.group(1)] += 1
                    ids.append((int(m.group(2)), ts))
        for field in e.get("unmapped", []):
            # Canonical fields, or "prop:<raw path>" for a raw property the mapping does not list.
            key = f"{field} ({e.get('platform')})"
            unmapped[key] += 1
            sp = unmapped_span.setdefault(key, [ts, ts])
            sp[0], sp[1] = min(sp[0], ts), max(sp[1], ts)
        t_min = ts if t_min is None or ts < t_min else t_min
        t_max = ts if t_max is None or ts > t_max else t_max
        if e["event_type"] == "screen_view" and e.get("screen") in ENTRY_SCREENS:
            views[(e["platform"], e["screen"])][hour_floor(ts)] += 1
        s = sessions.setdefault(e["session_id"], [ts, e["platform"], False, e.get("app_version"), set()])
        if ts < s[0]:            # a session's platform and version are those of its earliest event, as in the Watchdog
            s[0], s[1], s[3] = ts, e["platform"], e.get("app_version")
        s[2] = s[2] or e["event_type"] == "session_end"
        if e.get("screen") and e["event_type"] == "screen_view":
            s[4].add(e["screen"])

    findings, checks = [], []
    hours = []
    h = hour_floor(t_min)
    while h <= hour_floor(t_max):
        hours.append(h)
        h += timedelta(hours=1)

    # ---- volume gaps
    p_threshold = FWER / max(1, len(views) * len(hours))
    for (platform, screen), counts in sorted(views.items()):
        series = []
        for i, h in enumerate(hours):
            # expectation: same hour of day on the NEIGHBOR_DAYS days either side (robust to a trend or a ramp)
            others = [counts.get(hours[k], 0) for k in range(i % 24, len(hours), 24) if k != i and abs(k - i) <= 24 * NEIGHBOR_DAYS]
            if len(others) < 4:
                others = [counts.get(hours[k], 0) for k in range(i % 24, len(hours), 24) if k != i]
            exp = median(others) if others else 0
            obs = counts.get(h, 0)
            series.append((h, obs, exp, exp >= MIN_EXPECTED and obs <= LOW_RATIO * exp))
        for a, b in runs([s[3] for s in series]):
            if b - a < MIN_RUN:
                continue
            obs = sum(s[1] for s in series[a:b])
            exp = sum(s[2] for s in series[a:b])
            p = poisson_cdf(obs, exp)
            if obs <= LOW_RATIO * exp and p < p_threshold:
                findings.append({
                    "kind": "volume_gap", "severity": "high", "platform": platform, "screen": screen,
                    "start": iso(series[a][0]), "end": iso(series[b - 1][0] + timedelta(hours=1)),
                    "hours": b - a, "observed": obs, "expected": round(exp, 1), "p_value": p,
                    "explanation": f"{platform}/{screen} logged {obs} screen_views over {b - a} hours where "
                                   f"{exp:.0f} are normal for those hours (p={p:.1e}). Likely a telemetry outage, "
                                   f"not user behavior.",
                })
    checks.append({"check": "volume_gap", "status": "fail" if any(f["kind"] == "volume_gap" for f in findings) else "pass",
                   "series_checked": len(views), "p_threshold": p_threshold})

    # ---- missing session_end
    by_hour: dict = defaultdict(lambda: defaultdict(lambda: [0, 0]))   # platform -> hour -> [sessions, missing]
    cutoff = t_max - timedelta(hours=1)
    for ts, platform, has_end, _, _ in sessions.values():
        if ts >= cutoff:
            continue
        cell = by_hour[platform][hour_floor(ts)]
        cell[0] += 1
        cell[1] += 0 if has_end else 1
    for platform, cells in sorted(by_hour.items()):
        flags = [cells[h][0] >= END_MIN_SESSIONS and cells[h][1] / cells[h][0] >= END_MISSING_RATE
                 if h in cells else False for h in hours]
        for a, b in runs(flags):
            if b - a < MIN_RUN:
                continue
            tot = sum(cells[h][0] for h in hours[a:b])
            miss = sum(cells[h][1] for h in hours[a:b])
            findings.append({
                "kind": "missing_session_end", "severity": "high", "platform": platform, "screen": None,
                "start": iso(hours[a]), "end": iso(hours[b - 1] + timedelta(hours=1)), "hours": b - a,
                "observed": tot - miss, "expected": tot,
                "explanation": f"{miss} of {tot} {platform} sessions starting in this {b - a}-hour span never "
                               f"logged a session_end. Sessions look cut off, not abandoned.",
            })
    checks.append({"check": "session_end", "status": "fail" if any(f["kind"] == "missing_session_end" for f in findings) else "pass"})

    # ---- step skipped (silent tracker)
    quarantine = []
    series_n = 0
    step_findings = []
    groups: dict = defaultdict(list)
    logged: dict = defaultdict(Counter)       # group -> which predecessor screens were logged
    for ts, platform, _, ver, screens in sessions.values():
        for x, y, j in step_pairs():
            if y in screens:
                groups[(x, y, j, platform, ver)].append((ts, not (set(x) & screens)))
                logged[(x, y, j, platform, ver)].update(set(x) & screens)
    n_tests = max(1, len(groups))
    for (x, y, j, platform, ver), seq in sorted(groups.items(), key=lambda kv: str(kv[0])):
        series_n += 1
        seq.sort(key=lambda t: t[0])
        ij = scan_skips(seq) if sum(m for _, m in seq) >= STEP_MIN_N else None
        if not ij:
            continue
        a, b = ij
        inside, outside = seq[a:b], seq[:a] + seq[b:]
        x1, n1 = sum(m for _, m in inside), len(inside)
        x0, n0 = sum(m for _, m in outside), len(outside)
        if n1 < STEP_MIN_N or x1 / n1 < STEP_MIN_RATE or (n0 and x0 / n0 > 0.2):
            continue
        p = fisher_greater(x1, n1, x0, n0) if n0 else 0.0
        if p >= FWER / n_tests:
            continue
        before_ok = 1 - (x0 / n0) if n0 else 1.0
        # still running if the run reaches the end of the data, allowing for the few sessions that still log the step
        ongoing = len(seq) - b <= 2 or t_max - inside[-1][0] <= STEP_ONGOING
        step_findings.append({
            "kind": "step_skipped", "severity": "high", "platform": platform, "app_version": ver, "screen": logged[(x, y, j, platform, ver)].most_common(1)[0][0] if logged[(x, y, j, platform, ver)] else x[0],
            "next_screen": y, "journey": j[0], "journeys": list(j), "start": iso(inside[0][0]),
            "end": iso(t_max if ongoing else inside[-1][0] + timedelta(seconds=1)),
            "ongoing": ongoing, "observed": n1 - x1, "expected": n1, "drop": round(x1 / n1, 4),
            "baseline_logged_rate": round(before_ok, 4), "p_value": p,
            "explanation": f"{x1} of {n1} {platform} sessions on app {ver} that reached {SCREEN_LABELS.get(y, y)} never logged "
                           f"{SCREEN_LABELS.get(x[0], x[0])} since {iso(inside[0][0])} (normally {before_ok:.0%} log it). "
                           f"The step happens but is not tracked, so this is a silent tracker, not user behavior."})
    findings += step_findings
    checks.append({"check": "step_skipped", "status": "fail" if step_findings else "pass", "series_checked": series_n})

    # ---- quarantine windows: platform-wide for gaps, narrow for a silent tracker
    spans: dict = defaultdict(list)
    for f in findings:
        if f["kind"] in ("volume_gap", "missing_session_end"):
            spans[f["platform"]].append([parse_ts(f["start"]), parse_ts(f["end"]), {f["screen"]} if f["screen"] else set()])
    for platform, items in spans.items():
        items.sort(key=lambda x: x[0])
        merged = [items[0]]
        for s, e, sc in items[1:]:
            if s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
                merged[-1][2] |= sc
            else:
                merged.append([s, e, set(sc)])
        for s, e, sc in merged:
            quarantine.append({"platform": platform, "start": iso(s), "end": iso(e),
                               "screens": sorted(sc), "reason": "telemetry_gap"})
    for f in step_findings:
        quarantine.append({"platform": f["platform"], "app_version": f["app_version"], "journeys": f["journeys"],
                           "start": f["start"], "end": f["end"], "screens": [f["screen"]], "reason": "tracker_silent"})

    # ---- duplicates
    dup_rows = []
    for (screen, os_), d in sorted(dups.items(), key=lambda kv: str(kv[0])):
        resolved = d["last"] < t_max - timedelta(days=DUP_RESOLVED_DAYS)
        later = Counter(s[3] for s in sessions.values() if s[0] > d["last"] and s[3])
        fixed = sorted(v for v in later if v not in d["versions"]) if resolved else []
        dup_rows.append({"screen": screen, "os": os_, "events": d["count"], "start": iso(d["first"]), "end": iso(d["last"]),
                         "app_versions": sorted(v for v in d["versions"] if v), "status": "resolved" if resolved else "active",
                         "no_longer_on_versions": fixed})
    for r in dup_rows:
        findings.append({"kind": "duplicate_events", "severity": "low" if r["status"] == "resolved" else "medium",
                         "platform": "app", "screen": r["screen"], "os": r["os"], "start": r["start"], "end": r["end"],
                         "observed": r["events"], "status": r["status"], "app_versions": r["app_versions"],
                         "explanation": f"{r['events']} {SCREEN_LABELS.get(r['screen'], r['screen'])} events on {r['os']} were logged twice "
                                        f"({r['start'][:10]} to {r['end'][:10]}); "
                                        + ("no duplicates since, so it looks fixed. Deduplicated before analysis." if r["status"] == "resolved"
                                           else "still happening. Deduplicated before analysis.")})
    checks.append({"check": "duplicates", "status": "warn" if any(r["status"] == "active" for r in dup_rows) else "pass",
                   "duplicate_event_ids": dup_count, "resolved": bool(dup_rows) and all(r["status"] == "resolved" for r in dup_rows),
                   "groups": dup_rows})

    # ---- row loss (gaps in the event id sequence)
    loss_days = []
    if ids and len(prefixes) == 1 and len(ids) >= 0.95 * len(seen_ids):
        ids.sort()
        present, missing = Counter(), Counter()
        for (a, _), (b, tb) in zip(ids, ids[1:]):
            present[tb.date()] += 1
            if b - a > 1:
                missing[tb.date()] += b - a - 1
        present[ids[0][1].date()] += 1
        for day in sorted(missing):
            tot = present[day] + missing[day]
            if missing[day] >= ROW_LOSS_MIN_ROWS and missing[day] / tot >= ROW_LOSS_MIN:
                loss_days.append({"day": day.isoformat(), "rows_lost": missing[day], "rows_logged": present[day],
                                  "loss_rate": round(missing[day] / tot, 4)})
        for r in loss_days:
            findings.append({"kind": "row_loss", "severity": "medium", "platform": None, "screen": None,
                             "start": r["day"] + "T00:00:00Z", "end": r["day"] + "T23:59:59Z", "observed": r["rows_logged"],
                             "expected": r["rows_logged"] + r["rows_lost"], "loss_rate": r["loss_rate"],
                             "explanation": f"{r['day']} is missing {r['rows_lost']} of {r['rows_logged'] + r['rows_lost']} rows "
                                            f"({r['loss_rate']:.1%}): the event id sequence has holes. Treat that day's counts as slightly low."})
        checks.append({"check": "row_loss", "status": "warn" if loss_days else "pass", "days_flagged": loss_days})
    else:
        checks.append({"check": "row_loss", "status": "skipped", "note": "event ids are not a single numeric sequence"})

    # ---- data-quality checks
    bad_schema = sum(schema_problems.values())
    checks.append({"check": "schema", "status": "fail" if bad_schema else "pass", "problems": dict(schema_problems)})
    if unmapped:
        spans_out = {}
        for k, c in unmapped.items():
            a, b = unmapped_span[k]
            hrs = max(1.0, (b - a).total_seconds() / 3600)
            spans_out[k] = {"events": c, "first": iso(a), "last": iso(b), "events_per_hour": round(c / hrs, 2)}
        findings.append({"kind": "unmapped_events", "severity": "medium", "platform": None, "screen": None,
                         "observed": sum(unmapped.values()), "values": dict(unmapped), "detail": spans_out,
                         "explanation": "Values or properties the mapping does not know, counted per field and platform. Kept and flagged for review, not ignored. The raw values are in normalize's .report.json (unmapped_values)."})
    checks.append({"check": "unmapped", "status": "warn" if unmapped else "pass",
                   "events": sum(unmapped.values()), "values": dict(unmapped)})

    active_fail = any(c["status"] == "fail" for c in checks)
    return {
        "events": n, "sessions": len(sessions),
        "range": [iso(t_min), iso(t_max)],
        "status": "fail" if active_fail else "pass",
        "checks": checks, "findings": findings, "quarantine_windows": quarantine,
        "faults": fault_list(findings, unmapped_span, unmapped, t_max),
    }


def fault_list(findings: list, spans: dict, unmapped: Counter, t_max: datetime) -> list[dict]:
    """The Guardian's findings as a short health list for the UI. Plain language, every number measured."""
    out = []
    for f in findings:
        if f["kind"] == "step_skipped":
            out.append({"id": f"fault:silent:{f['screen']}:{f['app_version']}", "kind": "tracker_silent", "status": "active" if f["ongoing"] else "resolved",
                        "severity": "high", "title": f"{SCREEN_LABELS.get(f['screen'], f['screen'])} tracking is silent on app {f['app_version']}",
                        "start": f["start"], "end": f["end"], "screen": f["screen"], "app_version": f["app_version"],
                        "detail": f"{f['drop']:.0%} of {f['platform']} sessions on {f['app_version']} that got past it logged no "
                                  f"{SCREEN_LABELS.get(f['screen'], f['screen'])} events since {f['start'][:16].replace('T', ' ')} UTC.",
                        "metric": {"label": "events missing", "value": f["drop"]}, "effect": "Those sessions are excluded from the analysis; the screen looks quieter than it is."})
        elif f["kind"] == "row_loss":
            out.append({"id": f"fault:rowloss:{f['start'][:10]}", "kind": "row_loss", "status": "active", "severity": "medium",
                        "title": f"{f['start'][:10]} is missing {f['loss_rate']:.1%} of its rows", "start": f["start"], "end": f["end"],
                        "screen": None, "app_version": None,
                        "detail": f"{f['expected'] - f['observed']} of {f['expected']} event ids are absent from the sequence that day (not backfilled).",
                        "metric": {"label": "rows missing", "value": f["loss_rate"]}, "effect": "Counts for that day are slightly low. No behavior finding is based on it alone."})
        elif f["kind"] == "duplicate_events":
            out.append({"id": f"fault:dup:{f['screen']}:{f['os']}", "kind": "duplicate_events", "status": f["status"], "severity": f["severity"],
                        "title": f"{SCREEN_LABELS.get(f['screen'], f['screen'])} events double-fired on {f['os']}",
                        "start": f["start"], "end": f["end"], "screen": f["screen"], "app_version": None,
                        "detail": f"{f['observed']} duplicate events, {f['start'][:10]} to {f['end'][:10]}, on app " + ", ".join(f["app_versions"]) +
                                  (". No duplicates since." if f["status"] == "resolved" else ". Still happening."),
                        "metric": {"label": "duplicate events", "value": f["observed"]}, "effect": "Removed before analysis (same event id)."})
        elif f["kind"] == "unmapped_events":
            for key, d in f["detail"].items():
                out.append({"id": f"fault:unmapped:{key}", "kind": "unmapped", "status": "active", "severity": "medium",
                            "title": f"Unmapped property {key.split(':', 1)[-1].split(' ')[0].split('.')[-1]}" if key.startswith("prop:") else f"Unmapped values in {key}",
                            "start": d["first"], "end": d["last"], "screen": None, "app_version": None,
                            "detail": f"{d['events']} events carry it, about {d['events_per_hour']} per hour, since {d['first'][:10]}. The mapping does not list it, so it is kept but not analysed.",
                            "metric": {"label": "events per hour", "value": d["events_per_hour"]}, "effect": "Nothing is lost; add it to the mapping to use it."})
        elif f["kind"] in ("volume_gap", "missing_session_end"):
            out.append({"id": f"fault:gap:{f['platform']}:{f.get('screen')}:{f['start']}", "kind": f["kind"],
                        "status": "active" if parse_ts(f["end"]) >= t_max - timedelta(hours=1) else "resolved", "severity": "high",
                        "title": f"{f['platform']} events dropped {f['start'][:10]}", "start": f["start"], "end": f["end"],
                        "screen": f.get("screen"), "app_version": None, "detail": f["explanation"],
                        "metric": {"label": "observed vs expected", "value": f.get("observed")}, "effect": "Window excluded from analysis."})
    return out


def verify(report: dict, gt: dict) -> list[tuple[bool, str]]:
    res = []
    f = {g["id"].split("_")[0]: g for g in gt["guardian_must_catch"]}
    kinds = Counter(x["kind"] for x in report["findings"])
    wins = report["quarantine_windows"]
    # G1
    g1 = f["G1"]
    sk = [x for x in report["findings"] if x["kind"] == "step_skipped"]
    hit = [x for x in sk if x["screen"] == g1["screen"] and x["app_version"] == g1["app_version"]]
    res.append((len(sk) == 1 and len(hit) == 1, f"G1: exactly one silent-step finding, on {g1['screen']} app {g1['app_version']} (found {[(x['screen'], x['app_version']) for x in sk]})"))
    if hit:
        x = hit[0]
        first = parse_ts(g1["first_silent_session_utc"])
        off = abs((parse_ts(x["start"]) - first).total_seconds()) / 60
        res.append((parse_ts(x["start"]) >= parse_ts(g1["silent_from_utc"]) and off <= 1,
                    f"G1: start = first silent session {g1['first_silent_session_utc']} (found {x['start']}); the true fault start {g1['silent_from_utc']} had no traffic before it"))
        res.append((abs(x["drop"] - g1["measured_drop"]) <= 0.05 and x["drop"] >= 0.75, f"G1: measured drop {x['drop']:.1%} vs planted {g1['planted_drop']:.0%} (true sample {g1['measured_drop']:.1%})"))
        res.append((x["ongoing"] and any(w.get("reason") == "tracker_silent" and w.get("app_version") == g1["app_version"] for w in wins),
                    "G1: quarantine window narrowed to that app version, still active"))
    res.append((len(wins) == 1, f"exactly one quarantine window (found {len(wins)}): no false alarms"))
    res.append((kinds["volume_gap"] == 0 and kinds["missing_session_end"] == 0, "no volume-gap or missing-session_end alarms"))
    # G2
    g2 = f["G2"]
    rl = [x for x in report["findings"] if x["kind"] == "row_loss"]
    res.append((len(rl) == 1 and rl[0]["start"][:10] == g2["day_utc"], f"G2: exactly one row-loss day, {g2['day_utc']} (found {[x['start'][:10] for x in rl]})"))
    if rl:
        res.append((abs(rl[0]["loss_rate"] - g2["measured_loss"]) <= 0.005, f"G2: loss {rl[0]['loss_rate']:.2%} vs true {g2['measured_loss']:.2%}"))
    # G3
    g3 = f["G3"]
    unm = next((x for x in report["findings"] if x["kind"] == "unmapped_events"), None)
    key = next((k for k in (unm or {}).get("detail", {}) if g3["property"] in k), None)
    res.append((key is not None and unm["detail"][key]["events"] == g3["events"] and len(unm["detail"]) == 1,
                f"G3: only unmapped item is {g3['property']} with {g3['events']} events (found {None if not unm else {k: v['events'] for k, v in unm['detail'].items()}})"))
    # G4
    g4 = f["G4"]
    dp = [x for x in report["findings"] if x["kind"] == "duplicate_events"]
    res.append((len(dp) == 1 and dp[0]["screen"] == g4["screen"] and dp[0]["os"] == g4["os"] and dp[0]["status"] == "resolved"
                and dp[0]["observed"] == g4["duplicated_events"],
                f"G4: one resolved duplicate group on {g4['screen']}/{g4['os']} with {g4['duplicated_events']} events (found {[(x['screen'], x['os'], x['status'], x['observed']) for x in dp]})"))
    if dp:
        res.append((dp[0]["start"][:10] >= g4["from_utc"][:10] and dp[0]["end"][:10] <= g4["to_utc"][:10], f"G4: dates {dp[0]['start'][:10]}..{dp[0]['end'][:10]} inside {g4['from_utc'][:10]}..{g4['to_utc'][:10]}"))
    res.append((not any(c["status"] == "fail" for c in report["checks"] if c["check"] in ("schema",)), "schema check passes"))
    res.append((report["status"] == "fail", "overall status is fail while a tracker is silent"))
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ground-truth")
    args = ap.parse_args()

    report = run_guardian(Path(args.input))
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{report['events']} events, {report['sessions']} sessions, status={report['status']}")
    for c in report["checks"]:
        print(f"  {c['check']:12} {c['status']}")
    for w in report["quarantine_windows"]:
        print(f"  quarantine: {w['platform']} {w.get('app_version', '')} {w['start']} -> {w['end']} screens={w['screens']}")
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
