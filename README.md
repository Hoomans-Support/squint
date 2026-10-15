# Squint

An agentic behavior dashboard for AI Builder Cup 2026. It watches product event data, finds the screens and user groups where people struggle, and explains why in plain English.

> **All data in this repo is synthetic.** It was generated to look like a SmartSari-style fintech app. Nothing here comes from real users, and the dashboard, deck and video say so.

Live demo (public, synthetic data only): https://squint.web.app

**Team Hoomans Support**: [@chelseacastro](https://github.com/chelseacastro) and [@angelicawiliana](https://github.com/angelicawiliana).

## What it does

Product analytics usually shows that users drop off, not why. Squint runs a three-tier pipeline over event data and writes one file, `results.json`, that the dashboard reads.

| Tier | Component | Job | Uses AI |
|---|---|---|---|
| 0 | **Guardian** | Detects telemetry faults (a silent tracker, row loss, an unmapped property, a double-firing event) and quarantines those windows so they are not mistaken for user drop-off | No |
| 1 | **Watchdog** | Finds screens that got worse over time, time-window bursts and user groups that do worse than everyone else, using exact tests, corrected thresholds and minimum sample sizes | No |
| 2 | **Diagnostic Agent** | Classifies each finding (technical bug, UX friction, language/cognitive overload, behavior pattern, natural exit, or unclassified), with confidence, an explanation and a next step | Gemini (`gemini-2.5-flash`), checked by code |

Code computes and checks; Gemini only classifies and explains. Every number the model quotes must appear in the evidence package or the answer is rejected and retried, and the fallback is "unclassified, needs review", never a guess.

Measured against the planted ground truth (five seeds: 42, 7, 123, 2024, 99, 48 cases): the rule table alone scores 43/48, the Diagnostic Agent 47/48 with no wrong class. The prompt was tuned once on seed 42, so the other four seeds are a partial hold-out. Per-case results come from `pipeline/eval.py`.

The dashboard has seven tabs: Onboarding, Overview, Journeys, Friction, Cohorts, Ask and Brief. Ask answers only from the saved results.

## Run the dashboard

The repo includes a ready `app/static/results.json`, so the dashboard runs without generating anything. Python 3.11 or newer.

```bash
python -m venv .venv
.venv/Scripts/activate            # macOS/Linux: source .venv/bin/activate
pip install -r app/requirements.txt
python app/server.py              # http://127.0.0.1:8080
```

On Windows you can also double-click `run-dashboard.cmd` (it expects `.venv` to exist).

The three Gemini endpoints (Ask, Fact-check, Brief rewrite) are guarded and off unless switched on by an environment flag (`ASK_GEMINI_ENABLED`, `FACTCHECK_ENABLED`, `BRIEF_AI_ENABLED`; see `docs/factcheck-endpoint.md` and `docs/brief-ai-endpoint.md`). The dashboard works without them.

## Rebuild the data and results

Run from the repo root. Generated data goes in `data/`, which is git-ignored (about 170 MB per seed).

```bash
# Generate synthetic events, normalize, run Guardian and Watchdog (both check themselves against ground truth),
# then build results.json. No Gemini here:
python pipeline/pipeline.py --generate --seed 42 --workdir data/synthetic --no-diagnose

# With the Diagnostic Agent (Gemini through Vertex AI; saved answers in data/cache/ are reused):
gcloud auth application-default login
python pipeline/pipeline.py --workdir data/synthetic
python pipeline/pipeline.py --workdir data/synthetic --offline   # no network: cache, then rules, then unclassified

# Read the wallet sample from BigQuery instead of the file (see docs/bigquery-source.md; needs google-cloud-bigquery and the same login)
python pipeline/bq_source.py load                      # once: load data/synthetic/events_raw.jsonl into the table
python pipeline/pipeline.py --source bigquery --workdir data/synthetic --offline

# Accuracy against the planted patterns, five seeds
python pipeline/eval.py --rules-only
python pipeline/eval.py
```

`pipeline/pipeline.py --publish` copies the result to `app/static/results.json`. Gemini calls need `pip install -r requirements.txt` and a Google Cloud project with Vertex AI enabled. Never put keys or tokens in this folder.

## Synthetic data

`pipeline/generate_v2.py` (dataset `synthetic-v2`, brief in `docs/smartsari-dataset-spec.md`) produces 1,000 users in seven groups over 30 days, with planted patterns so detections can be checked:

| ID | Pattern | Expected |
|---|---|---|
| P1 | OTP not delivered for 8 hours (Oct 9) | Technical bug |
| P2 | Large businesses top up far more than others | Behavior pattern, not a problem |
| P3 | Sari-sari stores buy e-load in most transactions | Behavior pattern, not a problem |
| P4 | Individual traders abandon send-money at checkout | Technical bug or UX friction |
| M1 | Fraudster bursts at night, shared devices | Unclassified, needs review |
| M2 | Unregistered users check prices repeatedly before registering | Natural exit |
| G1-G4 | Silent tracker, row loss, unmapped property, double-firing checkout | Guardian faults, quarantined |
| control | Steady 18% and 8% drop at Personal data and TIN | UX friction |

`pipeline/generate.py` is the earlier `synthetic-v1` generator, kept as a rollback.

### A second sample: a dining app
To show that Squint is not tied to one product, there is a second synthetic dataset, `synthetic-dining-v1`: a food ordering and table booking app with its own raw event layout (translated by `pipeline/mapping_dining.json`), its own labels and story, and the same internal ids, so the whole pipeline and dashboard run unchanged. The Onboarding page lets you pick a dataset (wallet or dining) and, separately, a flow (the journeys and the source events each step reads); a flow that does not match the data is flagged with measured counts and Squint will not continue until you pick one that does. The Diagnostic Agent got 9 of 9 dining findings right without any tuning on that dataset. Details, planted patterns and commands: [docs/dining-dataset.md](docs/dining-dataset.md).

```bash
python pipeline/pipeline.py --profile dining --generate --seed 42   # generate, check, diagnose and build the dining results
```

## Repo layout

| Path | Contents |
|---|---|
| `pipeline/` | Schema, generators, dataset profiles (`profiles/`), normalizer, mapping configs, Guardian, Watchdog, Diagnostic Agent (`diagnose.py`), results builder, eval, results contract |
| `app/` | Flask server and the dashboard (`static/`: plain HTML, CSS and JS, no build step), the guarded Gemini endpoints, Dockerfile, tests |
| `app/tests/` | `clickthrough.py` (Playwright, 199 checks; `--real` reads `app/static/results.json`), endpoint tests, contrast and layout audits |
| `docs/` | Dataset spec, results needs, deploy notes, endpoint notes |
| `data/` | Generated data and cached AI output (git-ignored, not in the image) |

Browser tests: `pip install playwright`, start the server, then `PYTHONUTF8=1 python app/tests/clickthrough.py <screenshot-folder> --real`.

## Deployment

Google Cloud project `panopticon-hackathon` (the id cannot change), region `us-central1`. Firebase Hosting (`squint.web.app`) serves the static dashboard from the CDN and passes `/api` to the Cloud Run service `squint`; Vertex AI serves Gemini for the offline pipeline. The image holds the server, the guarded Ask and Fact-check modules and `static/`. Everything shown is saved output; the only live model call is Ask answering a free-text question, and only when the service has `ASK_GEMINI_ENABLED=1`.

## Cut to fit the hackathon timeline

Real-time ingestion, graph or vector memory, and live uploads or database connections (the demo is gated to the sample dataset).

## Team

Built by **Team Hoomans Support** for AI Builder Cup 2026: [@chelseacastro](https://github.com/chelseacastro) and [@angelicawiliana](https://github.com/angelicawiliana).
