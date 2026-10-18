# Brief rewrite endpoint ("Rewrite with Gemini")

All data is SYNTHETIC. **Built but OFF by default.** Nothing in this feature calls Gemini unless `BRIEF_AI_ENABLED=1` is set, on any machine. Wired into the Recommendations tab (`app/static/sq/c/Recommendations.{html,js}`, renamed from `Brief.{html,js}` on 2026-10-18; logic in `app/static/sq/data-ask.js`'s `A.briefAi`/`A.rewriteBrief`, 2026-10-17): the page checks `/api/brief-ai/status` once and the **Rewrite with Gemini** button only renders at all when that returns `true` and the scope is a single user group with at least one open finding; while it is off, the button is absent, not disabled, and the Brief shows only its standard wording.

## What it does

On the Recommendations tab, **Rewrite with Gemini** asks Gemini to rewrite only the *wording* of the brief for the current timeframe and user group:

- a headline and a second line,
- one sentence per driver (the top two findings),
- up to three "what we would do this week" steps, each with an owner (Engineering, Design, Product, Support or Data).

The three number tiles, the finding titles, the dates and the money figures stay computed by code. A rewritten brief carries the tag "Wording by Gemini, numbers checked by code" (also in print and in the copied text). **Standard wording** puts the code-written text back. Rewriting is hidden when two or more user groups are combined, because the server only holds single-group views.

## One click, one call

- The browser sends `{"range", "platform", "persona", "ids" (1 to 3 finding ids), "again"}`. The server builds the facts itself from `static/results.json` for that view and those findings, never from the client. A hidden group (fraudster, unknown), a finding that is not in that view, or a healthy finding returns 404.
- The first answer is **saved** (`data/ask/br_*.json`, keyed by view, findings, results hash and prompt version `br-v1`). Later visitors and repeat clicks get it for free (`cached: true`).
- **Rewrite again** is a new call: 30 s cooldown per visitor and view, 4 live calls per visitor, view and hour, then the per-visitor and daily limits of the Ask endpoint (`ASK_RATE_PER_MIN`, `ASK_RATE_PER_DAY`, `ASK_GLOBAL_DAILY_CAP`; the daily counter is shared with Ask and Fact-check).

## What code verifies

The whole answer is thrown away (the standard wording stays, with a reason) if any of these fail: wrong shape or lengths; no links, code fences or control characters; exactly one driver line per finding (up to 2); at most one step per finding that has saved next steps (up to 3); owner from the fixed list; **any number in the text that is not in the facts** (small counts 1, 2, 3, 7, 24 and 30 are allowed; roundings of facts are allowed). It never shows a partly checked answer.

## On and off

| Where | Default | Change with |
|---|---|---|
| Anywhere (local, Cloud Run) | OFF | `BRIEF_AI_ENABLED=1` |

`BRIEF_AI_MOCK=1` answers from a canned output without network, but only together with `BRIEF_AI_ENABLED=1` (used by the tests and for previews). `GET /api/brief-ai/status` returns `{"enabled": true|false}`; the page asks it once and enables the button only on `true`; a static host with no server shows the greyed-out button.

To activate later (a deliberate switch): set `BRIEF_AI_ENABLED=1` on the running process, restart, and check `/api/brief-ai/status`. For a public service, review the limits above and the daily cap first.

## Privacy and logs

The model sees only aggregated numbers already in `results.json` plus saved explanations, never raw events or user ids. Logs carry reason codes and counts only (`outcome=answered|cache|cooldown|rate_limited|budget_exhausted|model_unavailable|unverified|off`).

## Tests

`.venv/Scripts/python app/tests/brief_ai_test.py` (no network; check count drifts as the suite grows, run it for the current number). A real Gemini call has been made against this feature: 2026-10-15, prompt `br-v6`, 9 of 10 live answers verified (the tenth fell back to standard wording, as designed) — see that date's `log.md` entry before changing the prompt again. Also verified locally 2026-10-17 end to end through the wired-up Recommendations tab (then still named Brief) in mock mode (rewrite, revert to standard wording, and the combo-scope hide all behave as documented above); not yet exercised against a real (non-mock) Gemini call through this particular UI wiring.
