#!/usr/bin/env python3
"""Diagnostic Agent (Tier 2). All data it reads is SYNTHETIC in this build.

Four deterministic layers around one Gemini call per insight:
  1. Impact Score and every number are computed in code (build_results.py / Watchdog), never by the model.
  2. build_package(): the evidence the model sees, with every number in it and a list of reference ids it may cite.
  3. rules_verdict(): the Watchdog / builder rule table as a hint. Gemini may overrule it with a stated reason;
     the disagreement is kept and flagged. When the rule is not trusted (RULE_TRUSTED) it abstains. It never guesses.
  4. validate(): after the call: schema, every claim has a ref that exists in this insight, every number quoted exists in
     the package, confidence fits the sample size, and no instruction to force users. One retry, then the cache, then
     the rules (only if trusted), then "unclassified, needs review".

Every result carries its `source`: gemini | cached | rules | unclassified.
Validated outputs are cached in data/cache/ under a hash of (evidence + prompt version + model), so a rerun without
network serves them (`source: "cached"`).

Usage (post-process a results.json that has pending diagnoses):
  python pipeline/diagnose.py --results data/synthetic/results_v2.json --out data/synthetic/results_v2.json [--offline] [--refresh]
build_results.py --diagnose calls diagnose_insights() directly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

PROJECT, LOCATION, MODEL = "panopticon-hackathon", "us-central1", "gemini-2.5-flash"
PROMPT_VERSION = "v3"
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"

CLASSES = ["technical_bug", "ux_friction", "language_cognitive_overload", "natural_exit", "behavior_pattern", "unclassified_needs_review"]
# Watchdog / builder rule names -> class. None = the rule names two classes at once, so it cannot decide.
RULE_CLASS = {"technical_fault": "technical_bug", "technical_bug_or_ux_friction": None, "language_cognitive_overload": "language_cognitive_overload",
              "ux_friction": "ux_friction", "natural_exit": "natural_exit", "behavior_pattern": "behavior_pattern",
              "unclassified_needs_review": "unclassified_needs_review"}
# Rules trusted to classify on their own (test-first, see pipeline/eval.py --rules-only; decided 2026-10-14 on seeds
# 42, 7, 123, 2024, 99). A rule that was never exercised by the planted data stays out until it is re-tested.
RULE_TRUSTED = {"technical_fault", "natural_exit", "behavior_pattern", "unclassified_needs_review"}
EXPECTED_ACCEPT = {   # what counts as a correct class for a planted case (used by eval.py)
    "technical_fault": {"technical_bug"}, "technical_bug_or_ux_friction": {"technical_bug", "ux_friction"},
    "unclassified_needs_review": {"unclassified_needs_review"}, "natural_exit": {"natural_exit"},
}


# ----------------------------------------------------------------------------- the model's output shape
def _models():
    from pydantic import BaseModel

    class Claim(BaseModel):
        text: str
        ref_ids: list[str]

    class Step(BaseModel):
        kind: Literal["check", "fix", "monitor"]
        text: str

    class Diag(BaseModel):
        reasoning: list[str]
        diagnosis_class: Literal["technical_bug", "ux_friction", "language_cognitive_overload", "natural_exit", "behavior_pattern", "unclassified_needs_review"]
        confidence: float
        summary: str
        claims: list[Claim]
        next_steps: list[Step]
        caveats: list[str]
        overrule_reason: str
    return Diag


SYSTEM = """You are the Diagnostic Agent of a behavior-analytics dashboard. All data is SYNTHETIC sample data.
You receive ONE finding as JSON (signals, breakdown, evidence statistics, a few raw sessions, a rule-based hint).
Decide WHY users behave this way, using only that JSON.

Classes (pick exactly one):
- technical_bug: the product fails: errors, dead taps or rage taps with the failure, a fault confined to a time window or version.
- ux_friction: usable but awkward: users hesitate, go back or leave a step, with no failure signal.
- language_cognitive_overload: long time on a screen or repeated focus on wording or fields, with no failure signal.
- natural_exit: users leave because they got what they came for (for example checking prices) and the rate is steady. Only allowed
  when the hint's class is natural_exit. A steady drop-off at a screen where people must fill in or confirm something (a form, a
  verification step) is never a natural exit: they did not get what they came for.
