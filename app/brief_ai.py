"""Brief rewrite endpoint: the "Rewrite with Gemini" button on the Brief tab. See docs/brief-ai-endpoint.md.

BUILT BUT OFF. Nothing here runs unless BRIEF_AI_ENABLED=1, on any machine (local or platform). Until the owner switches it on, the Brief
shows its standard wording and the button is not drawn.

POST /api/brief-ai {"range": "7d", "platform": "all", "persona": "all", "ids": ["<finding id>", ...], "again": false}. Gemini rewrites only
the WORDING of the Brief: a headline, a second line, one line per driver and up to three next steps. The numbers (the three tiles, the
finding titles, the chart) stay computed by code. The server builds the facts itself from results.json (SYNTHETIC) for that view and those
findings; the client sends ids, never facts.

Every number in the answer must exist in the facts, otherwise the whole answer is thrown away and the standard wording stays. One live
call per click, with a saved first answer per view and findings, a 30 s cooldown and 4 live calls per visitor, view and hour, the
per-visitor and daily limits shared with the Ask endpoint, and a kill switch. Logs carry counts and reason codes only.

BRIEF_AI_MOCK=1 answers from a canned output without network (tests, previews).
"""
import hashlib
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

import ask_gemini as ask          # shared helpers: grounding limits, daily counter, client

log = logging.getLogger("brief_ai")
bp = Blueprint("brief_ai", __name__)

PROMPT_VERSION = "br-v6"
COOLDOWN_S = 30
LIVE_PER_HOUR = 4
MAX_BODY = 1024
RANGES = {"24h", "7d", "30d"}
OWNERS = ("Engineering", "Design", "Product", "Support", "Data")
SMALL = {1.0, 2.0, 3.0, 7.0, 24.0, 30.0}          # counts and window lengths the wording may use without them being in the facts
NOTICE = "Wording by Gemini from the numbers on this page. Code checked every number. AI can make mistakes."
_lock = threading.Lock()
_recent = {}          # (visitor hash, cache key) -> live-call timestamps


def enabled_state():
    return os.environ.get("BRIEF_AI_ENABLED") == "1"


def mock():
    return os.environ.get("BRIEF_AI_MOCK") == "1"


# ---------------------------------------------------------------- facts

def _pct(x):
    return None if x is None else round(x, 1)


def brief_facts(r, rng, platform, persona, ids):
    """(facts dict, finding ids used) for one view and the findings the Brief shows, or None if anything is not available."""
    if rng not in RANGES or persona in ask.HIDDEN_PERSONAS:
        return None
    v = r.get("views", {}).get(f"{rng}|{platform}|{persona}")
    if not v:
        return None
    by = {i.get("id"): i for i in r.get("insights", [])}
    items, used = [], []
    for fid in ids:
        i = by.get(fid)
        if i is None or fid not in v.get("insight_ids", []) or i.get("severity") == "healthy":
            return None
        pids = i.get("persona_ids") or []
        if pids and all(p in ask.HIDDEN_PERSONAS for p in pids):
            return None
        dg = i.get("diagnosis") or {}
        ok_ai = dg.get("status") in ("done", "cached") and dg.get("source") != "unclassified"
        steps = [(s.get("text") if isinstance(s, dict) else s) for s in (dg.get("next_steps") or [])] if ok_ai else []
        items.append({
            "title": i.get("title"), "group": i.get("segment_text"), "screen": i.get("screen_label"), "sessions_affected": i.get("n_sessions"),
            "estimated_value_php_per_week": (i.get("impact") or {}).get("per_week_value") or None,
            "saved_reason": (dg.get("summary") if ok_ai else None) or ((i.get("causes") or [{}])[0] or {}).get("title"),
            "saved_next_steps": [s for s in steps if s][:2],
            "facts": (i.get("facts") or [])[:2],
        })
        used.append(fid)
    kp = {k.get("id"): k for k in v.get("kpis", [])}
    conv, risk, bs = kp.get("conversion"), kp.get("value_at_risk"), kp.get("blind_spots")
    rh = v.get("rhythm") or {}
    facts = {
        "window": rng, "user_group": persona, "sessions": v.get("sessions"),
        "completion": {"label": (conv or {}).get("label"), "percent": _pct((conv or {}).get("value")), "previous_percent": _pct((conv or {}).get("prev")),
                       "change_in_points": (round(abs(conv["value"] - conv["prev"]), 1) if conv.get("prev") is not None else None),
                       "direction": (None if conv.get("prev") is None else "down" if conv["value"] < conv["prev"] else "up" if conv["value"] > conv["prev"] else "flat")} if conv else None,
        "estimated_value_at_risk_php_per_week": (risk or {}).get("value"), "serious_problems": (bs or {}).get("value"),
        "exits_natural": sum(rh.get("natural") or []), "exits_frustrated": sum(rh.get("frustrated") or []),
        "findings": items,
    }
    return facts, used


