#!/usr/bin/env python3
"""Tier 0: Telemetry Guardian. Deterministic pre-flight checks, no AI.

Runs on canonical events before any analysis. Its job is to separate genuine behavioral shifts
from broken telemetry, so the Watchdog and the Diagnostic Agent never report an outage as user
behavior. It produces:

  findings            what looks wrong with the data and why
  quarantine_windows  (platform, start, end) spans the Watchdog must exclude
  checks              pass/warn/fail per check, for the UI and the deck

Checks:
  schema       every event validates against schema.py
  duplicates   event_id is unique
  unmapped     events whose raw name had no mapping (flagged for review, never ignored)
  volume_gap   hourly screen_view count per (platform, screen) vs the same hour-of-day on other
               days; a run of >= MIN_RUN low hours is flagged when it is also statistically
               implausible (Poisson tail)
  session_end  runs of hours where most sessions never log a session_end

Usage:
  python pipeline/guardian.py --input data/synthetic/canonical_events.jsonl \
      --out data/synthetic/guardian_report.json [--ground-truth data/synthetic/ground_truth.json]
Exit code is 1 if --ground-truth is given and any expectation fails.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from schema import validate_event

UTC = timezone.utc
MIN_EXPECTED = 1.5      # ignore series too sparse to judge an hour
LOW_RATIO = 0.25        # an hour is "low" if observed <= this share of expected
MIN_RUN = 3             # consecutive low hours before flagging
FWER = 1e-3             # family-wise false-alarm rate; per-test threshold = FWER / (series x hours)
END_MISSING_RATE = 0.5  # share of sessions without session_end that makes an hour "low"
END_MIN_SESSIONS = 3
QUARANTINE_PAD = timedelta(minutes=30)


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def hour_floor(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def poisson_cdf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0
    return min(1.0, sum(math.exp(-lam + i * math.log(lam) - math.lgamma(i + 1)) for i in range(k + 1)))


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


def is_quarantined(platform: str, ts: datetime, windows: list[dict]) -> bool:
    """For the Watchdog: should a session starting at ts on this platform be excluded?"""
    for w in windows:
        if w["platform"] == platform and parse_ts(w["start"]) <= ts < parse_ts(w["end"]) + QUARANTINE_PAD:
            return True
    return False


def load(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def run_guardian(path: Path) -> dict:
    n = 0
    schema_problems: Counter = Counter()
    seen_ids: set = set()
    dup_count = 0
    unmapped: Counter = Counter()
    views: dict = defaultdict(Counter)           # (platform, screen) -> hour -> count
    sessions: dict = {}                          # sid -> [first_ts, platform, has_end]
    t_min = t_max = None

    for e in load(path):
        n += 1
        for p in validate_event(e):
            schema_problems[p] += 1
        eid = e.get("event_id")
        if eid is not None:      # a missing id is already a schema problem; do not also call it a duplicate
            if eid in seen_ids:
                dup_count += 1
            seen_ids.add(eid)
        for field in e.get("unmapped", []):
            # Only canonical fields here (the raw names live in normalize's .report.json), so this
            # works with any mapping.
            unmapped[f"{field} ({e.get('platform')})"] += 1
        ts = parse_ts(e["ts"])
        t_min = ts if t_min is None or ts < t_min else t_min
        t_max = ts if t_max is None or ts > t_max else t_max
        if e["event_type"] == "screen_view" and e.get("screen"):
            views[(e["platform"], e["screen"])][hour_floor(ts)] += 1
        s = sessions.setdefault(e["session_id"], [ts, e["platform"], False])
        if ts < s[0]:            # a session's platform is that of its earliest event, as in the Watchdog
            s[0], s[1] = ts, e["platform"]
        s[2] = s[2] or e["event_type"] == "session_end"

    findings, checks = [], []
    hours = []
    h = hour_floor(t_min)
    while h <= hour_floor(t_max):
        hours.append(h)
        h += timedelta(hours=1)

    # volume gaps
    p_threshold = FWER / max(1, len(views) * len(hours))
    for (platform, screen), counts in sorted(views.items()):
        by_hod: dict = defaultdict(list)
        for h in hours:
            by_hod[h.hour].append(counts.get(h, 0))
        series = []
        for h in hours:
            others = list(by_hod[h.hour])
            others.remove(counts.get(h, 0))
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

    # missing session_end
    by_hour: dict = defaultdict(lambda: defaultdict(lambda: [0, 0]))   # platform -> hour -> [sessions, missing]
    cutoff = t_max - timedelta(hours=1)
    for ts, platform, has_end in sessions.values():
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

    # quarantine windows: union of gap findings per platform
    spans: dict = defaultdict(list)
    for f in findings:
        spans[f["platform"]].append([parse_ts(f["start"]), parse_ts(f["end"]), {f["screen"]} if f["screen"] else set()])
    quarantine = []
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

    # data-quality checks
    bad_schema = sum(schema_problems.values())
    checks.append({"check": "schema", "status": "fail" if bad_schema else "pass", "problems": dict(schema_problems)})
    checks.append({"check": "duplicates", "status": "fail" if dup_count else "pass", "duplicate_event_ids": dup_count})
    if unmapped:
        findings.append({"kind": "unmapped_events", "severity": "medium", "platform": None, "screen": None,
                         "observed": sum(unmapped.values()), "values": dict(unmapped),
                         "explanation": "Values the mapping does not know, counted per field and platform. Kept and flagged for review, not ignored. The raw values are in normalize's .report.json (unmapped_values)."})
    checks.append({"check": "unmapped", "status": "warn" if unmapped else "pass",
                   "events": sum(unmapped.values()), "values": dict(unmapped)})

    return {
        "events": n, "sessions": len(sessions),
        "range": [iso(t_min), iso(t_max)],
        "status": "fail" if any(c["status"] == "fail" for c in checks) else "pass",
        "checks": checks, "findings": findings, "quarantine_windows": quarantine,
    }


def verify(report: dict, gt: dict) -> list[tuple[bool, str]]:
    results = []
    g1 = next(g for g in gt["guardian_must_catch"] if g["id"] == "G1_app_telemetry_outage")
    ts, te = (parse_ts(x) for x in g1["window_utc"])
    wins = report["quarantine_windows"]
    results.append((len(wins) == 1, f"exactly one quarantine window (found {len(wins)}): no false alarms"))
    hit = [w for w in wins if parse_ts(w["start"]) < te and parse_ts(w["end"]) > ts]
    results.append((bool(hit), "a quarantine window overlaps the true outage"))
    if hit:
        w = hit[0]
        ws, we = parse_ts(w["start"]), parse_ts(w["end"])
        overlap = max(timedelta(0), min(te, we) - max(ts, ws)) / (te - ts)
        results.append((w["platform"] == g1["platform"], f"window is on platform {g1['platform']} (found {w['platform']})"))
        results.append((overlap >= 0.9, f"window covers {overlap:.0%} of the true outage (need >= 90%)"))
        results.append(((we - ws) <= (te - ts) + timedelta(hours=3), f"window is {(we - ws)} long vs true {te - ts}"))
    unm = next((c for c in report["checks"] if c["check"] == "unmapped"), {})
    seen = " ".join(unm.get("values", {}))
    results.append(("(web)" in seen and "(app)" in seen, "unmapped events flagged on both platforms"))
    results.append((report["checks"][0]["status"] == "fail" and report["status"] == "fail", "overall status is fail while an outage exists"))
    return results


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
        print(f"  quarantine: {w['platform']} {w['start']} -> {w['end']} screens={w['screens']}")
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
