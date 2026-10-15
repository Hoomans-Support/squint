#!/usr/bin/env python3
"""Synthetic event generator for Squint.

ALL DATA PRODUCED HERE IS SYNTHETIC. Label it as such in the UI, the deck and the video.

Emits raw, source-shaped events (web and app use different field names on purpose, so the
normalization step is real) plus a ground-truth file listing what the pipeline should and
should not find.

Planted patterns (see ground_truth.json for measured values):
  S1  KYC language confusion   kyc_identity dwell x3 + repeated kyc_tooltip focus + silent exits,
                               starting 2026-09-27 (a "copy change") so a historical baseline exists.
  S2  SMB / low-end Android    connect_bank drop-off ~60% with rage clicks in one micro-segment
      blind spot               while the overall funnel stays healthy.
  S3  Natural exit             pricing sessions that scroll to the bottom and leave. Must NOT be flagged.
  G1  App telemetry outage     app events after signup are lost for 12 hours (05:00-17:00 UTC) on 2026-10-04. Looks like a
                               drop-off, is not. The Guardian must catch it before any AI analysis.

Usage:  python pipeline/generate.py [--seed 42] [--out data/synthetic]
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

DATASET = "synthetic-v1"
UTC = timezone.utc
JKT = timezone(timedelta(hours=7))

START = datetime(2026, 9, 12, tzinfo=UTC)
DAYS = 30
SESSIONS_PER_DAY = 300
N_USERS = 4000
FUNNEL_SHARE = 0.78

KYC_CHANGE = datetime(2026, 9, 27, tzinfo=UTC)
KYC_DWELL_MULT = 3.0
KYC_CONTINUE_AFTER = 0.82
BLIND_CONTINUE = 0.40
OUTAGE_START = datetime(2026, 10, 4, 5, tzinfo=UTC)
OUTAGE_END = datetime(2026, 10, 4, 17, tzinfo=UTC)
OUTAGE_SCREENS = {"kyc_identity", "connect_bank", "dashboard"}
CUSTOM_PING_RATE = 0.004  # sessions that carry one event with a name the mapping does not know

FUNNEL = ["signup", "kyc_identity", "connect_bank", "dashboard"]
DWELL_MEDIAN_MS = {"home": 8000, "signup": 40000, "kyc_identity": 28000,
                   "connect_bank": 20000, "pricing": 35000, "dashboard": 60000}
CONTINUE_P = {"signup": 0.95, "kyc_identity": 0.96, "connect_bank": 0.95}

SCREEN_WEB = {"home": "/", "signup": "/signup", "kyc_identity": "/verify/identity",
              "connect_bank": "/connect-bank", "pricing": "/pricing", "dashboard": "/dashboard"}
SCREEN_APP = {"home": "HomeScreen", "signup": "SignupScreen", "kyc_identity": "KycIdentityScreen",
              "connect_bank": "ConnectBankScreen", "pricing": "PricingScreen", "dashboard": "DashboardScreen"}
EVT_WEB = {"screen_view": "page_view", "screen_leave": "page_hide", "click": "click",
           "form_focus": "input_focus", "scroll": "scroll", "rage_click": "rage_click",
           "error": "error", "session_end": "session_end"}
EVT_APP = {"screen_view": "screen_view", "screen_leave": "screen_exit", "click": "tap",
           "form_focus": "field_focus", "scroll": "scroll", "rage_click": "rage_tap",
           "error": "error", "session_end": "app_background"}

LOW_END_MODELS = ["Redmi 6A", "Samsung Galaxy J2 Prime", "Infinix Smart 3", "Oppo A1k"]
MID_ANDROID_MODELS = ["Pixel 7", "Samsung Galaxy S23", "Xiaomi 13", "Oppo Reno 10"]
IPHONE_MODELS = ["iPhone 13", "iPhone 14", "iPhone 15"]

HOUR_WEIGHTS = [0.4 + 0.6 * (1 + math.sin((h - 5) / 24 * 2 * math.pi)) / 2 for h in range(24)]


def iso_ms(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def make_users(rng: random.Random) -> list[dict]:
    users = []
    for i in range(N_USERS):
        persona = rng.choices(["enterprise", "smb", "retail"], [0.25, 0.30, 0.45])[0]
        web_share = {"enterprise": 0.85, "smb": 0.5, "retail": 0.45}[persona]
        platform = "web" if rng.random() < web_share else "app"
        if platform == "web":
            w = [0.55, 0.35, 0.05, 0.05] if persona == "enterprise" else [0.30, 0.15, 0.35, 0.20]
            os_ = rng.choices(["windows", "macos", "android", "ios"], w)[0]
        else:
            os_ = rng.choices(["android", "ios"], [0.6, 0.4])[0]
        low_end = os_ == "android" and rng.random() < 0.5
        if os_ == "android" and low_end:
            model, ver, vw, vh = rng.choice(LOW_END_MODELS), rng.choice(["8.1", "9"]), 360, 640
        elif os_ == "android":
            model, ver, vw, vh = rng.choice(MID_ANDROID_MODELS), rng.choice(["12", "13", "14"]), 412, 915
        elif os_ == "ios":
            model, ver, vw, vh = rng.choice(IPHONE_MODELS), rng.choice(["16", "17", "18"]), 390, 844
        elif os_ == "windows":
            model, ver, vw, vh = "desktop", "11", rng.choice([1366, 1920]), 900
        else:
            model, ver, vw, vh = "desktop", "14", 1440, 900
        users.append({"uid": f"u_{i:05d}", "persona": persona, "platform": platform, "os": os_,
                      "os_version": ver, "model": model, "vw": vw, "vh": vh, "low_end": low_end})
    return users


def is_blindspot(user: dict) -> bool:
    return user["persona"] == "smb" and user["os"] == "android" and user["low_end"]


def simulate_session(rng: random.Random, user: dict, start: datetime):
    """Return (events, outcome). Events use canonical type names and absolute timestamps."""
    ev: list[dict] = []

    def add(ts, etype, screen, element=None, **kw):
        ev.append({"ts": ts, "type": etype, "screen": screen, "element": element, **kw})

    funnel = rng.random() < FUNNEL_SHARE
    path = FUNNEL if funnel else ["home", "pricing"]
    blind = is_blindspot(user)
    t = start
    out = {"funnel": funnel, "blind": blind, "last_screen": None, "kyc_dwell_ms": None,
           "post_change": False, "rage": 0, "pricing_dwell_ms": None, "pricing_scroll": None}

    for i, screen in enumerate(path):
        post = t >= KYC_CHANGE
        dwell = rng.lognormvariate(math.log(DWELL_MEDIAN_MS[screen]), 0.45)
        if screen == "kyc_identity" and post:
            dwell *= KYC_DWELL_MULT
        dwell = int(min(max(dwell, 1500), 600000))

        def frac(a, b):
            return int(dwell * rng.uniform(a, b))

        inter = []  # (offset_ms, type, element, extra)
        cont = True
        scroll_final = round(rng.uniform(0.3, 0.8), 2)

        if screen == "signup":
            inter += [(frac(.05, .3), "form_focus", "email", {}), (frac(.3, .5), "form_focus", "password", {})]
            if rng.random() < 0.08:
                for _ in range(rng.randint(1, 3)):
                    o = frac(.5, .8)
                    inter += [(o, "error", "password", {"error_code": "validation_error"}),
                              (o + rng.randint(800, 3000), "form_focus", "password", {})]
            inter.append((frac(.9, .95), "click", "signup_submit", {}))
            cont = rng.random() < CONTINUE_P["signup"]
        elif screen == "kyc_identity":
            inter.append((frac(.1, .4), "form_focus", "id_upload", {}))
            if post:
                for _ in range(rng.randint(3, 7)):
                    inter.append((frac(.2, .85), "form_focus", "kyc_tooltip", {}))
            inter.append((frac(.9, .95), "click", "kyc_submit", {}))
            cont = rng.random() < (KYC_CONTINUE_AFTER if post else CONTINUE_P["kyc_identity"])
        elif screen == "connect_bank":
            cta = frac(.3, .5)
            inter.append((cta, "click", "connect_bank_cta", {}))
            cont = rng.random() < (BLIND_CONTINUE if blind else CONTINUE_P["connect_bank"])
            if blind and not cont:
                k = rng.randint(3, 6)
                out["rage"] += k
                dwell = max(dwell, cta + 450 * k + 800)
                for j in range(k):
                    inter.append((cta + 300 + 350 * j, "rage_click", "connect_bank_cta", {}))
        elif screen == "home":
            inter.append((frac(.5, .8), "click", "nav_pricing", {}))
        elif screen == "pricing":
            inter += [(frac(.15, .35), "scroll", None, {"scroll_depth": 0.3}),
                      (frac(.4, .6), "scroll", None, {"scroll_depth": 0.6}),
                      (frac(.7, .9), "scroll", None, {"scroll_depth": 1.0})]
            for _ in range(rng.randint(0, 3)):
                inter.append((frac(.3, .8), "click", "plan_toggle", {}))
            scroll_final = round(rng.uniform(0.9, 1.0), 2)
        elif screen == "dashboard":
            inter.append((frac(.3, .7), "scroll", None, {"scroll_depth": 0.5}))

        add(t, "screen_view", screen)
        for off, et, el, extra in inter:
            add(t + timedelta(milliseconds=min(off, dwell - 1)), et, screen, el, **extra)
        t_end = t + timedelta(milliseconds=dwell)
        add(t_end, "screen_leave", screen, dwell_ms=dwell, scroll_depth=scroll_final)

        out["last_screen"] = screen
        if screen == "kyc_identity":
            out["kyc_dwell_ms"], out["post_change"] = dwell, post
        if screen == "pricing":
            out["pricing_dwell_ms"], out["pricing_scroll"] = dwell, scroll_final
        if not cont or i == len(path) - 1:
            add(t_end + timedelta(milliseconds=rng.randint(50, 500)), "session_end", screen)
            break
        t = t_end + timedelta(milliseconds=rng.randint(300, 2500))

    if rng.random() < CUSTOM_PING_RATE:
        add(start + timedelta(milliseconds=rng.randint(100, 2000)), "custom_ping", path[0])
    return ev, out


def render_raw(rng: random.Random, user: dict, sid: str, e: dict, n: int) -> dict:
    """Render one internal event in its source's shape (web and app differ on purpose)."""
    eid = f"evt_{n:07d}"
    ts = e["ts"]
    if user["platform"] == "web":
        props = {"ab_flags": {"onboarding_v": rng.choice(["a", "b"])}, "lang": "id-ID",
                 "referrer": rng.choice(["direct", "google", "ads", "email"]),
                 "page_load_ms": rng.randint(300, 2500)}
        if e.get("dwell_ms") is not None:
            props["dwell_ms"] = e["dwell_ms"]
        if e.get("scroll_depth") is not None:
            props["scroll_pct"] = int(round(e["scroll_depth"] * 100))
        if e.get("error_code"):
            props["err"] = e["error_code"]
        return {"_dataset": DATASET, "src": "web", "id": eid, "sid": sid, "uid": user["uid"],
                "t": int(ts.timestamp() * 1000),
                "evt": EVT_WEB.get(e["type"], f"x_{e['type']}"),
                "url_path": SCREEN_WEB[e["screen"]], "el": e["element"],
                "user": {"persona": user["persona"], "tags": [user["persona"]]},
                "ctx": {"os": user["os"], "os_version": user["os_version"], "device_model": user["model"],
                        "viewport": {"w": user["vw"], "h": user["vh"]}},
                "props": props}
    params = {"network": rng.choice(["wifi", "4g", "4g", "3g"]), "battery_pct": rng.randint(10, 100)}
    if e.get("dwell_ms") is not None:
        params["time_on_screen_ms"] = e["dwell_ms"]
    if e.get("scroll_depth") is not None:
        params["scroll_ratio"] = e["scroll_depth"]
    if e.get("error_code"):
        params["error_code"] = e["error_code"]
    return {"_dataset": DATASET, "platform": "app", "event_id": eid, "session_id": sid,
            "user_id": user["uid"], "timestamp": ts.astimezone(JKT).isoformat(timespec="milliseconds"),
            "event_name": EVT_APP.get(e["type"], e["type"]),
            "screen_name": SCREEN_APP[e["screen"]], "target": e["element"],
            "user_properties": {"segment": user["persona"], "app_version": "3.4.1"},
            "device_info": {"os": user["os"], "os_version": user["os_version"], "model": user["model"],
                            "screen_w": user["vw"], "screen_h": user["vh"]},
            "params": params}


