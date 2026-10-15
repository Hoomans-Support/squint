"""Fact-check endpoint: the "Fact-check with AI" button in the finding drawer. See docs/factcheck-endpoint.md.

POST /api/factcheck {"id": "<finding id>", "again": false}. The saved explanation of a finding is never changed. The button asks
Gemini to check each line of that explanation against the numbers of the same finding and says Supported, Partly, Not supported or
Cannot check for each line. Only numbers already in results.json (SYNTHETIC) are sent; the client sends an id, never facts.

One live call per click, with: a saved first answer per finding (repeat clicks cost nothing), a 30 s cooldown and 3 re-checks per
finding and visitor per hour, the per-visitor and daily limits shared with the Ask endpoint, a kill switch, and a plain code
check as the fallback, so the button always answers. Log lines carry counts and reason codes only.

Default state: ON when run locally (no PORT variable), OFF on a platform that sets PORT (Cloud Run) unless FACTCHECK_ENABLED=1.
FACTCHECK_ENABLED=0 turns it off everywhere. FACTCHECK_MOCK=1 answers from canned outputs without network (tests).
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

import ask_gemini as ask          # shared helpers: results grounding, limits, daily counter, client

log = logging.getLogger("factcheck")
bp = Blueprint("factcheck", __name__)

PROMPT_VERSION = "fc-v1"
COOLDOWN_S = 30
AGAIN_PER_HOUR = 3
MAX_BODY = 512
NOTICE = ("AI can make mistakes. It only saw the numbers on this page, not your database. Treat it as a second opinion.")
_lock = threading.Lock()
_recent = {}          # (visitor hash, finding id) -> list of live-call timestamps


def enabled_state():
    v = os.environ.get("FACTCHECK_ENABLED")
    if v == "0":
        return False
    if v == "1":
        return True
    return not os.environ.get("PORT")          # unset: on locally, off on a platform that sets PORT


def mock():
    return os.environ.get("FACTCHECK_MOCK") == "1"


# ---------------------------------------------------------------- facts for one finding

def _pct(x):
    return None if x is None else round(x * 100, 1)


def finding_facts(r, fid):
    """(facts dict, claims list, valid) for one finding, or None. Hidden groups are not available."""
    for i in r.get("insights", []):
        if i.get("id") != fid:
            continue
        pids = i.get("persona_ids") or []
        if pids and all(p in ask.HIDDEN_PERSONAS for p in pids):
            return None
        dg = i.get("diagnosis") or {}
        claims = [c.get("text") for c in (dg.get("claims") or []) if isinstance(c, dict) and c.get("text")]
        if not claims and dg.get("summary"):
            claims = [dg["summary"]]
        es = i.get("evidence_stats") or {}
        g, ref = es.get("group") or {}, es.get("reference") or {}
        facts = {
            "title": i.get("title"), "group": i.get("segment_text"), "screen": i.get("screen_label"), "sessions_affected": i.get("n_sessions"),
            "signals": [{"metric": s.get("metric"), "percent_now": _pct(s.get("value")), "percent_usual": _pct(s.get("reference")), "sessions": s.get("n"),
                         "times_higher": s.get("ratio")} for s in i.get("signals", [])],
            "breakdown": [{"split": b.get("dim_label"), "label": b.get("label"), "sessions": b.get("n"), "percent_now": _pct(b.get("rate")),
                           "percent_usual": _pct(b.get("rate_before"))} for b in i.get("breakdown", [])],
            "facts": i.get("facts"),
            "group_stats": {"exit_rate_percent": _pct(g.get("exit_rate")), "with_error_percent": _pct(g.get("with_error")), "with_repeated_tap_percent": _pct(g.get("with_rage_tap")),
                            "with_dead_tap_percent": _pct(g.get("with_dead_tap")), "with_back_percent": _pct(g.get("with_back")), "median_dwell_seconds": g.get("median_dwell_s"),
                            "top_error_codes": g.get("top_error_codes"), "top_repeated_tap_elements": g.get("top_rage_tap_elements")},
            "usual_stats": {"exit_rate_percent": _pct(ref.get("exit_rate")), "with_error_percent": _pct(ref.get("with_error")), "with_repeated_tap_percent": _pct(ref.get("with_rage_tap"))},
            "impact": {"lost_sessions_per_week": (i.get("impact") or {}).get("lost_sessions_per_week"), "assumed_value_per_week": (i.get("impact") or {}).get("per_week_value")},
        }
        return facts, claims
    return None


# ---------------------------------------------------------------- the code check (no AI)

def _numbers(text):
    return ask._nums(re.sub(r"\b(?:19|20)\d\d-\d\d-\d\d\b", " ", text))


def code_check(claims, allowed):
    """For each claim: do the numbers it quotes exist in the facts? Not a judgement about meaning."""
    out = []
    for n, text in enumerate(claims):
        nums = _numbers(text)
        if not nums:
            out.append({"index": n, "text": text, "verdict": "cannot_check", "number": "", "note": "No numbers in this line to check."})
            continue
        found = [x for x in nums if any(abs(x - a) < 1e-9 for a in allowed)]
        verdict = "supported" if len(found) == len(nums) else "partly" if found else "not_supported"
        miss = [x for x in nums if x not in found]
        note = "Every number matches the data." if verdict == "supported" else (
            "Not found in the data: " + ", ".join(("%g" % x) for x in miss[:4]) + ".")
        out.append({"index": n, "text": text, "verdict": verdict, "number": ", ".join(("%g" % x) for x in found[:4]), "note": note})
    return out


def overall_of(rows):
    vs = [r["verdict"] for r in rows if r["verdict"] != "cannot_check"]
    if not vs:
        return "cannot_check"
    if all(v == "supported" for v in vs):
        return "supported"
    if all(v == "not_supported" for v in vs):
        return "not_supported"
    return "mixed"


# ---------------------------------------------------------------- the model

INSTRUCTION = (
    "You fact-check one saved explanation of an analytics finding for a mobile app. The data is SYNTHETIC.\n"
    "You get FACTS (numbers computed by code) and CLAIMS (numbered lines written earlier by an AI).\n"
    "For each claim decide: supported (every number and statement matches FACTS), partly (some do), not_supported (contradicts FACTS "
    "or is not in FACTS), or cannot_check (no numbers or facts to check against).\n"
    "Rules:\n"
    "- Use only FACTS. Quote numbers exactly as written there. Do not compute new numbers.\n"
    "- number: the one figure from FACTS that decides your verdict, or an empty string.\n"
    "- note: one short plain sentence, no markdown, no links.\n"
    "- missed: up to 2 short sentences about important things in FACTS that the claims leave out. May be empty.\n"
    "- Never suggest forcing, tricking or pressuring users.\n"
    "- Answer for every claim index given, in order.\n"
    "FACTS (synthetic):\n"
)
SCHEMA = {"type": "OBJECT", "properties": {
    "claims": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "index": {"type": "INTEGER"}, "verdict": {"type": "STRING", "enum": ["supported", "partly", "not_supported", "cannot_check"]},
        "number": {"type": "STRING"}, "note": {"type": "STRING"}}, "required": ["index", "verdict", "number", "note"]}},
    "missed": {"type": "ARRAY", "items": {"type": "STRING"}}}, "required": ["claims", "missed"]}


def _mock_out(claims):
    return {"claims": [{"index": n, "verdict": "supported" if n % 2 == 0 else "partly", "number": "", "note": "Mock check."} for n in range(len(claims))],
            "missed": ["Mock: something the explanation leaves out."]}


def call_model(claims, facts_text, again, c):
    if mock():
        return _mock_out(claims)
    from google.genai import types
    cl = ask._get_client()
    if cl is None:
        return None
    user = "CLAIMS:\n" + "\n".join(f"{n}. {t}" for n, t in enumerate(claims))
    conf = types.GenerateContentConfig(system_instruction=INSTRUCTION + facts_text, temperature=0.3 if again else 0, max_output_tokens=900,
                                       response_mime_type="application/json", response_schema=SCHEMA,
                                       thinking_config=types.ThinkingConfig(thinking_budget=0), http_options=types.HttpOptions(timeout=c["timeout_s"] * 1000))
    try:
        resp = cl.models.generate_content(model=ask.MODEL, contents=user, config=conf)
        out = json.loads(resp.text)
        return out if isinstance(out, dict) else None
    except Exception as e:
        log.warning("factcheck model_error type=%s status=%s", type(e).__name__, getattr(e, "code", None))
        return None


def verify(out, claims, allowed):
    """Rows for the UI, or None. Code decides what is shown: a note with a number that is not in the facts is dropped."""
    got = out.get("claims")
    if not isinstance(got, list):
        return None, []
    by = {}
    for r in got:
        if isinstance(r, dict) and isinstance(r.get("index"), int) and 0 <= r["index"] < len(claims) and r.get("verdict") in ("supported", "partly", "not_supported", "cannot_check"):
            by.setdefault(r["index"], r)
    if len(by) < len(claims):
        return None, []
    bad = "http" in json.dumps(out).lower() or "```" in json.dumps(out)
    if bad:
        return None, []
    rows = []
    for n, text in enumerate(claims):
        r = by[n]
        note, number = str(r.get("note") or "")[:220], str(r.get("number") or "")[:30]
        if any(not any(abs(x - a) < 1e-9 for a in allowed) for x in _numbers(note + " " + number)):
            note, number = "", ""                    # an invented figure: say nothing rather than show it
        rows.append({"index": n, "text": text, "verdict": r["verdict"], "number": number, "note": note})
    missed = [str(m)[:200] for m in (out.get("missed") or []) if isinstance(m, str) and not any(not any(abs(x - a) < 1e-9 for a in allowed) for x in _numbers(m))][:2]
    return rows, missed


# ---------------------------------------------------------------- limits and cache

def take_finding_slot(vh, fid, again):
    """(allowed, retry_in_s, left). Cooldown between live calls per visitor and finding, and a few re-checks per hour."""
    now = time.time()
    with _lock:
        ts = [t for t in _recent.get((vh, fid), []) if now - t < 3600]
        if ts and now - ts[-1] < COOLDOWN_S:
            _recent[(vh, fid)] = ts
            return False, int(COOLDOWN_S - (now - ts[-1])) + 1, max(0, AGAIN_PER_HOUR + 1 - len(ts))
        if len(ts) >= AGAIN_PER_HOUR + 1:
            _recent[(vh, fid)] = ts
            return False, 0, 0
        ts.append(now)
        _recent[(vh, fid)] = ts
        if len(_recent) > 5000:
            for k in [k for k, v in _recent.items() if not v or now - v[-1] > 3600]:
                _recent.pop(k, None)
        return True, COOLDOWN_S, max(0, AGAIN_PER_HOUR + 1 - len(ts))


def cache_path(fid, rhash):
    return ask.data_dir() / ("fc_" + hashlib.sha256(f"{fid}|{rhash}|{PROMPT_VERSION}".encode()).hexdigest()[:40] + ".json")


# ---------------------------------------------------------------- route

def reply(code, **body):
    return jsonify(body), code


def fallback(rows, reason, code_reason, retry=0):
    return reply(200, retry_in_s=retry, source="code", overall=overall_of(rows), claims=rows, missed=[], reason=reason, reason_code=code_reason, notice="Code check: it only compares the numbers in each line with the data. It does not judge the meaning.")


@bp.route("/api/factcheck", methods=["POST", "GET", "OPTIONS"], provide_automatic_options=False)
def factcheck():
    if request.method != "POST":
        resp, code = reply(405, error="method_not_allowed", reason="Use POST.")
        resp.headers["Allow"] = "POST"
        return resp, code
    request.max_content_length = MAX_BODY
    if (request.content_length or 0) > MAX_BODY:
        return reply(413, error="too_large", reason="Request body is too large.")
    body = request.get_json(silent=True)
    fid = body.get("id") if isinstance(body, dict) else None
    again = bool(body.get("again")) if isinstance(body, dict) else False
    ds = ask.dataset_of(body)
    if ds is None:
        return reply(400, error="bad_input", reason="Unknown dataset.")
    if not isinstance(fid, str) or not fid or len(fid) > 160:
        return reply(400, error="bad_input", reason='Send JSON like {"id": "<finding id>"}.')
    try:
        raw = ask.results_path(ds).read_bytes()
        r = json.loads(raw)
    except (OSError, ValueError):
        return reply(503, error="unavailable", reason="The dataset is not available.")
    got = finding_facts(r, fid)
    if got is None:
        return reply(404, error="unknown_finding", reason="No such finding.")
    facts, claims = got
    if not claims:
        return reply(200, source="code", overall="cannot_check", claims=[], missed=[], reason="This finding has no saved explanation to check.", reason_code="no_claims", notice="")
    facts_text = json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
    allowed = ask.allowed_numbers(facts_text)
    rows = code_check(claims, allowed)
    c = ask.cfg()
    if not enabled_state():
        log.info("factcheck outcome=off")
        return fallback(rows, "The AI check is switched off here, so this is a plain code check.", "off")
    rhash = hashlib.sha256(raw).hexdigest()
    path = cache_path(fid, rhash)
    if not again:
        hit = ask.cache_get(path)
        if hit:
            log.info("factcheck outcome=cache")
            hit.update(cached=True, retry_in_s=0)
            return reply(200, **hit)
    vh = hashlib.sha256((ask.SALT + ask.client_ip(c["xff_hops"])).encode()).hexdigest()[:10]
    ok, retry, left = take_finding_slot(vh, fid, again)
    if not ok:
        log.info("factcheck outcome=cooldown")
        return fallback(rows, "Easy on the button: wait a few seconds before checking again." if retry else "You have used the re-checks for this finding. This is a plain code check.", "cooldown" if retry else "limit", retry)
    if not ask.ip_limit("fc" + vh, c["per_min"], c["per_day"]):
        log.info("factcheck outcome=rate_limited")
        return fallback(rows, "Too many AI checks from here for now. This is a plain code check.", "rate_limited")
    if not ask.global_take(c["global_day"]):
        log.info("factcheck outcome=budget_exhausted")
        return fallback(rows, "Today's AI check budget is used up. This is a plain code check.", "budget")
    out = call_model(claims, facts_text, again, c)
    if out is None:
        log.info("factcheck outcome=model_unavailable")
        return fallback(rows, "The AI did not answer. This is a plain code check.", "model_unavailable")
    ai_rows, missed = verify(out, claims, allowed)
    if ai_rows is None:
        log.info("factcheck outcome=unverified")
        return fallback(rows, "The AI answer could not be verified. This is a plain code check.", "unverified")
    res = {"source": "gemini", "model": "mock" if mock() else ask.MODEL, "generated_at": datetime.now(timezone.utc).strftime("%H:%M UTC"), "overall": overall_of(ai_rows),
           "claims": ai_rows, "missed": missed, "notice": NOTICE, "cached": False, "retry_in_s": COOLDOWN_S, "checks_left": left}
    if not again:
        ask.cache_put(path, {k: v for k, v in res.items() if k not in ("cached", "retry_in_s")}, c["cache_max"])
    log.info("factcheck outcome=answered again=%s", again)
    return reply(200, **res)


@bp.errorhandler(413)
def too_big(_):
    return reply(413, error="too_large", reason="Request body is too large.")


def register(app):
    app.register_blueprint(bp)
