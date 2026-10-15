#!/usr/bin/env python3
"""BigQuery as a source for the wallet sample (dataset synthetic-v2). ALL OF IT IS SYNTHETIC SAMPLE DATA.

The raw events of the wallet sample live in a BigQuery table in this project. The pipeline can read them from there instead of from
data/synthetic/events_raw.jsonl (pipeline.py --source bigquery). Nothing else changes: the rows come back as the same JSON records, so
Guardian, Watchdog, the Diagnostic Agent and the results are identical (checked with `compare`).

Table: <project>.squint_samples.wallet_events, one row per raw event:
  line_no INT64 (the line in the source file), event_id STRING, session_id STRING, platform STRING, event_ts TIMESTAMP,
  raw JSON (the event exactly as the source logged it)
Only the wallet sample is loaded; the dining sample stays file-based.

The dashboard never queries BigQuery. Visitors do not log in and cannot run queries: the pipeline reads the table with the builder's
Application Default Credentials, and the page only shows a small summary file this script writes (app/static/bigquery_source.json).

  python pipeline/bq_source.py load                       # (re)load the table from data/synthetic/events_raw.jsonl
  python pipeline/bq_source.py read --out <raw.jsonl> [--meta app/static/bigquery_source.json]
  python pipeline/bq_source.py compare --a <raw.jsonl> --b <raw.jsonl>   # same events? (ignores key order)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = os.environ.get("SQUINT_BQ_PROJECT", "panopticon-hackathon")
LOCATION = "us-central1"
DATASET = "squint_samples"
TABLE = "wallet_events"
FQ = f"{PROJECT}.{DATASET}.{TABLE}"
DEFAULT_RAW = ROOT / "data" / "synthetic" / "events_raw.jsonl"
DEFAULT_META = ROOT / "app" / "static" / "bigquery_source.json"
DESCRIPTION = ("SYNTHETIC sample data for the Squint demo (a made-up mobile wallet app). No real customer data. "
               "One row per raw event; raw holds the event as the source logged it.")


def client():
    from google.cloud import bigquery
    return bigquery.Client(project=PROJECT, location=LOCATION)


def load(raw_path: Path) -> None:
    from google.cloud import bigquery
    bq = client()
    ds = bigquery.Dataset(f"{PROJECT}.{DATASET}")
    ds.location = LOCATION
    ds.description = DESCRIPTION
    ds.labels = {"synthetic": "true", "app": "squint"}
    bq.create_dataset(ds, exists_ok=True)
    # line_no is the event's line in the source file: event_id repeats in the sample (the generator plants duplicates), so the export orders by line_no
    schema = [bigquery.SchemaField("line_no", "INT64", mode="REQUIRED"), bigquery.SchemaField("event_id", "STRING", mode="REQUIRED"),
              bigquery.SchemaField("session_id", "STRING"), bigquery.SchemaField("platform", "STRING"),
              bigquery.SchemaField("event_ts", "TIMESTAMP"), bigquery.SchemaField("raw", "JSON")]
    tmp = tempfile.NamedTemporaryFile("w", suffix=".ndjson", delete=False, encoding="utf-8", newline="\n")
    try:
        # one NDJSON row per raw event; raw is the original record as a JSON string (a JSON column takes the value as text in a load file)
        n = 0
        with tmp, open(raw_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                ts = datetime.fromisoformat(r["timestamp"]).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
                n += 1
                tmp.write(json.dumps({"line_no": n, "event_id": r["event_id"], "session_id": r.get("session_id"), "platform": r.get("platform"),
                                      "event_ts": ts, "raw": json.dumps(r, ensure_ascii=False, separators=(",", ":"))}) + "\n")
        cfg = bigquery.LoadJobConfig(source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON, schema=schema,
                                     write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE)
        with open(tmp.name, "rb") as fh:
            job = bq.load_table_from_file(fh, FQ, job_config=cfg)
        job.result()
    finally:
        os.unlink(tmp.name)      # also when a bad line stops the build of the file
    t = bq.get_table(FQ)
    t.description = DESCRIPTION
    t.labels = {"synthetic": "true", "app": "squint"}
    bq.update_table(t, ["description", "labels"])
    print(f"loaded {n:,} events into {FQ} ({bq.get_table(FQ).num_rows:,} rows)")


def read(out: Path, meta_path: Path | None) -> None:
    bq = client()
    job = bq.query(f"SELECT raw FROM `{FQ}` ORDER BY line_no")      # the source file's own order (event_id is not unique)
    n = 0
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        for row in job.result():
            raw = row["raw"]
            rec = json.loads(raw) if isinstance(raw, str) else raw
            f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
            n += 1
    stats = next(iter(bq.query(f"SELECT COUNT(*) n, MIN(event_ts) a, MAX(event_ts) b, COUNT(DISTINCT session_id) s FROM `{FQ}`").result()))
    t = bq.get_table(FQ)
    print(f"read {n:,} events from {FQ} (job {job.job_id}) into {out}")
    if meta_path:
        meta = {"synthetic": True, "note": "Synthetic sample data. Read by the pipeline with the builder's credentials; visitors do not log in and cannot query it.",
                "dataset": DATASET, "table": TABLE, "location": LOCATION,      # no project id: this file is published with the site
                "rows": int(stats["n"]), "sessions": int(stats["s"]),
                "first_event": stats["a"].strftime("%Y-%m-%dT%H:%M:%SZ"), "last_event": stats["b"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "size_bytes": int(t.num_bytes or 0), "read_job_id": job.job_id, "bytes_billed": int(job.total_bytes_billed or 0),
                "read_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {meta_path}")


def compare(a: Path, b: Path) -> int:
    def lines(p):
        with open(p, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]
    la, lb = lines(a), lines(b)
    same = len(la) == len(lb) and all(x == y for x, y in zip(la, lb))     # dict equality ignores key order
    print(f"{len(la):,} vs {len(lb):,} events: {'IDENTICAL' if same else 'DIFFERENT'}")
    return 0 if same else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("load"); p.add_argument("--input", type=Path, default=DEFAULT_RAW)
    p = sub.add_parser("read"); p.add_argument("--out", type=Path, required=True); p.add_argument("--meta", type=Path, default=None)
    p = sub.add_parser("compare"); p.add_argument("--a", type=Path, required=True); p.add_argument("--b", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "load":
        load(a.input)
    elif a.cmd == "read":
        read(a.out, a.meta)
    else:
        return compare(a.a, a.b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