- behavior_pattern: groups behave differently in an expected, healthy way (what they buy, how much they top up) with no failure signal:
  no elevated drop-off, no errors. Only allowed when the hint's class is behavior_pattern. A segment that drops off far more than
  others, or shows errors, is NOT a behavior_pattern.
- unclassified_needs_review: the evidence does not support one class with confidence, or the intent behind the behavior cannot
  be read from events. A segment that is labelled as a risk persona (for example fraudster or unknown) with failed attempts is this case:
  declines and errors there can be the product working as designed, or abuse, or a fault, and events cannot tell which. Say what a human
  should check. This is a valid, honest answer.

Rules, all mandatory:
1. Use only numbers that appear in the JSON. Never compute, estimate or round to a new number. Write fractions as whole percentages (0.4254 becomes 43%),
   ratios as they appear, counts as they appear. Do not number your sentences or lists with digits.
2. Every claim cites one to three ref_ids taken exactly from the list "refs" in the JSON. A claim states only what its refs show.
3. Events show behavior, not causes. Where a cause (the app, the network, an SMS provider, intent) cannot be told from the data, say so in caveats.
4. The field "hint" is a rule-based guess. You may overrule it. If your class differs from the hint's class, explain why in overrule_reason
   (otherwise leave overrule_reason empty). If the hint says it cannot decide, that is not a disagreement.
5. confidence is 0 to 1. It must not exceed confidence_cap in the JSON. Use at most 0.6 for unclassified_needs_review.
6. Recommendations must never force or trap users: no forced steps, no pop-ups, no blocking people from leaving, no pressure or countdowns.
   Good next steps check logs, review the flow, test a fix, or monitor.
