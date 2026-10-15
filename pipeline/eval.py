#!/usr/bin/env python3
"""Accuracy of the Diagnostic Agent against the planted ground truth. All data is SYNTHETIC.

  python pipeline/eval.py --rules-only          # step 1 (test-first): the rule table alone, no Gemini, five seeds
  python pipeline/eval.py                       # step 2: the Diagnostic Agent (Gemini, cached per evidence hash), five seeds
  python pipeline/eval.py --seeds 42 --offline  # cache only, no calls

Per seed it generates the synthetic data into data/eval/seed_<n>/, runs normalize -> Guardian -> Watchdog -> build_results
(pending diagnoses), then scores each planted case. Gemini calls are saved in data/cache/, so a second run costs nothing.
Large event files are deleted after each seed unless --keep.

Two scores are printed. STRICT is the headline. LENIENT is the older, looser reading.
  P1 OTP outage -> technical_bug | P4 send-money drop-off -> technical_bug or ux_friction | M1 fraudsters -> unclassified_needs_review
  M2 price checks -> natural_exit
  P2 / P3 patterns -> strict: behavior_pattern; lenient: behavior_pattern or natural_exit
  control screens (steady drop-off at a form) -> strict: ux_friction, language_cognitive_overload or unclassified (never technical_bug,
  never natural_exit); lenient: anything except technical_bug.
Seed 42 was used to tune the prompt and the code guards; the other four seeds are reported separately as the hold-out (their results were
seen once before the last changes, so it is a partial hold-out, not a clean one).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagnose as dg
import pipeline as pl

ROOT = pl.ROOT
SEEDS = [42, 7, 123, 2024, 99]
TUNING_SEED = 42
W = 40
SHORT = {"unclassified_needs_review": "unclassified", "language_cognitive_overload": "language"}


def case_of(i: dict):
    """(case id, strict accepted set, lenient accepted set), or (None, None, None) when the ground truth plants nothing there."""
    iid, seg = i["id"], i["segment"]
    if i["scope"] == "burst" and i["screen"] == "otp":
        a = {"technical_bug"}
        return "P1 OTP outage", a, a
    if i["scope"] == "segment" and i["screen"] == "txn_checkout" and seg == {"persona": "individual_trader", "product": "send_money"}:
        a = {"technical_bug", "ux_friction"}
        return "P4 trader send-money", a, a
    if i["scope"] == "segment" and seg.get("persona") == "fraudster" and not iid.startswith("pattern"):
        a = {"unclassified_needs_review"}
        return f"M1 fraudsters @ {i['screen']}", a, a
    if iid == "pattern:topup_amount:large_business":
        return "P2 large top-ups", {"behavior_pattern"}, {"behavior_pattern", "natural_exit"}
    if iid.startswith("pattern:product:sari_sari"):
        return "P3 Retail e-load", {"behavior_pattern"}, {"behavior_pattern", "natural_exit"}
    if iid == "exit:prices":
        a = {"natural_exit"}
        return "M2 price checks", a, a
    if iid.endswith(":control"):
        return (f"control @ {i['screen']}", {"ux_friction", "language_cognitive_overload", "unclassified_needs_review"},
                set(dg.CLASSES) - {"technical_bug"})
    return None, None, None


def seed_dir(seed: int) -> Path:
    return ROOT / "data" / "eval" / f"seed_{seed}"


def prepare(seed: int, reuse: bool, keep: bool):
    d = seed_dir(seed)
    out = d / "results_pending.json"
    if not (reuse and out.exists()):
        pl.stages(d, seed, True, False, False, False, out)
        if not keep:
            for f in ("events_raw.jsonl", "canonical_events.jsonl"):
                (d / f).unlink(missing_ok=True)
    return json.loads(out.read_text(encoding="utf-8"))


def tally(rows_by_seed: dict, seeds: list, which: int) -> dict:
    """which: 0 strict, 1 lenient."""
    t = {"ok": 0, "n": 0, "wrong": 0, "unclassified": 0, "undetected": 0}
    for s in seeds:
        for c, r in rows_by_seed.get(s, {}).items():
            cls, acc = r[0], r[1 + which]
            t["n"] += 1
            t["ok"] += cls in acc
            if cls not in acc:
                t["unclassified" if cls == "unclassified_needs_review" else "wrong"] += 1
    return t


def line(t: dict) -> str:
    return (f"{t['ok']}/{t['n']} ({100 * t['ok'] / max(1, t['n']):.0f}%); wrong class {t['wrong']}, "
            f"unclassified where a class was expected {t['unclassified']}")


def score(rows_by_seed: dict, label: str):
    """rows_by_seed: seed -> {case: (class, strict set, lenient set, source)}. Prints one table (cells judged STRICT) and totals."""
    seeds = list(rows_by_seed)
    cases = sorted({c for r in rows_by_seed.values() for c in r})
    wid = max(len(c) for c in cases) + 2
    print(f"\n{label}")
    print("case".ljust(wid) + "".join(f"seed {s}".ljust(W) for s in seeds))
    for c in cases:
        out = c.ljust(wid)
        for s in seeds:
            r = rows_by_seed[s].get(c)
            if r is None:
                out += ("(not listed)" if c.startswith("control") else "NOT DETECTED").ljust(W)
                continue
            cls, strict, lenient, src = r
            out += (("ok   " if cls in strict else "MISS ") + f"{SHORT.get(cls, cls)} [{src}]").ljust(W)
        print(out)
    others = [s for s in seeds if s != TUNING_SEED]
    res = {}
    for name, ss in (("all seeds", seeds), (f"seed {TUNING_SEED} (tuning)", [s for s in seeds if s == TUNING_SEED]), ("hold-out seeds", others)):
        if not ss:
            continue
        st, le = tally(rows_by_seed, ss, 0), tally(rows_by_seed, ss, 1)
        print(f"=> {name}: STRICT {line(st)}")
        print(f"   {' ' * len(name)}  LENIENT {line(le)}")
        res[name] = {"strict": st, "lenient": le}
    return res


def extra_insights(res: dict) -> list:
    return [i["id"] for i in res["insights"] if case_of(i)[0] is None]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, nargs="*", default=SEEDS)
    ap.add_argument("--rules-only", action="store_true", help="score the rule table alone; no Gemini")
    ap.add_argument("--offline", action="store_true", help="no Gemini calls: cache, then trusted rules, then unclassified")
    ap.add_argument("--reuse", action="store_true", help="reuse data/eval/seed_<n>/results_pending.json if present")
    ap.add_argument("--keep", action="store_true", help="keep the large event files")
    ap.add_argument("--max-calls", type=int, default=70, help="stop before exceeding this many live Gemini calls")
    a = ap.parse_args()

    rows: dict = {}
    rules_rows: dict = {}
    calls = 0
    detail = {}
    for seed in a.seeds:
        res = prepare(seed, a.reuse, a.keep)
        ex = extra_insights(res)
        if ex:
            print(f"seed {seed}: insights outside the ground truth: {ex}")
        rules_rows[seed] = {}
        for i in res["insights"]:
            c, strict, lenient = case_of(i)
            if c:
                v = dg.rules_verdict(i)
                # rule-only answer: the rule's class when it names one class, else "abstain" (never a guess)
                cls = v["mapped_class"] if v["mapped_class"] else "unclassified_needs_review"
                src = "rule" if v["mapped_class"] else "rule abstains"
                if v["rule_name"] == "technical_bug_or_ux_friction":
                    src = "rule names two classes"
                rules_rows[seed][c] = (cls, strict, lenient, src)
        if a.rules_only:
            continue
        if calls >= a.max_calls:
            raise SystemExit(f"stopping: {calls} live calls reached --max-calls")
        stats = dg.diagnose_insights(res["insights"], res["meta"], a.offline, False, log=print)
        calls += stats["calls"]
        print(f"seed {seed}: {json.dumps(stats)}")
        rows[seed] = {}
        detail[seed] = []
        for i in res["insights"]:
            c, strict, lenient = case_of(i)
            d = i["diagnosis"]
            detail[seed].append({"id": i["id"], "case": c, "class": d["class"], "source": d["source"], "confidence": d["confidence"],
                                 "rules": d["rules"], "status": d["status"], "summary": d["summary"]})
            if c:
                rows[seed][c] = (d["class"], strict, lenient, d["source"] + ("" if d["rules"]["agreement"] != "overruled" else ", overruled rule"))
        (seed_dir(seed) / "results_diagnosed.json").write_text(json.dumps(res, indent=1, allow_nan=False) + "\n", encoding="utf-8")

    summary = {"rules_only": score(rules_rows, "RULES ONLY (Watchdog / builder hint table, no model). 'unclassified' = rule abstains")}
    if not a.rules_only:
        summary["agent"] = score(rows, f"DIAGNOSTIC AGENT ({dg.MODEL}, prompt {dg.PROMPT_VERSION}, rule hint shown to the model)")
        dis = [(s, d["case"], d["class"], d["rules"]["class"], d["rules"]["overrule_reason"]) for s, ds in detail.items() for d in ds
               if d["rules"]["flagged"]]
        print(f"\nrule vs model disagreements: {len(dis)}")
        for s, c, k, rk, why in dis:
            print(f"  seed {s} {c}: rule said {rk}, model said {k}. Reason: {(why or '')[:160]}")
        failed = [(s, d["id"]) for s, ds in detail.items() for d in ds if d["status"] == "failed"]
        print(f"\ninsights with no valid output (unclassified, status failed): {failed}")
        print(f"live Gemini calls this run: {calls}")
        summary.update({"live_calls": calls, "disagreements": len(dis), "failed": failed})
        (ROOT / "data" / "eval").mkdir(parents=True, exist_ok=True)
        (ROOT / "data" / "eval" / "eval_results.json").write_text(
            json.dumps({"summary": summary, "rows": {str(s): {c: [v[0], v[3]] for c, v in r.items()} for s, r in rows.items()}, "detail": detail},
                       indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
