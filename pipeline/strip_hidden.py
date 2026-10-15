#!/usr/bin/env python3
"""Take the hidden user groups out of a results file before it is published. ALL DATA HERE IS SYNTHETIC.

The dashboard never shows two groups: the fraud-like one (Fraudster in the wallet sample, Promo abusers in the dining sample) and Unknown.
Until now the page only hid them when it loaded results.json, so anyone who opened the file could still read their rows. This step
removes them from the file itself, so the published copy no longer contains them. What the page shows does not change: the same
findings, cohorts, replays, Ask answers and group rows are dropped that the page used to drop at load (scrub() in app/static/app.js),
plus the group-keyed views, table rows, breakdown rows, evidence sessions and group lists the page already filtered out when drawing.

  python pipeline/strip_hidden.py --in data/synthetic/results_v2.json --out app/static/results.json

Aggregate numbers (session and event counts, rates for everyone else) are left as they are: they describe the whole sample.
`pipeline.py --publish` calls this, so a published file is always stripped. The unstripped build stays in the work folder (data/, git-ignored).
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

HIDDEN_PERSONAS = {"fraudster", "unknown"}      # Unknown is hidden everywhere (filters, Ask, model); the page's scrub() drops only Fraudster-only findings because none is Unknown-only
DATASETS_FILE = Path(__file__).resolve().parent.parent / "app" / "static" / "datasets.json"


def _hidden_text() -> re.Pattern:
    """The words the page hides: ui.hidden_text of every dataset in datasets.json (so a new dataset or a reworded label is covered), plus the built-in ones."""
    words = ["fraud|shared-device|promo[ -]?abus"]
    try:
        for ds in json.loads(DATASETS_FILE.read_text(encoding="utf-8")).get("datasets", []):
            t = (ds.get("ui") or {}).get("hidden_text")
            if t and t not in words:
                words.append(t)
    except (OSError, ValueError):
        pass
    return re.compile("|".join(f"(?:{w})" for w in words), re.I)


HIDDEN_TEXT = _hidden_text()


def strip_hidden(src: dict) -> dict:
    d = copy.deepcopy(src)
    hid = HIDDEN_TEXT.search

    # --- what the page's scrub() already dropped at load
    gone = {i["id"] for i in d.get("insights", []) if i.get("persona_ids") and all(p in HIDDEN_PERSONAS for p in i["persona_ids"])}
    d["insights"] = [i for i in d.get("insights", []) if i["id"] not in gone]
    for vw in d.get("views", {}).values():
        vw["insight_ids"] = [x for x in vw.get("insight_ids", []) if x not in gone]
        b = vw.get("blind")
        if b and isinstance(b.get("bars"), list):
            bars = [x for x in b["bars"] if not hid(x["l1"] + " " + x["l2"])]
            peak = max([0] + [x["value"] for x in bars])
            if len(bars) < 2 or not b["baseline"] > 0 or peak < 1.5 * b["baseline"]:
                vw["blind"] = None
            else:
                b["bars"] = [{**x, "hot": x["value"] >= 1.5 * b["baseline"]} for x in bars]
                b["badge"] = f"{peak / b['baseline']:.1f}x the overall rate"
        c = vw.get("cohorts")
        if c and isinstance(c.get("items"), list):
            c["items"] = [x for x in c["items"] if not hid(x.get("name") or "")]
            if isinstance(c.get("note"), str):
                c["note"] = " ".join(s for s in re.split(r"(?<=\.)\s+", c["note"]) if not hid(s))
    d["stuck_sessions"] = [s for s in d.get("stuck_sessions", []) if s.get("persona") not in HIDDEN_PERSONAS and s.get("insight_id") not in gone]
    d["intents"] = [x for x in d.get("intents", []) if not hid(json.dumps(x))]
    d["ask"] = [x for x in d.get("ask", []) if not hid(json.dumps(x))]

    # --- group-keyed structures the page filtered out when drawing
    keep_key = lambda k: not any(part in HIDDEN_PERSONAS for part in str(k).split("|"))
    d["views"] = {k: v for k, v in d.get("views", {}).items() if keep_key(k)}
    d["journeys"] = {k: v for k, v in d.get("journeys", {}).items() if keep_key(k)}
    ov = d.get("overview", {})
    if isinstance(ov.get("views"), dict):
        ov["views"] = {k: v for k, v in ov["views"].items() if keep_key(k)}
        for v in ov["views"].values():
            if isinstance(v.get("table"), list):
                v["table"] = [r for r in v["table"] if r.get("persona") not in HIDDEN_PERSONAS]
    if isinstance(d.get("filters", {}).get("personas"), list):
        d["filters"]["personas"] = [p for p in d["filters"]["personas"] if p not in HIDDEN_PERSONAS]
    if isinstance(d.get("scope", {}).get("personas"), list):
        d["scope"]["personas"] = [p for p in d["scope"]["personas"] if p.get("id") not in HIDDEN_PERSONAS]
    for i in d["insights"]:
        if isinstance(i.get("breakdown"), list):
            i["breakdown"] = [x for x in i["breakdown"] if not (x.get("dim") == "persona" and x.get("value") in HIDDEN_PERSONAS)]
        ev = i.get("evidence")
        if isinstance(ev, dict) and isinstance(ev.get("sessions"), list):
            ev["sessions"] = [s for s in ev["sessions"] if s.get("persona") not in HIDDEN_PERSONAS]
    return d


def leftovers(d: dict) -> list[str]:
    """Paths that still mention a hidden group (empty means clean)."""
    out: list[str] = []

    def walk(x, path=""):
        if isinstance(x, dict):
            for k, v in x.items():
                if hid_key(k):
                    out.append(f"{path}/{k} (key)")
                walk(v, f"{path}/{k}")
        elif isinstance(x, list):
            for n, v in enumerate(x):
                walk(v, f"{path}[{n}]")
        elif isinstance(x, str) and (HIDDEN_TEXT.search(x) or x in HIDDEN_PERSONAS):
            out.append(f"{path}: {x[:60]!r}")

    hid_key = lambda k: bool(HIDDEN_TEXT.search(str(k))) or any(part in HIDDEN_PERSONAS for part in str(k).split("|"))
    walk(d)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--strict", action="store_true", help="exit 1 if any hidden-group mention is left")
    a = ap.parse_args()
    d = strip_hidden(json.loads(a.src.read_text(encoding="utf-8")))
    left = leftovers(d)
    a.out.write_text(json.dumps(d, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    print(f"wrote {a.out} ({len(left)} hidden-group mentions left)")
    for line in left[:15]:
        print("  left:", line)
    return 1 if (left and a.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
