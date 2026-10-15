#!/usr/bin/env python3
"""Build results.json for the app from canonical events, the Guardian report and the Watchdog output.

synthetic-v2 version (schema `ui-v2`, see pipeline/results_contract.md and docs/ui-results-needs.md). Every number is
measured from the events; every sentence is a fixed template over those numbers. Fields that belong to the Diagnostic
Agent stay empty with `diagnosis_status: "pending"`. Nothing here is hand-edited, and raw user ids and device ids
never reach the output (evidence records are redacted).

Usage:
  python pipeline/build_results.py --events data/synthetic/canonical_events.jsonl \
      --raw data/synthetic/events_raw.jsonl --guardian data/synthetic/guardian_report.json \
      --watchdog data/synthetic/watchdog_candidates.json --out data/synthetic/results_v2.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from guardian import is_quarantined, parse_ts
from profiles import load as load_profile
from schema import (DEVICE_CLASS_LABELS, JOURNEY_LABELS, JOURNEYS, PERSONA_LABELS, PERSONAS, PRODUCT_LABELS, PRODUCTS,
                    SCREEN_LABELS, TERMINAL_SCREENS, journey_of)

PROFILE = load_profile()      # the active dataset profile: wording and a few business numbers (profiles/__init__.py)

UTC = timezone.utc
CURRENCY = "PHP"
VALUE_PER_SESSION = {"register_login": 150, "topup": 100, "transaction": 200}   # ASSUMPTIONS, not data
VALUE_ASSUMPTION = ("Assumed value: placeholder values per completed task (PHP 150 registration or login, PHP 100 top-up, PHP 200 transaction). "
                    "Not measured; replace with real figures before quoting pesos.")
DATASET_LABEL = "Sample dataset (synthetic)"
SEVERITY_ORDER = {"critical": 0, "warning": 1, "healthy": 2}
RANGES = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
SALT = "scout-synthetic-v2"          # not a secret: it only keeps the pseudonyms stable inside this dataset
MIN_DAY_N = 5
MIN_ROW_N = 20
MIN_STEP_N = 20
HOT_RADIUS = 0.05       # normalised screen units
ONSET_MIN_DIFF = 0.10
ONSET_MIN_FIT = 0.6
STUCK_MS = 30_000
BUCKETS = 14
# the three journeys the UI shows; screens of several backend journeys fold into one step where they play the same role
UI_STEPS = {
    "register_login": [("prices", ["prices"], "Price check"), ("welcome", ["welcome"], "App open"),
                       ("phone", ["register_phone", "login_phone"], "Phone number"), ("otp", ["otp"], "OTP code"),
                       ("personal_data", ["personal_data"], "Personal data"), ("tin", ["tin"], "TIN number"),
                       ("kyc_selfie", ["kyc_selfie"], "Selfie check"), ("done", ["register_done", "home"], "Registered or signed in")],
    "topup": [("wallet", ["wallet"], "Wallet"), ("amount", ["topup_amount"], "Amount"), ("confirm", ["topup_confirm"], "Confirm"),
              ("done", ["topup_done"], "Top-up done")],
    "transaction": [("product", ["product_list"], "Choose product"), ("details", ["txn_details"], "Details"),
                    ("confirm", ["txn_checkout"], "Checkout and PIN"), ("done", ["txn_done"], "Transaction done")],
}
UI_JOURNEY_NAMES = {"register_login": "Register and login", "topup": "Wallet top-up", "transaction": "Transaction"}
BACKEND_TO_UI = {"browse": "register_login", "register": "register_login", "login": "register_login", "topup": "topup",
                 "transaction": "transaction"}
UI_STEPS = PROFILE.get("UI_STEPS", UI_STEPS)
UI_JOURNEY_NAMES = PROFILE.get("UI_JOURNEY_NAMES", UI_JOURNEY_NAMES)
STEP_OF = {sc: (j, sid) for j, steps in UI_STEPS.items() for sid, scs, _ in steps for sc in scs}
STEP_NAME = {(j, sid): name for j, steps in UI_STEPS.items() for sid, _, name in steps}
LANDMARK_TERMINAL = {(j, steps[-1][0]) for j, steps in UI_STEPS.items()}
ELEMENT_LABELS = {"resend": "Resend code / receive via SMS", "verify": "Verify button", "pay": "Confirm payment (PIN)",
                  "continue": "Continue button", "submit": "Submit button", "confirm": "Confirm button"}
# schematic wireframes for the tap-hotspot card: [top%, left%, w%, h%, kind, label?]. Layout only; the spots are measured.
WIREFRAMES = {
    "otp": [[0, 0, 100, 11, "bar", "< Verify your phone"], [14, 6, 62, 3, "line"], [19, 6, 48, 3, "line"],
            [28, 6, 15, 8, "box"], [28, 24, 15, 8, "box"], [28, 42, 15, 8, "box"], [28, 60, 15, 8, "box"], [28, 78, 15, 8, "box"],
            [60, 20, 60, 12, "btnLight", "Resend code / receive via SMS"], [80, 10, 80, 10, "btn", "Verify"]],
    "txn_checkout": [[0, 0, 100, 11, "bar", "< Confirm payment"], [14, 6, 62, 3, "line"], [19, 6, 48, 3, "line"],
                     [30, 6, 88, 10, "box"], [48, 6, 88, 10, "box"], [66, 10, 80, 6, "line"], [85, 10, 80, 10, "btn", "Confirm with PIN"]],
}
VALUE_PER_SESSION = PROFILE.get("VALUE_PER_SESSION", VALUE_PER_SESSION)
VALUE_ASSUMPTION = PROFILE.get("VALUE_ASSUMPTION", VALUE_ASSUMPTION)
ELEMENT_LABELS = {**ELEMENT_LABELS, **PROFILE.get("ELEMENT_LABELS", {})}
WIREFRAMES = {**WIREFRAMES, **PROFILE.get("WIREFRAMES", {})}

# Every wallet-specific sentence the builder writes. The defaults are the wallet wording; a profile may override any key.
VOCAB = {
    "conv_label": "Register and login completion",
    "conv_sub": "{n} register or login sessions that reach Registered or Home",
    "funnel_start": "Started a register, login, top-up or transaction",
    "funnel_end": "Reached the success screen",
    "pat_amount_title": "{who} top up large amounts",
    "pat_amount_fact": "{share} of {who} top-ups are above {cur} {thr:,} (median {cur} {med:,}), against {ref} for everyone else (median {cur} {refmed:,}).",
    "pat_prod_title": "{who} mostly buy {prod}",
    "pat_prod_fact": "{share} of {who} transactions are {prod}, against {ref} for everyone else.",
    "natural_assumption": "No value assumed: people checking prices before signing up are not lost customers.",
    "intent_otp_raw": "otp screen_view dwell_ms={dwell} rage_tap resend x{rage}",
    "intent_browse_raw": "prices screen_view tap product_card (unregistered)",
    "intent_browse": "Checking prices before signing up",
    "intent_pay_raw": "txn_checkout product=send_money rage_tap pay",
    "intent_risk_raw": "{last} error (fraudster, shared device)",
    "intent_unmapped_raw": "param otp_channel_v2",
    "ask_burst_q": "Why do sign-ups stall on {day}?",
    "ask_burst_a": "Between {start} and {end} UTC on {day}, {rate} of sessions at the {screen} screen ended there, against {ref} outside the window "
                   "({n} sessions inside it). {rage}The pattern is the same for every persona, which points to codes not being delivered rather than user behavior.",
    "ask_burst_kw": ["otp", "code", "stall", "sign", "register", "login", "sms", "timestamp", "window", "resend"],
    "ask_p4_q": "Which persona drops off before a transaction succeeds?",
    "ask_p4_a": "{seg}: {rate} of {n} sessions at checkout end there, against {ref} for everyone else.",
    "ask_p4_kw": ["persona", "transaction", "succeed", "success", "send", "money", "trader", "confirm", "pin", "abandon", "drop", "checkout"],
    "ask_amount_q": "Who tops up large amounts?",
    "ask_amount_a": "{who} do: {share} of their top-ups are above {cur} {thr:,} (median {cur} {med:,}). Everyone else has a median of {cur} {refmed:,}.",
    "ask_amount_kw": ["top", "topup", "up", "amount", "large", "big", "business", "php", "peso", "cash"],
    "ask_prod_q": "What does Retail buy?",
    "ask_prod_a": "{share} of {who} transactions are {prod}, against {ref} for other personas. This is expected behavior, not a problem.",
    "ask_prod_kw": ["sari", "store", "retail", "product", "buy", "eload", "load", "prefer"],
    "ask_risk_q": "Are fraudster accounts a problem?",
    "ask_risk_a": "Fraudster accounts fail far more often: {fact} {shared} devices are shared by 3 or more users. They are flagged as needing review, not classified.",
    "ask_risk_kw": ["fraud", "fraudster", "device", "shared", "burst", "failed", "attempts"],
    "ask_natural_q": "Why do unregistered users leave at the price list?",
    "ask_natural_a": "{fact} The rate has not changed, so it is treated as a natural exit and kept out of the problem feed.",
    "ask_natural_kw": ["unregistered", "price", "prices", "natural", "exit", "browse", "register"],
    "ask_control_q": "Where do most users drop off?",
    "ask_control_kw": ["drop", "dropoff", "most", "where", "page", "pages", "personal", "tin", "steady"],
    "sk_pay_q": "Show the journey of the users who abandoned after payment",
    "sk_pay_title": "Abandoned after payment",
    "sk_pay_kw": ["journey", "abandon", "payment", "checkout", "pin", "transaction", "topup"],
    "sk_otp_q": "Where do people go after the OTP step fails?",
    "sk_otp_title": "Exited at OTP",
    "sk_otp_kw": ["otp", "fail", "resend", "phone", "verification"],
    "sk_group_q": "What happens to Retail buyers who leave before success?",
    "sk_group_title": "Retail buyers who left before transaction success",
    "sk_group_persona": "Retail",
    "sk_group_kw": ["retail", "buyer", "sari", "transaction", "success", "leave"],
}
VOCAB.update(PROFILE.get("VOCAB", {}))


def pct(x) -> str:
    return f"{x * 100:.0f}%"


def pct1(x) -> str:
    return f"{x * 100:.1f}%"


def pseudo(prefix: str, raw: str) -> str:
    return prefix + hashlib.sha256((SALT + raw).encode()).hexdigest()[:6]


def humanize(screen: str) -> str:
    return SCREEN_LABELS.get(screen, screen.replace("_", " ").capitalize())


def matches(s: dict, seg: dict) -> bool:
    return all(s.get(k) == v for k, v in seg.items())


def segment_text(seg: dict) -> str:
    if not seg:
        return "All users"
    parts = []
    if "persona" in seg:
        parts.append(PERSONA_LABELS.get(seg["persona"], seg["persona"]))
    if "product" in seg:
        parts.append(PRODUCT_LABELS.get(seg["product"], seg["product"]))
    if "device_class" in seg:
        parts.append(DEVICE_CLASS_LABELS.get(seg["device_class"], seg["device_class"]))
    if "app_version" in seg:
        parts.append(f"app {seg['app_version']}")
    return ", ".join(parts)


def iso_day(dt) -> str:
    return dt.strftime("%Y-%m-%d")


def label_day(dt: datetime) -> str:
    return f"{dt.strftime('%b')} {dt.day}"


# ----------------------------------------------------------------------------- loading
def load_sessions(path: Path, need: set, windows: list):
    """One pass over canonical events: dedupe, group by session, derive what every later step needs."""
    by_sid: dict = defaultdict(list)
    seen: set = set()
    totals = Counter()
    daily_events: Counter = Counter()
    unmapped_by_screen: Counter = Counter()
    daily_unmapped: Counter = Counter()
    events_by_screen: Counter = Counter()
    last_event_by_screen: dict = {}
    first_version: dict = {}
    taps: dict = defaultdict(list)                     # (screen, event_type) -> [(x, y, element)]
    keep: dict = defaultdict(list)
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
            totals["events"] += 1
            ts = e["ts"]
            daily_events[ts[:10]] += 1
            sc = e.get("screen")
            if sc:
                events_by_screen[sc] += 1
                if e.get("unmapped"):
                    unmapped_by_screen[sc] += 1
                    daily_unmapped[ts[:10]] += 1
                if ts > last_event_by_screen.get(sc, ""):
                    last_event_by_screen[sc] = ts
            ver = e.get("app_version")
            if ver and (ver not in first_version or ts < first_version[ver]):
                first_version[ver] = ts
            if e.get("tap_x") is not None and e["event_type"] in ("rage_click", "dead_tap"):
                taps[(sc, e["event_type"])].append((e["tap_x"], e["tap_y"], e.get("element")))
            sid = e["session_id"]
            by_sid[sid].append((ts, e["event_type"], sc, e.get("element"), e.get("dwell_ms"), e.get("error_code"),
                                e.get("app_version"), e.get("persona"), e.get("device_class"), e.get("product"),
                                e.get("amount_php"), e.get("user_id"), e.get("device_id"), e.get("os"), eid))
            if sid in need:
                keep[sid].append(e)
    out = []
    for sid, evs in by_sid.items():
        evs.sort(key=lambda t: t[0])
        s = {"sid": sid, "start": evs[0][0], "persona": None, "device_class": None, "app_version": None, "product": None,
             "amount": None, "user": None, "device": None, "os": None, "views": [], "back_moves": [],
             "back_moves_after_payment": [], "back_moves_after_otp": [], "back_after_payment": False,
             "back_after_otp": False, "stats": {},
             "last": None, "platform": "app"}
        pending_back = None
        payment_reached = False
        otp_reached = False
        prev_t = prev_sc = None
        taps_at: dict = {}
        for ts, et, sc, el, dw, err, ver, per, dc, prod, amt, uid, did, os_, _ in evs:
            t_now = parse_ts(ts).timestamp()
            # stuck = no forward progress for 30 s or more (a gap between two events on the same screen), or 3+ taps on one target within 2 s
            if prev_t is not None and prev_sc and et != "screen_view" and t_now - prev_t >= STUCK_MS / 1000 and prev_sc in s["stats"]:
                s["stats"][prev_sc]["stuck"] = True
            prev_t, prev_sc = t_now, sc or prev_sc
            if et in ("click", "rage_click", "dead_tap") and el and sc:
                w = [x for x in taps_at.get((sc, el), []) if t_now - x <= 2.0] + [t_now]
                taps_at[(sc, el)] = w
                if len(w) >= 3 and sc in s["stats"]:
                    s["stats"][sc]["stuck"] = True
            for k, v in (("persona", per), ("device_class", dc), ("app_version", ver), ("product", prod), ("user", uid),
                         ("device", did), ("os", os_)):
                if s[k] is None and v:
                    s[k] = v
            if sc:
                s["last"] = sc
                st = s["stats"].setdefault(sc, {"dwell": 0, "rage": 0, "dead": 0, "back": 0, "errors": 0, "resend": 0, "view_ts": ts, "codes": {}, "rage_el": {}, "stuck": False})
                if et == "screen_view":
                    s["views"].append(sc)
                    if pending_back is not None and pending_back != sc:
                        s["back_moves"].append((pending_back, sc))
                        if payment_reached:
                            s["back_moves_after_payment"].append((pending_back, sc))
                        if otp_reached:
                            s["back_moves_after_otp"].append((pending_back, sc))
                    pending_back = None
                    payment_reached = payment_reached or sc in ("txn_checkout", "topup_confirm")
                    otp_reached = otp_reached or sc == "otp"
                elif et == "screen_leave" and dw is not None:
                    st["dwell"] += dw
                elif et == "rage_click":
                    st["rage"] += 1
                    st["rage_el"][el or "unknown"] = st["rage_el"].get(el or "unknown", 0) + 1
                elif et == "click" and (el or "").lower() in ("resend", "resend_code", "resend_otp"):
                    st["resend"] += 1
                elif et == "dead_tap":
                    st["dead"] += 1
                elif et == "back":
                    st["back"] += 1
                    pending_back = sc
                    if payment_reached:
                        s["back_after_payment"] = True
                    if otp_reached:
                        s["back_after_otp"] = True
                elif et == "error":
                    st["errors"] += 1
                    st["codes"][err or "unknown"] = st["codes"].get(err or "unknown", 0) + 1
                if sc == "topup_confirm" and amt is not None:
                    s["amount"] = amt
        s["end"] = evs[-1][0]
        s["dt"] = parse_ts(s["start"])
        s["persona"] = s["persona"] or "unknown"
        s["seen"] = set(s["views"])
        s["journey"] = journey_of(s["seen"])
        s["ui_journey"] = BACKEND_TO_UI.get(s["journey"])
        s["completed"] = s["last"] in TERMINAL_SCREENS
        s["dur_s"] = (parse_ts(s["end"]) - s["dt"]).total_seconds()
        s["quarantined"] = is_quarantined("app", s["dt"], windows, s["app_version"], s["journey"])
        tot = {k: sum(v[k] for v in s["stats"].values()) for k in ("rage", "dead", "back", "errors")}
        s.update({f"n_{k}": v for k, v in tot.items()})
        s["stuck"] = any(v["stuck"] for v in s["stats"].values())
        s["exit_class"] = None if s["completed"] else exit_class(s)
        out.append(s)
    meta = {"events": totals["events"], "daily_events": daily_events, "daily_unmapped": daily_unmapped, "unmapped_by_screen": unmapped_by_screen,
            "events_by_screen": events_by_screen, "last_event_by_screen": last_event_by_screen, "first_version": first_version,
            "taps": taps}
    return out, keep, meta


def exit_class(s: dict) -> str:
    """Rules-based class of an exit: technical (errors, dead or rage taps on the last screen), ux (went back),
    language (stuck on the last screen for more than 30 s with none of that), else natural. Not an AI label."""
    if s["journey"] == "browse":
        return "natural"
    st = s["stats"].get(s["last"], {})
    if st.get("errors") or st.get("dead") or st.get("rage"):
        return "technical"
    if s["n_back"]:
        return "ux"
    if st.get("dwell", 0) > STUCK_MS:
        return "language"
    return "natural"


def raw_records(path: Path, ids: set) -> dict:
    out: dict = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for line in f:
            if '"session_id"' not in line:
                continue
            r = json.loads(line)
            if r.get("session_id") in ids:
                out[r["session_id"]].append(redact(r))
    return out


def redact(r: dict) -> dict:
    """Public copy of a raw record: pseudonymous user and device ids, no model name, major OS version only."""
    r = json.loads(json.dumps(r))
    if r.get("user_id"):
        r["user_id"] = pseudo("u_", r["user_id"])
    di = r.get("device_info")
    if isinstance(di, dict):
        if di.get("device_id"):
            di["device_id"] = pseudo("d_", di["device_id"])
        if di.get("model"):
            di["model"] = "iPhone" if di.get("os") == "ios" else "Android phone"
        if di.get("os_version"):
            di["os_version"] = str(di["os_version"]).split(".")[0]
    return r


# ----------------------------------------------------------------------------- insight helpers (kept from v1)
def ended_rate(group: list, screen: str):
    viewed = [s for s in group if screen in s["seen"]]
    return (len(viewed), sum(s["last"] == screen for s in viewed) / len(viewed)) if viewed else (0, None)


def day_series(clean: list, screen: str, seg: dict, with_reference: bool) -> list:
    out = []
    by_day = defaultdict(list)
    for s in clean:
        by_day[s["dt"].date()].append(s)
    for d in sorted(by_day):
        day = by_day[d]
        n, r = ended_rate([s for s in day if matches(s, seg)], screen)
        row = {"d": d.isoformat(), "n": n, "rate": round(r, 4) if r is not None and n >= MIN_DAY_N else None}
        if with_reference:
            rn, rr = ended_rate([s for s in day if not matches(s, seg)], screen)
            row.update(ref_n=rn, ref_rate=round(rr, 4) if rr is not None and rn >= MIN_DAY_N else None)
        out.append(row)
    return out


def estimate_onset(series: list):
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


DIM_LABELS = {"persona": PERSONA_LABELS, "device_class": DEVICE_CLASS_LABELS, "product": PRODUCT_LABELS, "app_version": {}}
DIM_NAMES = {"persona": "Persona", "device_class": "Device", "product": "Product", "app_version": "App version", "platform": "Platform"}


def breakdown(now_at: list, before_at: list, screen: str, seg: dict, temporal: bool) -> list:
    rows = []
    for dim in ("persona", "device_class", "product", "app_version"):
        for v in sorted({s[dim] for s in now_at if s[dim]}):
            g = [s for s in now_at if s[dim] == v]
            if len(g) < MIN_ROW_N:
                continue
            _, r = ended_rate(g, screen)
            row = {"dim": dim, "dim_label": DIM_NAMES[dim], "value": v, "label": DIM_LABELS[dim].get(v, v), "n": len(g),
                   "rate": round(r, 4), "in_segment": seg.get(dim) == v}
            if temporal:
                gb = [s for s in before_at if s[dim] == v]
                bn, br = ended_rate(gb, screen)
                row["rate_before"] = round(br, 4) if br is not None and bn >= MIN_ROW_N else None
            rows.append(row)
    return rows


def evidence_stats(group: list, ref: list, screen: str, users_by_device: dict) -> dict:
    """Numbers the Diagnostic Agent may quote, measured over the WHOLE group (not only the sample sessions)."""
    def one(g: list):
        if not g:
            return None
        at = [s["stats"].get(screen, {}) for s in g]
        n = len(g)
        codes, rage_el = Counter(), Counter()
        for a in at:
            codes.update(a.get("codes", {}))
            rage_el.update(a.get("rage_el", {}))
        dw = [a.get("dwell", 0) for a in at if a.get("dwell")]
        ends = [s for s in g if s["last"] == screen]
        sh = lambda k: round(sum(1 for a in at if a.get(k)) / n, 4)
        return {"sessions": n, "exit_rate": round(len(ends) / n, 4), "with_error": sh("errors"), "with_rage_tap": sh("rage"),
                "with_dead_tap": sh("dead"), "with_back": sh("back"),
                "median_dwell_s": round(median(dw) / 1000, 1) if dw else None,
                "shared_device_share": round(sum(1 for s in g if len(users_by_device.get(s["device"], ())) > 1) / n, 4),
                "night_share_00_06_wib": round(sum(1 for s in g if 17 <= s["dt"].hour <= 22) / n, 4),
                "top_error_codes": [{"code": k, "events": v} for k, v in codes.most_common(3)],
                "top_rage_tap_elements": [{"element": k, "taps": v} for k, v in rage_el.most_common(3)]}
    return {"group": one(group), "reference": one(ref)}


def fact(sig: dict, scope: str) -> str:
    v, r, m = sig["value"], sig["reference"], sig["metric"]
    ref = {"temporal": "before", "burst": "outside the window"}.get(scope, "for everyone else")
    if m == "drop_off":
        return f"{pct(v)} of sessions at this screen end here, versus {pct(r)} {ref}."
    if m == "dwell":
        return f"Median time on the screen is {v / 1000:.0f}s, versus {r / 1000:.0f}s {ref}."
    if m == "rage":
        return f"{pct(v)} of sessions include rage taps (rapid repeated taps), versus {pct(r)} {ref}."
    if m == "error":
        return f"{pct(v)} of sessions show an error on this screen, versus {pct(r)} {ref}."
    return f"{m}: {v} versus {r}."


def pending_diagnosis() -> dict:
    return {"status": "pending", "model": None, "generated_at": None, "source_note": None, "class": None, "confidence": None,
            "summary": None, "claims": [], "next_steps": [], "guardrail_flags": [], "caveats": []}


def evidence_session(sid: str, role: str, evs: list, raw: list, sess: dict) -> dict:
    evs = sorted(evs, key=lambda e: e["ts"])
    t0 = parse_ts(evs[0]["ts"])
    rows, path = [], []
    for e in evs:
        flag = {"rage_click": "Rage click", "dead_tap": "Dead tap", "error": "Error", "back": "Back", "unknown": "Unrecognized event"}.get(e["event_type"])
        if e["event_type"] == "screen_view" and e.get("screen") and (not path or path[-1] != e["screen"]):
            path.append(e["screen"])
        rows.append({"t": int((parse_ts(e["ts"]) - t0).total_seconds() * 1000), "type": e["event_type"], "screen": e.get("screen"),
                     "element": e.get("element"), "dwell_ms": e.get("dwell_ms"), "error_code": e.get("error_code"), "flag": flag})
    return {"session_id": sid, "role": role, "platform": "app", "persona": sess["persona"], "path": path, "rows": rows,
            "events": sorted(raw, key=lambda r: r.get("timestamp", ""))}


# ----------------------------------------------------------------------------- the build
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--events", required=True)
    ap.add_argument("--raw", help="raw events file; evidence shows redacted raw records when given")
    ap.add_argument("--guardian", required=True)
    ap.add_argument("--watchdog", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--diagnose", action="store_true", help="run the Diagnostic Agent (pipeline/diagnose.py) on every insight")
    ap.add_argument("--offline", action="store_true", help="with --diagnose: never call Gemini (cache, trusted rules, unclassified)")
    ap.add_argument("--refresh", action="store_true", help="with --diagnose: ignore the cache and call Gemini again")
    args = ap.parse_args()

    guardian = json.loads(Path(args.guardian).read_text(encoding="utf-8"))
    wd = json.loads(Path(args.watchdog).read_text(encoding="utf-8"))
    first_line = next(open(args.events, encoding="utf-8"))
    mapping_ds = json.loads(first_line).get("dataset")
    dataset = mapping_ds or "unknown"
    synthetic = str(dataset).startswith("synthetic")
    now_start, now_end = parse_ts(wd["window"]["now_start"]), parse_ts(wd["window"]["now_end"])
    now_days = wd["params"]["now_days"]

    need = set()
    for c in wd["candidates"]:
        need |= set(c["sample_sessions"]["affected"][:4]) | set(c["sample_sessions"]["comparison"][:1])
    for h in wd["high_exit_screens"]:
        need |= set(h["sample_sessions"]["affected"][:2])
    all_s, keep, em = load_sessions(Path(args.events), need, guardian["quarantine_windows"])
    raw = raw_records(Path(args.raw), need) if args.raw else {}
    clean = [s for s in all_s if not s["quarantined"]]
    t_end = now_end
    t_first = min(s["dt"] for s in all_s)
    window_days = max(1, round((t_end - t_first.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds() / 86400))
    as_of = (t_end - timedelta(seconds=1)).date()
    by_sid = {s["sid"]: s for s in all_s}
    users_by_device: dict = defaultdict(set)
    for s in all_s:
        users_by_device[s["device"]].add(s["user"])
    persona_users = Counter()
    seen_u = set()
    for s in all_s:
        if s["user"] not in seen_u:
            seen_u.add(s["user"])
            persona_users[s["persona"]] += 1

    # ---------- insights
    insights = []
    patterns_ins = []
    members: dict = {}

    def population(c: dict):
        """(member(s) -> bool) for the sessions an insight is about."""
        sc, seg = c["screen"], c["segment"]
        if c["scope"] == "burst":
            ws, we = parse_ts(c["window"]["start"]), parse_ts(c["window"]["end"])
            return lambda s: sc in s["seen"] and ws <= parse_ts(s["stats"][sc]["view_ts"]) < we
        if c["scope"] == "temporal":
            return lambda s: sc in s["seen"] and s["dt"] >= now_start
        return lambda s: sc in s["seen"] and matches(s, seg)

    def causes_for(c: dict, affected: list) -> list:
        tech = sum(s["exit_class"] == "technical" for s in affected)
        n = max(1, len(affected))
        t_share, b_share = tech / n, 1 - tech / n
        out = []
        if tech:
            out.append({"type": "technical", "share": round(t_share, 2), "title": f"Errors, dead taps or rage taps on {humanize(c['screen'])}",
                        "why": f"{tech} of {len(affected)} exits at this screen carry an error, a dead tap or rage taps. "
                               "Events alone cannot say whether the cause is the app, the network or a provider.",
                        "fault_id": None, "resolved": False, "quarantine": False})
        if len(affected) - tech:
            out.append({"type": "behavior", "share": round(b_share, 2), "title": "Users leave without a failure signal",
                        "why": f"{len(affected) - tech} of {len(affected)} exits show no error, dead tap or rage tap.",
                        "fault_id": None, "resolved": False, "quarantine": False})
        for f in guardian["faults"]:
            if f.get("screen") == c["screen"] or (f["kind"] == "unmapped" and c["screen"] == "otp" and "otp" in f["title"].lower()):
                out.append({"type": "technical", "share": 0, "title": f["title"], "why": f["detail"], "fault_id": f["id"],
                            "resolved": f["status"] == "resolved", "quarantine": f["kind"] == "tracker_silent"})
        return out

    def value_of(c: dict) -> int:
        j = BACKEND_TO_UI.get(next((jj for jj, p in JOURNEYS.items() if c["screen"] in p and jj != "browse"), "register"), "register_login")
        return VALUE_PER_SESSION[j]

    for c in wd["candidates"]:
        temporal, burst = c["scope"] == "temporal", c["scope"] == "burst"
        member = population(c)
        members[c["id"]] = (member, (parse_ts(c["window"]["start"]), parse_ts(c["window"]["end"])) if burst else None)
        pop = [s for s in clean if member(s)]
        affected = [s for s in pop if s["last"] == c["screen"]]
        drop = next((x for x in c["signals"] if x["metric"] == "drop_off"), None)
        sev_effect = drop["diff"] if drop else 0.0
        period_weeks = (now_days if temporal else window_days) / 7
        lost_week = c["excess_sessions"] / period_weeks
        severity = "critical" if (sev_effect >= 0.10 and c["excess_sessions"] >= 50) else "warning"
        who = segment_text(c["segment"])
        label = humanize(c["screen"])
        if burst:
            w = c["window"]
            ws, we = parse_ts(w["start"]), parse_ts(w["end"])
            who = f"All users, {label_day(ws)} {ws.strftime('%H:%M')} to {we.strftime('%H:%M')} UTC"
            title = f"{label}: exits jump from {pct(drop['reference'])} to {pct(drop['value'])} between {ws.strftime('%H:%M')} and {we.strftime('%H:%M')} UTC on {label_day(ws)}"
            kind = "Time window"
        elif temporal:
            title, kind = f"{label}: more people leave here than before", "Trend"
        else:
            title, kind = f"{label}: {who} drop off far more often than everyone else", "Blind spot"
        if burst:
            series = day_series(clean, c["screen"], {}, False)
            onset = ws.date().isoformat()
            rows = breakdown([s for s in pop], [s for s in clean if c["screen"] in s["seen"] and not member(s)], c["screen"], {}, True)
            gaps = []
        else:
            series = day_series(clean, c["screen"], c["segment"], with_reference=not temporal)
            onset = estimate_onset(series) if temporal else None
            rows = breakdown([x for x in clean if c["screen"] in x["seen"] and (not temporal or x["dt"] >= now_start)],
                             [x for x in clean if c["screen"] in x["seen"] and x["dt"] < now_start], c["screen"], c["segment"], temporal)
            gaps = []
        aff_ids, cmp_ids = c["sample_sessions"]["affected"][:3], c["sample_sessions"]["comparison"][:1]
        ev_sessions = [evidence_session(sid, "affected", keep[sid], raw.get(sid, []), by_sid[sid]) for sid in aff_ids if sid in keep]
        ev_sessions += [evidence_session(sid, "comparison", keep[sid], raw.get(sid, []), by_sid[sid]) for sid in cmp_ids if sid in keep]
        rng_ranges = ranges_for(member, clean, as_of, t_end, burst and (parse_ts(c["window"]["start"]), parse_ts(c["window"]["end"])))
        first_aff = min((s["dt"] for s in affected), default=None)
        ins = {
            "id": c["id"], "severity": severity, "severity_source": "watchdog rule (provisional)", "class": None,
            "diagnosis_status": "pending", "title": title, "title_source": "template", "summary": None, "hypothesis": None,
            "confidence": None, "recommendation": None, "guardrail_flags": [], "diagnosis": pending_diagnosis(),
            "hint_class": c["hint_class"], "hint_rule": c["hint_rule"],
            "screen": c["screen"], "screen_label": label, "scope": c["scope"], "segment": c["segment"], "segment_text": who,
            "compared_with": c["reference"], "signals": c["signals"], "facts": [fact(x, c["scope"]) for x in c["signals"]],
            "n_sessions": c["n_sessions"],
            "impact": {"severity": round(sev_effect, 4), "volume_per_week": round(len(pop) / period_weeks),
                       "lost_sessions_per_week": round(lost_week), "volume": c["excess_sessions"],
                       "value_per_session": value_of(c), "score": round(sev_effect * (len(pop) / period_weeks) * value_of(c)),
                       "per_week_value": round(lost_week * value_of(c)), "per_week_dollars": round(lost_week * value_of(c)),
                       "currency": CURRENCY, "assumption": VALUE_ASSUMPTION},
            "evidence": {"affected_session_ids": aff_ids, "comparison_session_ids": cmp_ids, "sessions": ev_sessions},
            "timeline": {"metric": "drop_off", "metric_label": "Share of sessions that end on this screen", "series": series,
                         "gaps": gaps, "now_start": wd["window"]["now_start"], "has_reference": not temporal and not burst,
                         "onset": onset},
            "breakdown": rows,
            "concentration": (f"Concentrated in {who}: {pct(drop['value'])} end here, compared with {pct(drop['reference'])} for everyone else."
                              if drop and c["scope"] == "segment" else
                              (f"Every persona is hit inside the window: exits at this screen are {pct(drop['value'])} there and {pct(drop['reference'])} outside it." if burst and drop else None)),
            "ticket_draft": None,
            # ui-v2
            "journey": STEP_OF[c["screen"]][0], "step": STEP_OF[c["screen"]][1], "tone": severity,
            "label": f"{'Critical' if severity == 'critical' else 'Warning'} · {kind}",
            "persona_ids": [c["segment"]["persona"]] if "persona" in c["segment"] else [],
            "ranges": rng_ranges, "detected_hours_ago": round((t_end - (first_aff or t_end)).total_seconds() / 3600),
            "is_new": False, "replays": len(c["sample_sessions"]["affected"]),
            "causes": causes_for(c, affected),
            "affected_sessions": len(affected),
        }
        if burst:
            ins["window"] = c["window"]
        insights.append(ins)

    # patterns (never problems)
    for p in wd["patterns"]:
        if p["kind"] == "topup_amount":
            who = PERSONA_LABELS.get(p["persona"], p["persona"])
            title = VOCAB["pat_amount_title"].format(who=who)
            fact_txt = VOCAB["pat_amount_fact"].format(share=pct(p["value"]), who=who, cur=CURRENCY, thr=p["threshold_php"], med=p["median_php"],
                                                      ref=pct(p["reference"]), refmed=p["reference_median_php"])
            screen, seg, jid = "topup_confirm", {"persona": p["persona"]}, "topup"
        else:
            who = PERSONA_LABELS.get(p["persona"], p["persona"])
            prod_label = PRODUCT_LABELS.get(p["product"], p["product"])
            title = VOCAB["pat_prod_title"].format(who=who, prod=prod_label)
            fact_txt = VOCAB["pat_prod_fact"].format(share=pct(p["value"]), who=who, prod=prod_label, ref=pct(p["reference"]))
            screen, seg, jid = "product_list", {"persona": p["persona"]}, "transaction"
        members[p["id"]] = (lambda s, sc=screen, pe=p["persona"]: sc in s["seen"] and s["persona"] == pe, None)
        patterns_ins.append(pattern_insight(p, title, fact_txt, screen, seg, jid, clean, as_of, t_end))
    insights += patterns_ins

    # natural exits and steady drop-offs (control)
    exits_all = screen_exit_table(clean)
    for h in wd["high_exit_screens"]:
        label = humanize(h["screen"])
        mem = lambda s, sc=h["screen"]: sc in s["seen"]
        members[f"exit:{h['screen']}"] = (mem, None)
        uu = [s for s in clean if h["screen"] in s["seen"]]
        ex = [s for s in uu if s["last"] == h["screen"]]
        multi = Counter(s["user"] for s in ex)
        insights.append(healthy_insight(f"exit:{h['screen']}", h["screen"], "natural_exit",
                                        f"{label}: exits are high but unchanged" if h["stable"] else f"{label}: most sessions end here",
                                        [f"{pct(h['exit_rate_now'])} of sessions at this screen end here now and {pct(h['exit_rate_baseline'])} did before. "
                                         f"{len(multi)} people opened it {sum(multi.values())} times and left each time."],
                                        "Natural exit", "healthy", len(uu), clean, mem, as_of, t_end,
                                        VOCAB["natural_assumption"], [s for s in ex]))
    flagged = {c["screen"] for c in wd["candidates"]} | {h["screen"] for h in wd["high_exit_screens"]}
    rates = sorted(r["rate"] for sc, r in exits_all.items())
    med_rate = median(rates) if rates else 0
    for sc, r in sorted(exits_all.items(), key=lambda kv: -kv[1]["rate"]):
        if sc in flagged or sc in TERMINAL_SCREENS or r["rate"] < max(0.06, 1.05 * med_rate) or not r["stable"]:
            continue
        mem = lambda s, sc=sc: sc in s["seen"]
        members[f"segment:{sc}:control"] = (mem, None)
        by_p = {p: round(v, 4) for p, v in r["by_persona"].items()}
        insights.append(healthy_insight(f"segment:{sc}:control", sc, "ux_friction",
                                        f"{humanize(sc)}: a steady drop-off, the same for every persona",
                                        [f"{pct(r['rate'])} of sessions at this screen end here, steady across the whole period "
                                         f"(first half {pct(r['first'])}, second half {pct(r['second'])}); persona rates range from {pct(min(by_p.values()))} to {pct(max(by_p.values()))}."],
                                        "Steady drop-off", "warning", r["n"], clean, mem, as_of, t_end,
                                        "Assumed value only: a steady drop-off is not priced as lost customers.", [s for s in clean if sc in s["seen"] and s["last"] == sc],
                                        value=VALUE_PER_SESSION[STEP_OF[sc][0]]))
    insights.sort(key=lambda i: (SEVERITY_ORDER[i["severity"]], -i["impact"]["score"]))
    for rank, i in enumerate(insights, 1):
        i["rank"] = rank
    ins_by_id = {i["id"]: i for i in insights}
    # whole-group numbers the Diagnostic Agent may quote (additive; the UI does not read it)
    for i in insights:
        mem = members[i["id"]][0]
        i["evidence_stats"] = evidence_stats([s for s in clean if mem(s)], [s for s in clean if i["screen"] in s["seen"] and not mem(s)],
                                             i["screen"], users_by_device)

    # ---------- guardian faults for the UI
    faults_ui = ui_faults(guardian, em, clean, t_end, ins_by_id)

    # ---------- views
    views = {}
    all_hours_back = {}
    for rng_id, delta in RANGES.items():
        r_end, r_start = t_end, max(t_end - delta, t_first)
        p_start = r_start - delta
        day0 = t_first.replace(hour=0, minute=0, second=0, microsecond=0)
        if p_start >= day0:
            pw = (p_start, r_start, f"previous {rng_id.replace('h', ' hours').replace('d', ' days')}")
        else:    # no earlier data (the window starts here): compare with the first half of the window instead
            pw = (t_first, t_first + (r_end - r_start) / 2, "first half of the window (no earlier data)")
        for pe in ["all"] + sorted(PERSONAS):
            sub = [s for s in clean if (pe == "all" or s["persona"] == pe)]
            cur = [s for s in sub if r_start <= s["dt"] < r_end]
            prev = [s for s in sub if pw[0] <= s["dt"] < pw[1]]
            views[f"{rng_id}|all|{pe}"] = build_view(rng_id, pe, cur, prev, r_start, r_end, pw, insights, members, guardian, em, wd, all_s)

    # ---------- scope
    conf = step_conf(em)
    scope = {
        "personas": [{"id": p, "label": PERSONA_LABELS[p], "users": persona_users.get(p, 0)} for p in
                     ["unregistered", "large_business", "sari_sari", "individual_trader", "individual", "unknown", "fraudster"]],
        "products": [{"id": p, "label": PRODUCT_LABELS[p]} for p in PRODUCTS],
        "ranges": list(RANGES),
        "journeys": [{"id": j, "name": UI_JOURNEY_NAMES[j],
                      "steps": [{"id": sid, "name": name, "event": " | ".join(scs), "conf": conf.get(sid_key(j, sid)),
                                 "status": "matched" if (conf.get(sid_key(j, sid)) or 0) >= 0.9 else "review"}
                                for sid, scs, name in steps]} for j, steps in UI_STEPS.items()],
    }

    # ---------- legacy v1 blocks (journeys by persona, overview)
    legacy = legacy_blocks(clean, now_start, now_days)

    stuck = stuck_sessions(insights, keep, by_sid)
    hotspots = hotspot_cards(em["taps"])
    results = {
        "meta": {
            "dataset": dataset, "dataset_label": DATASET_LABEL if synthetic else "Dataset", "synthetic": synthetic,
            "schema": "ui-v2", "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "as_of": as_of.isoformat(), "window": {"start": t_first.date().isoformat(), "end": as_of.isoformat()},
            "currency": CURRENCY, "platforms": sorted({s["platform"] for s in all_s}), "now_days": now_days,
            "counts": {"events": em["events"], "sessions": len(all_s), "users": len(seen_u),
                       "sessions_in_window": len(clean), "sessions_quarantined": len(all_s) - len(clean),
                       "first_day": t_first.date().isoformat(), "last_day": as_of.isoformat()},
            "model": None, "diagnosis_source": None, "diagnosis_status": "pending", "value_assumption": VALUE_ASSUMPTION,
            "window_detail": wd["window"], "funnel": legacy["funnel"],
        },
        "scope": scope,
        "views": views,
        "guardian": {"status": guardian["status"], "checks": guardian["checks"], "quarantine_windows": guardian["quarantine_windows"],
                     "findings": guardian["findings"], "gap_explanations": [f["explanation"] for f in guardian["findings"]][:3],
                     "faults": faults_ui},
        "insights": insights,
        "journeys": legacy["journeys"],
        "overview": legacy["overview"],
        "filters": {"platforms": sorted({s["platform"] for s in all_s}), "personas": sorted(PERSONAS)},
        "product_funnels": product_funnels(clean),
        "stuck_sessions": stuck,
        "hotspot": hotspots[0] if hotspots else None,
        "hotspots": hotspots,
        "intents": intent_rows(clean, em),
        "agents": agents_rows(guardian, wd, insights, all_s, clean),
    }
    results["ask"] = ask_rows(results, clean, wd, guardian, users_by_device, persona_users, hotspots)
    if args.diagnose:
        import diagnose
        stats = diagnose.diagnose_insights(insights, results["meta"], args.offline, args.refresh)
        results["meta"].update(diagnose.summarize_meta(insights, stats))
        print("diagnosis:", json.dumps(stats))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    print(f"{len(insights)} insights, {len(views)} views, {out.stat().st_size / 1024:.0f} KB -> {out}")
    for i in insights:
        print(f"  {i['rank']}. [{i['severity']}] {i['title']}")


# ----------------------------------------------------------------------------- pieces
def sid_key(j, sid):
    return f"{j}:{sid}"


def step_conf(em: dict) -> dict:
    """Mapping confidence of a step: share of its events that carry no unmapped value or property."""
    out = {}
    for j, steps in UI_STEPS.items():
        for sid, scs, _ in steps:
            tot = sum(em["events_by_screen"].get(sc, 0) for sc in scs)
            bad = sum(em["unmapped_by_screen"].get(sc, 0) for sc in scs)
            out[sid_key(j, sid)] = round(1 - bad / tot, 3) if tot else None
    return out


def ranges_for(member, clean, as_of, t_end, window) -> list:
    out = []
    for rid, delta in RANGES.items():
        start = t_end - delta
        if window:
            if window[1] > start:
                out.append(rid)
        elif sum(1 for s in clean if s["dt"] >= start and member(s)) >= 5:
            out.append(rid)
    return out


def screen_exit_table(clean: list) -> dict:
    out = {}
    mid = min(s["dt"] for s in clean) + (max(s["dt"] for s in clean) - min(s["dt"] for s in clean)) / 2
    screens = {sc for s in clean for sc in s["seen"]}
    for sc in screens:
        at = [s for s in clean if sc in s["seen"]]
        if len(at) < 60:
            continue
        r = sum(s["last"] == sc for s in at) / len(at)
        h1, h2 = [s for s in at if s["dt"] < mid], [s for s in at if s["dt"] >= mid]
        f1 = sum(s["last"] == sc for s in h1) / len(h1) if h1 else 0
        f2 = sum(s["last"] == sc for s in h2) / len(h2) if h2 else 0
        bp = {}
        for p in PERSONAS:
            g = [s for s in at if s["persona"] == p]
            if len(g) >= 20:
                bp[p] = sum(s["last"] == sc for s in g) / len(g)
        out[sc] = {"rate": r, "n": len(at), "first": f1, "second": f2, "stable": abs(f1 - f2) < 0.04 and len(h1) >= 20 and len(h2) >= 20,
                   "by_persona": bp or {"all": r}}
    return out


def healthy_insight(iid, screen, cls, title, facts, kind, severity, n, clean, member, as_of, t_end, assumption, exits, value=0):
    j, step = STEP_OF[screen]
    tone = "warning" if severity == "warning" else "healthy"
    weeks = max(1, (t_end - min(s["dt"] for s in clean)).total_seconds() / 86400) / 7
    return {
        "id": iid, "severity": severity, "severity_source": "watchdog rule (provisional)", "class": None, "diagnosis_status": "pending",
        "title": title, "title_source": "template", "summary": None, "hypothesis": None, "confidence": None, "recommendation": None,
        "guardrail_flags": [], "diagnosis": pending_diagnosis(), "hint_class": cls, "hint_rule": "stable exit rate, no failure signal",
        "screen": screen, "screen_label": humanize(screen), "scope": "temporal", "segment": {}, "segment_text": "All users",
        "compared_with": "first half of the period", "signals": [], "facts": facts, "n_sessions": n,
        "impact": {"severity": 0, "volume_per_week": round(n / weeks), "lost_sessions_per_week": 0, "volume": 0, "value_per_session": value,
                   "score": 0, "per_week_value": 0, "per_week_dollars": 0, "currency": CURRENCY, "assumption": assumption},
        "evidence": {"affected_session_ids": [], "comparison_session_ids": [], "sessions": []},
        "ticket_draft": None, "journey": j, "step": step, "tone": tone, "label": f"{'Warning' if severity == 'warning' else 'Healthy'} · {kind}",
        "persona_ids": [], "ranges": [r for r, d in RANGES.items() if sum(1 for s in clean if s["dt"] >= t_end - d and member(s)) >= 5],
        "detected_hours_ago": 0, "is_new": False, "replays": 0, "causes": [], "affected_sessions": len(exits),
    }


def pattern_insight(p, title, fact_txt, screen, seg, jid, clean, as_of, t_end):
    mem = lambda s: screen in s["seen"] and s["persona"] == p["persona"]
    j, step = STEP_OF[screen]
    return {
        "id": p["id"], "severity": "healthy", "severity_source": "watchdog pattern", "class": None, "diagnosis_status": "pending",
        "title": title, "title_source": "template", "summary": None, "hypothesis": None, "confidence": None, "recommendation": None,
        "guardrail_flags": [], "diagnosis": pending_diagnosis(), "hint_class": p["hint_class"], "hint_rule": p["hint_rule"],
        "screen": screen, "screen_label": humanize(screen), "scope": "segment", "segment": seg, "segment_text": segment_text(seg),
        "compared_with": "all other personas", "signals": [], "facts": [fact_txt], "n_sessions": p["n"],
        "impact": {"severity": 0, "volume_per_week": 0, "lost_sessions_per_week": 0, "volume": 0, "value_per_session": 0, "score": 0,
                   "per_week_value": 0, "per_week_dollars": 0, "currency": CURRENCY,
                   "assumption": "No value assumed: this is expected behavior, not lost customers."},
        "evidence": {"affected_session_ids": [], "comparison_session_ids": [], "sessions": []}, "ticket_draft": None,
        "journey": j, "step": step, "tone": "positive", "label": "Healthy · Expected behavior", "persona_ids": [p["persona"]],
        "ranges": [r for r, d in RANGES.items() if sum(1 for s in clean if s["dt"] >= t_end - d and mem(s)) >= 5],
        "detected_hours_ago": 0, "is_new": False, "replays": 0, "causes": [], "affected_sessions": 0, "pattern": p,
    }


def ui_faults(guardian, em, clean, t_end, ins_by_id) -> list:
    out = []
    held = Counter()
    for f in guardian["faults"]:
        start = parse_ts(f["start"])
        sev = "resolved" if f["status"] == "resolved" else ("critical" if f["severity"] == "high" else "warning")
        link, share = None, 0
        if f["kind"] == "tracker_silent":
            kind, link = "Tracker", {"journey": "register_login", "step": STEP_OF[f["screen"]][1]}
            share = round(f["metric"]["value"], 2)
        elif f["kind"] == "row_loss":
            kind, share = "Database", round(f["metric"]["value"], 3)
        elif f["kind"] == "duplicate_events":
            kind, link = "Tracker", {"journey": STEP_OF[f["screen"]][0], "step": STEP_OF[f["screen"]][1]}
        elif f["kind"] in ("volume_gap", "missing_session_end"):
            kind = "Tracker"
            link = {"journey": STEP_OF[f["screen"]][0], "step": STEP_OF[f["screen"]][1]} if f.get("screen") in STEP_OF else None
        else:
            kind, link = "Schema", {"journey": "register_login", "step": "otp"}
            tot = em["events_by_screen"].get("otp", 0)
            share = round(em["unmapped_by_screen"].get("otp", 0) / tot, 3) if tot else 0
        end = parse_ts(f["end"])
        ui = {"id": f["id"], "sev": sev, "kind": kind, "title": f["title"], "desc": f["detail"], "impact": f["effect"],
              "hours_ago": max(0, round((t_end - start).total_seconds() / 3600)), "quarantine": f["kind"] == "tracker_silent" and f["status"] == "active",
              "link": link, "share": share, "cause": f["title"], "why": f["detail"], "guardian_kind": f["kind"], "start": f["start"], "end": f["end"],
              "status": f["status"]}
        if f["kind"] == "row_loss":
            day = f["start"][:10]
            ex = Counter()
            for s in clean:
                if not s["completed"] and s["dt"].date().isoformat() == day:
                    ex["frustrated" if s["exit_class"] != "natural" else "natural"] += 1
            others = defaultdict(Counter)
            for s in clean:
                if not s["completed"]:
                    others[s["dt"].date().isoformat()]["frustrated" if s["exit_class"] != "natural" else "natural"] += 1
            base = [v["frustrated"] for d, v in others.items() if d != day]
            avg = sum(base) / len(base) if base else 0
            chg = (ex["frustrated"] / avg - 1) if avg else 0
            ui["link"] = None
            ui["metric"] = {"title": f"{parse_ts(f['start']).strftime('%a')} {parse_ts(f['start']).day} exits", "sub": "Frustrated exits, all journeys",
                            "value": f"{chg:+.0%} frustrated exits", "beh": "Within the usual range" if abs(chg) < 0.15 else "Above the usual range",
                            "behType": "behavior",
                            "behWhy": f"{ex['frustrated']} frustrated exits that day against an average of {avg:.0f} on other days.",
                            "rhythmNote": f"{day} is also missing {pct1(f['metric']['value'])} of its rows (a data fault), so the real count may be slightly higher."}
        out.append(ui)
    return out


def completion(group: list):
    j = [s for s in group if s["ui_journey"] == "register_login" and s["journey"] != "browse"]
    return (sum(s["completed"] for s in j) / len(j) * 100, len(j)) if j else (None, 0)


def buckets_of(start, end, n=BUCKETS):
    step = (end - start) / n
    return [(start + step * i, start + step * (i + 1)) for i in range(n)]


def carry(vals):
    last = next((v for v in vals if v is not None), 0.0)
    out = []
    for v in vals:
        last = v if v is not None else last
        out.append(round(last, 2))
    return out


def build_view(rng_id, pe, cur, prev, r_start, r_end, pw, insights, members, guardian, em, wd, all_s):
    v = {"sessions": len(cur)}
    # insights that apply
    ins_ids = [i["id"] for i in insights if rng_id in i["ranges"] and (not i["persona_ids"] or pe == "all" or pe in i["persona_ids"])]
    v["insight_ids"] = ins_ids
    # kpis
    conv, n_c = completion(cur)
    conv_prev = completion(prev)[0]
    series = carry([completion([s for s in cur if a <= s["dt"] < b])[0] if len([s for s in cur if a <= s["dt"] < b]) >= MIN_DAY_N else None for a, b in buckets_of(r_start, r_end)])
    pser = carry([completion([s for s in prev if a <= s["dt"] < b])[0] if len([s for s in prev if a <= s["dt"] < b]) >= MIN_DAY_N else None
                  for a, b in buckets_of(pw[0], pw[1])])
    blind_ids = [i for i in insights if i["id"] in ins_ids and i["scope"] == "segment" and i["severity"] in ("critical", "warning") and i["impact"]["score"] > 0
                 or (i["id"] in ins_ids and i["scope"] == "burst")]
    crit = [i for i in insights if i["id"] in ins_ids and i["severity"] == "critical"]
    var = sum(i["impact"]["per_week_value"] for i in insights if i["id"] in ins_ids and i["severity"] in ("critical", "warning"))
    pids = [i["id"] for i in insights if i["persona_ids"] == [] or pe == "all" or pe in i["persona_ids"]]
    prev_ids = [i for i in insights if i["id"] in pids and in_period(members.get(i["id"], (lambda s: True, None)), prev, pw[0], pw[1])]
    crit_prev = [i for i in prev_ids if i["severity"] == "critical"]
    var_prev = sum(i["impact"]["per_week_value"] for i in prev_ids if i["severity"] in ("critical", "warning"))
    cov_now, cov_prev = cov_between(em, r_start, r_end), cov_between(em, pw[0], pw[1])
    steps_total = sum(len(s) for s in UI_STEPS.values())
    conf = step_conf(em)
    matched = sum(1 for k, c in conf.items() if (c or 0) >= 0.9)
    v["kpis"] = [
        {"id": "conversion", "label": VOCAB["conv_label"], "format": "pct1", "higher_is_better": True,
         "value": round(conv, 1) if conv is not None else 0, "prev": round(conv_prev, 1) if conv_prev is not None else 0,
         "series": series, "prev_series": pser, "prev_label": pw[2], "sub": VOCAB["conv_sub"].format(n=n_c)},
        {"id": "blind_spots", "label": "Critical blind spots", "format": "count", "higher_is_better": False, "value": len(crit), "prev": len(crit_prev),
         "series": [len(crit)] * BUCKETS, "prev_series": [len(crit_prev)] * BUCKETS, "prev_label": pw[2],
         "sub": "Findings are computed over the whole period, so there is no daily series"},
        {"id": "value_at_risk", "label": "Value at risk", "format": "php_week", "higher_is_better": False, "value": var, "prev": var_prev,
         "series": [var] * BUCKETS, "prev_series": [var_prev] * BUCKETS, "prev_label": pw[2], "sub": "Assumed value, not measured"},
        {"id": "mapping_coverage", "label": "Event mapping coverage", "format": "pct1", "higher_is_better": True,
         "value": cov_now, "prev": cov_prev, "series": cov_series(em, r_start, r_end), "prev_series": cov_series(em, pw[0], pw[1]), "prev_label": pw[2],
         "sub": f"{matched} of {steps_total} steps matched, {steps_total - matched} to review"},
    ]
    # journeys, signals, loops
    jv, sig, loops = [], {}, {}
    exits = Counter()
    for j, steps in UI_STEPS.items():
        js = [s for s in cur if s["ui_journey"] == j]
        if not js:
            continue
        rows, sg = [], {}
        ex_all = [s for s in js if not s["completed"]]
        for sid, scs, _ in steps:
            at = [s for s in js if any(sc in s["seen"] for sc in scs)]
            if not at:
                continue
            ex = [s for s in at if s["last"] in scs and not s["completed"]]
            cls = Counter(s["exit_class"] for s in ex)
            ex_cls = cls.most_common(1)[0][0] if cls else "natural"
            rate = len(ex) / len(at)
            crit_here = any(i["tone"] == "critical" and i["journey"] == j and i["step"] == sid and i["id"] in ins_ids for i in insights)
            warn_here = any(i["tone"] == "warning" and i["journey"] == j and i["step"] == sid and i["id"] in ins_ids for i in insights)
            tone = "critical" if crit_here or rate >= 0.40 else "warning" if warn_here or rate >= 0.15 else "healthy"
            low = len(at) < MIN_STEP_N       # too few sessions in this view to call a rate: shown, but never colored or tagged as a finding
            if low:
                tone = "healthy"
            rows.append({"id": sid, "sessions": len(at), "exits": len(ex), "exit_class": ex_cls, "tone": tone,
                         "tag": "Few sessions" if low else f"{rate * 100:.0f}% exit" if rate >= 0.10 else "Steady", "low_sample": low})
            n = len(at)
            sg[sid] = [round(sum(any(s["stats"].get(sc, {}).get(k, 0) for sc in scs) for s in at) / n * 100, 1)
                       for k in ("rage", "back", "dead")] + [round(sum(any(s["stats"].get(sc, {}).get("stuck") for sc in scs) for s in at) / n * 100, 1)]
        jv.append({"id": j, "steps": rows})
        sig[j] = sg
        lc = Counter()
        for s in js:
            for a, b in s["back_moves"]:
                if a in STEP_OF and b in STEP_OF and STEP_OF[a][0] == j and STEP_OF[b][0] == j and STEP_OF[a][1] != STEP_OF[b][1]:
                    lc[(STEP_OF[a][1], STEP_OF[b][1])] += 1
        first = UI_STEPS[j][0][0]
        loops[j] = [{"from": a, "to": b, "count": n, "kind": "pos" if b == first else "neg"} for (a, b), n in lc.most_common(6)]
        for s in ex_all:
            exits[s["exit_class"]] += 1
    v["journeys"], v["signals"], v["loops"] = jv, sig, {k: x for k, x in loops.items() if x}
    v["blind"] = blind_for(cur, [i for i in insights if i["id"] in ins_ids])
    v["exits"] = {k: exits.get(k, 0) for k in ("ux", "language", "technical", "natural")}
    v["rhythm"] = rhythm_for(cur, r_start, r_end, rng_id, guardian, wd, all_s, exits)
    v["cohorts"] = cohorts_for(cur, prev, all_s)
    held = sum(1 for s in all_s if s["quarantined"] and r_start <= s["dt"] < r_end and (pe == "all" or s["persona"] == pe))
    v["health"] = health_for(guardian, em, held, r_start, r_end)
    return v


def in_period(member, group, a, b) -> bool:
    mem, window = member
    if window:
        return window[1] > a and window[0] < b
    return sum(1 for s in group if mem(s)) >= 5


def cov_between(em, a, b):
    days = [d for d in em["daily_events"] if a.date() <= datetime.fromisoformat(d).date() <= (b - timedelta(seconds=1)).date()]
    tot = sum(em["daily_events"][d] for d in days)
    return round((1 - sum(em["daily_unmapped"].get(d, 0) for d in days) / tot) * 100, 1) if tot else 100.0


def cov_series(em, a, b):
    return [cov_between(em, x, y) for x, y in buckets_of(a, b)]


def blind_for(cur, ins):
    cand = [i for i in ins if i["scope"] == "segment" and i["severity"] in ("critical", "warning") and i["impact"]["score"] > 0]
    if not cand:
        return None
    i = max(cand, key=lambda x: x["impact"]["per_week_value"])
    sc, seg = i["screen"], i["segment"]
    at = [s for s in cur if sc in s["seen"]]
    if len(at) < MIN_ROW_N:
        return None
    base = sum(s["last"] == sc for s in at) / len(at)
    bars = []
    prod = seg.get("product")
    for p in sorted({s["persona"] for s in at}):
        g = [s for s in at if s["persona"] == p and (prod is None or s["product"] == prod)]
        if len(g) >= 10:
            r = sum(s["last"] == sc for s in g) / len(g)
            bars.append({"l1": PERSONA_LABELS.get(p, p), "l2": PRODUCT_LABELS.get(prod, "All products") if prod else "All products",
                         "value": round(r * 100), "hot": matches({"persona": p}, {k: v for k, v in seg.items() if k == "persona"}) and "persona" in seg and seg["persona"] == p, "_n": len(g)})
    if "persona" in seg and prod:
        for q in PRODUCTS:
            if q == prod:
                continue
            g = [s for s in at if s["persona"] == seg["persona"] and s["product"] == q]
            if len(g) >= 10:
                bars.append({"l1": PERSONA_LABELS.get(seg["persona"]), "l2": PRODUCT_LABELS[q], "value": round(sum(s["last"] == sc for s in g) / len(g) * 100), "hot": False, "_n": len(g)})
    if not bars:
        return None
    hot = [b for b in bars if b["hot"]]
    worst = max(b["value"] for b in bars)
    for b in bars:
        b["hot"] = b["value"] >= 0.8 * worst and b["value"] >= 2 * base * 100 / 2 if not hot else b["hot"]
        b.pop("_n", None)
    ratio = (worst / 100) / base if base else None
    return {"journey": i["journey"], "step": i["step"], "title": f"Blind spot: {humanize(sc)}",
            "sub": f"Exit rate at {humanize(sc)}, by persona" + (f" for {PRODUCT_LABELS[prod]}" if prod else "") + ", against the overall rate",
            "baseline": round(base * 100, 1), "baseline_label": f"Overall rate {base * 100:.1f}% hides the segment",
            "badge": f"{ratio:.1f}x the overall rate" if ratio else "", "bars": bars}


def rhythm_for(cur, r_start, r_end, rng_id, guardian, wd, all_s, exits):
    bs = buckets_of(r_start, r_end, 7)
    nat, fru, labels = [], [], []
    for a, b in bs:
        ex = [s for s in cur if a <= s["dt"] < b and not s["completed"]]
        nat.append(sum(s["exit_class"] == "natural" for s in ex))
        fru.append(sum(s["exit_class"] != "natural" for s in ex))
        labels.append(a.strftime("%H:00") if rng_id == "24h" else label_day(a + timedelta(minutes=30)))   # a day bucket starts minutes before midnight: name the day it covers
    markers = []
    for c in wd["candidates"]:
        if c["scope"] == "burst":
            ws = parse_ts(c["window"]["start"])
            for i, (a, b) in enumerate(bs):
                if a <= ws < b:
                    markers.append({"index": i, "label": f"{humanize(c['screen'])}: exits jump"})
    for f in guardian["faults"]:
        if f["kind"] in ("tracker_silent", "row_loss", "unmapped") and f["status"] == "active":
            st = parse_ts(f["start"])
            for i, (a, b) in enumerate(bs):
                if a <= st < b:
                    markers.append({"index": i, "label": f["title"][:48]})
    ver_first = {}
    for s in all_s:
        v = s["app_version"]
        if v and (v not in ver_first or s["dt"] < ver_first[v]):
            ver_first[v] = s["dt"]
    base_day = min(ver_first.values())
    for v, d in ver_first.items():
        if d - base_day > timedelta(days=2):
            for i, (a, b) in enumerate(bs):
                if a <= d < b:
                    markers.append({"index": i, "label": f"App {v} rollout"})
    tot_f, tot_n = sum(fru), sum(nat)
    if len(fru) >= 2 and sum(fru) > 0:
        peak = max(range(len(fru)), key=lambda i: fru[i])
        near = [m["label"] for m in markers if m["index"] == peak]
        note = (f"{tot_f} frustrated exits and {tot_n} natural exits in this range ({pct(tot_f / (tot_f + tot_n))} frustrated); the busiest stretch starts {labels[peak]}"
                + (f" and lines up with: {near[0]}." if near else "."))
    else:
        note = "Too few exits in this range to describe a rhythm."
    return {"labels": labels, "natural": nat, "frustrated": fru, "markers": markers, "note": note}


COHORTS = PROFILE.get("COHORTS", [("shared", "Shared-device bursts", "crit"), ("otp", "Stalled at the OTP code", "warn"),
                                  ("big", "High-value top-uppers", "accent"), ("load", "Load-first store owners", "accent"),
                                  ("price", "Price-checkers, register later", "info"), ("straight", "Straight-through completers", "accent"),
                                  ("other", "Other", "muted")])
COHORT_NAME = {k: n for k, n, _ in COHORTS}


def assign_cohort(uid, ss, shared_users):
    ss = sorted(ss, key=lambda s: s["dt"])
    dev_shared = max((shared_users.get(s["device"], 1) for s in ss), default=1) >= 3
    close = sum(1 for a, b in zip(ss, ss[1:]) if (b["dt"] - a["dt"]) < timedelta(minutes=15))
    if dev_shared and close >= 2:
        return "shared"
    if sum(1 for s in ss if s["last"] == "otp" and not s["completed"]) >= 1 and sum(s["n_rage"] > 0 for s in ss if "otp" in s["seen"]) >= 1:
        return "otp"
    tops = [s["amount"] for s in ss if s["journey"] == "topup" and s["amount"]]
    if tops and median(tops) >= 50_000:
        return "big"
    tx = [s["product"] for s in ss if s["journey"] == "transaction" and s["product"]]
    if len(tx) >= 3 and tx.count("eload") / len(tx) >= 0.6:
        return "load"
    if sum(s["journey"] == "browse" for s in ss) >= 2:
        return "price"
    real = [s for s in ss if s["journey"] != "browse"]
    if real and sum(s["completed"] for s in real) / len(real) >= 0.9:
        return "straight"
    return "other"


def cohort_shares(group, shared_users):
    by_u = defaultdict(list)
    for s in group:
        by_u[s["user"]].append(s)
    cnt = Counter(assign_cohort(u, ss, shared_users) for u, ss in by_u.items())
    return cnt, len(by_u)


def largest_remainder(counts: dict, total: int) -> dict:
    if not total:
        return {k: 0 for k in counts}
    raw = {k: v * 100 / total for k, v in counts.items()}
    fl = {k: int(x) for k, x in raw.items()}
    left = 100 - sum(fl.values())
    for k in sorted(raw, key=lambda k: raw[k] - fl[k], reverse=True)[:left]:
        fl[k] += 1
    return fl


_shared_cache: dict = {}


def cohorts_for(cur, prev, all_s):
    if "u" not in _shared_cache:
        d = defaultdict(set)
        for s in all_s:
            d[s["device"]].add(s["user"])
        _shared_cache["u"] = {k: len(v) for k, v in d.items()}
    sh = _shared_cache["u"]
    cnt, n = cohort_shares(cur, sh)
    pcnt, pn = cohort_shares(prev, sh) if prev else (Counter(), 0)
    shares = largest_remainder({k: cnt.get(k, 0) for k, _, _ in COHORTS}, n)
    items = []
    for k, name, tone in COHORTS:
        if not cnt.get(k):
            continue
        new = bool(pn) and (shares[k] - pcnt.get(k, 0) * 100 / pn) >= 2 and k not in ("straight", "other")
        items.append({"name": name, "share": shares[k], "tone": tone, "is_new": new})
    top = max((i for i in items if i["name"] not in (COHORT_NAME["other"],)), key=lambda i: i["share"], default=None)
    sm = next((i for i in items if i["name"] == COHORT_NAME["shared"]), None)
    note = (f"{n} users active in this range, grouped by simple behavior rules. "
            + (f"Largest group: {top['name']} ({top['share']}%). " if top else "")
            + (f"Shared-device bursts: {sm['share']}% of users, accounts on a device used by 3 or more users with repeated attempts within 15 minutes." if sm else ""))
    return {"items": items, "note": note.strip()}


def health_for(guardian, em, held, r_start, r_end):
    delta = r_end - r_start
    days = em["daily_events"]
    def ev_between(a, b):
        return sum(c for d, c in days.items() if a.date() <= datetime.fromisoformat(d).date() < b.date())
    now_ev, prev_ev = ev_between(r_start, r_end) if delta >= timedelta(days=1) else None, ev_between(r_start - delta, r_start) if delta >= timedelta(days=1) and r_start - delta >= datetime(2000, 1, 1, tzinfo=UTC) else None
    if now_ev is not None and prev_ev:
        chg = now_ev / prev_ev - 1
        vol = {"label": "Event volume", "value": f"{chg:+.1%}", "sub": f"vs. the {delta.days} days before", "status": "ok" if abs(chg) < 0.15 else "warning"}
    else:
        vol = {"label": "Event volume", "value": f"{now_ev if now_ev is not None else 0:,}", "sub": "events in this range, no earlier range to compare", "status": "ok"}
    unm = sum(em["unmapped_by_screen"].values())
    mapped = 1 - unm / em["events"]
    silent = [f for f in guardian["faults"] if f["kind"] == "tracker_silent" and f["status"] == "active"]
    screens = len(em["events_by_screen"])
    return {"tiles": [vol,
                      {"label": "Schema match", "value": f"{mapped * 100:.1f}%", "sub": "of events fully mapped", "status": "ok" if mapped > 0.99 else "warning"},
                      {"label": "Trackers firing", "value": f"{screens - len(silent)} of {screens}",
                       "sub": (f"{len(silent)} silent ({silent[0]['title']})" if silent else "all screens logging"), "status": "critical" if silent else "ok"},
                      {"label": "Sessions held out", "value": f"{held}", "sub": "inside a telemetry fault window", "status": "warning" if held else "ok"}]}


def product_funnels(clean):
    out = {}
    # The Fraudster group is not featured in this demo (the UI hides it everywhere), so its checkout declines must not drive every product's funnel.
    tx = [s for s in clean if s["journey"] == "transaction" and s["persona"] != "fraudster"]
    steps = UI_STEPS["transaction"]
    for p in PRODUCTS:
        g = [s for s in tx if s["product"] == p]
        if not g:
            continue
        rows = []
        for sid, scs, name in steps:
            at = [s for s in g if any(sc in s["seen"] for sc in scs)]
            ex = [s for s in at if s["last"] in scs and not s["completed"]]
            top_cls = Counter(s["exit_class"] for s in ex).most_common(1)
            rows.append({"id": sid, "name": name, "sessions": len(at), "exits": len(ex), "exit_rate": round(len(ex) / len(at), 4) if at else None,
                         "exit_class": top_cls[0][0] if top_cls else None})   # additive: the usual reason people leave at this step
        out[p] = {"label": PRODUCT_LABELS[p], "sessions": len(g), "steps": rows,
                  "completion": round(sum(s["completed"] for s in g) / len(g), 4)}
    return out


def legacy_blocks(clean, now_start, now_days):
    """The v1 shape: journeys[<platform>|<persona>] route maps and the overview views, kept for older readers."""
    t0 = min(s["dt"] for s in clean)
    pos = {}
    lane_of = {"browse": 0, "register": 1, "login": 2, "topup": 3, "transaction": 4}
    for jn, path in JOURNEYS.items():
        for i, sc in enumerate(path):
            pos.setdefault(sc, {"col": i, "lane": lane_of[jn]})
    personas = sorted({s["persona"] for s in clean})
    journeys = {}
    for pf in ["all", "app"]:
        for pe in ["all"] + personas:
            sub = [s for s in clean if s["dt"] >= now_start and (pe == "all" or s["persona"] == pe)]
            views, exits, dwell, edges = Counter(), Counter(), defaultdict(list), Counter()
            for s in sub:
                prev = None
                for sc in s["seen"]:
                    views[sc] += 1
                    if s["stats"][sc]["dwell"]:
                        dwell[sc].append(s["stats"][sc]["dwell"])
                seq = [x for i, x in enumerate(s["views"]) if i == 0 or x != s["views"][i - 1]]
                for a, b in zip(seq, seq[1:]):
                    edges[(a, b)] += 1
                if s["last"]:
                    exits[s["last"]] += 1
            nodes = [{"id": sc, "label": humanize(sc), "sessions": views[sc], "exits": exits[sc],
                      "exit_rate": round(exits[sc] / views[sc], 4) if views[sc] else 0,
                      "median_dwell_ms": int(median(dwell[sc])) if dwell[sc] else None, **pos[sc]} for sc in sorted(views, key=lambda x: (pos[x]["lane"], pos[x]["col"]))]
            journeys[f"{pf}|{pe}"] = {"sessions": len(sub), "nodes": nodes, "edges": [{"from": a, "to": b, "sessions": n} for (a, b), n in sorted(edges.items())]}
    days = sorted({s["dt"].date() for s in clean})
    ov = {}
    for pe in ["all"] + personas:
        sub = [s for s in clean if pe == "all" or s["persona"] == pe]
        now = [s for s in sub if s["dt"] >= now_start]
        before = [s for s in sub if s["dt"] < now_start]

        def conv(g):
            st = [s for s in g if s["journey"] != "browse"]
            return len(st), sum(s["completed"] for s in st)

        a, b = conv(now)
        c, d = conv(before)
        ss, cs = [], []
        for dd in days:
            day = [s for s in sub if s["dt"].date() == dd]
            n, done = conv(day)
            ss.append({"d": dd.isoformat(), "n": len(day)})
            cs.append({"d": dd.isoformat(), "n": n, "rate": round(done / n, 4) if n >= MIN_DAY_N else None})
        ov_rows = []
        for per in sorted({s["persona"] for s in now}):
            for dc in sorted({s["device_class"] for s in now if s["device_class"]}):
                g = [s for s in now if s["persona"] == per and s["device_class"] == dc]
                n, done = conv(g)
                if n >= MIN_ROW_N:
                    ov_rows.append({"persona": per, "device_class": dc, "label": f"{PERSONA_LABELS.get(per, per)} · {DEVICE_CLASS_LABELS.get(dc, dc)}",
                                    "started": n, "rate": round(done / n, 4), "vs_overall": round(done / n - (b / a if a else 0), 4), "finding_id": None})
        ov[f"all|{pe}"] = {"sessions": {"now": len(now), "per_day_now": round(len(now) / now_days, 1),
                                        "per_day_before": round(len(before) / max(1, (now_start.date() - days[0]).days), 1), "change": None, "series": ss},
                           "conversion": {"now": round(b / a, 4) if a else None, "before": round(d / c, 4) if c else None, "n_now": a, "n_before": c, "series": cs},
                           "table": ov_rows}
    funnel = {"start": "journey_start", "end": "journey_success", "start_label": VOCAB["funnel_start"],
              "end_label": VOCAB["funnel_end"]}
    return {"journeys": journeys, "overview": {"funnel": funnel, "now_days": now_days, "views": ov}, "funnel": funnel}


def stuck_sessions(insights, keep, by_sid):
    out = []
    picks = []
    for i in insights:
        ids = i["evidence"]["affected_session_ids"] + i["evidence"]["comparison_session_ids"][:1] * (1 if i["severity"] == "critical" else 0)
        for sid in ids[:2]:
            if sid in keep and sid not in [p[0] for p in picks]:
                picks.append((sid, i))
    for sid, i in picks[:10]:
        s = by_sid[sid]
        evs = sorted(keep[sid], key=lambda e: e["ts"])
        t0 = parse_ts(evs[0]["ts"])
        sec = lambda e: round((parse_ts(e["ts"]) - t0).total_seconds(), 1)
        if sec(evs[-1]) > 120:
            continue
        bands, marks, cur = [], [], None
        for e in evs:
            if e["event_type"] == "screen_view":
                if cur:
                    bands.append([cur[0], sec(e), humanize(cur[1])])
                cur = (sec(e), e["screen"])
        if cur:
            bands.append([cur[0], sec(evs[-1]), humanize(cur[1])])
        prev_t, rage_start = None, None
        for e in evs:
            t = sec(e)
            if e["event_type"] in ("click", "dead_tap"):
                marks.append(["tap", t])
            elif e["event_type"] == "rage_click":
                if marks and marks[-1][0] == "rage" and t - marks[-1][2] <= 1.5:
                    marks[-1][2] = t
                else:
                    marks.append(["rage", t, t])
            elif e["event_type"] == "back":
                marks.append(["back", t])
            if prev_t is not None and t - prev_t >= 10 and e["event_type"] != "screen_leave":
                marks.append(["idle", prev_t, t])
            prev_t = t
        for m in marks:
            if m[0] == "rage" and m[2] == m[1]:
                m[2] = round(m[1] + 1, 1)
        done = s["completed"]
        marks.append(["done" if done else "exit", sec(evs[-1])])
        os_ = "iOS" if s["os"] == "ios" else "Android"
        out.append({"id": f"x{len(out) + 1}", "persona": s["persona"], "journey": s["ui_journey"],
                    "who": f"{PERSONA_LABELS.get(s['persona'], s['persona'])}, {os_}" + (f", {PRODUCT_LABELS[s['product']]}" if s["product"] else ""),
                    "outcome": (f"Completed in {sec(evs[-1]):.0f} s" if done else f"Exited after {sec(evs[-1]):.0f} s"),
                    "good": done, "bands": bands, "marks": marks, "insight_id": i["id"]})
    return out


def hotspot_cards(taps) -> list:
    """Densest rage-tap clusters per screen, from tap_x / tap_y. One card per screen with at least MIN_SPOT taps."""
    by_screen = defaultdict(list)
    for (sc, et), pts in taps.items():
        if et == "rage_click":
            by_screen[sc] += pts
    cards = []
    for sc, pts in sorted(by_screen.items(), key=lambda kv: -len(kv[1])):
        if len(pts) < 30 or sc not in WIREFRAMES:
            continue
        cells = defaultdict(list)
        for x, y, el in pts:
            cells[(int(x * 10), int(y * 10))].append((x, y, el))
        cen = lambda g: (sum(p[0] for p in g) / len(g), sum(p[1] for p in g) / len(g))
        merged: list = []                # neighbouring cells whose centres are under HOT_RADIUS apart are one spot
        for g in sorted(cells.values(), key=len, reverse=True):
            for m in merged:
                (ax, ay), (bx, by) = cen(m), cen(g)
                if ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 < HOT_RADIUS:
                    m += g
                    break
            else:
                merged.append(list(g))
        top = sorted(merged, key=len, reverse=True)[:3]
        mx = len(top[0])
        spots = []
        for g in top:
            if len(g) < 0.1 * mx:
                continue
            el = Counter(e for _, _, e in g).most_common(1)[0][0]
            spots.append([round(sum(p[1] for p in g) / len(g) * 100, 1), round(sum(p[0] for p in g) / len(g) * 100, 1),
                          round(34 + 40 * len(g) / mx), len(g), ELEMENT_LABELS.get(el, f"Element {el}")])
        j, step = STEP_OF[sc]
        cards.append({"screen": humanize(sc), "journey": j, "step": step,
                      "note": f"{len(pts)} rage taps on this screen; the densest cluster has {mx} of them ({mx / len(pts):.0%}).",
                      "elements": WIREFRAMES[sc], "spots": spots})
    return cards


def intent_rows(clean, em):
    rows = []
    def pick(pred):
        return next((s for s in clean if pred(s)), None)
    s = pick(lambda s: s["last"] == "otp" and s["stats"].get("otp", {}).get("rage", 0) >= 3)
    if s:
        rows.append({"raw": VOCAB["intent_otp_raw"].format(dwell=s["stats"]["otp"]["dwell"], rage=s["stats"]["otp"]["rage"]),
                     "intent": "Waiting for a code that has not arrived", "meta": "App, sample, rule-based label", "flagged": False})
    s = pick(lambda s: s["journey"] == "browse" and s["persona"] == "unregistered")
    if s:
        rows.append({"raw": VOCAB["intent_browse_raw"], "intent": VOCAB["intent_browse"],
                     "meta": "App, sample, rule-based label", "flagged": False})
    s = pick(lambda s: s["last"] == "txn_checkout" and s["product"] == "send_money" and s["persona"] == "individual_trader")
    if s:
        rows.append({"raw": VOCAB["intent_pay_raw"], "intent": "Trying to confirm a payment that does not go through",
                     "meta": "App, sample, rule-based label", "flagged": False})
    s = pick(lambda s: s["persona"] == "fraudster" and not s["completed"])
    if s:
        rows.append({"raw": VOCAB["intent_risk_raw"].format(last=s["last"]), "intent": "Repeated failed attempt, needs review",
                     "meta": "App, sample, rule-based label", "flagged": True})
    rows.append({"raw": VOCAB["intent_unmapped_raw"], "intent": "Flagged for review: property not in the mapping", "meta": "App, sample", "flagged": True})
    return rows


def agents_rows(guardian, wd, insights, all_s, clean):
    prob = [i for i in insights if i["severity"] in ("critical", "warning") and i["impact"]["score"] > 0]
    return [
        {"tier": "0", "name": "Telemetry Guardian", "sub": f"{sum(1 for f in guardian['faults'] if f['status'] == 'active')} active faults, {len(all_s) - len(clean)} sessions held out",
         "status": "warn" if guardian["status"] == "fail" else "ok"},
        {"tier": "1", "name": "The Watchdog", "sub": f"{len(wd['candidates'])} deviations found, {len(wd['patterns'])} behavior patterns and {len(wd['high_exit_screens'])} natural exit kept out of the feed",
         "status": "warn" if wd["candidates"] else "ok"},
        {"tier": "2", "name": "Diagnostic Agent", "sub": f"Not run yet: {len(prob)} findings wait for a diagnosis", "status": "warn"},
    ]


def ask_rows(res, clean, wd, guardian, users_by_device, persona_users, hotspots):
    out = []

    def add(q, a, refs, kw, chip=False):
        out.append({"id": f"a{len(out) + 1}", "question": q, "answer": a, "refs": refs, "keywords": kw, "chip": chip})

    def ref(i, label=None):
        return {"type": "insight", "id": i["id"], "label": label or i["title"]}

    burst = next((i for i in res["insights"] if i["scope"] == "burst"), None)
    if burst:
        d = burst["signals"][0]
        rage = next((x for x in burst["signals"] if x["metric"] == "rage"), None)
        w = burst["window"]
        ws, we = parse_ts(w["start"]), parse_ts(w["end"])
        add(VOCAB["ask_burst_q"].format(day=label_day(ws)),
            VOCAB["ask_burst_a"].format(start=ws.strftime("%H:%M"), end=we.strftime("%H:%M"), day=label_day(ws), rate=pct(d["value"]),
                                        screen=burst["screen_label"], ref=pct(d["reference"]), n=d["n"],
                                        rage=(pct(rage["value"]) + " of them showed rage taps. ") if rage else ""),
            [ref(burst)], VOCAB["ask_burst_kw"], True)
    p4 = next((i for i in res["insights"] if i["scope"] == "segment" and i["segment"].get("product") == "send_money"), None)
    if p4:
        d = next(x for x in p4["signals"] if x["metric"] == "drop_off")
        add(VOCAB["ask_p4_q"],
            VOCAB["ask_p4_a"].format(seg=p4["segment_text"], rate=pct(d["value"]), n=d["n"], ref=pct(d["reference"])),
            [ref(p4)], VOCAB["ask_p4_kw"], True)
    for i in res["insights"]:
        if i.get("pattern") and i["pattern"]["kind"] == "topup_amount":
            p = i["pattern"]
            add(VOCAB["ask_amount_q"], VOCAB["ask_amount_a"].format(who=PERSONA_LABELS[p["persona"]], share=pct(p["value"]), cur=CURRENCY, thr=p["threshold_php"],
                                                                   med=p["median_php"], refmed=p["reference_median_php"]),
                [ref(i)], VOCAB["ask_amount_kw"], True)
        if i.get("pattern") and i["pattern"]["kind"] == "product_preference":
            p = i["pattern"]
            add(VOCAB["ask_prod_q"], VOCAB["ask_prod_a"].format(share=pct(p["value"]), who=PERSONA_LABELS[p["persona"]], prod=PRODUCT_LABELS[p["product"]], ref=pct(p["reference"])),
                [ref(i)], VOCAB["ask_prod_kw"])
    fr = next((i for i in res["insights"] if i["segment"] == {"persona": "fraudster"}), None)
    if fr:
        shared = sum(1 for k, v in users_by_device.items() if len(v) >= 3)
        add(VOCAB["ask_risk_q"], VOCAB["ask_risk_a"].format(fact=" ".join(fr["facts"][:1]), shared=shared),
            [ref(fr)], VOCAB["ask_risk_kw"])
    he = next((i for i in res["insights"] if i["id"].startswith("exit:")), None)
    if he:
        add(VOCAB["ask_natural_q"], VOCAB["ask_natural_a"].format(fact=he["facts"][0]),
            [ref(he)], VOCAB["ask_natural_kw"])
    ctrl = [i for i in res["insights"] if i["id"].endswith(":control")]
    if ctrl:
        add(VOCAB["ask_control_q"], " ".join(f"{i['screen_label']}: {i['facts'][0]}" for i in ctrl[:2]), [ref(i) for i in ctrl[:2]],
            VOCAB["ask_control_kw"])
    act = [f for f in res["guardian"]["faults"] if f["sev"] != "resolved"]
    add("Can I trust this data?", f"The Guardian found {len(act)} active faults and {len([f for f in res['guardian']['faults'] if f['sev'] == 'resolved'])} resolved: " + "; ".join(f["title"] for f in res["guardian"]["faults"]) +
        f". {res['meta']['counts']['sessions_quarantined']} sessions are held out of the analysis.", [{"type": "view", "id": "health", "label": "Data health"}],
        ["data", "trust", "health", "fault", "tracker", "missing", "quality", "guardian", "duplicate", "unmapped"])
    add("How big is the dataset?", f"{res['meta']['counts']['events']:,} events, {res['meta']['counts']['sessions']:,} sessions and {res['meta']['counts']['users']:,} users between {res['meta']['window']['start']} and {res['meta']['window']['end']}. " + ("All of it is synthetic." if res["meta"]["synthetic"] else ""),
        [{"type": "view", "id": "30d|all|all", "label": "30 days, all personas"}], ["how", "many", "users", "sessions", "events", "size", "dataset", "synthetic"])
    if hotspots:
        h = hotspots[0]
        add("Where do people rage-tap?", f"{h['screen']}: {h['note']} Densest spot: {h['spots'][0][4]}.", [{"type": "view", "id": "hotspot", "label": h["screen"]}],
            ["rage", "tap", "taps", "hotspot", "click", "frustrated", "button"])

    # These prepared answers are deterministic summaries of the clean 7-day session cohort.
    we = parse_ts(wd["window"]["now_end"])
    ws = we - timedelta(days=7)
    active = [s for s in clean if s["persona"] not in {"unknown", "fraudster"} and ws <= parse_ts(s["start"]) <= we]
    earlier_screens = {"prices", "product_list", "topup_amount", "txn_details", "register_phone", "login_phone"}

    def branch_for(s, otp=False):
        stats = s["stats"]
        has_fault = any(v["errors"] or v["dead"] or v["rage"] for v in stats.values())
        if otp:
            has_fault = has_fault or stats.get("otp", {}).get("resend", 0) > 0
        if has_fault:
            return ("error_loop", "Error loop", "negative", "negative friction",
                    "An error, dead tap, rage tap, or OTP resend tap occurred before the session ended.")
        later_moves = s.get("back_moves_after_otp" if otp else "back_moves_after_payment", [])
        returns = [b for _, b in later_moves if b in earlier_screens]
        start_screens = {"otp"} if otp else {"txn_checkout", "topup_confirm"}
        start_idx = min((i for i, screen in enumerate(s["views"]) if screen in start_screens), default=-1)
        returns += [screen for screen in s["views"][start_idx + 1:] if screen in earlier_screens]
        if s.get("back_after_otp" if otp else "back_after_payment") or returns:
            comparing = not otp and any(x in {"prices", "product_list"} for x in returns)
            return ("looped_back", "Looped back", "positive" if comparing else "negative",
                    "comparing · positive" if comparing else "negative friction",
                    "The session returned to an earlier screen before it ended.")
        return ("left_quietly", "Left quietly", "neutral", "natural exit",
                "No error, dead tap, rage tap, resend tap, or return to an earlier screen was observed.")

    def add_sankey(q, cohort, title, persona, keywords, otp=False):
        grouped = Counter()
        loop_calls = Counter()
        ids = defaultdict(list)
        for session in cohort:
            branch = branch_for(session, otp)
            key = branch[0]
            grouped[key] += 1
            if key == "looped_back":
                loop_calls[branch[3]] += 1
            ids[key].append(session["sid"])
        n = len(cohort)
        active_n = len(active)
        pct_active = n / active_n if active_n else 0
        answer = (f"{n:,} of {active_n:,} eligible active sessions in the 7-day window ({pct(pct_active)}) "
                  f"{title.lower()}; {grouped['error_loop']:,} showed an error loop, {grouped['looped_back']:,} looped back, and {grouped['left_quietly']:,} left quietly.")
        refs = []
        row = {"id": f"a{len(out) + 1}", "question": q, "answer": answer, "refs": refs,
               "keywords": keywords, "chip": True}
        if n >= 20:
            branch_defs = {
                "error_loop": ("Error loop", "negative", "negative friction"),
                "looped_back": ("Looped back", "positive" if loop_calls["comparing · positive"] > loop_calls["negative friction"] else "negative",
                                "comparing · positive" if loop_calls["comparing · positive"] > loop_calls["negative friction"] else "negative friction"),
                "left_quietly": ("Left quietly", "neutral", "natural exit"),
            }
            branch_rows = []
            for key in ("error_loop", "looped_back", "left_quietly"):
                if not grouped[key]:
                    continue
                label, tone, call = branch_defs[key]
                exemplar = next(s for s in cohort if branch_for(s, otp)[0] == key)
                branch_rows.append({"id": key, "label": label, "value": grouped[key], "tone": tone, "call": call,
                                    "note": branch_for(exemplar, otp)[4]})
            # Keep unsupported branches out of the visual and state why in the subtitle.
            omitted = [branch_defs[k][0] for k in branch_defs if not grouped[k]]
            subtitle = (f"Synthetic sample data. Measured from {n:,} sessions; share of eligible active sessions in the 7-day window (n={active_n:,})." +
                        (f" No observed sessions supported: {', '.join(omitted)}." if omitted else ""))
            if grouped["error_loop"]:
                hypothesis = "Hypothesis: error loops may contribute to these exits; verify the observed events and provider path before changing the flow."
            elif grouped["looped_back"]:
                hypothesis = "Hypothesis: returning to an earlier screen may contribute to these exits; review the observed paths before changing the flow."
            else:
                hypothesis = "Hypothesis: these exits may be intentional; check the user goal before treating them as friction."
            row["viz"] = {
                "type": "sankey", "title": title, "subtitle": subtitle, "unit": "sessions",
                "source": {"id": "abandoned", "label": title, "value": n, "share_of_active": pct_active,
                           "sub": f"{pct(pct_active)} of {active_n:,} active sessions"},
                "branches": branch_rows,
                "ticket": {"insight_id": refs[0]["id"] if refs and refs[0].get("type") == "insight" else None,
                           "title": f"Review {title.lower()}", "persona": persona,
                           "hypothesis": hypothesis,
                           "evidence_json": {"cohort_sessions": n, "active_sessions_7d": active_n,
                                             "branch_counts": {b["id"]: b["value"] for b in branch_rows},
                                             "session_ids": {key: ids[key][:3] for key in ("error_loop", "looped_back", "left_quietly") if ids[key]}}}
            }
        else:
            row["answer"] = f"Only {n:,} sessions met this definition in the 7-day window; at least 20 are needed for a Sankey summary."
        out.append(row)

    pay = [s for s in active if ("txn_checkout" in s["seen"] or "topup_confirm" in s["seen"])
           and not ({"txn_done", "topup_done"} & s["seen"])]
    for old in out:
        old["chip"] = False
    add_sankey(VOCAB["sk_pay_q"], pay, VOCAB["sk_pay_title"], "Eligible users", VOCAB["sk_pay_kw"])
    otp_exits = [s for s in active if s["last"] == "otp" and "otp" in s["seen"]]
    add_sankey(VOCAB["sk_otp_q"], otp_exits, VOCAB["sk_otp_title"], "Eligible users", VOCAB["sk_otp_kw"], otp=True)
    retail_txn = [s for s in pay if s["persona"] == "sari_sari" and "txn_checkout" in s["seen"]]
    add_sankey(VOCAB["sk_group_q"], retail_txn, VOCAB["sk_group_title"], VOCAB["sk_group_persona"], VOCAB["sk_group_kw"])
    return out


if __name__ == "__main__":
    main()
