#!/usr/bin/env python3
"""Build results.json for the app from canonical events, the Guardian report and the Watchdog output.

This is the pre-AI version: every number is measured, every sentence is generated from those
numbers by fixed templates, and the fields that belong to the Diagnostic Agent are left empty with
`diagnosis_status: "pending"`. The UI shows that honestly. When the Diagnostic Agent exists it
fills class, hypothesis, confidence and recommendation, and sets the status to "done".

Shape: see pipeline/results_contract.md.

Usage:
  python pipeline/build_results.py --events data/synthetic/canonical_events.jsonl \
      --guardian data/synthetic/guardian_report.json --watchdog data/synthetic/watchdog_candidates.json \
      --out app/static/results.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from guardian import is_quarantined, parse_ts
from watchdog import device_class, matches

# ASSUMPTION, not data: what one completed signup is worth. The UI shows this next to every dollar figure.
VALUE_PER_SESSION = 20.0
VALUE_ASSUMPTION = (f"Placeholder of ${VALUE_PER_SESSION:.0f} per completed signup. "
                    "Not measured; replace with the real value before quoting dollar figures.")
SEVERITY_ORDER = {"critical": 0, "warning": 1, "healthy": 2}
ACRONYMS = {"kyc": "KYC", "smb": "SMB", "api": "API", "ios": "iOS"}
PERSONA_TEXT = {"smb": "SMB users", "enterprise": "Enterprise users", "retail": "Retail users"}
DEVICE_TEXT = {"android_small": "on small-screen Android", "android": "on Android", "ios": "on iOS",
               "windows": "on Windows", "macos": "on macOS"}
PLATFORM_TEXT = {"web": "on web", "app": "in the app"}
DIM_LABELS = {
    "platform": {"web": "Web", "app": "App"},
    "persona": {"smb": "SMB", "enterprise": "Enterprise", "retail": "Retail"},
    "device_class": {"android_small": "Small-screen Android", "android": "Android", "ios": "iOS",
                     "windows": "Windows", "macos": "macOS"},
}
DIM_NAMES = {"platform": "Platform", "persona": "Persona", "device_class": "Device"}
MIN_DAY_N = 5          # a day with fewer sessions is left off the chart, not plotted as noise
MIN_ROW_N = 20         # breakdown rows need this many sessions
ONSET_MIN_DIFF = 0.10  # a start date is only suggested when the rate really stepped up
ONSET_MIN_FIT = 0.6    # ...and a single step explains at least this share of the daily variation
REPEAT_FOCUS = 3


def pending_diagnosis() -> dict:
    """Empty `diagnosis` object (contract v0.4). The Diagnostic Agent replaces it; until then the UI says "Not diagnosed yet"."""
    return {"status": "pending", "model": None, "generated_at": None, "class": None, "confidence": None,
            "summary": None, "claims": [], "next_steps": [], "guardrail_flags": [], "caveats": []}


def humanize(screen: str) -> str:
    return " ".join(ACRONYMS.get(w, w.capitalize()) for w in screen.split("_"))


def segment_text(seg: dict) -> str:
    if not seg:
        return "All users"
    parts = [PERSONA_TEXT.get(seg["persona"], f"{seg['persona']} users")] if "persona" in seg else ["Users"]
    if "device_class" in seg:
        parts.append(DEVICE_TEXT.get(seg["device_class"], f"on {seg['device_class']}"))
    if "platform" in seg:
        parts.append(PLATFORM_TEXT.get(seg["platform"], seg["platform"]))
    return " ".join(parts)


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def secs(ms: float) -> str:
    return f"{ms / 1000:.0f}s"


def fact(sig: dict, scope: str) -> str:
    v, r = sig["value"], sig["reference"]
    ref = "before" if scope == "temporal" else "for everyone else"
    m = sig["metric"]
    if m == "drop_off":
        return ((f"{pct(v)} of sessions end on this screen, up from {pct(r)} before." if scope == "temporal"
                 else f"{pct(v)} of this group's sessions end on this screen, versus {pct(r)} for everyone else."))
    if m == "dwell":
        return f"Median time on the screen is {secs(v)}, versus {secs(r)} {ref}."
    if m == "repeat_focus":
        return f"{pct(v)} of sessions click into the same field 3 or more times (versus {pct(r)} {ref})."
    if m == "rage":
        who = "sessions" if scope == "temporal" else "of this group's sessions"
        return (f"{pct(v)} of sessions include rage clicks, meaning rapid repeated clicks (versus {pct(r)} {ref})."
                if scope == "temporal" else
                f"{pct(v)} {who} include rage clicks, meaning rapid repeated clicks (versus {pct(r)} for everyone else).")
    return f"{m}: {v} versus {r}."


def applies(seg: dict, platform: str, persona: str) -> bool:
    return ((platform == "all" or seg.get("platform", platform) == platform)
            and (persona == "all" or seg.get("persona", persona) == persona))


def load_sessions(path: Path, need: set, windows: list[dict], now_start, now_end):
    sessions: dict = {}
    evidence: dict = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            e = json.loads(line)
            sid = e["session_id"]
            if sid in need and len(evidence[sid]) < 40:
                evidence[sid].append(e)
            s = sessions.setdefault(sid, {"platform": e["platform"], "persona": None, "device_class": None,
                                          "start": e["ts"], "views": [], "dwell": Counter(), "last_ts": "",
                                          "last": None})
            s["start"] = min(s["start"], e["ts"])
            if e.get("persona") and not s["persona"]:
                s["persona"] = e["persona"]
            if s["device_class"] is None and e.get("os"):
                s["device_class"] = device_class(e)
            screen = e.get("screen")
            if screen and e["ts"] >= s["last_ts"]:
                s["last_ts"], s["last"] = e["ts"], screen
            if e["event_type"] == "screen_view" and screen:
                s["views"].append(screen)
            elif e["event_type"] == "screen_leave" and screen and e.get("dwell_ms") is not None:
                s["dwell"][screen] += e["dwell_ms"]
    out = []
    for sid, s in sessions.items():
        s["dt"] = parse_ts(s["start"])
        s["persona"] = s["persona"] or "unknown"
        s["device_class"] = s["device_class"] or "unknown"
        s["seen"] = set(s["views"])
        s["quarantined"] = is_quarantined(s["platform"], s["dt"], windows)
        s["in_now"] = now_start <= s["dt"] < now_end
        out.append(s)
    return out, evidence


def ended_rate(group: list[dict], screen: str):
    viewed = [s for s in group if screen in s["seen"]]
    return (len(viewed), sum(s["last"] == screen for s in viewed) / len(viewed)) if viewed else (0, None)


def day_series(clean: list[dict], screen: str, seg: dict, with_reference: bool) -> list[dict]:
    """Daily share of sessions that end on this screen, for the group (and everyone else, if asked)."""
    out = []
    for d in sorted({s["dt"].date() for s in clean}):
        day = [s for s in clean if s["dt"].date() == d]
        n, r = ended_rate([s for s in day if matches(s, seg)], screen)
        row = {"d": d.isoformat(), "n": n, "rate": round(r, 4) if r is not None and n >= MIN_DAY_N else None}
        if with_reference:
            rn, rr = ended_rate([s for s in day if not matches(s, seg)], screen)
            row.update(ref_n=rn, ref_rate=round(rr, 4) if rr is not None and rn >= MIN_DAY_N else None)
        out.append(row)
    return out


def estimate_onset(series: list[dict]):
    """Best single step in the daily rate. Returns a date only when a step clearly explains the series."""
    pts = [(p["d"], p["rate"]) for p in series if p["rate"] is not None]
    if len(pts) < 10:
        return None
    ys = [r for _, r in pts]
    mean = lambda a: sum(a) / len(a)
    sse = lambda a: sum((x - mean(a)) ** 2 for x in a)
    total = sse(ys)
    cost, k = min((sse(ys[:k]) + sse(ys[k:]), k) for k in range(3, len(ys) - 2))
    if total > 0 and 1 - cost / total >= ONSET_MIN_FIT and mean(ys[k:]) - mean(ys[:k]) >= ONSET_MIN_DIFF:
        return pts[k][0]
    return None


def breakdown(now_at: list[dict], before_at: list[dict], screen: str, seg: dict, temporal: bool) -> list[dict]:
    rows = []
    for dim in ("platform", "persona", "device_class"):
        for v in sorted({s[dim] for s in now_at}):
            g = [s for s in now_at if s[dim] == v]
            if len(g) < MIN_ROW_N:
                continue
            _, r = ended_rate(g, screen)
            row = {"dim": dim, "dim_label": DIM_NAMES[dim], "value": v,
                   "label": DIM_LABELS[dim].get(v, v), "n": len(g), "rate": round(r, 4),
                   "in_segment": seg.get(dim) == v}
            if temporal:
                gb = [s for s in before_at if s[dim] == v]
                bn, br = ended_rate(gb, screen)
                row["rate_before"] = round(br, 4) if br is not None and bn >= MIN_ROW_N else None
            rows.append(row)
    return rows


def concentration(rows: list[dict], temporal: bool, who: str, drop_signal):
    if temporal:
        usable = [r for r in rows if r.get("rate_before") is not None]
        if len(usable) >= 3 and drop_signal:
            overall = drop_signal["diff"]
            if all(r["rate"] - r["rate_before"] >= 0.5 * overall for r in usable):
                return ("The increase shows up in every platform, persona and device group, "
                        "so it is not tied to one kind of user.")
            worst = max(usable, key=lambda r: r["rate"] - r["rate_before"])
            return f"The increase is largest for {worst['label']} ({worst['dim_label'].lower()})."
        return None
    if drop_signal:
        return (f"Concentrated in {who}: {pct(drop_signal['value'])} end here, "
                f"compared with {pct(drop_signal['reference'])} for everyone else.")
    return None


def evidence_session(sid: str, role: str, events: list[dict]) -> dict:
    evs = sorted(events, key=lambda e: e["ts"])
    t0 = parse_ts(evs[0]["ts"])
    focus = Counter((e.get("screen"), e.get("element")) for e in evs
                    if e["event_type"] == "form_focus" and e.get("element"))
    rows, path = [], []
    for e in evs:
        flag = None
        if e["event_type"] == "rage_click":
            flag = "Rage click"
        elif e["event_type"] == "error":
            flag = "Error"
        elif e["event_type"] == "form_focus" and focus[(e.get("screen"), e.get("element"))] >= REPEAT_FOCUS:
            flag = "Repeated focus"
        elif e["event_type"] == "unknown":
            flag = "Unrecognized event"
        if e["event_type"] == "screen_view" and e.get("screen") and (not path or path[-1] != e["screen"]):
            path.append(e["screen"])
        rows.append({"t": int((parse_ts(e["ts"]) - t0).total_seconds() * 1000), "type": e["event_type"],
                     "screen": e.get("screen"), "element": e.get("element"), "dwell_ms": e.get("dwell_ms"),
                     "error_code": e.get("error_code"), "flag": flag})
    return {"session_id": sid, "role": role, "platform": evs[0]["platform"], "persona": evs[0].get("persona"),
            "path": path, "rows": rows, "events": [e["raw"] for e in evs]}


def layout(sessions: list[dict]) -> dict:
    """Column = typical step number; lane = which entry screen most of its sessions came through."""
    steps, entries = defaultdict(list), Counter()
    reach = defaultdict(Counter)
    for s in sessions:
        v = [x for i, x in enumerate(s["views"]) if i == 0 or x != s["views"][i - 1]]
        if not v:
            continue
        entries[v[0]] += 1
        for i, scr in enumerate(v):
            steps[scr].append(i)
            reach[scr][v[0]] += 1
    lane_of = {e: i for i, (e, _) in enumerate(entries.most_common())}
    return {scr: {"col": int(round(median(ix))), "lane": lane_of[reach[scr].most_common(1)[0][0]]}
            for scr, ix in steps.items()}


def journey(sessions: list[dict], pos: dict) -> dict:
    views, exits, dwell, edges = Counter(), Counter(), defaultdict(list), Counter()
    for s in sessions:
        seen = set()
        for i, scr in enumerate(s["views"]):
            if scr not in seen:
                views[scr] += 1
                seen.add(scr)
                if scr in s["dwell"]:
                    dwell[scr].append(s["dwell"][scr])
            if i and s["views"][i - 1] != scr:
                edges[(s["views"][i - 1], scr)] += 1
        if s["last"]:
            exits[s["last"]] += 1
    nodes = [{"id": scr, "label": humanize(scr), "sessions": views[scr], "exits": exits[scr],
              "exit_rate": round(exits[scr] / views[scr], 4) if views[scr] else 0,
              "median_dwell_ms": int(median(dwell[scr])) if dwell[scr] else None, **pos[scr]}
             for scr in sorted(views, key=lambda x: (pos[x]["lane"], pos[x]["col"]))]
    return {"nodes": nodes, "edges": [{"from": a, "to": b, "sessions": n} for (a, b), n in sorted(edges.items())]}


def funnel_ends(pos: dict):
    """First and last screen of the main path: the entry lane's earliest and latest column."""
    lane0 = sorted((v["col"], scr) for scr, v in pos.items() if v["lane"] == 0)
    return lane0[0][1], lane0[-1][1]


