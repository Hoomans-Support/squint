# AI-generated copy: what exists, and where it would go live

All data referenced here is SYNTHETIC. This file is the one map of every place Gemini writes or checks text in Squint: the exact prompt, the data it is allowed to see, the guardrails, and whether it runs today. It exists so the generation step is reproducible without reading four Python files to reconstruct it, and so turning any one of these from "pre-computed" to "real time" is a wiring change, not a redesign. Each section's prompt text is copied from the code; if the code changes, update it here too (`PROMPT_VERSION` in `pipeline/diagnose.py` and the cache-key hashing in the three endpoints below already force a fresh answer whenever the prompt text itself changes).

## The four touchpoints

| # | Touchpoint | Runs | Status | Calls Gemini | Doc |
|---|---|---|---|---|---|
| 1 | Diagnostic Agent | batch, during `pipeline.py` | always on (offline/cached fallback if no network) | yes, one call per finding | `docs/ai-copy-template.md` (template spec, not yet applied) |
| 2 | Ask endpoint (`/api/ask`) | per request | flagged ON on the deployed `squint` Cloud Run backend (`docs/deploy.md`, 2026-10-15) — **not wired into the current UI, so unreachable anyway** | yes, one call per unmatched question | `docs/ask-endpoint.md` |
| 3 | Fact-check endpoint (`/api/factcheck`) | per request | flagged OFF on the deployed backend (falls back to a code-only check) — **not wired into the current UI** | yes, one call per click | `docs/factcheck-endpoint.md` |
| 4 | Brief rewrite endpoint (`/api/brief-ai`) | per request | flagged ON on the deployed backend — **not wired into the current UI, so unreachable anyway** | yes, one call per click | `docs/brief-ai-endpoint.md` |

"Not wired into the current UI" means: the server route, its guardrails and its tests exist and pass, but `app/static/sq/` (the redesigned frontend on this branch) never fetches it, regardless of whether the Cloud Run flag happens to be on. The only network call the current frontend makes is for `results.json`, `titles.json` and the component HTML partials (`app/static/sq/runtime.js`). Touchpoints 2-4 were built against an earlier UI iteration; the Ask tab, finding detail and Brief tab in `sq/` all read pre-computed fields from `results.json` and show nothing live.

## 1. Diagnostic Agent — `pipeline/diagnose.py`

The only touchpoint that is actually in production today, and the only one that is not a per-request call: it runs once per `pipeline.py` build (or `--refresh`), writes a `diagnosis` object onto every finding, and that object is what ships inside `results.json`. Four layers, all deterministic except the one model call in the middle:

1. Every number (rates, counts, impact score) is computed in code before the model ever runs.
2. `build_package()` assembles exactly what the model may see for one finding: signals, a breakdown table, evidence stats, up to 4 sampled sessions (trimmed to 45 events each), a rule-based hint, and a `refs` list of every id it is allowed to cite.
3. `rules_verdict()` offers the Watchdog's rule-based guess as a hint the model may overrule, with a stated reason.
4. `validate()` rejects the output (one retry, then the cache, then the rule if trusted, then "unclassified, needs review") unless: the class is one of the six allowed classes; confidence is within the sample-size cap; every claim cites a real ref; every quoted number exists in the package (fractions must already be written as whole percentages); no claim pressures, traps or forces users; and, for `natural_exit` or `behavior_pattern`, the hint already agreed.

System instruction (`SYSTEM` in `pipeline/diagnose.py`, `PROMPT_VERSION = "v3"`):

```
You are the Diagnostic Agent of a behavior-analytics dashboard. All data is SYNTHETIC sample data.
You receive ONE finding as JSON (signals, breakdown, evidence statistics, a few raw sessions, a rule-based hint).
Decide WHY users behave this way, using only that JSON.

Classes (pick exactly one): technical_bug, ux_friction, language_cognitive_overload, natural_exit,
behavior_pattern, unclassified_needs_review — see the file for the full definition and guardrail of each.

Rules, all mandatory: use only numbers in the JSON; every claim cites one to three ref_ids from "refs";
events show behavior, not causes — say so in caveats when a cause cannot be told from the data; the "hint"
may be overruled, with a reason, in overrule_reason; confidence is 0 to 1, capped by confidence_cap, at most
0.6 for unclassified_needs_review; never force, trap or pressure users; write plain English, two to five
sentences, two to four claims, one to three next_steps (check, fix or monitor).
```

