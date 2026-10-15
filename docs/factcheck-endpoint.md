# Fact-check endpoint ("Fact-check with AI")

All data is SYNTHETIC. This is the one place the dashboard calls Gemini live, next to the off-by-default Ask endpoint.

## What it does

In a finding's detail, the button **Fact-check with AI** asks Gemini to check each line of the *saved* explanation against the numbers of the same finding. Each line comes back **Supported**, **Partly**, **Not supported** or **Cannot check**, with the deciding number and one short note, plus up to two things the explanation leaves out. The saved text never changes.

## One click, one call

- The browser sends only `{"id": "<finding id>", "again": false}`. Facts are built on the server from `static/results.json`, never taken from the client. Findings about hidden groups return 404.
- The first answer for a finding is **saved** (`data/ask/fc_*.json`, keyed by finding, results hash and prompt version). Later visitors and repeat clicks get it for free (`cached: true`).
- **Check again** is a new call: 30 s cooldown per visitor and finding, 3 re-checks per finding per visitor per hour (4 live calls in all), then the per-visitor and daily limits of the Ask endpoint (`ASK_RATE_PER_MIN`, `ASK_RATE_PER_DAY`, `ASK_GLOBAL_DAILY_CAP`; the daily counter is shared).
- One in-flight request per click in the browser; the button is disabled while it waits and during the cooldown.

## It always answers

If the AI is off, rate limited, over budget, down, or its answer fails verification, the endpoint returns a **plain code check** instead (`source: "code"`, with a `reason`): it only compares the numbers each line quotes with the numbers in the facts. The UI labels it "Code check, no AI".

## What code verifies in the AI answer

Every claim index present; no links or code fences; any number in a note or in `missed` that is not in the facts is dropped (the note is blanked rather than shown). Numbers are compared after the same rounding rules as the Ask endpoint.

## On and off

| Where | Default | Change with |
|---|---|---|
| Local (`python app/server.py`, no `PORT`) | ON | `FACTCHECK_ENABLED=0` |
| Platform that sets `PORT` (Cloud Run) | OFF | `FACTCHECK_ENABLED=1` |

`FACTCHECK_MOCK=1` answers from canned outputs without network (used by the tests). The **deploy freeze is on**: nothing here is deployed. Before turning it on for the public service, check the limits above and the daily cap.

## Privacy and logs

The model sees only aggregated numbers already in `results.json` plus the saved explanation, never raw events or user ids. Logs carry reason codes and counts only (`outcome=answered|cache|cooldown|rate_limited|budget_exhausted|model_unavailable|unverified|off`).

## Tests

`.venv/Scripts/python app/tests/factcheck_test.py` (15 checks, no network). One real call was made by hand on 2026-10-15 (finding "OTP code: exits jump"): all four lines judged supported, two sensible "missed" notes.