def overview_view(sub: list[dict], days: list, now_start, now_days: int, start: str, end: str) -> dict:
    """Numbers for the Overview tab for one platform/persona view."""
    now = [x for x in sub if x["in_now"]]
    before = [x for x in sub if x["dt"] < now_start]

    def conv(group):
        started = [x for x in group if start in x["seen"]]
        return len(started), sum(end in x["seen"] for x in started)

    n_now, d_now = conv(now)
    n_bef, d_bef = conv(before)
    rate_now = d_now / n_now if n_now else None
    rate_bef = d_bef / n_bef if n_bef else None
    before_days = max(1, (now_start.date() - days[0]).days)
    per_day_now, per_day_bef = len(now) / now_days, len(before) / before_days

    sessions_series, conv_series = [], []
    for d in days:
        day = [x for x in sub if x["dt"].date() == d]
        started, done = conv(day)
        sessions_series.append({"d": d.isoformat(), "n": len(day)})
        conv_series.append({"d": d.isoformat(), "n": started,
                            "rate": round(done / started, 4) if started >= MIN_DAY_N else None})

    rows = []
    for persona in sorted({x["persona"] for x in now if x["persona"] != "unknown"}):
        for dc in sorted({x["device_class"] for x in now}):
            g = [x for x in now if x["persona"] == persona and x["device_class"] == dc]
            started, done = conv(g)
            if started < MIN_ROW_N:
                continue
            rows.append({"persona": persona, "device_class": dc,
                         "label": f"{DIM_LABELS['persona'].get(persona, persona)} · {DIM_LABELS['device_class'].get(dc, dc)}",
                         "started": started, "rate": round(done / started, 4),
                         "vs_overall": round(done / started - rate_now, 4) if rate_now is not None else None})
    rows.sort(key=lambda r: (r["vs_overall"] if r["vs_overall"] is not None else 0))
    return {
        "sessions": {"now": len(now), "per_day_now": round(per_day_now, 1), "per_day_before": round(per_day_bef, 1),
                     "change": round(per_day_now / per_day_bef - 1, 4) if per_day_bef else None,
                     "series": sessions_series},
        "conversion": {"now": round(rate_now, 4) if rate_now is not None else None,
                       "before": round(rate_bef, 4) if rate_bef is not None else None,
                       "n_now": n_now, "n_before": n_bef, "series": conv_series},
        "table": rows,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--events", required=True)
    ap.add_argument("--guardian", required=True)
    ap.add_argument("--watchdog", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    guardian = json.loads(Path(args.guardian).read_text(encoding="utf-8"))
    wd = json.loads(Path(args.watchdog).read_text(encoding="utf-8"))
    now_start, now_end = parse_ts(wd["window"]["now_start"]), parse_ts(wd["window"]["now_end"])
    now_days = wd["params"]["now_days"]

    need = set()
    for c in wd["candidates"]:
        need |= set(c["sample_sessions"]["affected"][:3]) | set(c["sample_sessions"]["comparison"][:1])
    for h in wd["high_exit_screens"]:
        need |= set(h["sample_sessions"]["affected"][:2])
    all_sessions, evidence = load_sessions(Path(args.events), need, guardian["quarantine_windows"], now_start, now_end)
    clean = [s for s in all_sessions if not s["quarantined"]]
    sessions = [s for s in clean if s["in_now"]]
    before = [s for s in clean if s["dt"] < now_start]

    pos = layout(sessions)
    personas = sorted({s["persona"] for s in sessions if s["persona"] != "unknown"})
    platforms = sorted({s["platform"] for s in sessions})
    journeys = {}
    for pf in ["all"] + platforms:
        for pe in ["all"] + personas:
            sub = [s for s in sessions if (pf == "all" or s["platform"] == pf) and (pe == "all" or s["persona"] == pe)]
            journeys[f"{pf}|{pe}"] = {"sessions": len(sub), **journey(sub, pos)}

    def evid(ids_affected, ids_comparison):
        out = [evidence_session(sid, "affected", evidence[sid]) for sid in ids_affected if sid in evidence]
        out += [evidence_session(sid, "comparison", evidence[sid]) for sid in ids_comparison if sid in evidence]
        return out

    insights = []
    for c in wd["candidates"]:
        drop = next((s for s in c["signals"] if s["metric"] == "drop_off"), None)
        sev_effect = drop["diff"] if drop else 0.0
        weekly_sessions = c["n_sessions"] / (now_days / 7)
        weekly_lost = c["excess_sessions"] / (now_days / 7)
        severity = "critical" if (sev_effect >= 0.10 and c["excess_sessions"] >= 50) else "warning"
        label = humanize(c["screen"])
        who = segment_text(c["segment"])
        title = (f"{label}: more people leave here than before" if c["scope"] == "temporal"
                 else f"{label}: {who} fail far more often than everyone else")
        temporal = c["scope"] == "temporal"
        series = day_series(clean, c["screen"], c["segment"], with_reference=not temporal)
        onset = estimate_onset(series) if temporal else None
        rows = breakdown([x for x in sessions if c["screen"] in x["seen"]],
                         [x for x in before if c["screen"] in x["seen"]], c["screen"], c["segment"], temporal)
        gaps = [{"start": w["start"], "end": w["end"], "platform": w["platform"]}
                for w in guardian["quarantine_windows"]
                if c["segment"].get("platform", w["platform"]) == w["platform"]]
        insights.append({
            "id": c["id"], "severity": severity, "severity_source": "watchdog rule (provisional)",
            "class": None, "diagnosis_status": "pending",
            "title": title, "title_source": "template",
            "summary": None, "hypothesis": None, "confidence": None, "recommendation": None, "guardrail_flags": [],
            "diagnosis": pending_diagnosis(),
            "screen": c["screen"], "screen_label": label, "scope": c["scope"], "segment": c["segment"],
            "segment_text": who, "compared_with": c["reference"],
            "signals": c["signals"], "facts": [fact(s, c["scope"]) for s in c["signals"]],
            "n_sessions": c["n_sessions"],
            "impact": {"severity": round(sev_effect, 4), "volume_per_week": round(weekly_sessions),
                       "lost_sessions_per_week": round(weekly_lost),
                       "value_per_session": VALUE_PER_SESSION,
                       "score": round(sev_effect * weekly_sessions * VALUE_PER_SESSION),
                       "per_week_dollars": round(weekly_lost * VALUE_PER_SESSION),
                       "assumption": VALUE_ASSUMPTION},
            "evidence": {"affected_session_ids": c["sample_sessions"]["affected"][:3],
                         "comparison_session_ids": c["sample_sessions"]["comparison"][:1],
                         "sessions": evid(c["sample_sessions"]["affected"][:3], c["sample_sessions"]["comparison"][:1])},
            "timeline": {"metric": "drop_off", "metric_label": "Share of sessions that end on this screen",
                         "series": series, "gaps": gaps, "now_start": wd["window"]["now_start"],
                         "has_reference": not temporal, "onset": onset},
            "breakdown": rows,
            "concentration": concentration(rows, temporal, who, drop),
            "ticket_draft": None,
        })
    for h in wd["high_exit_screens"]:
        label = humanize(h["screen"])
        insights.append({
            "id": f"exit:{h['screen']}", "severity": "healthy", "severity_source": "watchdog rule (provisional)",
            "class": None, "diagnosis_status": "pending",
            "title": f"{label}: exits are high but unchanged" if h["stable"] else f"{label}: most sessions end here",
            "title_source": "template", "summary": None, "hypothesis": None, "confidence": None,
            "recommendation": None, "guardrail_flags": [],
            "diagnosis": pending_diagnosis(),
            "screen": h["screen"], "screen_label": label, "scope": "temporal", "segment": {}, "segment_text": "All users",
            "compared_with": "baseline period",
            "signals": [], "facts": [f"{pct(h['exit_rate_now'])} of sessions end on this screen now and "
                                     f"{pct(h['exit_rate_baseline'])} did before. The rate is steady."],
            "n_sessions": h["n_sessions"],
            "impact": {"severity": 0, "volume_per_week": round(h["n_sessions"] / (now_days / 7)),
                       "lost_sessions_per_week": 0, "value_per_session": VALUE_PER_SESSION, "score": 0,
                       "per_week_dollars": 0, "assumption": VALUE_ASSUMPTION},
            "evidence": {"affected_session_ids": h["sample_sessions"]["affected"][:2], "comparison_session_ids": [],
                         "sessions": evid(h["sample_sessions"]["affected"][:2], [])},
            "ticket_draft": None,
        })
    insights.sort(key=lambda i: (SEVERITY_ORDER[i["severity"]], -i["impact"]["score"]))
    for rank, i in enumerate(insights, 1):
        i["rank"] = rank

    f_start, f_end = funnel_ends(pos)
    all_days = sorted({x["dt"].date() for x in clean})
    ov_views = {}
    for pf in ["all"] + platforms:
        for pe in ["all"] + personas:
            sub = [x for x in clean if (pf == "all" or x["platform"] == pf) and (pe == "all" or x["persona"] == pe)]
            view = overview_view(sub, all_days, now_start, now_days, f_start, f_end)
            for row in view["table"]:
                match = next((i for i in insights if i["scope"] == "segment"
                              and i["segment"].get("persona") == row["persona"]
                              and i["segment"].get("device_class") == row["device_class"]), None)
                row["finding_id"] = match["id"] if match else None
            ov_views[f"{pf}|{pe}"] = view
    funnel = {"start": f_start, "end": f_end, "start_label": humanize(f_start), "end_label": humanize(f_end)}

    gaps = [f["explanation"] for f in guardian["findings"] if f["kind"] in ("volume_gap", "missing_session_end")]
    results = {
        "meta": {
            "dataset": json.loads(Path(args.watchdog).read_text(encoding="utf-8")).get("dataset", "synthetic-v1"),
            "synthetic": True,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window": wd["window"], "now_days": now_days,
            "counts": {"sessions_in_window": len(sessions), "sessions_quarantined": wd["sessions"]["quarantined"],
                       "first_day": min(x["dt"] for x in all_sessions).date().isoformat(),
                       "last_day": max(x["dt"] for x in all_sessions).date().isoformat()},
            "diagnosis_status": "pending",
            "value_assumption": VALUE_ASSUMPTION,
            "funnel": funnel,
        },
        "guardian": {"status": guardian["status"], "checks": guardian["checks"],
                     "quarantine_windows": guardian["quarantine_windows"], "gap_explanations": gaps[:3]},
        "insights": insights,
        "journeys": journeys,
        "overview": {"funnel": funnel, "now_days": now_days, "views": ov_views},
        "filters": {"platforms": platforms, "personas": personas},
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    print(f"{len(insights)} insights, {len(journeys)} journey views, {out.stat().st_size / 1024:.0f} KB -> {out}")
    for i in insights:
        print(f"  {i['rank']}. [{i['severity']}] {i['title']}  (~${i['impact']['per_week_dollars']}/wk assumed)")


if __name__ == "__main__":
    main()