def build(seed: int):
    rng = random.Random(seed)
    users = make_users(rng)
    raw_events, sessions, dropped = [], [], Counter()
    n_evt = n_sess = 0

    for d in range(DAYS):
        day = START + timedelta(days=d)
        weekend = day.weekday() >= 5
        for _ in range(int(SESSIONS_PER_DAY * (0.85 if weekend else 1.0) * rng.uniform(0.92, 1.08))):
            user = rng.choice(users)
            hour = rng.choices(range(24), HOUR_WEIGHTS)[0]
            start = day + timedelta(hours=hour, minutes=rng.randint(0, 59), seconds=rng.randint(0, 59),
                                    milliseconds=rng.randint(0, 999))
            n_sess += 1
            sid = f"s_{n_sess:06d}"
            events, out = simulate_session(rng, user, start)
            affected = False
            for e in events:
                if (user["platform"] == "app" and OUTAGE_START <= e["ts"] < OUTAGE_END
                        and (e["screen"] in OUTAGE_SCREENS or e["type"] == "session_end")):
                    affected = True
                    dropped[e["type"]] += 1
                    continue
                n_evt += 1
                raw_events.append((e["ts"], render_raw(rng, user, sid, e, n_evt)))
            out.update(sid=sid, persona=user["persona"], platform=user["platform"], affected=affected)
            sessions.append(out)

    raw_events.sort(key=lambda x: (x[0], x[1].get("id") or x[1].get("event_id")))
    return [r for _, r in raw_events], sessions, dropped