7. Never write ref ids inside sentences; they go only in ref_ids. reasoning: three to five short steps, evidence first, conclusion last. summary: two or three plain sentences. Two to four claims.
   One to three next_steps (kind is check, fix or monitor). Be brief; write plain English."""


# ----------------------------------------------------------------------------- layer 2: the evidence package
def _fmt(v, key: str = "") -> str:
    if key.endswith("_s"):
        return f"{v:g} s"
    if isinstance(v, float) and abs(v) <= 1.0:
        return f"{v * 100:.0f}%"
    return f"{v:g}" if isinstance(v, float) else str(v)


def build_package(ins: dict, meta: dict) -> dict:
    """Everything the model may see, plus the reference ids it may cite. Deterministic: same insight, same package."""
    refs: dict = {}                                   # id -> ref object (what the UI gets) ; label made in code
    signals = []
    for sg in ins.get("signals") or []:
        signals.append({"id": f"signal:{sg['metric']}", "metric": sg["metric"], "value": sg["value"], "reference": sg["reference"],
                        "n": sg["n"], "n_ref": sg["n_ref"], "ratio": sg.get("ratio"), "difference": sg.get("diff")})
        refs[f"signal:{sg['metric']}"] = {"type": "signal", "metric": sg["metric"],
                                           "label": f"{sg['metric'].replace('_', ' ')} {_fmt(sg['value'])} vs {_fmt(sg['reference'])}"}
    if ins.get("pattern"):
        p = ins["pattern"]
        signals.append({"id": "signal:pattern", "metric": p["kind"], "value": p["value"], "reference": p["reference"], "n": p["n"],
                        "n_ref": p["n_ref"], "persona": p["persona"], "product": p.get("product"), "threshold_php": p.get("threshold_php"),
                        "median_php": p.get("median_php"), "reference_median_php": p.get("reference_median_php")})
        refs["signal:pattern"] = {"type": "signal", "metric": p["kind"], "label": f"{p['kind'].replace('_', ' ')} {_fmt(p['value'])} vs {_fmt(p['reference'])}"}
    bd = []
    for r in ins.get("breakdown") or []:
        rid = f"breakdown:{r['dim']}:{r['value']}"
        row = {"id": rid, "dimension": r["dim_label"], "value": r["label"], "sessions": r["n"], "exit_rate": r["rate"], "in_segment": r["in_segment"]}
        if r.get("rate_before") is not None:
            row["exit_rate_before"] = r["rate_before"]
        bd.append(row)
        refs[rid] = {"type": "breakdown", "dim": r["dim"], "value": r["value"], "label": f"{r['label']} {_fmt(r['rate'])} ({r['n']} sessions)"}
    st = ins.get("evidence_stats") or {}
    g, ref = st.get("group") or {}, st.get("reference") or {}
    for k, v in g.items():
        if k == "sessions":
            continue
        rv = ref.get(k)
        if isinstance(v, list):
            lab = f"{k.replace('_', ' ')}: " + ", ".join(f"{x.get('code') or x.get('element')} {x.get('events') or x.get('taps')}" for x in v[:3]) if v else None
        else:
            lab = f"{k.replace('_', ' ')} {_fmt(v, k) if v is not None else 'n/a'}" + (f" vs {_fmt(rv, k)}" if rv is not None else "")
        if lab and v not in (None, []):
            refs[f"stat:{k}"] = {"type": "stat", "id": f"stat:{k}", "label": lab}
    sessions = []
    for es in (ins.get("evidence") or {}).get("sessions", [])[:4]:
        rid = f"session:{es['session_id']}"
        rows = []
        for r in es["rows"][:45]:
            piece = f"+{r['t'] / 1000:.1f}s {r['type']} {r['screen'] or ''}"
            if r.get("element"):
                piece += f":{r['element']}"
            if r.get("error_code"):
                piece += f" error={r['error_code']}"
            rows.append(piece)
        sessions.append({"id": rid, "role": es["role"], "persona": es["persona"], "path": es["path"], "events": rows})
        refs[rid] = {"type": "session", "id": es["session_id"], "label": f"session {es['session_id']}"}
    facts = []
    for i, f in enumerate(ins.get("facts") or []):
        facts.append({"id": f"fact:{i}", "text": f})
        refs[f"fact:{i}"] = {"type": "fact", "id": f"fact:{i}", "label": f[:60]}
    n_group = (g or {}).get("sessions") or ins.get("n_sessions") or 0
    cap = 0.5 if n_group < 30 else 0.75 if n_group < 100 else 0.9
    imp = ins["impact"]
    pkg = {
        "finding": {"id": ins["id"], "title": ins["title"], "screen": ins["screen_label"], "journey": ins.get("journey"), "step": ins.get("step"),
                    "scope": ins["scope"], "who": ins["segment_text"], "compared_with": ins["compared_with"],
                    "window": ins.get("window"), "sessions": ins["n_sessions"], "dataset": "synthetic (generated, not real users)"},
        "facts": facts, "signals": signals, "breakdown": bd,
        "concentration": ins.get("concentration"),
        "evidence_stats": {"group": g or None, "reference": ref or None},
        "builder_causes": [{"type": c["type"], "share": c["share"], "title": c["title"], "why": c["why"], "resolved": c["resolved"]} for c in ins.get("causes") or []],
        "impact": {"score": imp["score"], "excess_sessions": imp["volume"], "lost_sessions_per_week": imp["lost_sessions_per_week"],
                   "assumed_value_php_per_week": imp["per_week_value"], "assumption": imp["assumption"]},
        "hint": {"class": ins["hint_class"], "rule": ins["hint_rule"]},
        "sessions": sessions,
        "refs": sorted(refs),
        "confidence_cap": cap,
    }
    pkg["_refs"] = refs        # kept out of the prompt and out of the hash
    return pkg


def prompt_json(pkg: dict) -> str:
    return json.dumps({k: v for k, v in pkg.items() if not k.startswith("_")}, indent=1, sort_keys=True, ensure_ascii=False)


def cache_key(pkg: dict) -> str:
    h = hashlib.sha256((PROMPT_VERSION + "|" + MODEL + "|" + SYSTEM + "|" + prompt_json(pkg)).encode("utf-8")).hexdigest()
    return h[:16]


# ----------------------------------------------------------------------------- layer 3: the rule hint
def rules_verdict(ins: dict) -> dict:
    name = ins.get("hint_class")
    cls = RULE_CLASS.get(name)
    trusted = name in RULE_TRUSTED and cls is not None
    return {"rule_name": name, "rule": ins.get("hint_rule"), "class": cls if trusted else None, "mapped_class": cls, "trusted": trusted}


# ----------------------------------------------------------------------------- layer 4: the validator
NUM = re.compile(r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
# instructions to force or pressure users; neutral words ("forced to retry", "compelled" in a description) do not match on their own
_WHO = r"(?:users?|people|customers?|visitors?|them|everyone|anyone|persons?)"
FORCE = re.compile(r"\b(?:(?:force|compel|coerce|oblige|trap|nag|pressure|guilt|scare|rush)\w*\s+(?:all\s+|the\s+|these\s+)?" + _WHO +
                   r"|(?:forced|mandatory|compulsory)\s+(?:step|steps|pop-?up|popup|flow|action|verification|registration|login|upgrade|update|retry|tutorial|survey|rating)"
                   r"|pop-?ups?|interstitial\w*|countdown\w*|dark patterns?|urgency (?:timer|message|banner)|fake (?:urgency|scarcity)"
                   r"|(?:prevent|block|stop|discourage)\w*\s+" + _WHO + r"\s+from\s+(?:leaving|exiting|quitting|closing|cancelling|canceling)"
                   r"|lock\w*\s+" + _WHO + r"\s+in)\b", re.I)
RAW_FRACTION = re.compile(r"(?<![\w.])(?:0\.\d+|1\.0+)(?![\d.]*\s*(?:%|s\b|seconds?|times|x\b))")


def _numbers(text: str):
    for m in NUM.finditer(text):
        tok = m.group(0).rstrip(".").replace(",", "")
        try:
            yield float(tok), (len(tok.split(".")[1]) if "." in tok else 0)
        except ValueError:
            continue


def allowed_numbers(pkg: dict) -> set:
    out: set = set()

    def walk(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            out.add(float(v))
            if isinstance(v, float) and abs(v) <= 1.0:
                out.add(v * 100)
            return
        if isinstance(v, str):
            out.update(x for x, _ in _numbers(v))
            return
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk({k: v for k, v in pkg.items() if not k.startswith("_")})
    return out


def number_ok(x: float, dec: int, allowed: set) -> bool:
    tol = 0.5 * 10 ** (-dec) + 1e-9
    return any(abs(a - x) <= tol for a in allowed)


def validate(out: dict, pkg: dict, rules: dict) -> list:
    """List of problems; empty means the output may be shown."""
    bad = []
    if out.get("diagnosis_class") not in CLASSES:
        bad.append("class is not an allowed class")
    conf = out.get("confidence")
    if not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
        bad.append("confidence is not between 0 and 1")
    else:
        if conf > pkg["confidence_cap"] + 1e-9:
            bad.append(f"confidence {conf} is above the cap {pkg['confidence_cap']} for this sample size")
        if out.get("diagnosis_class") == "unclassified_needs_review" and conf > 0.6 + 1e-9:
            bad.append("confidence above 0.6 for unclassified_needs_review")
    if not (out.get("summary") or "").strip():
        bad.append("empty summary")
    claims = out.get("claims") or []
    if not claims:
        bad.append("no claims")
    for i, c in enumerate(claims):
        ids = c.get("ref_ids") or []
        if not ids:
            bad.append(f"claim {i + 1} has no ref")
        for r in ids:
            if r not in pkg["_refs"]:
                bad.append(f"claim {i + 1} cites a ref that does not exist: {r}")
    if not out.get("next_steps"):
        bad.append("no next steps")
    texts = [out.get("summary", ""), out.get("overrule_reason", "")] + [c.get("text", "") for c in claims] + \
            [s.get("text", "") for s in out.get("next_steps") or []] + list(out.get("caveats") or []) + list(out.get("reasoning") or [])
    allowed = allowed_numbers(pkg)
    for t in texts:
        for x, dec in _numbers(t):
            if not number_ok(x, dec, allowed):
                bad.append(f"number {x:g} is not in the evidence (text: {t[:70]!r})")
        m = FORCE.search(t)
        if m:
            bad.append(f"no-force guardrail: {m.group(0)!r} in {t[:70]!r}")
        m = RAW_FRACTION.search(t)
        if m:
            bad.append(f"write fractions as percentages, not {m.group(0)!r} (text: {t[:70]!r})")
    cls = out.get("diagnosis_class")
    if cls in ("natural_exit", "behavior_pattern") and rules["rule_name"] != cls:
        bad.append(f"class {cls} is only allowed where the rule table found it (hint is {rules['rule_name']}); "
                   "a steady drop-off at a form or a segment with failures is not one")
    mapped = rules["mapped_class"]
    if mapped is not None and rules["trusted"] and out.get("diagnosis_class") != mapped and not (out.get("overrule_reason") or "").strip():
        bad.append("class differs from the rule hint and no overrule_reason is given")
    return bad


# ----------------------------------------------------------------------------- the Gemini call
_client = None


def _call(pkg: dict, problems: list | None):
    """One Gemini call. Returns the parsed dict. Raises on transport errors (never prints credentials)."""
    global _client
    from google import genai
    from google.genai import types
    if _client is None:
        _client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    text = "Finding to diagnose (JSON):\n" + prompt_json(pkg)
    if problems:
        text += "\n\nYour previous answer was rejected by the validator for these reasons. Fix them and answer again:\n- " + "\n- ".join(problems[:8])
    resp = _client.models.generate_content(
        model=MODEL, contents=text,
        config=types.GenerateContentConfig(system_instruction=SYSTEM, temperature=0.0, response_mime_type="application/json",
                                           response_schema=_models(), max_output_tokens=4096,
                                           thinking_config=types.ThinkingConfig(thinking_budget=0)))
    return _models().model_validate_json(resp.text).model_dump()


# ----------------------------------------------------------------------------- cache
def _cache_path(iid: str, key: str) -> Path:
    return CACHE_DIR / (re.sub(r"[^A-Za-z0-9_.=-]", "_", iid) + "__" + key + ".json")


def cache_get(iid: str, key: str):
    p = _cache_path(iid, key)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return None


def cache_put(iid: str, key: str, out: dict, generated_at: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(iid, key).write_text(json.dumps({"insight_id": iid, "key": key, "prompt_version": PROMPT_VERSION, "model": MODEL,
                                                 "generated_at": generated_at, "output": out}, indent=1) + "\n", encoding="utf-8")


def cache_latest(iid: str):
    """Newest cached output for this insight id, whatever its key (the caller re-validates it against today's evidence)."""
    best = None
    for p in CACHE_DIR.glob(re.sub(r"[^A-Za-z0-9_.=-]", "_", iid) + "__*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("prompt_version") == PROMPT_VERSION and d.get("model") == MODEL and isinstance(d.get("output"), dict)                 and isinstance(d.get("generated_at"), str) and (best is None or d["generated_at"] > best["generated_at"]):
            best = d
    return best


# ----------------------------------------------------------------------------- assemble the diagnosis object
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _agreement(out_class: str, rules: dict) -> str:
    if rules["mapped_class"] is None:
        return "rules_abstained"
    if not rules["trusted"]:
        return "agree" if out_class == rules["mapped_class"] else "differs_untrusted_rule"
    return "agree" if out_class == rules["mapped_class"] else "overruled"


REF_IN_TEXT = re.compile(r"\s*\((?:\s*(?:fact|stat|signal|breakdown|session):[^,()]+,?)+\)")


def scrub(t: str) -> str:
    """The model sometimes writes its ref ids into the sentence; the refs are shown as buttons instead."""
    return REF_IN_TEXT.sub("", t or "").strip()


def make_diagnosis(out: dict, pkg: dict, rules: dict, status: str, source: str, generated_at: str, note: str | None, attempts: int, key: str) -> dict:
    refs = pkg["_refs"]
    out = {**out, "summary": scrub(out["summary"]), "reasoning": [scrub(x) for x in out["reasoning"]], "caveats": [scrub(x) for x in out["caveats"]],
           "next_steps": [{**x, "text": scrub(x["text"])} for x in out["next_steps"]]}
    claims = [{"text": scrub(c["text"]), "refs": [refs[r] for r in c["ref_ids"] if r in refs]} for c in out["claims"]]
    ag = _agreement(out["diagnosis_class"], rules)
    return {"status": status, "source": source, "model": MODEL, "generated_at": generated_at, "source_note": note,
            "class": out["diagnosis_class"], "confidence": round(float(out["confidence"]), 2), "summary": out["summary"],
            "claims": claims, "next_steps": out["next_steps"], "guardrail_flags": [], "caveats": list(out["caveats"]),
            "reasoning": list(out["reasoning"]),
            "rules": {"rule": rules["rule_name"], "rule_text": rules["rule"], "class": rules["mapped_class"], "trusted": rules["trusted"],
                      "agreement": ag, "overrule_reason": out.get("overrule_reason") or None, "flagged": ag in ("overruled", "differs_untrusted_rule")},
            "validation": {"passed": True, "attempts": attempts}, "cache_key": key, "prompt_version": PROMPT_VERSION}


def fallback_diagnosis(ins: dict, rules: dict, why: str, attempts: int, key: str, problems: list) -> dict:
    """No valid model output. A trusted rule may answer; otherwise unclassified, needs review. Never a guess."""
    base = {"model": None, "generated_at": _now(), "claims": [], "reasoning": [], "guardrail_flags": [],
            "rules": {"rule": rules["rule_name"], "rule_text": rules["rule"], "class": rules["mapped_class"], "trusted": rules["trusted"],
                      "agreement": "n/a", "overrule_reason": None, "flagged": False},
            "validation": {"passed": False, "attempts": attempts, "problems": problems[:6]}, "cache_key": key, "prompt_version": PROMPT_VERSION}
    if rules["class"] and rules["class"] != "unclassified_needs_review":
        return {**base, "status": "done", "source": "rules", "source_note": f"Rule-based result, not an AI diagnosis ({why}).",
                "class": rules["class"], "confidence": None, "summary": f"Rule match: {rules['rule']}. No AI explanation is available ({why}).",
                "next_steps": [{"kind": "check", "text": "Retry the AI diagnosis when it is available, and review the evidence sessions."}],
                "caveats": ["The class comes from a fixed rule, not from the model; no explanation was generated."]}
    return {**base, "status": "failed", "source": "unclassified", "source_note": f"Needs review: {why}.", "class": "unclassified_needs_review",
            "confidence": None, "summary": f"Not classified. {why[:1].upper() + why[1:]}. A person should look at the evidence.",
            "next_steps": [{"kind": "check", "text": "Review the evidence sessions and signals by hand."}],
            "caveats": ["No valid AI output and no trusted rule matched, so no class is claimed."]}


def diagnose_one(ins: dict, meta: dict, stats: dict, offline: bool = False, refresh: bool = False, log=print) -> dict:
    pkg = build_package(ins, meta)
    rules = rules_verdict(ins)
    key = cache_key(pkg)
    iid = ins["id"]
    if not refresh:
        hit = cache_get(iid, key)
        if hit:
            probs = validate(hit["output"], pkg, rules)
            if not probs:
                stats["cache_hits"] += 1
                return make_diagnosis(hit["output"], pkg, rules, "cached", "cached", hit["generated_at"],
                                      f"Saved result from {hit['generated_at'][:10]}, not a live call", 0, key)
    problems: list = []
    attempts = 0
    why = "offline run" if offline else "no valid model output"
    if not offline:
        for attempt in range(2):
            attempts += 1
            try:
                stats["calls"] += 1
                out = _call(pkg, problems if attempt else None)
            except Exception as e:                       # transport, auth, quota, parse: type name only, never the message
                stats["errors"] += 1
                problems = [f"call failed: {type(e).__name__}"]
                why = f"the model call failed ({type(e).__name__})"
                log(f"  {iid}: call failed ({type(e).__name__})")
                if attempt == 0 and type(e).__name__ in ("ValidationError", "JSONDecodeError"):
                    continue
                break
            problems = validate(out, pkg, rules)
            if not problems:
                ts = _now()
                cache_put(iid, key, out, ts)
                return make_diagnosis(out, pkg, rules, "done", "gemini", ts, None, attempts, key)
            stats["rejected"] += 1
            log(f"  {iid}: rejected ({len(problems)}): {problems[0]}")
            why = "the model output failed validation twice" if attempt else why
    # last resort before the rules: the newest cached output for this insight, if it still passes today's checks
    old = cache_latest(iid)
    if old:
        probs = validate(old["output"], pkg, rules)
        if not probs:
            stats["cache_fallbacks"] += 1
            return make_diagnosis(old["output"], pkg, rules, "cached", "cached", old["generated_at"],
                                  f"Saved result from {old['generated_at'][:10]}, not a live call", attempts, key)
    stats["fallbacks"] += 1
    return fallback_diagnosis(ins, rules, why, attempts, key, problems)


def diagnose_insights(insights: list, meta: dict, offline: bool = False, refresh: bool = False, log=print) -> dict:
    stats = {"insights": len(insights), "calls": 0, "cache_hits": 0, "cache_fallbacks": 0, "rejected": 0, "errors": 0, "fallbacks": 0}
    for ins in insights:
        ins["diagnosis"] = diagnose_one(ins, meta, stats, offline, refresh, log)
        apply_flat(ins)
    return stats


def apply_flat(ins: dict) -> None:
    """Keep the older flat fields in step with the diagnosis object (additive, for readers of the v0.1 shape)."""
    d = ins["diagnosis"]
    ins["class"] = d["class"]
    ins["diagnosis_status"] = d["status"]
    ins["confidence"] = d["confidence"]
    ins["summary"] = d["summary"]
    ins["hypothesis"] = d["summary"]
    ins["recommendation"] = " ".join(s["text"] for s in d["next_steps"][:2]) or None
    ins["guardrail_flags"] = d["guardrail_flags"]


def summarize_meta(insights: list, stats: dict) -> dict:
    srcs = {i["diagnosis"]["source"] for i in insights}
    live = "gemini" in srcs
    kind = "mixed" if live and (srcs - {"gemini"}) else "live" if live else "cached" if "cached" in srcs and len(srcs) == 1 else "mixed" if len(srcs) > 1 else next(iter(srcs), "none")
    status = "done" if all(i["diagnosis"]["status"] in ("done", "cached") for i in insights) else "partial"
    return {"model": MODEL, "diagnosis_source": kind, "diagnosis_status": status, "diagnosis_stats": stats, "prompt_version": PROMPT_VERSION}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", required=True, help="a results.json built by build_results.py (needs evidence_stats)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--offline", action="store_true", help="never call Gemini: cache, then trusted rules, then unclassified")
    ap.add_argument("--refresh", action="store_true", help="ignore the cache and call Gemini again (costs calls)")
    args = ap.parse_args()
    res = json.loads(Path(args.results).read_text(encoding="utf-8"))
    stats = diagnose_insights(res["insights"], res["meta"], args.offline, args.refresh)
    res["meta"].update(summarize_meta(res["insights"], stats))
    Path(args.out).write_text(json.dumps(res, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(stats))


if __name__ == "__main__":
    sys.exit(main())
