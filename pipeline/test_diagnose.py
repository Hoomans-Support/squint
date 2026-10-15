#!/usr/bin/env python3
"""No-network tests of the Diagnostic Agent's validator and fallbacks (synthetic data). Run: python pipeline/test_diagnose.py
Needs a built results file: data/eval/seed_42/results_pending.json (python pipeline/eval.py --rules-only --seeds 42)."""
import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagnose as dg

res = json.loads((Path(__file__).resolve().parent.parent / "data" / "eval" / "seed_42" / "results_pending.json").read_text(encoding="utf-8"))
by = {i["id"]: i for i in res["insights"]}
ins = by["burst:otp:2026-10-09T02"]
pkg = dg.build_package(ins, res["meta"])
rules = dg.rules_verdict(ins)
ref0 = next(r for r in pkg["refs"] if r.startswith("signal:"))
sig = ins["signals"][0]
good = {"reasoning": ["Exits rise inside one window."], "diagnosis_class": "technical_bug", "confidence": 0.7,
        "summary": f"Exits are {round(sig['value'] * 100)}% in the window.",
        "claims": [{"text": f"{round(sig['value'] * 100)}% end here.", "ref_ids": [ref0]}],
        "next_steps": [{"kind": "check", "text": "Check the SMS provider logs for the window."}], "caveats": [], "overrule_reason": ""}
fails = 0


def check(name, out, expect_bad):
    global fails
    bad = dg.validate(out, pkg, rules)
    ok = bool(bad) == expect_bad
    fails += not ok
    print(("ok  " if ok else "FAIL"), name, "->", bad[:2])


def mut(**kw):
    o = copy.deepcopy(good)
    o.update(kw)
    return o


check("good output passes", good, False)
check("fabricated number is caught", mut(summary="Exits are 83% in the window."), True)
check("claim without a ref is caught", mut(claims=[{"text": "x", "ref_ids": []}]), True)
check("ref that does not exist is caught", mut(claims=[{"text": "x", "ref_ids": ["signal:nope"]}]), True)
check("force instruction is caught", mut(next_steps=[{"kind": "fix", "text": "Show a pop-up that forces users to retry."}]), True)
check("overconfidence for the sample is caught", mut(confidence=0.99), True)
check("unclassified above 0.6 is caught", mut(diagnosis_class="unclassified_needs_review", confidence=0.8, overrule_reason="x"), True)
check("disagreeing with a trusted rule needs a reason", mut(diagnosis_class="ux_friction"), True)
check("disagreeing with a reason passes", mut(diagnosis_class="ux_friction", overrule_reason="No errors are shown."), False)
check("unknown class is caught", mut(diagnosis_class="fraud"), True)
check("natural_exit is refused where the rule table did not find it", mut(diagnosis_class="natural_exit", overrule_reason="x"), True)
check("behavior_pattern is refused where the rule table did not find it", mut(diagnosis_class="behavior_pattern", overrule_reason="x"), True)
check("neutral 'forced' is not a guardrail hit", mut(summary="Users were forced to retry after the timeout."), False)
check("raw fraction is refused", mut(summary="Exit rate is 0.0464 here."), True)
check("trap users is a guardrail hit", mut(next_steps=[{"kind": "fix", "text": "Trap users on the screen."}]), True)

# fallbacks, no network: an insight with a trusted rule -> rules; one the rule names two classes for -> unclassified
with tempfile.TemporaryDirectory() as t:
    dg.CACHE_DIR = Path(t)
    stats = {"calls": 0, "cache_hits": 0, "cache_fallbacks": 0, "rejected": 0, "errors": 0, "fallbacks": 0}
    a = dg.diagnose_one(copy.deepcopy(by["burst:otp:2026-10-09T02"]), res["meta"], stats, offline=True)
    b = dg.diagnose_one(copy.deepcopy(by["segment:txn_checkout:persona=individual_trader,product=send_money"]), res["meta"], stats, offline=True)
    c = dg.diagnose_one(copy.deepcopy(by["segment:personal_data:control"]), res["meta"], stats, offline=True)
    for name, d, src, cls in (("trusted rule answers offline", a, "rules", "technical_bug"), ("ambiguous rule never guesses", b, "unclassified", "unclassified_needs_review"),
                               ("untrusted rule never answers", c, "unclassified", "unclassified_needs_review")):
        ok = d["source"] == src and d["class"] == cls
        fails += not ok
        print(("ok  " if ok else "FAIL"), name, "->", d["source"], d["class"], d["status"])
    # cache round trip: a stored valid output is served as cached with no call
    k = dg.cache_key(pkg)
    dg.cache_put(ins["id"], k, good, "2026-10-14T00:00:00Z")
    d = dg.diagnose_one(copy.deepcopy(ins), res["meta"], stats, offline=True)
    ok = d["source"] == "cached" and d["status"] == "cached" and stats["calls"] == 0
    fails += not ok
    print(("ok  " if ok else "FAIL"), "cached output served without a call ->", d["source"], d["status"])
print("FAILED" if fails else "all passed")
sys.exit(1 if fails else 0)
