"""Canonical event schema (Squint, dataset synthetic-v2).

Everything downstream of normalize.py (Guardian, Watchdog, Diagnostic Agent, UI) reads
only these fields. Raw source fields never leak past the mapping step. Unless the mapping sets
`"keep_raw": false`, the original record is kept under `raw`; synthetic-v2 sets it to false to keep
the canonical file small, and build_results.py re-reads the raw file for the few evidence sessions.

Canonical event (one JSON object per line in canonical_events.jsonl):

    event_id      str        unique event id (required)
    session_id    str        session the event belongs to (required)
    user_id       str|None
    ts            str        UTC ISO-8601 with milliseconds and trailing Z (required)
    platform      str        "web" | "app" (required; synthetic-v2 is app only)
    event_type    str        one of EVENT_TYPES, or "unknown" when the raw name is unmapped (required)
    screen        str|None   canonical screen name, e.g. "otp"
    element       str|None   UI element id, e.g. "resend"
    persona       str|None   one of PERSONAS
    os            str|None
    os_version    str|None
    device_model  str|None
    device_id     str|None   (v2) at most 5 distinct user_ids per device_id
    device_class  str|None   (v2) "android_low" | "android_mid" | "ios"
    app_version   str|None   (v2)
    product       str|None   (v2) one of PRODUCTS, on events after a product is chosen
    amount_php    int|float|None (v2) top-up or transaction amount in PHP
    step          str|None   (v2) journey step id (see SCREEN_STEP)
    tap_x, tap_y  float|None (v2) tap position 0-1 relative to the screen, on click / rage_click / dead_tap
    viewport_w    int|None
    dwell_ms      int|None   time on screen (set on screen_leave)
    scroll_depth  float|None 0.0-1.0
    error_code    str|None
    dataset       str|None   dataset label, e.g. "synthetic-v2"
    unmapped      list[str]  canonical fields whose raw value had no mapping, or "prop:<raw path>" for a
                             raw property the mapping does not list (omitted when empty)
    raw           object     the original source record (optional, see above)

v2 additions are additive: every v1 field is unchanged.
"""
from __future__ import annotations

EVENT_TYPES = {
    "screen_view",
    "screen_leave",
    "click",
    "form_focus",
    "scroll",
    "rage_click",
    "dead_tap",      # v2: a tap that did nothing
    "back",          # v2: user pressed back
    "error",
    "session_end",
}
PLATFORMS = {"web", "app"}
PERSONAS_V1 = {"enterprise", "smb", "retail"}
PERSONAS = {"unregistered", "large_business", "sari_sari", "individual_trader", "individual", "unknown", "fraudster"}
PERSONA_LABELS = {"unregistered": "Unregistered", "large_business": "Large business", "sari_sari": "Retail",
                  "individual_trader": "Individual trader", "individual": "Individual", "unknown": "Unknown",
                  "fraudster": "Fraudster"}
PRODUCTS = ["eload", "water_bill", "electricity_bill", "game_voucher", "cable_internet", "send_money", "postpaid_telecom"]
PRODUCT_LABELS = {"eload": "E-load", "water_bill": "Water bills", "electricity_bill": "Electricity bills",
                  "game_voucher": "Game voucher", "cable_internet": "Cable TV and internet",
                  "send_money": "Send money", "postpaid_telecom": "Post-paid telecom"}
DEVICE_CLASSES = {"android_low", "android_mid", "ios"}
DEVICE_CLASS_LABELS = {"android_low": "Android (low-end)", "android_mid": "Android (mid/high)", "ios": "iOS"}

# Journeys: ordered screens. `otp` is shared by register and login. Terminal screens end a journey with success.
JOURNEYS = {
    "browse": ["prices"],
    "register": ["welcome", "register_phone", "otp", "personal_data", "tin", "kyc_selfie", "register_done"],
    "login": ["login_phone", "otp", "home"],
    "topup": ["wallet", "topup_amount", "topup_confirm", "topup_done"],
    "transaction": ["product_list", "txn_details", "txn_checkout", "txn_done"],
}
JOURNEY_LABELS = {"browse": "Browse prices", "register": "Register", "login": "Login", "topup": "Wallet top-up",
                  "transaction": "Transaction"}
