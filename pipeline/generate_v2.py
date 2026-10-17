#!/usr/bin/env python3
"""Synthetic event generator, dataset synthetic-v2 (SmartSari-shaped).

ALL DATA PRODUCED HERE IS SYNTHETIC. Label it as such in the UI, the deck and the video.
Brief and decided defaults: docs/smartsari-dataset-spec.md (the contract). Deterministic for a seed.

Emits source-shaped RAW app events (JSON Lines, one event per line) plus ground_truth.json with the
measured value of every planted pattern. 4,000 users: 800 unregistered and 3,200 registered (large
business 640, sari-sari store 1,600, individual trader 320, individual 320, unknown 160, fraudster 160).
Android / iOS 50/50, at most 5 user ids per device id. Window 2026-09-15 to 2026-10-15 UTC.

Every user has at least 5 completed attempts per scenario that applies to their persona (unregistered:
register only; registered: login, top-up and transaction, plus one registration), at different
timestamps. Failed attempts are extra sessions.

Planted (see ground_truth.json):
  control  personal_data and tin lose ~18% and ~8% of sessions all window, every persona
  P1       OTP not delivered 2026-10-09 02:00-10:00 UTC: ~70% of attempts stall on the otp screen
  P2       large_business tops up above PHP 50,000 in most top-ups; everyone else stays under PHP 5,000
  P3       sari_sari buys eload in ~70% of transactions (expected behavior, not a problem)
  P4       individual_trader abandons send_money at checkout ~55% of the time (others ~5%)
  P5       sari_sari on an android_low device abandons topup_confirm ~70% of the time (others ~5%): dead and
           rage taps near the bottom of the screen, no error code (the button is effectively unreachable, not broken)
  P7       individual on iOS abandons login_phone ~65% of the time (others ~2%): an autofill bug mangles the
           phone number, so verification keeps failing until most people give up
  P8       large_business on an android_low device abandons topup_amount ~65% of the time (others ~4%): the
           numeric keypad truncates large top-up amounts, so Continue stays dead or shows an occasional format error
  M1       fraudsters: bursts, odd hours, failed attempts, up to 5 users per device
  M2       unregistered users open prices repeatedly before registering (natural exit)
  G1-G4    telemetry faults for the Guardian (kyc_selfie tracker silent on 4.12, 3.2% row loss on
           2026-10-11, unmapped property otp_channel_v2, checkout double-fire on Android 09-22..09-26)

Usage:  python pipeline/generate_v2.py [--seed 42] [--out data/synthetic]
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from schema import JOURNEYS, PRODUCTS, TERMINAL_SCREENS

DATASET = "synthetic-v2"
UTC = timezone.utc
JKT = timezone(timedelta(hours=7))
START = datetime(2026, 9, 15, tzinfo=UTC)
DAYS = 30
END = START + timedelta(days=DAYS)

# Four times the original population gives small platform/persona slices enough
# observations to show measured rates in the selected 7-day view.
POPULATION = [("unregistered", 800), ("large_business", 640), ("sari_sari", 1600), ("individual_trader", 320),
              ("individual", 320), ("unknown", 160), ("fraudster", 160)]

# planted values
OTP_START, OTP_END = datetime(2026, 10, 9, 2, tzinfo=UTC), datetime(2026, 10, 9, 10, tzinfo=UTC)
OTP_STALL = 0.70
TOPUP_BIG_MIN, TOPUP_SMALL_MAX = 50_000, 4_999
LARGE_TOPUP_SHARE = 0.85
ELOAD_SHARE = 0.70
P4_CONTINUE = 0.45
CONF_OOS_PERSONA, CONF_OOS_DEVICE, CONF_OOS_SCREEN = "sari_sari", "android_low", "topup_confirm"
CONF_OOS_CONTINUE = 0.30         # the promo banner on small/old screens pushes Confirm out of reach: no error, just dead/rage taps
P6_DEVICE, P6_SCREEN = "web_mobile", "web_pay"
P6_CONTINUE = 0.35               # the bank redirect loses the session in a mobile in-app browser far more than on desktop
P7_PERSONA, P7_DEVICE, P7_SCREEN = "individual", "ios", "login_phone"
P7_CONTINUE = 0.35               # an iOS autofill bug mangles the phone field; verification keeps failing until most people give up
P8_PERSONA, P8_DEVICE, P8_SCREEN = "large_business", "android_low", "topup_amount"
P8_CONTINUE = 0.35               # the numeric keypad truncates large top-up amounts past a few digits; Continue stays dead
V412_DATE = datetime(2026, 10, 6, tzinfo=UTC)
V412_SHARE = 0.60
ANDROID_FIX = datetime(2026, 9, 27, tzinfo=UTC)          # Android runs 4.11.1 before this, 4.11.2 after
G1_START = datetime(2026, 10, 13, 18, tzinfo=UTC)         # kyc_selfie tracker silent on 4.12
G1_DROP = 0.94
G2_DAY = datetime(2026, 10, 11, tzinfo=UTC)
G2_LOSS = 0.032
G4_START, G4_END = datetime(2026, 9, 22, tzinfo=UTC), datetime(2026, 9, 27, tzinfo=UTC)

# continue probability per screen (everyone, outside planted faults)
P_CONT = {"welcome": .98, "register_phone": .97, "otp": .95, "personal_data": .82, "tin": .92, "kyc_selfie": .96,
          "login_phone": .98, "wallet": .98, "topup_amount": .96, "topup_confirm": .95,
          "product_list": .96, "txn_details": .95, "txn_checkout": .95}
# Each product has its own weakest step, so the demo does not show the same drop-off everywhere. Kept mild on purpose (a few points
# above the normal 5%), so the Watchdog does not read them as planted faults. Reason shown by the exit rules afterwards:
#   error -> technical, back -> ux (went back before leaving), language -> stuck on the screen over 30 s, natural -> just browsing.
P_CONT_PRODUCT = {("eload", "product_list"): .93, ("water_bill", "txn_details"): .91, ("electricity_bill", "txn_checkout"): .91,
                  ("game_voucher", "txn_checkout"): .91, ("cable_internet", "txn_details"): .90, ("postpaid_telecom", "txn_details"): .91}
PRODUCT_REASON = {("water_bill", "txn_details"): ("error", "account_not_found"), ("electricity_bill", "txn_checkout"): ("error", "amount_mismatch"),
                  ("game_voucher", "txn_checkout"): ("back", None), ("cable_internet", "txn_details"): ("language", None),
                  ("postpaid_telecom", "txn_details"): ("back", None), ("eload", "product_list"): ("natural", None)}
P_CONT_FRAUD = {"login_phone": .95, "otp": .78, "topup_confirm": .60, "txn_details": .94, "txn_checkout": .55}
P_BACK = 0.02
P_DEAD = 0.012
P_RAGE = 0.006
IDLE_P = 0.20            # share of long-enough screen visits with no activity heartbeat

# screen: (median dwell ms, sigma, focus elements, cta element)
SPEC = {
    "prices": (30000, .5, [], "product_card"),
    "welcome": (6000, .4, [], "get_started"),
    "register_phone": (14000, .4, ["phone"], "continue"),
    "login_phone": (9000, .4, ["phone"], "login"),
    "otp": (18000, .5, ["otp_input"], "verify"),
    "personal_data": (50000, .5, ["full_name", "birthdate"], "continue"),
    "tin": (28000, .5, ["tin_input"], "continue"),
    "kyc_selfie": (32000, .45, [], "submit"),
    "register_done": (4000, .3, [], None),
    "home": (5000, .4, [], None),
    "wallet": (7000, .4, [], "topup_btn"),
    "topup_amount": (16000, .45, ["amount"], "continue"),
    "topup_confirm": (12000, .4, [], "confirm"),
    "topup_done": (4000, .3, [], None),
    "product_list": (12000, .45, [], "product"),
    "txn_details": (24000, .5, ["account_no", "amount"], "continue"),
    "txn_checkout": (15000, .45, ["pin"], "pay"),
    "txn_done": (4000, .3, [], None),
}
ERROR_CODES = {"otp": "otp_invalid", "txn_checkout": "pin_invalid", "topup_confirm": "limit_exceeded",
               "personal_data": "validation_error", "tin": "tin_invalid"}
PRODUCT_AMOUNT = {"eload": (20, 1000), "water_bill": (200, 2500), "electricity_bill": (300, 5000),
                  "game_voucher": (50, 1500), "cable_internet": (500, 3000), "send_money": (500, 20000),
                  "postpaid_telecom": (400, 4000)}
EVT_APP = {"screen_view": "screen_view", "screen_leave": "screen_exit", "click": "tap", "form_focus": "field_focus",
           "rage_click": "rage_tap", "dead_tap": "dead_tap", "back": "back_press", "error": "error",
           "session_end": "app_background"}
SCREEN_RAW = {s: "".join(w.capitalize() for w in s.split("_")) + "Screen" for s in SPEC}

# --- web_checkout: a merchant-site bill-pay redirect, platform=web only. Own screens, own raw shape (see render_raw_web),
# own browser_class dimension (web_desktop/web_mobile) instead of device_class. Not a mirror of the app journeys above.
WEB_PRODUCTS = ["eload", "water_bill", "electricity_bill", "game_voucher", "cable_internet", "postpaid_telecom"]
WEB_SPEC = {   # screen: (median dwell ms, sigma, focus elements, cta element)
    "web_landing": (5000, .4, [], "continue_btn"),
    "web_login": (11000, .4, ["phone"], "continue_btn"),
    "web_otp": (16000, .5, ["otp_input"], "verify_btn"),
    "web_review": (14000, .45, [], "pay_btn"),
    "web_pay": (9000, .4, [], "confirm_btn"),
    "web_done": (4000, .3, [], None),
}
WEB_P_CONT = {"web_landing": .97, "web_login": .96, "web_otp": .94, "web_review": .95, "web_pay": .93}
WEB_ERROR_CODES = {"web_otp": "otp_invalid", "web_pay": "session_expired"}
EVT_WEB = {"screen_view": "page_view", "screen_leave": "page_exit", "click": "click", "form_focus": "field_focus",
           "rage_click": "rage_click", "dead_tap": "dead_click", "back": "back_nav", "error": "error",
           "session_end": "tab_closed"}
PAGE_RAW = {s: "/" + s.replace("web_", "").replace("_", "-") for s in WEB_SPEC}   # e.g. web_review -> "/review"
LOW_MODELS = [("Redmi 9A", "10"), ("Samsung Galaxy A03", "11"), ("Infinix Smart 6", "11"), ("Realme C11", "10"),
              ("Oppo A15", "11"), ("Vivo Y12", "10")]
MID_MODELS = [("Samsung Galaxy S23", "14"), ("Pixel 7", "14"), ("Xiaomi 13", "13"), ("Oppo Reno 10", "13"),
              ("Samsung Galaxy A54", "13")]
IOS_MODELS = [("iPhone 11", "16.7"), ("iPhone 12", "17.4"), ("iPhone 13", "17.5.1"), ("iPhone 14", "18.0"),
              ("iPhone 15", "18.1")]


def iso_ms(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def hour_weights(persona: str) -> list[float]:
    w = []
    for h in range(24):
        wib = (h + 7) % 24
        if persona == "fraudster":
            w.append(1.0 if wib < 6 else 0.04)
        elif persona == "sari_sari":
            w.append(0.04 if wib < 5 else 1.0 if 5 <= wib <= 20 else 0.3)
        else:
            w.append(0.03 if wib < 6 else .5 if wib in (6, 7, 21) else 1.0 if wib <= 20 else .15)
    return w


HW = {p: hour_weights(p) for p, _ in POPULATION}
DAY_W = [0.85 if (START + timedelta(days=d)).weekday() >= 5 else 1.0 for d in range(DAYS)]


def sample_time(rng, persona: str) -> datetime:
    d = rng.choices(range(DAYS), DAY_W)[0]
    h = rng.choices(range(24), HW[persona])[0]
    return START + timedelta(days=d, hours=h, minutes=rng.randint(0, 59), seconds=rng.randint(0, 59),
                             milliseconds=rng.randint(0, 999))


def time_between(rng, persona: str, a: datetime, b: datetime) -> datetime:
    for _ in range(200):
        t = sample_time(rng, persona)
        if a <= t < b:
            return t
    return a + (b - a) * rng.random()


def plan_times(rng, persona: str, n: int) -> list[datetime]:
    if persona == "fraudster":     # bursts: groups of 2-6 sessions a few minutes apart, at odd hours
        out = []
        while len(out) < n:
            k = min(rng.randint(2, 6), n - len(out))
            t = sample_time(rng, persona)
            for _ in range(k):
                out.append(t)
                t = t + timedelta(minutes=rng.uniform(2, 8))
        out = [t for t in out if t < END - timedelta(minutes=5)] or [sample_time(rng, persona)]
        while len(out) < n:
            out.append(sample_time(rng, persona))
        return sorted(out)
    for _ in range(20):
        ts = sorted(sample_time(rng, persona) for _ in range(n))
        for i in range(1, len(ts)):
            if ts[i] - ts[i - 1] < timedelta(minutes=15):
                ts[i] = ts[i - 1] + timedelta(minutes=15, seconds=rng.randint(0, 600))
        if ts[-1] < END - timedelta(minutes=10):
            return ts
    return ts


def make_users_and_devices(rng):
    users, idx = [], 1
    for persona, n in POPULATION:
        for _ in range(n):
            users.append({"uid": f"U{idx:05d}", "persona": persona})
            idx += 1
    by_persona = defaultdict(list)
    for u in users:
        by_persona[u["persona"]].append(u)
    groups = []
    for persona, lst in by_persona.items():
        lst = lst[:]
        rng.shuffle(lst)
        i = 0
        while i < len(lst):
            if persona == "fraudster":
                size = 5
            elif persona == "unknown":
                size = rng.choice([2, 3, 4])
            elif persona == "sari_sari":
                size = rng.choice([1, 1, 1, 1, 1, 1, 2, 2, 2, 3])
            else:
                size = rng.choice([1] * 45 + [2] * 4 + [3])
            groups.append(lst[i:i + size])
            i += size
    rng.shuffle(groups)
    counts = {"android": 0, "ios": 0}
    devices = []
    for g in groups:
        os_ = "android" if counts["android"] < counts["ios"] else "ios" if counts["ios"] < counts["android"] else rng.choice(["android", "ios"])
        counts[os_] += len(g)
        if os_ == "android":
            low = rng.random() < 0.55
            model, ver = rng.choice(LOW_MODELS if low else MID_MODELS)
            cls = "android_low" if low else "android_mid"
        else:
            model, ver = rng.choice(IOS_MODELS)
            cls = "ios"
        dev = {"id": "dev_" + "".join(rng.choice("0123456789abcdef") for _ in range(10)), "os": os_, "model": model,
               "os_version": ver, "cls": cls, "users": [u["uid"] for u in g]}
        devices.append(dev)
        for u in g:
            u["dev"] = dev
    for k, dev in enumerate(rng.sample(devices, len(devices))):
        dev["new_sdk"] = k < round(V412_SHARE * len(devices))
    return users, devices


def app_version(dev: dict, ts: datetime) -> str:
    if ts >= V412_DATE and dev["new_sdk"]:
        return "4.12"
    if dev["os"] == "android" and ts < ANDROID_FIX:
        return "4.11.1"
    return "4.11.2"


def product_weights(rng_noise: random.Random, persona: str) -> list[float]:
    if persona == "sari_sari":
        return [ELOAD_SHARE if p == "eload" else (1 - ELOAD_SHARE) / 6 for p in PRODUCTS]
    return [rng_noise.uniform(0.9, 1.1) for _ in PRODUCTS]


def lognorm(rng, med, sig, lo=700, hi=240000) -> int:
    return int(min(max(rng.lognormvariate(math.log(med), sig), lo), hi))


def topup_amount(rng, persona: str) -> int:
    if persona == "large_business" and rng.random() < LARGE_TOPUP_SHARE:
        return int(round(math.exp(rng.uniform(math.log(TOPUP_BIG_MIN + 1), math.log(500_000))), -3)) or TOPUP_BIG_MIN + 1000
    return int(min(max(round(rng.lognormvariate(math.log(800), 0.8), -1), 100), TOPUP_SMALL_MAX))


def txn_amount(rng, product: str) -> int:
    lo, hi = PRODUCT_AMOUNT[product]
    return int(round(math.exp(rng.uniform(math.log(lo), math.log(hi))), -1)) or lo


# tap position (x, y as a share of the screen) of each element's centre; "*" is the screen's main button
ELEMENT_POS = {("otp", "resend"): (0.50, 0.66), ("otp", "verify"): (0.50, 0.86), ("txn_checkout", "pay"): (0.50, 0.90),
               ("otp", "*"): (0.50, 0.86), ("txn_checkout", "*"): (0.50, 0.90)}
AMOUNT_ALL = {"topup_confirm", "topup_done", "txn_checkout", "txn_done"}
AMOUNT_AFTER = {"topup_amount", "txn_details"}      # not on screen_view / form_focus (amount not typed yet)


def simulate(rng, user: dict, journey: str, t0: datetime, product: str | None):
    """One session. Returns (events, outcome). Events carry absolute UTC timestamps."""
    persona, dev = user["persona"], user["dev"]
    ver = app_version(dev, t0)
    path = JOURNEYS[journey]
    ev: list[dict] = []
    amount = topup_amount(rng, persona) if journey == "topup" else (txn_amount(rng, product) if journey == "transaction" else None)
    out = {"user": user["uid"], "persona": persona, "journey": journey, "product": product, "amount": amount,
           "t0": t0, "ver": ver, "completed": False, "last": None, "stalled": False, "in_otp_window": False,
           "p4_fail": False, "back": 0, "rage": 0, "dead": 0, "errors": 0, "otp_exit": False, "screens": set(),
           "dev": dev["id"], "platform": "app"}

    def add(ts, etype, screen, element=None, **kw):
        e = {"ts": ts, "type": etype, "screen": screen, "element": element, **kw}
        if etype in ("click", "rage_click", "dead_tap") and element and "tap_x" not in e:
            cx, cy = ELEMENT_POS.get((screen, element), ELEMENT_POS.get((screen, "*"), (0.5, 0.85)))
            sg = 0.02 if etype == "rage_click" and element in ("resend", "pay") else 0.045
            e["tap_x"], e["tap_y"] = round(min(max(rng.gauss(cx, sg), 0), 1), 3), round(min(max(rng.gauss(cy, sg), 0), 1), 3)
        if product and (screen == "product_list" and etype not in ("screen_view", "form_focus")
                        or screen in ("txn_details", "txn_checkout", "txn_done")):
            e["product"] = product
        if amount is not None and (screen in AMOUNT_ALL or (screen in AMOUNT_AFTER and etype not in ("screen_view", "form_focus"))):
            e["amount"] = amount
        ev.append(e)

    def visit(screen, t, dwell, extras=()):
        """Emit view, interactions (offset_ms, type, element, kw), leave. Returns end time."""
        add(t, "screen_view", screen)
        for off, et, el, kw in extras:
            add(t + timedelta(milliseconds=min(off, dwell - 1)), et, screen, el, **kw)
        # Activity heartbeat: a person who is filling in or reading a screen touches it every 14 to 26 s (scroll or tap on the content).
        # IDLE_P of the visits go quiet instead, so "no forward progress for 30 s" can mean something. Uses its own generator seeded from
        # the visit, so the main random stream (and every planted pattern) is unchanged.
        hb = random.Random(f"{user['uid']}|{t.isoformat()}|{screen}")
        if screen not in TERMINAL_SCREENS and hb.random() >= IDLE_P:
            o = hb.uniform(14000, 26000)
            while o < dwell - 3000:
                ev.append({"ts": t + timedelta(milliseconds=o), "type": "click", "screen": screen, "element": "content"})
                o += hb.uniform(14000, 26000)
        t_end = t + timedelta(milliseconds=dwell)
        if screen not in TERMINAL_SCREENS:      # terminal screens log a view only (the session ends there)
            add(t_end, "screen_leave", screen, dwell_ms=dwell)
        out["screens"].add(screen)
        out["last"] = screen
        return t_end

    t = t0
    for i, screen in enumerate(path):
        med, sig, focus, cta = SPEC[screen]
        dwell = lognorm(rng, med, sig)
        extras = []
        fr = lambda a, b: int(dwell * rng.uniform(a, b))
        if focus and rng.random() < 0.25:
            for k, el in enumerate(focus):
                extras.append((fr(.05 + .1 * k, .3 + .1 * k), "form_focus", el, {}))
        if screen == "product_list":
            extras.append((fr(.5, .8), "click", f"product_{product}", {}))
        elif cta and rng.random() < 0.4:
            extras.append((fr(.85, .95), "click", cta, {}))
        if screen == "otp" and ver == "4.12":
            for x in extras:
                x[3]["otp_channel_v2"] = "sms"
        terminal = screen in TERMINAL_SCREENS
        # --- continue decision
        p = P_CONT_FRAUD.get(screen, P_CONT.get(screen, 1.0)) if persona == "fraudster" else P_CONT.get(screen, 1.0)
        if persona != "fraudster" and product and (product, screen) in P_CONT_PRODUCT:
            p = P_CONT_PRODUCT[(product, screen)]
        if screen == CONF_OOS_SCREEN and persona == CONF_OOS_PERSONA and dev["cls"] == CONF_OOS_DEVICE:
            p = CONF_OOS_CONTINUE
        if screen == P7_SCREEN and persona == P7_PERSONA and dev["cls"] == P7_DEVICE:
            p = P7_CONTINUE
        if screen == P8_SCREEN and persona == P8_PERSONA and dev["cls"] == P8_DEVICE:
            p = P8_CONTINUE
        stalled = False
        reason_back = False
        if screen == "otp":
            out["in_otp_window"] = OTP_START <= t < OTP_END
            if out["in_otp_window"]:
                stalled = rng.random() < OTP_STALL
                p = 0.0 if stalled else p
        if screen == "txn_checkout" and persona == "individual_trader" and product == "send_money":
            p = P4_CONTINUE
        cont = True if terminal else rng.random() < p
        # --- friction
        if stalled:
            out["stalled"] = True
            dwell = lognorm(rng, 55000, .4)
            k = rng.randint(3, 6)
            out["rage"] += k
            extras = [(fr(.1, .2), "form_focus", "otp_input", {})] + \
                     [(int(dwell * (.25 + .5 * j / k)), "rage_click", "resend", {}) for j in range(k)]
            if rng.random() < 0.4:
                extras.append((fr(.8, .9), "error", "otp_input", {"error_code": "otp_timeout"}))
                out["errors"] += 1
        elif not cont:
            if screen == "txn_checkout" and persona == "individual_trader" and product == "send_money":
                out["p4_fail"] = True
                r = rng.random()
                if r < .45:
                    k = rng.randint(3, 5)
                    out["rage"] += k
                    extras += [(fr(.6, .9) + 200 * j, "rage_click", "pay", {}) for j in range(k)]
                if rng.random() < .40:
                    out["dead"] += 1
                    extras.append((fr(.7, .9), "dead_tap", "pay", {}))
                if rng.random() < .35:
                    out["errors"] += 1
                    extras.append((fr(.75, .95), "error", "pay", {"error_code": "payment_timeout"}))
            elif screen == CONF_OOS_SCREEN and persona == CONF_OOS_PERSONA and dev["cls"] == CONF_OOS_DEVICE:
                # the Confirm button is pushed toward the bottom edge of the screen: taps land near it, not on it, and nothing errors
                dwell = lognorm(rng, 30000, .35)
                oos_y = lambda: round(min(rng.gauss(0.97, 0.015), 1.0), 3)
                k = rng.randint(2, 4)
                out["dead"] += k
                extras += [(fr(.5, .95), "dead_tap", cta, {"tap_x": 0.5, "tap_y": oos_y()}) for _ in range(k)]
                j = rng.randint(2, 4)
                out["rage"] += j
                extras += [(fr(.3, .6) + 150 * x, "rage_click", cta, {"tap_x": 0.5, "tap_y": oos_y()}) for x in range(j)]
            elif screen == P7_SCREEN and persona == P7_PERSONA and dev["cls"] == P7_DEVICE:
                # autofill writes a mangled phone number into the field; verification fails, a couple of retries, then most give up
                out["errors"] += 1
                extras.append((fr(.55, .8), "error", "phone", {"error_code": "phone_format_invalid"}))
                if rng.random() < .4:
                    k = rng.randint(2, 4)
                    out["rage"] += k
                    extras += [(fr(.7, .9) + 200 * j, "rage_click", "login", {}) for j in range(k)]
                if rng.random() < .25:
                    out["dead"] += 1
                    extras.append((fr(.8, .92), "dead_tap", "login", {}))
            elif screen == P8_SCREEN and persona == P8_PERSONA and dev["cls"] == P8_DEVICE:
                # the keypad truncates the amount past a few digits; Continue looks tappable but the form never validates
                k = rng.randint(2, 4)
                out["dead"] += k
                extras += [(fr(.5, .9), "dead_tap", cta, {}) for _ in range(k)]
                j = rng.randint(1, 3)
                out["rage"] += j
                extras += [(fr(.3, .6) + 150 * x, "rage_click", cta, {}) for x in range(j)]
                if rng.random() < .2:
                    out["errors"] += 1
                    extras.append((fr(.7, .9), "error", "amount", {"error_code": "amount_format_error"}))
            elif persona == "fraudster" and screen in ERROR_CODES and rng.random() < .6:
                out["errors"] += 1
                extras.append((fr(.7, .95), "error", None, {"error_code": {"otp": "otp_invalid", "txn_checkout": "risk_declined", "topup_confirm": "limit_exceeded"}.get(screen, ERROR_CODES[screen])}))
            elif persona != "fraudster" and (product, screen) in PRODUCT_REASON and PRODUCT_REASON[(product, screen)][0] != "natural" and rng.random() < .8:
                kind, code = PRODUCT_REASON[(product, screen)]
                if kind == "error":
                    out["errors"] += 1
                    extras.append((fr(.7, .95), "error", None, {"error_code": code}))
                elif kind == "language":
                    dwell = lognorm(rng, 48000, .3)
                elif kind == "back":
                    reason_back = True
            elif screen in ("personal_data", "tin") and rng.random() < .2:
                out["errors"] += 1
                extras.append((fr(.6, .9), "error", None, {"error_code": ERROR_CODES[screen]}))
        if cont or not stalled:
            if cta and rng.random() < P_DEAD:
                out["dead"] += 1
                extras.append((fr(.8, .9), "dead_tap", cta, {}))
            if rng.random() < P_RAGE and cta:
                k = rng.randint(3, 4)
                out["rage"] += k
                extras += [(fr(.8, .9) + 250 * j, "rage_click", cta, {}) for j in range(k)]
        if cont and screen == "otp" and rng.random() < 0.03:
            out["errors"] += 1
            extras.append((fr(.4, .6), "error", "otp_input", {"error_code": "otp_invalid"}))
        t_end = visit(screen, t, dwell, extras)
        if reason_back and i > 0:
            add(t_end, "back", screen)
            out["back"] += 1
        if stalled and rng.random() < 0.3 and i > 0:      # back to retype the number, then give up
            add(t_end, "back", screen)
            out["back"] += 1
            t_end = visit(path[i - 1], t_end + timedelta(milliseconds=400), lognorm(rng, 5000, .4))
            t_end = visit(screen, t_end + timedelta(milliseconds=400), lognorm(rng, 30000, .4),
                          [(8000, "rage_click", "resend", {}), (9000, "rage_click", "resend", {}), (10000, "rage_click", "resend", {})])
            out["rage"] += 3
        if not cont:
            if screen == "otp":
                out["otp_exit"] = True
            add(t_end + timedelta(milliseconds=rng.randint(50, 500)), "session_end", screen)
            return ev, out
        if terminal:
            out["completed"] = True
            add(t_end + timedelta(milliseconds=rng.randint(50, 500)), "session_end", screen)
            return ev, out
        if i >= 1 and rng.random() < P_BACK * (2 if persona == "fraudster" else 1):
            add(t_end, "back", screen)
            out["back"] += 1
            t_back = visit(path[i - 1], t_end + timedelta(milliseconds=300), lognorm(rng, 3500, .4))
            t_end = visit(screen, t_back + timedelta(milliseconds=300), lognorm(rng, 6000, .4),
                          [(5000, "click", cta, {})] if cta else [])
        t = t_end + timedelta(milliseconds=rng.randint(300, 2500))
    return ev, out


def simulate_web(rng, user: dict, t0: datetime, product: str, browser_class: str):
    """One platform=web session: a merchant-site bill-pay redirect. Simpler than simulate() on purpose
    (no OTP-outage/fraud/product-reason branches; those are app-only stories). Returns (events, outcome)."""
    persona = user["persona"]
    path = JOURNEYS["web_checkout"]
    ev: list[dict] = []
    amount = txn_amount(rng, product)
    out = {"user": user["uid"], "persona": persona, "journey": "web_checkout", "product": product, "amount": amount,
           "t0": t0, "ver": None, "completed": False, "last": None, "stalled": False, "in_otp_window": False,
           "p4_fail": False, "back": 0, "rage": 0, "dead": 0, "errors": 0, "otp_exit": False, "screens": set(),
           "dev": None, "platform": "web", "device_class": browser_class}

    def add(ts, etype, screen, element=None, **kw):
        e = {"ts": ts, "type": etype, "screen": screen, "element": element, **kw}
        if etype in ("click", "rage_click", "dead_tap") and element and "tap_x" not in e:
            cx, cy = ELEMENT_POS.get((screen, element), (0.5, 0.85))
            e["tap_x"], e["tap_y"] = round(min(max(rng.gauss(cx, 0.045), 0), 1), 3), round(min(max(rng.gauss(cy, 0.045), 0), 1), 3)
        if screen in ("web_review", "web_pay", "web_done"):
            e["product"] = product
            e["amount"] = amount
        ev.append(e)

    def visit(screen, t, dwell, extras=()):
        add(t, "screen_view", screen)
        for off, et, el, kw in extras:
            add(t + timedelta(milliseconds=min(off, dwell - 1)), et, screen, el, **kw)
        t_end = t + timedelta(milliseconds=dwell)
        if screen not in TERMINAL_SCREENS:
            add(t_end, "screen_leave", screen, dwell_ms=dwell)
        out["screens"].add(screen)
        out["last"] = screen
        return t_end

    t = t0
    for i, screen in enumerate(path):
        med, sig, focus, cta = WEB_SPEC[screen]
        dwell = lognorm(rng, med, sig)
        extras = []
        fr = lambda a, b: int(dwell * rng.uniform(a, b))
        if focus and rng.random() < 0.3:
            extras.append((fr(.1, .3), "form_focus", focus[0], {}))
        elif cta and rng.random() < 0.4:
            extras.append((fr(.85, .95), "click", cta, {}))
        terminal = screen in TERMINAL_SCREENS
        p = WEB_P_CONT.get(screen, 1.0)
        if screen == P6_SCREEN and browser_class == P6_DEVICE:
            p = P6_CONTINUE
        cont = True if terminal else rng.random() < p
        if not cont:
            if screen == P6_SCREEN and browser_class == P6_DEVICE:
                # the bank redirect does not hand control back to the merchant tab: no error most of the time, just a dead page
                r = rng.random()
                if r < .5:
                    pass    # just leaves, long idle dwell already covers this
                elif r < .8:
                    out["back"] += 1
                    extras.append((fr(.6, .9), "back", None, {}))
                else:
                    out["errors"] += 1
                    extras.append((fr(.7, .9), "error", None, {"error_code": WEB_ERROR_CODES[screen]}))
                dwell = lognorm(rng, 42000, .4)
            elif screen in WEB_ERROR_CODES and rng.random() < .25:
                out["errors"] += 1
                extras.append((fr(.7, .9), "error", None, {"error_code": WEB_ERROR_CODES[screen]}))
        if cta and rng.random() < P_DEAD:
            out["dead"] += 1
            extras.append((fr(.8, .9), "dead_tap", cta, {}))
        t_end = visit(screen, t, dwell, extras)
        if not cont:
            add(t_end + timedelta(milliseconds=rng.randint(50, 500)), "session_end", screen)
            return ev, out
        if terminal:
            out["completed"] = True
            add(t_end + timedelta(milliseconds=rng.randint(50, 500)), "session_end", screen)
            return ev, out
        t = t_end + timedelta(milliseconds=rng.randint(200, 1200))
    return ev, out


def build_web(seed: int, users: list):
    """platform=web sessions: a separate RNG stream (seed+50) so the app-only generation above is never perturbed.
    Reuses the same registered users (not a new population) for a bounded share of them, personas that plausibly
    pay a bill from a merchant link: large_business, sari_sari, individual_trader, individual. Unregistered/unknown/
    fraudster are not part of this story."""
    rng = random.Random(seed + 50)
    eligible = [u for u in users if u["persona"] in ("large_business", "sari_sari", "individual_trader", "individual")]
    web_sessions, web_events = [], []
    for user in eligible:
        if rng.random() >= 0.35:      # not everyone pays a bill from a web link
            continue
        n = rng.choice([1, 1, 2, 2, 3])
        for _ in range(n):
            t0 = sample_time(rng, user["persona"])
            product = rng.choice(WEB_PRODUCTS)
            browser_class = "web_mobile" if rng.random() < 0.6 else "web_desktop"
            ev, out = simulate_web(rng, user, t0, product, browser_class)
            out["sno"] = len(web_sessions)
            web_sessions.append(out)
            for i, e in enumerate(ev):
                web_events.append((e["ts"], out["sno"], i, e, user))
    return web_sessions, web_events


def render_raw_web(user: dict, sid: str, e: dict, n: int, browser_class: str) -> dict:
    """Own raw shape on purpose (page/event/properties/context, not screen_name/event_name/params/device_info):
    looks like a real web analytics export, distinct from the app SDK shape above (same precedent as dining's
    own raw events, but as a second named source in the same mapping file, not a second dataset)."""
    ts = e["ts"]
    props = {}
    if e.get("dwell_ms") is not None:
        props["time_on_page_ms"] = e["dwell_ms"]
    for k in ("error_code", "product", "amount", "tap_x", "tap_y"):
        if e.get(k) is not None:
            props[k] = e[k]
    rec = {"_dataset": DATASET, "platform": "web", "event_id": f"evt_{n:07d}", "session_id": sid,
           "user_id": user["uid"], "occurred_at": ts.astimezone(JKT).isoformat(timespec="milliseconds"),
           "event": EVT_WEB[e["type"]], "page": PAGE_RAW[e["screen"]],
           "traits": {"segment": user["persona"]}, "context": {"browser_class": browser_class}}
    if e.get("element"):
        rec["element_id"] = e["element"]
    if props:
        rec["properties"] = props
    return rec


def render_raw(user: dict, sid: str, e: dict, n: int, rng, ver: str) -> dict:
    dev = user["dev"]
    ts = e["ts"]
    params = {}
    if e.get("dwell_ms") is not None:
        params["time_on_screen_ms"] = e["dwell_ms"]
    for k_src, k_dst in (("error_code", "error_code"), ("product", "product"), ("amount", "amount"),
                         ("otp_channel_v2", "otp_channel_v2"), ("tap_x", "tap_x"), ("tap_y", "tap_y")):
        if e.get(k_src) is not None:
            params[k_dst] = e[k_src]
    rec = {"_dataset": DATASET, "platform": "app", "event_id": f"evt_{n:07d}", "session_id": sid,
           "user_id": user["uid"], "timestamp": ts.astimezone(JKT).isoformat(timespec="milliseconds"),
           "event_name": EVT_APP[e["type"]], "screen_name": SCREEN_RAW[e["screen"]]}
    if e.get("element"):
        rec["target"] = e["element"]
    rec["user_properties"] = {"segment": user["persona"], "app_version": ver}
    rec["device_info"] = {"os": dev["os"], "os_version": dev["os_version"], "model": dev["model"], "device_id": dev["id"]}
    if params:
        rec["params"] = params
    return rec


def build(seed: int):
    rng = random.Random(seed)
    noise = random.Random(seed + 1)
    users, devices = make_users_and_devices(rng)
    pw = {p: product_weights(noise, p) for p, _ in POPULATION}
    sessions, all_events = [], []     # all_events: (ts, session_no, idx, event, user)

    def run(user, journey, t0, product=None):
        ev, out = simulate(rng, user, journey, t0, product)
        sno = len(sessions)
        out["sno"] = sno
        silent = False
        if out["ver"] == "4.12" and "kyc_selfie" in out["screens"] and out["t0"] >= G1_START:
            out["g1_exposed"] = True
            silent = rng.random() < G1_DROP
        out["g1_silent"] = silent
        if silent:
            ev = [e for e in ev if e["screen"] != "kyc_selfie"]
        sessions.append(out)
        for i, e in enumerate(ev):
            all_events.append((e["ts"], sno, i, e, user))
        return out

    for user in users:
        persona = user["persona"]
        slots = []     # (journey, product)
        target = {}
        if persona == "unregistered":
            nb = rng.randint(3, 5)
            target["register"] = 5 + (rng.random() < 0.2)
            s_u = START + timedelta(days=rng.uniform(-3, 20))          # when this person first shows up
            first_reg = s_u + timedelta(days=4, hours=rng.uniform(0, 12))
            browse = [time_between(rng, persona, max(s_u, START), first_reg - timedelta(minutes=10)) for _ in range(nb)]
            reg = sorted([first_reg] + [time_between(rng, persona, first_reg, END - timedelta(minutes=10))
                                        for _ in range(target["register"] - 1)])
            plan = [(t, ("browse", None)) for t in sorted(browse)] + [(t, ("register", None)) for t in reg]
        else:
            target = {"register": 1, "login": 5 + (rng.random() < 0.15), "topup": 5 + (rng.random() < 0.15),
                      "transaction": rng.randint(10, 14) if persona == "individual_trader" else 5 + (rng.random() < 0.15)}
            slots = [("register", None)] + [(j, None) for j in ("login", "topup", "transaction") for _ in range(target[j])]
            rng.shuffle(slots)       # the single register-flow session (re-verification) may fall anywhere in the window
            plan = list(zip(plan_times(rng, persona, len(slots)), slots))
        done = Counter()
        for t, (j, _) in plan:
            prod = rng.choices(PRODUCTS, pw[persona])[0] if j == "transaction" else None
            out = run(user, j, t, prod)
            done[j] += out["completed"]
        for j in target:
            tries = 0
            while done[j] < target[j] and tries < 60:
                tries += 1
                t = sample_time(rng, persona) if persona != "fraudster" else plan_times(rng, persona, 1)[0]
                prod = rng.choices(PRODUCTS, pw[persona])[0] if j == "transaction" else None
                done[j] += run(user, j, t, prod)["completed"]
    web_sessions, web_events = build_web(seed, users)      # independent RNG stream (seed+50): never touches `rng` above
    offset = len(sessions)
    for s in web_sessions:
        s["sno"] += offset
    for ts, sno, i, e, user in web_events:
        all_events.append((ts, sno + offset, i, e, user))
    sessions.extend(web_sessions)
    all_events.sort(key=lambda x: (x[0], x[1], x[2]))
    return users, devices, sessions, all_events


def assemble(seed: int, all_events: list, rng, sess_of: list):
    """Assign ids, then apply the delivery faults that happen after the id is assigned."""
    rows, dup_events, lost = [], Counter(), Counter()
    by_day = Counter(e[0].date() for e in all_events)
    lose_budget = round(G2_LOSS * by_day[G2_DAY.date()])
    day_idx = [i for i, e in enumerate(all_events) if e[0].date() == G2_DAY.date()]
    lose = set(rng.sample(day_idx, lose_budget))
    for n, (ts, sno, i, e, user) in enumerate(all_events, 1):
        sess = sess_of[sno]
        if sess.get("platform") == "web":
            rec = render_raw_web(user, f"s_{sno + 1:06d}", e, n, sess["device_class"])
        else:
            rec = render_raw(user, f"s_{sno + 1:06d}", e, n, rng, sess["ver"])
        if n - 1 in lose:
            lost["lost_rows"] += 1
            lost[e["type"]] += 1
            continue
        rows.append(rec)
        if user["dev"]["os"] == "android" and G4_START <= ts < G4_END and e["screen"] == "txn_checkout":
            rows.append(rec)
            dup_events["duplicated"] += 1
    return rows, dup_events, lost


def rate(num, den):
    return round(num / den, 4) if den else None


def ground_truth(seed, users, devices, sessions, n_rows, dup, lost, n_events_before) -> dict:
    by_p = Counter(u["persona"] for u in users)
    dev_users = Counter({d["id"]: len(d["users"]) for d in devices})
    os_users = Counter(u["dev"]["os"] for u in users)
    S = sessions
    comp = defaultdict(Counter)       # uid -> journey -> completed
    for s in S:
        comp[s["user"]][s["journey"]] += s["completed"]
    min_done = {}
    for j in ("register", "login", "topup", "transaction"):
        who = [u for u in users if (u["persona"] == "unregistered") == (j == "register")]
        min_done[j] = min(comp[u["uid"]][j] for u in who)
    reached = lambda scr, grp: [s for s in grp if scr in s["screens"]]
    exits_at = lambda scr, grp: sum(s["last"] == scr for s in grp)

    pd = reached("personal_data", S)
    tin = reached("tin", S)
    ctrl = {"personal_data_exit_rate": rate(exits_at("personal_data", pd), len(pd)), "personal_data_sessions": len(pd),
            "tin_exit_rate": rate(exits_at("tin", tin), len(tin)), "tin_sessions": len(tin),
            "personal_data_exit_rate_by_persona": {p: rate(exits_at("personal_data", [s for s in pd if s["persona"] == p]), len([s for s in pd if s["persona"] == p])) for p in by_p},
            "tin_exit_rate_by_persona": {p: rate(exits_at("tin", [s for s in tin if s["persona"] == p]), len([s for s in tin if s["persona"] == p])) for p in by_p}}

    otp = reached("otp", S)
    inw = [s for s in otp if s["in_otp_window"]]
    outw = [s for s in otp if not s["in_otp_window"]]
    p1 = {"window_utc": [iso_ms(OTP_START), iso_ms(OTP_END)], "otp_sessions_in_window": len(inw),
          "stall_share_in_window": rate(sum(s["stalled"] for s in inw), len(inw)),
          "otp_exit_rate_in_window": rate(exits_at("otp", inw), len(inw)),
          "otp_exit_rate_outside": rate(exits_at("otp", outw), len(outw)), "otp_sessions_outside": len(outw),
          "resend_rage_taps_in_window": sum(s["rage"] for s in inw if s["stalled"])}

    tops = [s for s in reached("topup_confirm", S)]
    lb = [s for s in tops if s["persona"] == "large_business"]
    oth = [s for s in tops if s["persona"] != "large_business"]
    p2 = {"threshold_php": TOPUP_BIG_MIN, "large_business_topups": len(lb),
          "large_business_share_above_threshold": rate(sum(s["amount"] > TOPUP_BIG_MIN for s in lb), len(lb)),
          "large_business_median_php": int(median(s["amount"] for s in lb)),
          "others_topups": len(oth), "others_max_php": max(s["amount"] for s in oth),
          "others_median_php": int(median(s["amount"] for s in oth)),
          "others_share_above_5000": rate(sum(s["amount"] > 5000 for s in oth), len(oth))}

    tx = [s for s in S if s["journey"] == "transaction"]
    share = {p: rate(sum(s["product"] == "eload" for s in tx if s["persona"] == p), len([s for s in tx if s["persona"] == p])) for p in by_p if p != "unregistered"}
    pers_top = {p: max(((rate(sum(s["product"] == q for s in tx if s["persona"] == p), len([s for s in tx if s["persona"] == p])), q) for q in PRODUCTS)) for p in share}
    p3 = {"persona": "sari_sari", "product": "eload", "eload_share_sari_sari": share["sari_sari"],
          "eload_share_by_persona": share, "top_product_share_by_persona": {p: list(v) for p, v in pers_top.items()},
          "transactions_sari_sari": len([s for s in tx if s["persona"] == "sari_sari"])}

    co = [s for s in reached("txn_checkout", S)]
    tr = [s for s in co if s["persona"] == "individual_trader" and s["product"] == "send_money"]
    others = [s for s in co if not (s["persona"] == "individual_trader" and s["product"] == "send_money")]
    p4 = {"segment_sessions_at_checkout": len(tr), "segment_abandon_rate": rate(exits_at("txn_checkout", tr), len(tr)),
          "others_abandon_rate": rate(exits_at("txn_checkout", others), len(others)),
          "trader_other_products_abandon_rate": rate(exits_at("txn_checkout", [s for s in co if s["persona"] == "individual_trader" and s["product"] != "send_money"]), len([s for s in co if s["persona"] == "individual_trader" and s["product"] != "send_money"])),
          "send_money_other_personas_abandon_rate": rate(exits_at("txn_checkout", [s for s in co if s["persona"] != "individual_trader" and s["product"] == "send_money"]), len([s for s in co if s["persona"] != "individual_trader" and s["product"] == "send_money"]))}

    dev_cls = {d["id"]: d["cls"] for d in devices}
    oos = [s for s in tops if s["persona"] == CONF_OOS_PERSONA and dev_cls.get(s["dev"]) == CONF_OOS_DEVICE]
    oos_rest = [s for s in tops if not (s["persona"] == CONF_OOS_PERSONA and dev_cls.get(s["dev"]) == CONF_OOS_DEVICE)]
    p5 = {"segment": {"persona": CONF_OOS_PERSONA, "device_class": CONF_OOS_DEVICE}, "screen": CONF_OOS_SCREEN,
          "segment_sessions": len(oos), "segment_abandon_rate": rate(exits_at(CONF_OOS_SCREEN, oos), len(oos)),
          "others_abandon_rate": rate(exits_at(CONF_OOS_SCREEN, oos_rest), len(oos_rest)),
          "segment_dead_taps": sum(s["dead"] for s in oos), "segment_rage_taps": sum(s["rage"] for s in oos),
          "segment_error_sessions": sum(s["errors"] > 0 for s in oos)}

    log_ph = reached(P7_SCREEN, S)
    p7seg = [s for s in log_ph if s["persona"] == P7_PERSONA and dev_cls.get(s["dev"]) == P7_DEVICE]
    p7rest = [s for s in log_ph if not (s["persona"] == P7_PERSONA and dev_cls.get(s["dev"]) == P7_DEVICE)]
    p7 = {"segment": {"persona": P7_PERSONA, "device_class": P7_DEVICE}, "screen": P7_SCREEN,
          "segment_sessions": len(p7seg), "segment_abandon_rate": rate(exits_at(P7_SCREEN, p7seg), len(p7seg)),
          "others_abandon_rate": rate(exits_at(P7_SCREEN, p7rest), len(p7rest)),
          "segment_error_sessions": sum(s["errors"] > 0 for s in p7seg), "segment_rage_taps": sum(s["rage"] for s in p7seg)}

    topam = reached(P8_SCREEN, S)
    p8seg = [s for s in topam if s["persona"] == P8_PERSONA and dev_cls.get(s["dev"]) == P8_DEVICE]
    p8rest = [s for s in topam if not (s["persona"] == P8_PERSONA and dev_cls.get(s["dev"]) == P8_DEVICE)]
    p8 = {"segment": {"persona": P8_PERSONA, "device_class": P8_DEVICE}, "screen": P8_SCREEN,
          "segment_sessions": len(p8seg), "segment_abandon_rate": rate(exits_at(P8_SCREEN, p8seg), len(p8seg)),
          "others_abandon_rate": rate(exits_at(P8_SCREEN, p8rest), len(p8rest)),
          "segment_dead_taps": sum(s["dead"] for s in p8seg), "segment_rage_taps": sum(s["rage"] for s in p8seg),
          "segment_error_sessions": sum(s["errors"] > 0 for s in p8seg)}

    web = [s for s in S if s["journey"] == "web_checkout"]
    wpay = reached(P6_SCREEN, web)
    wmob = [s for s in wpay if s.get("device_class") == P6_DEVICE]
    wdesk = [s for s in wpay if s.get("device_class") != P6_DEVICE]
    p6 = {"platform": "web", "segment": {"device_class": P6_DEVICE}, "screen": P6_SCREEN,
          "segment_sessions": len(wmob), "segment_abandon_rate": rate(exits_at(P6_SCREEN, wmob), len(wmob)),
          "others_abandon_rate": rate(exits_at(P6_SCREEN, wdesk), len(wdesk)), "others_sessions": len(wdesk),
          "web_sessions_total": len(web)}

    fr = [s for s in S if s["persona"] == "fraudster"]
    nf = [s for s in S if s["persona"] != "fraudster" and s["journey"] != "browse"]
    fr_dev = [d for d in devices if any(u in {x["uid"] for x in users if x["persona"] == "fraudster"} for u in d["users"])]
    odd = sum((s["t0"].hour + 7) % 24 < 6 for s in fr)
    fail = lambda g: rate(sum(not s["completed"] for s in g), len(g))
    m1 = {"fraudster_users": by_p["fraudster"], "sessions": len(fr), "failed_session_rate": fail(fr),
          "others_failed_session_rate": fail(nf), "odd_hour_share_00_06_wib": rate(odd, len(fr)),
          "devices_used": len(fr_dev), "max_users_per_fraud_device": max(len(d["users"]) for d in fr_dev),
          "abandon_rate_checkout": rate(exits_at("txn_checkout", [s for s in co if s["persona"] == "fraudster"]), len([s for s in co if s["persona"] == "fraudster"])),
          "abandon_rate_topup_confirm": rate(exits_at("topup_confirm", [s for s in tops if s["persona"] == "fraudster"]), len([s for s in tops if s["persona"] == "fraudster"])),
          "otp_exit_rate": rate(exits_at("otp", [s for s in otp if s["persona"] == "fraudster"]), len([s for s in otp if s["persona"] == "fraudster"]))}

    pr = [s for s in S if s["journey"] == "browse"]
    by_user = Counter(s["user"] for s in pr)
    first_reg = {}
    for s in S:
        if s["journey"] == "register" and s["persona"] == "unregistered":
            first_reg[s["user"]] = min(first_reg.get(s["user"], s["t0"]), s["t0"])
    before = Counter(s["user"] for s in pr if s["t0"] < first_reg.get(s["user"], END))
    pricing_all = reached("prices", S)
    m2 = {"unregistered_users": by_p["unregistered"], "price_sessions": len(pr), "price_session_exit_rate": rate(exits_at("prices", pricing_all), len(pricing_all)),
          "min_price_sessions_per_user": min(by_user.values()), "users_with_3plus_price_sessions_before_first_register": sum(v >= 3 for v in before.values())}

    kyc = [s for s in S if s.get("g1_exposed")]
    g1 = {"screen": "kyc_selfie", "app_version": "4.12", "silent_from_utc": iso_ms(G1_START),
          "first_exposed_session_utc": iso_ms(min(s["t0"] for s in kyc)),
          "first_silent_session_utc": iso_ms(min(s["t0"] for s in kyc if s["g1_silent"])),
          "sessions_exposed": len(kyc), "sessions_silent": sum(s["g1_silent"] for s in kyc),
          "measured_drop": rate(sum(s["g1_silent"] for s in kyc), len(kyc)), "planted_drop": G1_DROP}
    otp_v2 = [s for s in S if s["ver"] == "4.12" and "otp" in s["screens"]]
    span_h = (END - V412_DATE).total_seconds() / 3600
    g3 = {"property": "otp_channel_v2", "since_utc": iso_ms(V412_DATE), "events": None, "events_per_hour": None,
          "sessions_with_property": len(otp_v2)}
    return {
        "dataset": DATASET, "synthetic": True, "seed": seed,
        "label": "SYNTHETIC DATA: generated by pipeline/generate_v2.py, not real users",
        "window_utc": [iso_ms(START), iso_ms(END)],
        "counts": {"users": len(users), "sessions": len(S), "events_written": n_rows, "events_before_loss": n_events_before,
                   "sessions_by_journey": dict(Counter(s["journey"] for s in S))},
        "population": {"users_by_persona": dict(by_p), "registered": len(users) - by_p["unregistered"],
                       "android_users": os_users["android"], "ios_users": os_users["ios"],
                       "android_share": rate(os_users["android"], len(users)), "devices": len(devices),
                       "max_users_per_device": max(dev_users.values()),
                       "devices_with_more_than_one_user": sum(v > 1 for v in dev_users.values()),
                       "device_classes": dict(Counter(d["cls"] for d in devices)),
                       "min_completed_attempts": min_done},
        "control": ctrl, "_g3": g3, "_span_h": span_h,
        "measured": {"P1": p1, "P2": p2, "P3": p3, "P4": p4, "P5": p5, "P6": p6, "P7": p7, "P8": p8, "M1": m1, "M2": m2},
        "faults": {"G1": g1, "G2": {"day_utc": G2_DAY.date().isoformat(), "planted_loss": G2_LOSS, "rows_lost": lost["lost_rows"]},
                   "G3": g3, "G4": {"screen": "txn_checkout", "os": "android", "from_utc": iso_ms(G4_START), "to_utc": iso_ms(G4_END),
                                    "duplicated_events": dup["duplicated"], "fixed_in": "4.11.2", "status": "resolved"}},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/synthetic")
    args = ap.parse_args()

    users, devices, sessions, all_events = build(args.seed)
    rng = random.Random(args.seed + 2)
    day_total = sum(e[0].date() == G2_DAY.date() for e in all_events)
    rows, dup, lost = assemble(args.seed, all_events, rng, sessions)
    gt = ground_truth(args.seed, users, devices, sessions, len(rows), dup, lost, len(all_events))
    gt["faults"]["G2"]["events_that_day_before_loss"] = day_total
    gt["faults"]["G2"]["measured_loss"] = rate(lost["lost_rows"], day_total)
    gt["faults"]["G2"]["lost_by_event_type"] = {k: v for k, v in lost.items() if k != "lost_rows"}
    g3 = gt.pop("_g3")
    span_h = gt.pop("_span_h")
    n_prop = sum(1 for r in rows if "otp_channel_v2" in r.get("params", {}))
    g3["events"] = n_prop
    g3["events_per_hour"] = round(n_prop / span_h, 2)
    gt["faults"]["G3"] = g3
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "events_raw.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    add_expectations(gt)
    (out / "ground_truth.json").write_text(json.dumps(gt, indent=2) + "\n", encoding="utf-8")
    size = (out / "events_raw.jsonl").stat().st_size / 1e6
    print(f"{len(sessions)} sessions, {len(rows)} events, {size:.1f} MB -> {out}/events_raw.jsonl")
    print(json.dumps({k: gt[k] for k in ("counts", "population")}, indent=2))


def add_expectations(gt: dict) -> None:
    m, f = gt["measured"], gt["faults"]
    gt["must_flag"] = [
        {"id": "P1_otp_not_delivered", "kind": "problem", "screen": "otp", "scope": "burst",
         "segment": "all users (register and login), time window", "window_utc": m["P1"]["window_utc"],
         "expected_class": "technical_fault", "expected_signal": "drop-off and resend rage taps on the otp screen, only inside the window",
         "measured": m["P1"]},
        {"id": "P4_trader_send_money_checkout", "kind": "problem", "screen": "txn_checkout", "scope": "segment",
         "segment": {"persona": "individual_trader", "product": "send_money"},
         "expected_class": "technical_bug_or_ux_friction",
         "expected_signal": "abandon at checkout far above everyone else, with rage taps, dead taps and payment_timeout errors",
         "measured": m["P4"]},
        {"id": "P5_confirm_button_out_of_screen", "kind": "problem", "screen": CONF_OOS_SCREEN, "scope": "segment",
         "segment": {"persona": CONF_OOS_PERSONA, "device_class": CONF_OOS_DEVICE},
         "expected_class": "technical_bug_or_ux_friction",
         "expected_signal": "abandon at topup_confirm far above everyone else, with dead and rage taps near the bottom of the screen, no error code",
         "measured": m["P5"]},
        {"id": "P6_web_mobile_bank_redirect", "kind": "problem", "screen": P6_SCREEN, "scope": "segment",
         "segment": {"device_class": P6_DEVICE}, "expected_class": "unclassified_needs_review or technical_bug_or_ux_friction",
         "expected_signal": "abandon at the bank-redirect step far above web desktop, mostly silent (no error, no rage), "
                             "platform=web only; the weak signal sits at the rule table's confidence edge, so the exact "
                             "class can vary a little by seed (see watchdog.py verify())",
         "measured": m["P6"]},
        {"id": "P7_individual_ios_login_autofill", "kind": "problem", "screen": P7_SCREEN, "scope": "segment",
         "segment": {"persona": P7_PERSONA, "device_class": P7_DEVICE},
         "expected_class": "technical_bug_or_ux_friction",
         "expected_signal": "abandon at login_phone far above everyone else, with a phone-format error and some rage taps on Log in",
         "measured": m["P7"]},
        {"id": "P8_large_business_android_topup_amount", "kind": "problem", "screen": P8_SCREEN, "scope": "segment",
         "segment": {"persona": P8_PERSONA, "device_class": P8_DEVICE},
         "expected_class": "technical_bug_or_ux_friction",
         "expected_signal": "abandon at topup_amount far above everyone else, with dead and rage taps on Continue, mostly no error code",
         "measured": m["P8"]},
        {"id": "M1_fraudster_bursts", "kind": "problem", "screen": "any", "scope": "segment", "segment": {"persona": "fraudster"},
         "expected_class": "unclassified_needs_review",
         "expected_signal": "failed attempts in bursts at odd hours, up to 5 users per device",
         "measured": m["M1"]},
    ]
    gt["must_flag_patterns"] = [
        {"id": "P2_large_business_topup_amount", "kind": "pattern", "persona": "large_business", "threshold_php": TOPUP_BIG_MIN,
         "expected_class": "behavior_pattern", "measured": m["P2"]},
        {"id": "P3_sari_sari_eload", "kind": "pattern", "persona": "sari_sari", "product": "eload",
         "expected_class": "behavior_pattern", "measured": m["P3"]},
    ]
    gt["must_not_flag_as_problem"] = [
        {"id": "M2_unregistered_price_checks", "screen": "prices", "expected_class": "natural_exit", "measured": m["M2"]},
        {"id": "P3_sari_sari_eload", "note": "expected behavior, listed as a pattern only"},
        {"id": "P2_large_business_topup_amount", "note": "behavior pattern, listed as a pattern only"},
        {"id": "control_personal_data_tin", "screens": ["personal_data", "tin"], "note": "steady drop-off all window, every persona; not a candidate",
         "measured": gt["control"]},
    ]
    gt["guardian_must_catch"] = [
        {"id": "G1_kyc_selfie_tracker_silent", "expected_status": "active", **f["G1"]},
        {"id": "G2_missing_partition", "expected_status": "active", **f["G2"]},
        {"id": "G3_unmapped_property", "expected_status": "active", **f["G3"]},
        {"id": "G4_checkout_double_fire", "expected_status": "resolved", **f["G4"]},
    ]


if __name__ == "__main__":
    main()
