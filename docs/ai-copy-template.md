# AI copy template (for the Diagnostic Agent, Gemini)

Status: spec for the diagnostic step. Nothing in `pipeline/diagnose.py` has been changed to use it yet. When the AI text is next regenerated, build the prompt from this file so every finding reads the same way, in everyday business wording, and Gemini only fills named slots.

**Synthetic data:** every example number below is made up for illustration.

## Why a template

Gemini writes free text today, and it drifts into jargon ("technical bug", "rage taps", "behavioral pattern"). A bounded template fixes the structure, the length and the vocabulary. Code still computes every number and checks every quoted number (contract v0.6 validator). Gemini picks wording and the reason only.

## The slots (one finding = one filled template)

| Slot | What goes in | Who fills it | Limit |
|---|---|---|---|
| `headline` | Who, what they do, where, how much worse | Gemini, from the frame below | 14 words |
| `what_we_see` | Two facts with numbers: the rate now against the usual rate, and how many sessions | Gemini, numbers copied from `signals` | 1 sentence, 30 words |
| `likely_reason` | The most likely reason, in plain words, and the evidence in plain words | Gemini, choice limited to the reason list below | 1 sentence, 35 words |
| `how_sure` | High, Medium or Low | Code, from sample size and rule agreement (not Gemini) | one word |
| `business_effect` | "About ₱X a week (assumed value)." | Code (Impact Score), Gemini must not edit it | fixed |
| `next_step` | One action, one owner role | Gemini, imperative, from the step list below | 20 words |
| `caveat` | Only when a tracking gap touches this finding | Code decides if it exists, Gemini may reword it | 1 sentence |

Maps onto the existing `diagnosis` object (contract v0.6): `headline` goes to `title` when `title_source` is `ai`; `what_we_see` + `likely_reason` joined go to `summary`; `next_step` goes to `next_steps[0]`; `caveat` goes to `caveats[0]`; `how_sure` replaces the numeric confidence in the UI wording only.

## Sentence frames

- **headline:** `[User group] [verb] at [screen name] [much more / far more / noticeably more] often than [everyone else / usual].`
  Example: "Individual traders sending money give up at checkout far more often than other users."
- **what_we_see:** `[X]% of their sessions end at [screen], against [Y]% for everyone else ([N] sessions).`
- **likely_reason:** `Most likely [reason phrase], because [evidence phrase].`
- **next_step:** `[Owner role]: [verb] [object] [where or when].`
  Example: "Engineering: check the payment timeout errors for send-money checkouts since Oct 9."

## Allowed reasons (Gemini chooses one; code keeps the internal class)

| Internal class | Say this |
|---|---|
| `technical_bug` | "something is breaking for them" |
| `ux_friction` | "the screen is hard to use" |
| `language_cognitive_overload` | "the wording or the steps are confusing" |
| `natural_exit` | "people are leaving normally, not struggling" |
| `behavior_pattern` | "this is how this group normally behaves" |
| `unclassified_needs_review` | "we cannot tell yet, a person should look" |

If the reason is `natural_exit` or `behavior_pattern`, the next step must say no action is needed or to keep watching. Never suggest pop-ups, forced re-engagement or anything that pushes users.

## Allowed owner roles

Engineering, Product, Design, Support, Data. Pick one.

## Words to avoid, and what to say

| Avoid | Say |
|---|---|
| persona, cohort | user group, group |
| telemetry, tracker fault, schema | tracking, tracking problem, data format |
| rage click, rage tap | repeated taps |
| dead tap | tap that did nothing |
| dwell, dwell time | time on screen |
| friction | trouble, struggle |
| funnel, conversion, drop-off rate | the steps people go through, finishing, people leaving |
| anomaly, outlier, baseline | unusual, usual level |
| hypothesis | likely reason |
| quarantine, held out | set aside |
| mapped, unmapped | linked, not linked |
| exit (as a noun, once is fine) | leaving, dropping out |

The app also runs a plain-language pass on screen text (`PLAIN` in `app/static/app.js`), so a slip does not show, but the saved text should already be clean.

## Hard rules (unchanged, checked by the validator)

1. Every number in the text appears in `signals`, `breakdown` or `evidence`. No new numbers.
2. Every claim cites a ref that exists in the same insight.
3. No cause is claimed when confidence is low: say "we cannot tell yet".
4. Money is only the `business_effect` slot, and it says assumed.
5. No fraud wording for any user group in this demo.

## Prompt skeleton (fill the braces from code, not from the model)

```
You write one short finding for a business reader, not an analyst.
Use these facts only: {signals_json}
Fill exactly these slots as JSON: headline, what_we_see, likely_reason, next_step, caveat.
Follow the sentence frames: {frames}. Choose likely_reason from: {allowed_reasons}.
Choose owner from: {owner_roles}. Never use these words: {avoid_list}.
Copy numbers exactly as given; do not compute new ones. Maximum words per slot: {limits}.
If you cannot tell the reason, say so in likely_reason.
```

Bump `PROMPT_VERSION` when this file changes (the cache key already hashes the prompt text).