def rate(num, den):
    return round(num / den, 4) if den else None


def ground_truth(seed: int, sessions: list[dict], dropped: Counter, n_events: int) -> dict:
    clean = [s for s in sessions if not s["affected"]]
    funnel = [s for s in clean if s["funnel"]]
    blind = [s for s in funnel if s["blind"]]
    rest = [s for s in funnel if not s["blind"]]

    def at_bank(group):
        return [s for s in group if s["last_screen"] in ("connect_bank", "dashboard")]

    kyc = [s for s in funnel if s["kyc_dwell_ms"] is not None]
    pre = [s for s in kyc if not s["post_change"]]
    post = [s for s in kyc if s["post_change"]]
    pricing = [s for s in clean if s["pricing_dwell_ms"] is not None]
    return {
        "dataset": DATASET,
        "synthetic": True,
        "seed": seed,
        "window_utc": [iso_ms(START), iso_ms(START + timedelta(days=DAYS))],
        "counts": {"sessions": len(sessions), "events": n_events, "outage_affected_sessions": len(sessions) - len(clean)},
        "overall": {
            "funnel_conversion_all": rate(sum(s["last_screen"] == "dashboard" for s in funnel), len(funnel)),
            "funnel_conversion_excluding_blindspot": rate(sum(s["last_screen"] == "dashboard" for s in rest), len(rest)),
        },
        "must_flag": [
            {
                "id": "S1_kyc_language_confusion",
                "screen": "kyc_identity", "segment": "all users, web and app",
                "active_from_utc": iso_ms(KYC_CHANGE),
                "expected_class": "language_cognitive_overload",
                "expected_signal": "dwell ~3x baseline, repeated kyc_tooltip focus, exits with no error_code",
                "measured": {
                    "median_dwell_ms_before": int(median(s["kyc_dwell_ms"] for s in pre)),
                    "median_dwell_ms_after": int(median(s["kyc_dwell_ms"] for s in post)),
                    "kyc_exit_rate_before": rate(sum(s["last_screen"] == "kyc_identity" for s in pre), len(pre)),
                    "kyc_exit_rate_after": rate(sum(s["last_screen"] == "kyc_identity" for s in post), len(post)),
                    "sessions_after": len(post),
                },
            },
            {
                "id": "S2_smb_lowend_android_connect_bank",
                "screen": "connect_bank",
                "segment": "persona=smb, os=android, low-end device (viewport_w=360, os_version 8.1/9)",
                "expected_class": "technical_bug",
                "expected_signal": "rage_click on connect_bank_cta, ~60% drop-off in segment while overall funnel stays healthy",
                "measured": {
                    "segment_sessions_reaching_connect_bank": len(at_bank(blind)),
                    "segment_drop_off": rate(sum(s["last_screen"] == "connect_bank" for s in at_bank(blind)), len(at_bank(blind))),
                    "others_drop_off": rate(sum(s["last_screen"] == "connect_bank" for s in at_bank(rest)), len(at_bank(rest))),
                    "segment_rage_clicks": sum(s["rage"] for s in blind),
                    "others_rage_clicks": sum(s["rage"] for s in rest),
                    "overall_funnel_conversion": rate(sum(s["last_screen"] == "dashboard" for s in funnel), len(funnel)),
                },
            },
        ],
        "must_not_flag_as_problem": [
            {
                "id": "S3_pricing_natural_exit",
                "screen": "pricing",
                "expected_class": "natural_exit",
                "expected_signal": "scroll to bottom, normal dwell, no rage clicks; exits here are expected",
                "measured": {
                    "pricing_sessions": len(pricing),
                    "median_dwell_ms": int(median(s["pricing_dwell_ms"] for s in pricing)),
                    "median_scroll_depth": median(s["pricing_scroll"] for s in pricing),
                    "rage_clicks": sum(s["rage"] for s in pricing),
                },
            }
        ],
        "guardian_must_catch": [
            {
                "id": "G1_app_telemetry_outage",
                "window_utc": [iso_ms(OUTAGE_START), iso_ms(OUTAGE_END)],
                "platform": "app",
                "events_missing_after_signup_screens": sorted(OUTAGE_SCREENS),
                "also_missing": "session_end",
                "expected_behavior": "Guardian flags a telemetry gap; Watchdog and Diagnostic Agent must not report it as user behavior",
                "dropped_events_by_type": dict(dropped),
                "affected_sessions": len(sessions) - len(clean),
            },
            {
                "id": "G2_unmapped_event_names",
                "expected_behavior": "events named x_custom_ping (web) / custom_ping (app) are flagged as unmapped, not ignored",
            },
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/synthetic")
    args = ap.parse_args()

    events, sessions, dropped = build(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "events_raw.jsonl", "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, separators=(",", ":")) + "\n")
    gt = ground_truth(args.seed, sessions, dropped, len(events))
    (out / "ground_truth.json").write_text(json.dumps(gt, indent=2) + "\n", encoding="utf-8")
    print(f"{len(sessions)} sessions, {len(events)} events -> {out}/events_raw.jsonl")
    print(json.dumps({k: gt[k] for k in ("counts", "overall")}, indent=2))


if __name__ == "__main__":
    main()
