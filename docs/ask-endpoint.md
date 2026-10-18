# Ask endpoint ("Ask Squint" free-form questions)

All data is SYNTHETIC. This is the free-form sibling of the Chat now tab's built-in question matcher: when a visitor's question does not match a prepared `ask[]` entry, this endpoint can answer it live from the same dataset instead of refusing outright. Wired in since 2026-10-17 — see "Wired into the Chat now tab" below.

## What it does

`POST /api/ask` takes `{"question": "...", "dataset": "wallet"}` and answers using only a compact, id-free summary built from `static/results.json`: findings, their signals and diagnoses, last-7-days KPIs, data-health faults, cohorts and product funnels. Hidden user groups (fraudster, unknown) are stripped from the summary before the model ever sees it, the same as the UI. The model returns `{"answer", "refs", "can_answer"}`; `can_answer: false` or a failed verification becomes a refusal, never a guess.

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

## Wired into the Chat now tab (2026-10-17)

The Chat now tab (`app/static/sq/c/ChatNow.html`, `app/static/sq/data-ask.js`; the component was named `Ask.html` until a 2026-10-18 rename) matches against the prepared `results.json` `ask[]` entries first, same as before; when nothing matches, `data-ask.js` now calls this endpoint while its usual step animation plays, instead of going straight to the fixed refusal. A verified live answer renders through the same `A.model()` path a prepared entry uses (it is stored as a synthetic `ask[]`-shaped entry, keyed `live:<timestamp><random>`, not written back to `results.json`). Any failure — disabled, rate-limited, refused, model error, network error — falls through to exactly the original hardcoded refusal, so with `ASK_GEMINI_ENABLED` unset the visible behavior is unchanged (verified locally). `ChatNow.html` and `ChatNow.js` were not touched; the whole change lives in `data-ask.js`. See `docs/ai-generation-overview.md` for the equivalent status of Fact-check (still not wired, no button exists) and Brief rewrite (wired the same day), and the current deploy topology (Firebase Hosting `squint.web.app` → Cloud Run `squint` via `/api/**`) — this backend flag is already on there, so shipping the wiring live needs only a Hosting deploy of the static files, no Cloud Run redeploy.

## Privacy and logs

The model sees only the aggregated summary above, never raw events or user ids. Logs carry reason codes and counts only (`outcome=answered|cache|cooldown|rate_limited|budget_exhausted|model_unavailable|unverified|prefilter|disabled`); the visitor address is salted and hashed before it is logged.

## Tests

`.venv/Scripts/python app/tests/ask_endpoint_test.py --port 8097 --mode off|mock|live` (see the file header for how to start the server for each mode). `--mode live` makes 3 real Gemini calls and prints the outputs; it asserts nothing about wording, by design.