# ---------------------------------------------------------------- the model

INSTRUCTION = (
    "You rewrite the wording of a one-page analytics brief for a mobile app. The data is SYNTHETIC.\n"
    "You get FACTS (numbers computed by code, plus earlier saved explanations). Write plain English for a busy product manager.\n"
    "Return JSON with:\n"
    "- headline: one sentence, at most 110 characters, the main takeaway for this user group.\n"
    "- sub: one short line, at most 90 characters, what is driving it.\n"
    "- drivers: exactly 2 items when FACTS has 2 or more findings (exactly 1 if it has 1): one sentence for each of the first two findings, in order, at most 130 characters each (short), saying the likely reason.\n"
    "- steps: up to 3 items, one per finding that has saved_next_steps, in order; each has owner (one of Engineering, Design, Product, Support, Data) "
    "and text (an imperative sentence, at most 120 characters).\n"
    "Rules:\n"
    "- Use only FACTS. Quote numbers exactly as written there. Never compute a new number, percentage or total, not even a difference: completion.change_in_points and completion.direction already give the change.\n"
    "- Write money as PHP with the amount and say it is estimated, for example: PHP 3,780 a week (estimated).\n"
    "- Say 'tracking fault' when the cause may be the data, and never present a cause as certain unless FACTS says so.\n"
    "- Never suggest forcing, tricking or pressuring users. No markdown, no links, no emoji.\n"
    "FACTS (synthetic):\n"
)
SCHEMA = {"type": "OBJECT", "properties": {
    "headline": {"type": "STRING"}, "sub": {"type": "STRING"},
    "drivers": {"type": "ARRAY", "items": {"type": "STRING"}},
    "steps": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "owner": {"type": "STRING", "enum": list(OWNERS)}, "text": {"type": "STRING"}}, "required": ["owner", "text"]}}},
    "required": ["headline", "sub", "drivers", "steps"]}


def _mock_out(facts):
    n = min(2, len(facts["findings"]))
    return {"headline": "Mock headline: the brief wording was rewritten.", "sub": "Mock second line.",
            "drivers": [f"Mock reason for finding {k + 1}." for k in range(n)],
            "steps": [{"owner": "Engineering", "text": f"Mock step {k + 1}."} for k, f in enumerate(facts["findings"][:3]) if f["saved_next_steps"]]}


def call_model(facts, facts_text, again, c):
    if mock():
        return _mock_out(facts)
    from google.genai import types
    cl = ask._get_client()
    if cl is None:
        return None
    conf = types.GenerateContentConfig(system_instruction=INSTRUCTION + facts_text, temperature=0.5 if again else 0.2, max_output_tokens=900,
                                       response_mime_type="application/json", response_schema=SCHEMA,
                                       thinking_config=types.ThinkingConfig(thinking_budget=0), http_options=types.HttpOptions(timeout=c["timeout_s"] * 1000))
    try:
        resp = cl.models.generate_content(model=ask.MODEL, contents="Rewrite the brief wording now.", config=conf)
        out = json.loads(resp.text)
        return out if isinstance(out, dict) else None
    except Exception as e:
        log.warning("brief_ai model_error type=%s status=%s", type(e).__name__, getattr(e, "code", None))
        return None