TERMINAL_SCREENS = {"register_done", "home", "topup_done", "txn_done"}
SCREEN_LABELS = {
    "prices": "Prices", "welcome": "Welcome", "register_phone": "Register: phone number", "otp": "OTP code",
    "personal_data": "Personal data", "tin": "TIN", "kyc_selfie": "KYC selfie", "register_done": "Registered",
    "login_phone": "Login: phone number", "home": "Home", "wallet": "Wallet", "topup_amount": "Top-up amount",
    "topup_confirm": "Top-up confirm", "topup_done": "Top-up done",
    "product_list": "Choose product", "txn_details": "Transaction details", "txn_checkout": "Checkout and PIN",
    "txn_done": "Transaction done",
}
SCREEN_STEP = {  # screen -> journey step id
    "prices": "browse", "welcome": "start", "register_phone": "phone", "login_phone": "phone", "otp": "otp",
    "personal_data": "personal_data", "tin": "tin", "kyc_selfie": "kyc", "register_done": "done", "home": "done",
    "wallet": "start", "topup_amount": "amount", "topup_confirm": "confirm",
    "topup_done": "done", "product_list": "product", "txn_details": "details", "txn_checkout": "checkout",
    "txn_done": "done",
}


# The active dataset profile (profiles/__init__.py) may relabel screens, journeys, personas and products. The internal ids never change.
from profiles import load as _load_profile   # noqa: E402

_P = _load_profile()
for _name in ("JOURNEYS", "SCREEN_LABELS", "JOURNEY_LABELS", "PERSONA_LABELS", "PRODUCT_LABELS", "DEVICE_CLASS_LABELS"):   # JOURNEYS: only the paths a profile reorders
    if _name in _P:
        globals()[_name].update(_P[_name])


def journey_of(screens) -> str | None:
    """Which journey a session belongs to, from the set of screens it viewed (otp is shared, so it is ignored)."""
    s = set(screens)
    for j in ("transaction", "topup", "register", "login", "browse"):
        if s & (set(JOURNEYS[j]) - {"otp"}):
            return j
    return None


# field -> (python types, required)
FIELDS = {
    "event_id": (str, True),
    "session_id": (str, True),
    "user_id": (str, False),
    "ts": (str, True),
    "platform": (str, True),
    "event_type": (str, True),
    "screen": (str, False),
    "element": (str, False),
    "persona": (str, False),
    "os": (str, False),
    "os_version": (str, False),
    "device_model": (str, False),
    "device_id": (str, False),
    "device_class": (str, False),
    "app_version": (str, False),
    "product": (str, False),
    "amount_php": ((int, float), False),
    "step": (str, False),
    "tap_x": ((int, float), False),
    "tap_y": ((int, float), False),
    "viewport_w": (int, False),
    "dwell_ms": (int, False),
    "scroll_depth": ((int, float), False),
    "error_code": (str, False),
    "dataset": (str, False),
    "unmapped": (list, False),
    "raw": (dict, False),
}


def validate_event(event: dict) -> list[str]:
    """Return a list of problems with a canonical event (empty list means valid)."""
    problems = []
    for name, (types, required) in FIELDS.items():
        value = event.get(name)
        if value is None:
            if required:
                problems.append(f"missing required field: {name}")
            continue
        if not isinstance(value, types) or isinstance(value, bool):
            problems.append(f"bad type for {name}: {type(value).__name__}")
    extra = set(event) - set(FIELDS)
    if extra:
        problems.append(f"unknown fields: {sorted(extra)}")
    et = event.get("event_type")
    if et is not None and et != "unknown" and et not in EVENT_TYPES:
        problems.append(f"bad event_type: {et}")
    pf = event.get("platform")
    if pf is not None and pf not in PLATFORMS:
        problems.append(f"bad platform: {pf}")
    for fld, allowed in (("persona", PERSONAS), ("device_class", DEVICE_CLASSES), ("product", set(PRODUCTS)), ("screen", set(SCREEN_LABELS))):
        if event.get(fld) is not None and event[fld] not in allowed:
            problems.append(f"unknown {fld}: {event[fld]}")
    for fld in ("tap_x", "tap_y"):
        v = event.get(fld)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and not 0 <= v <= 1:
            problems.append(f"{fld} out of range: {v}")
    sd = event.get("scroll_depth")
    if isinstance(sd, (int, float)) and not 0 <= sd <= 1:
        problems.append(f"scroll_depth out of range: {sd}")
    return problems
