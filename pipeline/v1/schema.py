"""Canonical event schema for Squint.

Everything downstream of normalize.py (Guardian, Watchdog, Diagnostic Agent, UI) reads
only these fields. Raw source fields never leak past the mapping step; the original
record is kept under `raw` so the Diagnostic Drawer can show it as evidence.

Canonical event (one JSON object per line in canonical_events.jsonl):

    event_id      str        unique event id (required)
    session_id    str        session the event belongs to (required)
    user_id       str|None
    ts            str        UTC ISO-8601 with milliseconds and trailing Z (required)
    platform      str        "web" | "app" (required)
    event_type    str        one of EVENT_TYPES, or "unknown" when the raw name is unmapped (required)
    screen        str|None   canonical screen name, e.g. "kyc_identity"
    element       str|None   UI element id, e.g. "kyc_tooltip"
    persona       str|None   "enterprise" | "smb" | "retail"
    os            str|None
    os_version    str|None
    device_model  str|None
    viewport_w    int|None
    dwell_ms      int|None   time on screen (set on screen_leave)
    scroll_depth  float|None 0.0-1.0
    error_code    str|None
    dataset       str|None   dataset label, e.g. "synthetic-v1"
    unmapped      list[str]  canonical fields whose raw value had no mapping (omitted when empty)
    raw           object     the original source record, untouched
"""
from __future__ import annotations

EVENT_TYPES = {
    "screen_view",
    "screen_leave",
    "click",
    "form_focus",
    "scroll",
    "rage_click",
    "error",
    "session_end",
}
PLATFORMS = {"web", "app"}
PERSONAS = {"enterprise", "smb", "retail"}

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
    sd = event.get("scroll_depth")
    if isinstance(sd, (int, float)) and not 0 <= sd <= 1:
        problems.append(f"scroll_depth out of range: {sd}")
    return problems
