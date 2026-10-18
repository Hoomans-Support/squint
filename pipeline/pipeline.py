#!/usr/bin/env python3
"""One command: generate (optional) -> normalize -> Guardian -> Watchdog -> Diagnostic Agent -> results.json.

All data is SYNTHETIC in this build.

  python pipeline/pipeline.py                      # seed 42, data/synthetic, Gemini (cache first), writes results_v2.json
  python pipeline/pipeline.py --offline            # no network: cached diagnoses, trusted rules, else unclassified
  python pipeline/pipeline.py --generate --seed 7 --workdir data/eval/seed_7
  python pipeline/pipeline.py --publish            # also copy to app/static/results.json (only if no live UI claim)

Guardian and Watchdog run with --ground-truth when ground_truth.json is in the work dir: a failed check stops the run.
The diagnose step is build_results.py --diagnose (same process, evidence stays in memory); data/cache/ holds the saved outputs.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from strip_hidden import leftovers, strip_hidden

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
# One entry per sample dataset (pipeline/profiles/): which generator and mapping it uses and where its files go.
PROFILES = {
    "wallet": {"generator": "generate_v2.py", "mapping": "mapping_synthetic_v2.json", "workdir": "data/synthetic",
               "result": "results_v2.json", "published": "results.json", "dataset": "synthetic-v2"},
}


def run(args: list, label: str) -> None:
    t0 = time.time()
    r = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = (r.stdout.strip().splitlines() or [""])[-1][:160]
    print(f"[{label}] {'ok' if r.returncode == 0 else 'FAILED'} in {time.time() - t0:.0f}s  {tail}")
    if r.returncode != 0:
        print(r.stdout[-1500:], r.stderr[-1500:])
        raise SystemExit(f"stage {label} failed")


def stages(workdir: Path, seed: int, generate: bool, diagnose: bool, offline: bool, refresh: bool, out: Path, prof: dict, source: str = "file") -> None:
    raw, canon = workdir / "events_raw.jsonl", workdir / "canonical_events.jsonl"
    gt, grd, wd = workdir / "ground_truth.json", workdir / "guardian_report.json", workdir / "watchdog_candidates.json"
    if generate:
        run([HERE / prof["generator"], "--seed", seed, "--out", workdir], "generate")
    if source == "bigquery":      # the same raw events, read from the BigQuery table instead of the file (pipeline/bq_source.py)
        raw = workdir / "events_raw.bq.jsonl"
        run([HERE / "bq_source.py", "read", "--out", raw, "--meta", workdir / "bigquery_source.json"], "bigquery read")
    if not raw.exists():
        raise SystemExit(f"{raw} not found: run with --generate")
    first = json.loads(next(open(raw, encoding="utf-8")))          # checked before any stage writes: a wrong --profile or --workdir must not overwrite files
    if first.get("_dataset") != prof["dataset"]:
        raise SystemExit(f"{raw} holds dataset {first.get('_dataset')!r} but the profile expects {prof['dataset']!r}: check --profile and --workdir")
    run([HERE / "normalize.py", "--mapping", HERE / prof["mapping"], "--input", raw, "--out", canon], "normalize")
    g = ["--ground-truth", gt] if gt.exists() else []
    run([HERE / "guardian.py", "--input", canon, "--out", grd, *g], "guardian")
    run([HERE / "watchdog.py", "--input", canon, "--guardian", grd, "--out", wd, "--seed", seed, *g], "watchdog")
    b = [HERE / "build_results.py", "--events", canon, "--raw", raw, "--guardian", grd, "--watchdog", wd, "--out", out]
    if diagnose:
        b += ["--diagnose"] + (["--offline"] if offline else []) + (["--refresh"] if refresh else [])
    run(b, "build_results + diagnose" if diagnose else "build_results")


def ui_claim_live() -> str | None:
    """The board row that claims app/static, if any, so the final copy never lands under someone's UI work."""
    f = ROOT / "agent-coordination.md"      # optional local board: without it there is no claim to respect
    if not f.exists():
        return None
    board = f.read_text(encoding="utf-8")
    sec = board.split("## Active claims", 1)[-1].split("\n## ", 1)[0]
    for line in sec.splitlines():
        if line.startswith("|") and re.search(r"app/static", line) and "_unassigned_" not in line.split("|")[1]:
            return line.split("|")[1].strip()
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", choices=sorted(PROFILES), default="wallet", help="which sample dataset (default: wallet)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workdir", help="default: the profile's folder (data/synthetic)")
    ap.add_argument("--generate", action="store_true", help="regenerate the raw synthetic events first")
    ap.add_argument("--out", help="default: <workdir>/<the profile's results file>")
    ap.add_argument("--source", choices=("file", "bigquery"), default="file",
                    help="where the raw events come from (bigquery: wallet sample only, table described in bq_source.py)")
    ap.add_argument("--no-diagnose", action="store_true")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="ignore cached diagnoses and call Gemini again (costs calls)")
    ap.add_argument("--publish", action="store_true", help="copy the result to app/static/results.json if no UI claim is live")
    a = ap.parse_args()
    prof = PROFILES[a.profile]
    if a.source == "bigquery" and a.profile != "wallet":
        raise SystemExit("--source bigquery only exists for the wallet sample")
    if a.source == "bigquery" and a.generate:
        raise SystemExit("--generate writes the raw file: load it with `bq_source.py load`, then run with --source bigquery")
    os.environ["SQUINT_PROFILE"] = a.profile      # every stage below reads it (pipeline/profiles/)
    wd = Path(a.workdir or prof["workdir"])
    wd = wd if wd.is_absolute() else ROOT / wd
    out = Path(a.out) if a.out else wd / prof["result"]
    out = out if out.is_absolute() else ROOT / out
    stages(wd, a.seed, a.generate, not a.no_diagnose, a.offline, a.refresh, out, prof, a.source)
    print(f"results: {out}")
    if a.publish:
        who = ui_claim_live()
        if who:
            print(f"not published: '{who}' still claims app/static. Left at {out}; add a Handoffs row instead.")
        else:
            pub = ROOT / "app" / "static" / prof["published"]       # the published copy has the hidden user groups taken out (pipeline/strip_hidden.py); the build in the work folder keeps them
            clean = strip_hidden(json.loads(out.read_text(encoding="utf-8")))
            left = leftovers(clean)
            if left:       # never publish a file that still mentions a hidden group
                raise SystemExit(f"not published: {len(left)} hidden-group mentions survive the strip, first: {left[0]}")
            pub.write_text(json.dumps(clean, indent=1, allow_nan=False) + "\n", encoding="utf-8")
            print(f"published to app/static/{prof['published']}")
            if a.source == "bigquery":
                shutil.copyfile(wd / "bigquery_source.json", ROOT / "app" / "static" / "bigquery_source.json")
                print("published to app/static/bigquery_source.json")


if __name__ == "__main__":
    main()
