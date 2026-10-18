# BigQuery source for the wallet sample

**All of it is synthetic sample data.** One dataset only: the wallet sample (`synthetic-v2`).

## What it is
The raw events of the wallet sample are loaded into a BigQuery table, and the pipeline can read them from there instead of from
`data/synthetic/events_raw.jsonl`:

| | |
|---|---|
| Table | `panopticon-hackathon.squint_samples.wallet_events` (region `us-central1`, labelled `synthetic=true`) |
| Rows | 205,189, one per raw event (18,870 sessions, 2026-09-15 to 2026-10-14) |
| Columns | `line_no` (the line in the source file), `event_id`, `session_id`, `platform`, `event_ts` (TIMESTAMP), `raw` (JSON: the event exactly as the source logged it) |

`event_id` is not unique in the sample (the generator plants 1,432 duplicates on purpose), so the export orders by `line_no`: two reads are byte-identical to each other and to the source file. The summary file the site publishes (`app/static/bigquery_source.json`) holds dataset, table, row count, dates and the read job id, but not the project id.

The raw event is kept whole in `raw`, so what comes back is the same record that went in. Checked on 2026-10-15: the 205,189 records read
from BigQuery equal the file's (key order aside), the canonical events are byte-identical, and the results are identical to the
file-based run (only the cached-or-Gemini labels on the saved diagnoses differ when the cache is reused offline).

## Commands
```
python pipeline/bq_source.py load                     # (re)load the table from data/synthetic/events_raw.jsonl (WRITE_TRUNCATE)
python pipeline/bq_source.py read --out raw.jsonl --meta app/static/bigquery_source.json
python pipeline/bq_source.py compare --a data/synthetic/events_raw.jsonl --b raw.jsonl
python pipeline/pipeline.py --source bigquery --workdir data/synthetic [--offline | --no-diagnose] [--publish]
```
`--source bigquery` exports the table to `<workdir>/events_raw.bq.jsonl`, uses that as the raw file for every stage and writes
`<workdir>/bigquery_source.json`; `--publish` copies that summary to `app/static/bigquery_source.json`. It refuses `--generate`.
Needs `pip install -r requirements.txt` (`google-cloud-bigquery`) and Application Default Credentials with BigQuery access to the project.

## What visitors see
In Onboarding Step 1 a third sample tile, **BigQuery table**, selects the wallet sample and shows the table name, row count and the id of the
last pipeline read, with "Read-only, no login". The page only reads `app/static/bigquery_source.json`; **it never queries BigQuery**, visitors do
not log in, and the Cloud Run service has no BigQuery access and needs none. Upload JSON and **Your own BigQuery** stay disabled ("Ping us to unlock"):
connecting a visitor's own warehouse would need sign-in and permissions that this demo does not offer.

## Derived tables (2026-10-16)
Three more synthetic tables sit next to `wallet_events` in `squint_samples`: `wallet_orders` (8,818 rows, derived 1:1 from completed purchases and top-ups), `audience_members` (1,973) and `watch_sessions` (60, timeline as JSON). Load with `python pipeline/bq_source.py load-derived` after a build. What is derived and what is not: `docs/squint-data-v3.md`. Same rules: the page never queries them, no visitor login, no Cloud Run access.

## Cost
The table is about 90 MB. Reading it scans the whole table once (about 89 MB billed per read, well inside the free tier).