def _ok_text(x, limit):
    return isinstance(x, str) and 0 < len(x.strip()) <= limit and "http" not in x.lower() and "```" not in x and not re.search(r"[\x00-\x1f]", x)


def verify(out, facts, allowed):
    """Cleaned answer or None. Anything unexpected throws the whole answer away: the standard wording stays."""
    if not isinstance(out, dict):
        return None
    n_find = len(facts["findings"])
    want_drivers = min(2, n_find)
    drivers, steps = out.get("drivers"), out.get("steps")
    if not (_ok_text(out.get("headline"), 140) and _ok_text(out.get("sub"), 140) and isinstance(drivers, list) and isinstance(steps, list)):
        return None
    if isinstance(drivers, list) and len(drivers) > want_drivers:
        drivers = drivers[:want_drivers]            # one line per finding was asked for: keep the first two, never edit the wording
    if len(drivers) != want_drivers or not all(_ok_text(d, 280) for d in drivers):
        return None
    n_steps_max = sum(1 for f in facts["findings"][:3] if f["saved_next_steps"])
    steps = steps[:min(3, n_steps_max)]               # at most one step per finding that has saved steps: keep the first ones, never edit the wording
    for s in steps:
        if not isinstance(s, dict) or s.get("owner") not in OWNERS or not _ok_text(s.get("text"), 240):
            return None
    texts = [out["headline"], out["sub"]] + drivers + [s["text"] for s in steps]
    for t in texts:
        for x in ask._nums(re.sub(r"\b(?:19|20)\d\d-\d\d-\d\d\b", " ", t)):
            if x not in SMALL and not any(abs(x - a) < 1e-9 for a in allowed):
                return None                      # an invented figure: do not show any of it
    return {"headline": out["headline"].strip(), "sub": out["sub"].strip(), "drivers": [d.strip() for d in drivers],
            "steps": [{"owner": s["owner"], "text": s["text"].strip()} for s in steps]}


# ---------------------------------------------------------------- limits and cache

def take_slot(vh, key):
    """(allowed, retry_in_s, left). Cooldown between live calls per visitor and view, and a few calls per hour."""
    now = time.time()
    with _lock:
        ts = [t for t in _recent.get((vh, key), []) if now - t < 3600]
        if ts and now - ts[-1] < COOLDOWN_S:
            _recent[(vh, key)] = ts
            return False, int(COOLDOWN_S - (now - ts[-1])) + 1, max(0, LIVE_PER_HOUR - len(ts))
        if len(ts) >= LIVE_PER_HOUR:
            _recent[(vh, key)] = ts
            return False, 0, 0
        ts.append(now)
        _recent[(vh, key)] = ts
        if len(_recent) > 5000:
            for k in [k for k, v in _recent.items() if not v or now - v[-1] > 3600]:
                _recent.pop(k, None)
        return True, COOLDOWN_S, max(0, LIVE_PER_HOUR - len(ts))


def cache_path(key, rhash):
    return ask.data_dir() / ("br_" + hashlib.sha256(f"{key}|{rhash}|{PROMPT_VERSION}".encode()).hexdigest()[:40] + ".json")


def cache_put(p, obj, cmax):
    try:
        if sum(1 for _ in p.parent.glob("br_*.json")) >= cmax:
            return
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


# ---------------------------------------------------------------- routes

def reply(code, **body):
    return jsonify(body), code


def standard(reason, code_reason, retry=0):
    """The brief keeps its standard wording."""
    return reply(200, source="standard", reason=reason, reason_code=code_reason, retry_in_s=retry)


@bp.get("/api/brief-ai/status")
def status():
    on = enabled_state() and (mock() or ask._get_client() is not None)
    return reply(200, enabled=bool(on))


