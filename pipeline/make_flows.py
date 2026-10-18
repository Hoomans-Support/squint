#!/usr/bin/env python3
"""Write the sample flow definitions the Onboarding page checks against a dataset. SYNTHETIC samples.

A flow is what a customer tells Squint about their app: journeys, their steps, and the source event (the raw screen name) each step
reads. Squint checks a chosen flow against the events a dataset really logs, so a flow written for a different app is flagged.

Both files are derived, not hand-written: the journeys and step names come from each dataset's results file (scope.journeys), and the
raw event names come from its mapping file (maps.app_screens, the raw screens the source logs).

  python pipeline/make_flows.py

Writes app/static/flows/wallet.json and flows/source_events.json (the raw screens the dataset logs).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = [
    {"id": "wallet", "name": "Wallet app flow", "tagline": "Sign up and login, wallet top-up, and transaction steps of a mobile wallet.",
     "results": "app/static/results.json", "mapping": "pipeline/mapping_synthetic_v2.json"},
]


def main() -> None:
    out_dir = ROOT / "app" / "static" / "flows"
    out_dir.mkdir(parents=True, exist_ok=True)
    source_events = {}
    for s in SAMPLES:
        mapping = json.loads((ROOT / s["mapping"]).read_text(encoding="utf-8"))
        raw_of = {canon: raw for raw, canon in mapping["maps"]["app_screens"].items()}      # canonical screen -> the raw name the source logs
        scope = json.loads((ROOT / s["results"]).read_text(encoding="utf-8"))["scope"]
        journeys = []
        for j in scope["journeys"]:
            steps = [{"id": st["id"], "name": st["name"], "event": " | ".join(raw_of[c.strip()] for c in st["event"].split("|"))} for st in j["steps"]]
            journeys.append({"id": j["id"], "name": j["name"], "steps": steps})
        flow = {"id": s["id"], "name": s["name"], "tagline": s["tagline"], "synthetic": True, "journeys": journeys}
        (out_dir / f"{s['id']}.json").write_text(json.dumps(flow, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        source_events[s["id"]] = sorted(mapping["maps"]["app_screens"])
        print(f"{s['id']}: {len(journeys)} journeys, {sum(len(j['steps']) for j in journeys)} steps, {len(source_events[s['id']])} source screens")
    (out_dir / "source_events.json").write_text(json.dumps(source_events, indent=1) + "\n", encoding="utf-8")
    print("wrote", out_dir)


if __name__ == "__main__":
    main()