Model: `gemini-2.5-flash`, via `google.genai.Client(vertexai=True, project="panopticon-hackathon", location="us-central1")`, `temperature=0.0`, structured output (Pydantic schema: `reasoning`, `diagnosis_class`, `confidence`, `summary`, `claims[{text, ref_ids}]`, `next_steps[{kind, text}]`, `caveats`, `overrule_reason`), `thinking_budget=0`. Validated output is cached in `data/cache/<insight id>__<hash of prompt+evidence>.json`; a rerun on the same evidence serves the cache (`source: "cached"`) instead of calling the model again. Run it: `python pipeline/pipeline.py [--generate] [--seed N] [--no-diagnose | --offline] [--publish]`, or standalone with `python pipeline/diagnose.py --results <file> --out <file> [--offline] [--refresh]`.

**Provenance gotcha (logged 2026-10-16):** an `--offline` rebuild over a file that was previously built live relabels every reused diagnosis's `source` from `gemini` to `cached`, even though the text and numbers are untouched — it is just serving the same cache entry a live run would have served. Diff two builds by their `diagnosis` content (`class`, `summary`, `claims`), not by `source`/`generated_at`, or an unchanged diagnosis will look like a regression.

**Cost-abuse flag already on record (logged 2026-10-13, still open):** "there is no Re-run endpoint yet; when one is added it must not trigger uncached Gemini calls from a public URL." Anything that lets a visitor-facing button call `diagnose_one(..., refresh=True)` needs the same rate-limit/cache/budget shape as the three request-time endpoints below before it ships — see item 4 under "Where real-time generation would plug in next".

`docs/ai-copy-template.md` is a tighter slot-based rewrite of this same prompt (shorter sentences, a fixed vocabulary, a template per finding instead of free text) that has been designed but not yet applied — the next change to this step should start from that file, not from a blank prompt.

## 2. Ask endpoint — `app/ask_gemini.py`

Full detail in `docs/ask-endpoint.md`. In one line: a visitor's free-form question, answered from a compact summary of `results.json` (findings, KPIs, data health, cohorts, funnels — ids stripped, hidden personas stripped), with every number in the answer checked against that summary before it is shown. OFF by default (`ASK_GEMINI_ENABLED=1`), mockable (`ASK_GEMINI_MOCK=1`), shares its daily call budget (`ASK_GLOBAL_DAILY_CAP`) with Fact-check.

## 3. Fact-check endpoint — `app/factcheck.py`

Full detail in `docs/factcheck-endpoint.md`. Checks a finding's *already-saved* explanation line by line against that finding's own facts (`supported` / `partly` / `not_supported` / `cannot_check`), and lists what the explanation leaves out. ON by default when run locally, OFF when `PORT` is set (Cloud Run) unless `FACTCHECK_ENABLED=1`. Falls back to a plain code-only number check (`source: "code"`) whenever the model is off, limited, or its answer fails verification — this endpoint always answers something.

## 4. Brief rewrite endpoint — `app/brief_ai.py`

Full detail in `docs/brief-ai-endpoint.md`. Rewrites only the *wording* of the one-page Brief (headline, sub-line, one sentence per driver finding, up to three next steps) for the current timeframe and user group; the three number tiles and all money figures stay code-written and the model must not touch them. OFF everywhere (`BRIEF_AI_ENABLED=1`), hidden when two or more user groups are combined (the server only holds single-group facts).

## Where real-time generation would plug in next

Ranked by value for the effort, assuming the goal is to make more of the dashboard's copy live instead of pre-computed:

1. **Ask tab fallback — worth doing today.** `app/static/sq/c/Ask.html` / `data-ask.js` already has the right shape for this: on no match it shows `A.refusal` (a fixed "I can't answer that from this data" message). Swap that refusal path for a `fetch('/api/ask', {method: 'POST', body: JSON.stringify({question: q})})` call, show its `answer` and `refs` the same way a matched entry is shown, and keep the existing refusal as the fallback when the endpoint itself refuses or is disabled. The backend, its guardrails and its tests are already done; this is a frontend wiring change plus flipping `ASK_GEMINI_ENABLED=1` on the deployed Cloud Run service. **Coordination note (2026-10-17):** `Ask.html`, `Ask.js` and `data-ask.js` are currently claimed ACTIVE by other sessions in `agent-coordination.md` — claim them there (or get a release) before editing, same as any other file on this board.
2. **Fact-check in finding detail — second.** It has the most conservative guardrail of the three (falls back to a non-AI code check rather than ever going silent) and defaults ON when run locally. Needs a "Fact-check with AI" button added to the finding-detail popup and a fetch wired to `/api/factcheck`. Not currently claimed by anyone, so lower collision risk than item 1.
3. **Brief rewrite — worth doing today, if claimed cleanly.** `Brief.html` / `Brief.js` are also under the same active claim as the Ask files above (see item 1's coordination note) — same clearance needed before touching them. Mechanically the smallest of the three: one button, one fetch to `/api/brief-ai`, the response already carries the "Wording by Gemini, numbers checked by code" tag to show. Keep `BRIEF_AI_ENABLED` off until a real answer has been read end to end (its own doc flags prompt tuning history worth knowing first — see `docs/brief-ai-endpoint.md`).
4. **Diagnostic Agent, on demand per insight — hold off.** Today a new diagnosis only happens inside a full `pipeline.py` build, and that is deliberate: the one time this was looked at (2026-10-13), the note on record was "there is no Re-run endpoint yet; when one is added it must not trigger uncached Gemini calls from a public URL (cost abuse)." Doing this properly means giving a new public endpoint the same rate-limit/cache/daily-budget shape the other three already have, built from scratch, un-reviewed, the day before submission. `diagnose_one()` already supports refreshing one insight (`--refresh`), so the function exists — it is the endpoint wrapper (auth, limits, abuse-proofing) that doesn't, and that's exactly the part the other three endpoints spent the most iteration on. Recommendation: leave the "Re-run" button as a cache-fallback for the submission, and build this after, re-using the Ask/Fact-check limiter code directly instead of writing a fourth copy of it.

The point of this file is that the prompts, schemas, grounding shape and guardrails for all four are already fully specified above and in the per-endpoint docs, so wiring any one of them up is reading this file and writing the fetch/route, not re-deriving the design.

## Current deploy status (per `docs/deploy.md`, last redeployed 2026-10-15; reconfirmed not redeployed since by the 2026-10-17 security recheck in `log.md`)

Production is Firebase Hosting site `squint` (`squint.web.app`), serving `app/static` as static files, with `/api/**` rewritten to Cloud Run service `squint` in `us-central1` (`firebase.json`). That backend's env vars (`docs/deploy.md`'s redeploy command) set `ASK_GEMINI_ENABLED=1` and `BRIEF_AI_ENABLED=1`; `FACTCHECK_ENABLED` is not set, so Fact-check falls back to its plain code-only check there. None of that matters to a visitor today: a separate throwaway Cloud Run service, `squint-redesign-test`, was stood up specifically to test the current `sq/` frontend with **Gemini features deliberately left off**, and the `sq/` frontend itself (`app/static/sq/runtime.js`) never fetches anything except `results.json`, `titles.json` and its own component HTML. So on the live site right now: Ask and Brief rewrite are enabled on the backend but unreachable (no UI calls them), and Fact-check is both disabled on the backend and unreachable. That gap — backend ready, frontend silent — is what the four items above close. (Flags can be flipped without a code change, `gcloud run services update squint --update-env-vars ...`, so re-check `/api/*/status` directly before relying on this if time has passed.)

## Reproducing or extending any of this

- GCP: project `panopticon-hackathon`, region `us-central1`, model `gemini-2.5-flash` (confirmed working; `gemini-3-flash` and `gemini-2.0-flash` 404 in this project/region). Application Default Credentials, via `genai.Client(vertexai=True, project=..., location=...)`.
- Every live endpoint follows the same shape: build a grounding summary from `results.json` with ids stripped and hidden personas removed → one Gemini call with `temperature` near 0 and a structured `response_schema` → verify every number in the reply against the numbers the summary actually contained → cache the verified reply keyed by a hash of (question or claims, results-file hash, prompt version) → serve the cache on repeat requests → fall back to a refusal or a non-AI answer, never a partially-checked one.
- Shared knobs across the three request-time endpoints: `ASK_RATE_PER_MIN`, `ASK_RATE_PER_DAY` (per visitor), `ASK_GLOBAL_DAILY_CAP` (shared daily ceiling across Ask and Fact-check), `*_TIMEOUT_S`, and a `*_MOCK=1` flag on each that answers from canned output with no network call (used by every test suite).
- Tests, no network needed except where noted (exact check counts drift as the suites grow; run them for the current number): `app/tests/ask_endpoint_test.py` (`--mode off|mock|live`), `app/tests/factcheck_test.py` (one real call made by hand 2026-10-15, result: four lines judged supported, two sensible "missed" notes), `app/tests/brief_ai_test.py` (no network; real Gemini has been run against it though — 2026-10-15's first live pass against prompt `br-v6` verified 9 of 10 answers, the rest fell back to standard wording; read that log entry before changing the prompt again), `pipeline/eval.py` (Diagnostic Agent rule-trust ground truth, seeds 42/7/123/2024/99, currently 47/48 strict on prompt v3).
