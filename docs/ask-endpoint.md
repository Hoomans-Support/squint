# Ask endpoint ("Ask Squint" free-form questions)

All data is SYNTHETIC. This is the free-form sibling of the Ask tab's built-in question matcher: when a visitor's question does not match a prepared `ask[]` entry, this endpoint can answer it live from the same dataset instead of refusing outright. **Built, OFF by default**, and not yet wired into the current Squint UI (`app/static/sq/`) — see "Not yet wired" below.

## What it does

`POST /api/ask` takes `{"question": "...", "dataset": "wallet" | "dining"}` and answers using only a compact, id-free summary built from `static/results.json` (or `results_dining.json`): findings, their signals and diagnoses, last-7-days KPIs, data-health faults, cohorts and product funnels. Hidden user groups (fraudster, unknown) are stripped from the summary before the model ever sees it, the same as the UI. The model returns `{"answer", "refs", "can_answer"}`; `can_answer: false` or a failed verification becomes a refusal, never a guess.

## One click, one call

- The browser sends only `{"question", "dataset"}` (max 200 characters). Facts come from the server's own `results.json`, never from the client.
- The first answer for a given (question, dataset, results hash) is **saved** (`data/ask/c_*.json`). Repeat questions and other visitors get it for free (`source: "cache"`).
- Limits, in order: one in-flight request per visitor; a prompt-injection prefilter (`ignore previous instructions`, `reveal your prompt`, `act as...`) refused before any call; per-visitor `ASK_RATE_PER_MIN` (default 5) and `ASK_RATE_PER_DAY` (default 30); an all-visitors `ASK_GLOBAL_PER_MIN` (default 10, catches X-Forwarded-For spoofing on a direct Cloud Run URL); a shared daily budget `ASK_GLOBAL_DAILY_CAP` (default 150, shared with Fact-check and Brief rewrite).

## What code verifies

The whole answer is thrown away (a refusal is returned instead, and cached as a refusal) unless: it is a non-empty string under 600 characters; it has no links, code fences or HTML; **every number in the answer appears in the summary** (exact match, or a rounding to 0/1/2 decimals, or ×100 for a fraction written as a percent); every `ref` is a real finding or data-health id from this dataset. `can_answer: false` from the model is itself a kind of refusal (not an error).

## On and off

| Where | Default | Change with |
|---|---|---|
| Anywhere (local, Cloud Run) | OFF | `ASK_GEMINI_ENABLED=1` |

The deployed `squint` Cloud Run backend behind `squint.web.app` has had `ASK_GEMINI_ENABLED=1` set since the 2026-10-15 redeploy (`docs/deploy.md`) and has not been redeployed since (reconfirmed 2026-10-17). That flag is moot for a visitor today regardless — see "Not yet wired" below.

`ASK_GEMINI_MOCK=1` answers from canned outputs without network (used by tests; `mock-hallucinate`, `mock-url`, `mock-code`, `mock-long`, `mock-cannot` in the question text each exercise one validator branch). `GET /api/ask/status` returns `{"enabled": true|false}`.

## Not yet wired

The current Ask tab (`app/static/sq/c/Ask.html`, `app/static/sq/data-ask.js`) only matches against the prepared `results.json` `ask[]` entries and shows a fixed refusal ("I can't answer that from this data") when nothing matches — it never calls `/api/ask`, regardless of whether `ASK_GEMINI_ENABLED` happens to be set on the Cloud Run service behind it. This endpoint and its guardrails exist and pass their tests, but the frontend fetch that would call it on an unmatched question has not been written. See `docs/ai-generation-overview.md` for where this and the other two live endpoints (Fact-check, Brief rewrite) stand relative to the current UI, what wiring each one up would take, and the current deploy topology (Firebase Hosting `squint.web.app` → Cloud Run `squint` via `/api/**`).

**Coordination (2026-10-17):** `app/static/sq/c/Ask.html` and `app/static/sq/data-ask.js` are both listed as actively claimed by other sessions on `agent-coordination.md` as of this writing. Claim them there (or confirm a release) before wiring this in, same as any other edit to those files.

## Privacy and logs

The model sees only the aggregated summary above, never raw events or user ids. Logs carry reason codes and counts only (`outcome=answered|cache|cooldown|rate_limited|budget_exhausted|model_unavailable|unverified|prefilter|disabled`); the visitor address is salted and hashed before it is logged.

## Tests

`.venv/Scripts/python app/tests/ask_endpoint_test.py --port 8097 --mode off|mock|live` (see the file header for how to start the server for each mode). `--mode live` makes 3 real Gemini calls and prints the outputs; it asserts nothing about wording, by design.