@bp.route("/api/brief-ai", methods=["POST", "GET", "OPTIONS"], provide_automatic_options=False)
def brief_ai():
    if request.method != "POST":
        resp, code = reply(405, error="method_not_allowed", reason="Use POST.")
        resp.headers["Allow"] = "POST"
        return resp, code
    request.max_content_length = MAX_BODY
    if (request.content_length or 0) > MAX_BODY:
        return reply(413, error="too_large", reason="Request body is too large.")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return reply(400, error="bad_input", reason="Send JSON.")
    rng, platform, persona, ids = body.get("range"), body.get("platform", "all"), body.get("persona"), body.get("ids")
    again = bool(body.get("again"))
    ds = ask.dataset_of(body)
    if ds is None:
        return reply(400, error="bad_input", reason="Unknown dataset.")
    if (not isinstance(rng, str) or not isinstance(platform, str) or not isinstance(persona, str) or not isinstance(ids, list)
            or not 1 <= len(ids) <= 3 or not all(isinstance(x, str) and 0 < len(x) <= 160 for x in ids) or len(set(ids)) != len(ids)
            or len(platform) > 20 or len(persona) > 40):
        return reply(400, error="bad_input", reason="Send range, platform, persona and 1 to 3 finding ids.")
    if not enabled_state():
        log.info("brief_ai outcome=off")
        return standard("Gemini wording is switched off here, so the standard brief stays.", "off")
    try:
        raw = ask.results_path(ds).read_bytes()
        r = json.loads(raw)
    except (OSError, ValueError):
        return reply(503, error="unavailable", reason="The dataset is not available.")
    got = brief_facts(r, rng, platform, persona, ids)
    if got is None:
        return reply(404, error="unknown_view", reason="No such view or finding.")
    facts, used = got
    key = f"{rng}|{platform}|{persona}|{','.join(used)}"
    c = ask.cfg()
    path = cache_path(key, hashlib.sha256(raw).hexdigest())
    if not again:
        hit = ask.cache_get(path)
        if hit:
            log.info("brief_ai outcome=cache")
            hit.update(cached=True, retry_in_s=0)
            return reply(200, **hit)
    facts_text = json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
    allowed = ask.allowed_numbers(facts_text)
    vh = hashlib.sha256((ask.SALT + ask.client_ip(c["xff_hops"])).encode()).hexdigest()[:10]
    ok, retry, left = take_slot(vh, key)
    if not ok:
        log.info("brief_ai outcome=cooldown")
        return standard("Easy on the button: wait a few seconds before rewriting again." if retry else "You have used the rewrites for this view. The standard brief stays.", "cooldown" if retry else "limit", retry)
    if not ask.ip_limit("br" + vh, c["per_min"], c["per_day"]):
        log.info("brief_ai outcome=rate_limited")
        return standard("Too many AI requests from here for now. The standard brief stays.", "rate_limited")
    if not ask.global_take(c["global_day"]):
        log.info("brief_ai outcome=budget_exhausted")
        return standard("Today's AI budget is used up. The standard brief stays.", "budget")
    out = call_model(facts, facts_text, again, c)
    if out is None:
        log.info("brief_ai outcome=model_unavailable")
        return standard("The AI did not answer. The standard brief stays.", "model_unavailable")
    clean = verify(out, facts, allowed)
    if clean is None:
        log.info("brief_ai outcome=unverified")
        return standard("The AI wording could not be verified against the numbers. The standard brief stays.", "unverified")
    res = {"source": "gemini", "model": "mock" if mock() else ask.MODEL, "generated_at": datetime.now(timezone.utc).strftime("%H:%M UTC"),
           "key": key, "ids": used, **clean, "notice": NOTICE, "cached": False, "retry_in_s": COOLDOWN_S, "left": left}
    if not again:
        cache_put(path, {k: v for k, v in res.items() if k not in ("cached", "retry_in_s")}, c["cache_max"])
    log.info("brief_ai outcome=answered again=%s", again)
    return reply(200, **res)


@bp.errorhandler(413)
def too_big(_):
    return reply(413, error="too_large", reason="Request body is too large.")


def register(app):
    app.register_blueprint(bp)
