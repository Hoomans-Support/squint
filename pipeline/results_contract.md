# results.json contract

The single file the app reads. The pipeline writes it; the UI never touches raw events. Record any change to the shape in this file before changing it.

Status: **v0.1.** `pipeline/build_results.py` writes this shape today (pre-AI). Fields marked `(DA)` are left `null` with `diagnosis_status: "pending"` until the Diagnostic Agent exists; the UI shows "Not diagnosed yet" for them. Differences from the first draft: `journey` became `journeys` (one per `platform|persona` filter), insights carry `facts`, `segment_text`, `screen_label`, `compared_with`, `diagnosis_status`, and evidence holds the original source records per sample session.

```jsonc
{
  "meta": {
    "dataset": "synthetic-v1",          // from the mapping config
    "synthetic": true,                   // UI must show a "Synthetic sample" badge when true
    "generated_at": "2026-10-15T09:00:00Z",
    "window": { "baseline_start": "...", "now_start": "...", "now_end": "..." },
    "counts": { "events": 0, "sessions": 0, "sessions_quarantined": 0 },
    "model": "gemini-2.5-flash",         // (DA)
    "diagnosis_source": "live | cached"  // (DA) cached = replayed from saved outputs
  },

  "guardian": {                          // Tier 0, copied from guardian_report.json
    "status": "pass | fail",
    "checks": [ { "check": "volume_gap", "status": "pass | warn | fail" } ],
    "quarantine_windows": [ { "platform": "app", "start": "...", "end": "...", "screens": ["kyc_identity"], "reason": "telemetry_gap" } ],
    "findings": [ { "kind": "volume_gap", "explanation": "plain English" } ]
  },

  "insights": [                          // sorted by impact.score desc; the feed shows the top 3
    {
      "id": "temporal:kyc_identity:all",  // Watchdog candidate id
      "rank": 1,
      "severity": "critical | warning | healthy",
      "class": "technical_bug | ux_friction | language_cognitive_overload | natural_exit",  // (DA)
      "title": "short headline",                       // (DA)
      "summary": "plain-English finding",              // (DA)
      "hypothesis": "why it is happening",             // (DA)
      "confidence": 0.0,                               // (DA) 0-1
      "recommendation": "what to do, within the no-force guardrail",  // (DA)
      "guardrail_flags": [],                           // (DA) invasive patterns the recommendation avoided or flagged

      "screen": "kyc_identity",
      "segment": { "persona": "smb", "device_class": "android_small" },   // {} means all users
      "scope": "temporal | segment",
      "signals": [ { "metric": "drop_off | dwell | repeat_focus | rage", "value": 0.0, "reference": 0.0, "n": 0, "n_ref": 0, "p_value": 0.0 } ],

      "impact": {                          // Severity x Volume x Value
        "score": 0.0,
        "severity": 0.0,                   // effect size, 0-1
        "volume": 0,                       // excess sessions lost
        "value_per_session": 0.0,          // ASSUMPTION, must be shown in the UI
        "assumption": "text describing where value_per_session comes from"
      },

      "evidence": {
        "affected_session_ids": [],
        "comparison_session_ids": [],
        "raw_events": [ { } ]              // original source records (the `raw` field), shown in the Diagnostic Drawer
      },
      "ticket_draft": null                 // (DA) { "title": "", "body": "" } once Draft Ticket is clicked or pre-generated
    }
  ],

  "journey": {                             // for the Dynamic Journey Flow, about 10 nodes max
    "nodes": [ { "id": "kyc_identity", "sessions": 0, "exit_rate": 0.0, "median_dwell_ms": 0, "friction": "seamless | watch | high", "insight_id": null } ],
    "edges": [ { "from": "signup", "to": "kyc_identity", "sessions": 0 } ]
  },

  "filters": { "platforms": ["web", "app"], "personas": ["enterprise", "smb", "retail"] }
}
```

## Rules
- Healthy insights (for example a stable natural exit) use `severity: "healthy"` and `class: "natural_exit"`. They are shown, but only the top 3 by impact are pushed to the feed.
- `impact.value_per_session` is an assumption. Never present dollar impact without it.
- Anything under quarantine is excluded before analysis. The Guardian block is shown so a reader can see why.
- `evidence.raw_events` are the untouched source records, not canonical events, so the drawer proves the claim from the original data.
- If `meta.synthetic` is true, the UI, the deck and the video must say so.

## What the builder produces (v0.1)
- `insights[]` come from Watchdog `candidates` (problems) and `high_exit_screens` (severity `healthy`). Titles and `facts` are fixed templates over measured numbers, never invented. `severity` is a provisional Watchdog rule (`severity_source`), to be replaced by the Diagnostic Agent.
- `journeys["all|all"]`, `journeys["web|smb"]`, and so on: `{sessions, nodes[{id,label,sessions,exits,exit_rate,median_dwell_ms,col,lane}], edges[{from,to,sessions}]}`. `col` and `lane` come from the unfiltered data so the layout stays put when a filter changes.
- `impact`: `severity` (drop-off increase), `volume_per_week`, `lost_sessions_per_week`, `per_week_dollars`, `value_per_session` and `assumption`. The $20 value is a placeholder constant (`VALUE_PER_SESSION` in `build_results.py`).
- Each generated `views["<range>|<platform>|<persona>"]` carries only the insight IDs applicable to that scope; the UI renders that list rather than falling back to an all-platform view. Problem insights include `platform_ids`, derived from their affected sessions.

Run: `python pipeline/build_results.py --events data/synthetic/canonical_events.jsonl --guardian data/synthetic/guardian_report.json --watchdog data/synthetic/watchdog_candidates.json --out app/static/results.json`

## Added for the investigation workflow (v0.2)
Per problem insight (not for `healthy` ones):
- `timeline`: `{metric, metric_label, series[{d, n, rate, ref_n?, ref_rate?}], gaps[{start,end,platform}], now_start, has_reference, onset}`. `series` is one row per day: the share of sessions that viewed the screen and ended there. `rate` is `null` on days with fewer than 5 sessions. `ref_*` (everyone else) only exists for segment findings. `onset` is the best single-step estimate of when a rise started, or `null`; it is only set when one step explains at least 60% of the daily variation and the rise is at least 10 points. The UI must call it an estimate.
- `breakdown`: `[{dim, dim_label, value, label, n, rate, in_segment, rate_before?}]` for platform, persona and device class, last 14 days, rows with at least 20 sessions. `rate_before` only for temporal findings.
- `concentration`: one plain sentence saying whether the problem is broad or concentrated.
- `evidence.sessions[]` now carries `rows` (`{t, type, screen, element, dwell_ms, error_code, flag}` where `flag` is Rage click, Error, Repeated focus or Unrecognized event), `path` (screens in order) and `platform`/`persona`, next to the untouched `events` (original source records).
- `meta.counts.first_day` and `last_day`.
Run the builder after the Watchdog; it needs the whole event file, not only the last 14 days.

## Added for the Overview tab (v0.3)
- `meta.funnel` and `overview.funnel`: `{start, end, start_label, end_label}`, the first and last screen of the main path (entry lane, earliest and latest column). Conversion means: of sessions that viewed `start`, the share that also viewed `end`. Change the derivation in `funnel_ends()` if the reference data has a different main path.
- `overview.now_days` and `overview.views["<platform>|<persona>"]` (same keys as `journeys`): `sessions` (`now`, `per_day_now`, `per_day_before`, `change`, daily `series[{d,n}]`), `conversion` (`now`, `before`, `n_now`, `n_before`, daily `series[{d,n,rate}]`, `rate` null under 5 sessions) and `table` (persona by device rows with at least 20 started sessions: `label`, `started`, `rate`, `vs_overall`, `finding_id` when a segment finding covers that row), sorted worst first.
- Daily series cover every clean day; sessions inside Guardian quarantine windows are excluded, so the chart dips and the UI hatches the gap.

## Added for the Insights redesign (v0.4)
Each insight gets a `diagnosis` object (`status: pending | done | cached | failed`, `model`, `generated_at`, `source_note`, `class`, `confidence`, `summary`, `claims[{text, refs[{type: signal | breakdown | session, ...}]}]`, `next_steps[{kind: check | fix | monitor, text}]`, `guardrail_flags`, `caveats`). The builder writes it (`pending_diagnosis()` in `build_results.py`) as `pending` until the Diagnostic Agent exists; the UI falls back to the older flat fields if it is missing. Every claim must carry at least one ref to data that exists in the same insight, and no claim may state a number that is not in that insight's signals, breakdown or evidence. Full spec: `docs/insights-redesign.md`, section 8.

## Scene 8 Ask Sankey (v0.7, additive)
`ask[]` retains every existing prepared question and answer. The builder appends three prepared questions, and these are the only entries with `chip: true`:
- `Show the journey of the users who abandoned after payment`: clean sessions in the last seven days that reached transaction checkout/PIN or top-up confirmation and did not reach the matching success screen.
- `Where do people go after the OTP step fails?`: clean sessions in the last seven days whose last viewed screen is OTP.
- `What happens to Retail buyers who leave before success?`: the first cohort restricted to persona `sari_sari` and transaction checkout; display name is Retail.

Each answer is one measured sentence. `viz` is omitted for cohorts under 20 sessions. Otherwise it is `{type:"sankey", title, subtitle, unit:"sessions", source, branches, ticket}`. `source` has `{id,label,value,share_of_active,sub}`; `share_of_active` is cohort sessions divided by clean, eligible sessions started in the same seven-day window, excluding personas `unknown` and `fraudster`, and the subtitle names that denominator and exclusion. `branches` contains only observed branches, with values summing exactly to `source.value`; an unsupported branch is omitted and named in the subtitle. Branch rules are first match: any error, dead tap, rage tap (or OTP resend tap for the OTP question) is Error loop / negative friction; otherwise a return/back is Looped back (a return to prices or product choice is comparing / positive, other returns are negative friction); otherwise Left quietly / natural exit. The schema is unchanged for existing `ask` entries.

`ticket` is `{insight_id|null,title,persona,hypothesis,evidence_json}`. The hypothesis is explicitly labelled and must not be presented as a measured cause. `evidence_json` contains the measured cohort count, seven-day active-session denominator, branch counts and at most three synthetic session IDs per observed branch. All values are computed from the clean synthetic-v2 session data; no Gemini call is made during the build.

## synthetic-v2 and schema `ui-v2` (v0.5, additive)
`pipeline/build_results.py` now builds from `synthetic-v2` and writes everything the UI reads (`docs/ui-results-needs.md` is the UI's list; field names match `app/tests/fixtures/results_v2.json`). Old fields keep their shape. All of it is SYNTHETIC; `meta.synthetic` and `meta.dataset` come from the events, not from constants. Run:
`python pipeline/build_results.py --events data/synthetic/canonical_events.jsonl --raw data/synthetic/events_raw.jsonl --guardian data/synthetic/guardian_report.json --watchdog data/synthetic/watchdog_candidates.json --out data/synthetic/results_v2.json`

New or changed:
- `meta`: `schema: "ui-v2"`, `dataset_label`, `as_of`, `window{start,end}` (dates), `currency: "PHP"`, `platforms: ["app"]`, `counts{events,sessions,users,sessions_in_window,sessions_quarantined}`, `window_detail` (the old timestamp window). `value_assumption` states the per-task PHP placeholders.
- `scope`: `personas[{id,label,users}]`, `products[{id,label}]`, `ranges`, `journeys[{id,name,steps[{id,name,event,conf,status}]}]` for `register_login`, `topup`, `transaction`. `conf` is the share of the step's events with no unmapped value or property; `status` is `review` under 0.9. Register, login and the price list fold into `register_login` (phone and done steps merge the register and login screens).
- `views["<range>|all|<persona>"]` (24 of them): `sessions`, `kpis` (4), `insight_ids`, `journeys` (steps with `sessions`, `exits`, `exit_class`, `tone`, `tag`), `signals` (% of sessions at the step with a rage tap, a back, a dead tap, over 30 s on the screen), `loops` (back moves, from `back` events), `blind`, `exits` (ux, language, technical, natural), `rhythm` (7 buckets, natural vs frustrated exits, markers from the Watchdog and Guardian), `cohorts`, `health` (4 tiles). Ranges end at the last event; `30d` is the whole window.
  - KPI `prev` and `prev_series` are the previous period of equal length; when no earlier data exists (the whole `30d` range) they are the first half of the window and `prev_label` says so. `blind_spots` and `value_at_risk` are whole-period findings, so their series are constant; `mapping_coverage` is per day.
  - Exit classes are rules, not AI: technical (an error, dead tap or rage tap on the last screen), ux (went back), language (over 30 s on the last screen), natural (none of those; every price-list exit).
  - Cohorts are deterministic rules on user behavior (shared-device bursts, stalled at OTP, high-value top-uppers, load-first store owners, price-checkers who register later, straight-through completers, other); `share` adds to 100 (largest remainder); `is_new` when the share rose at least 2 points against the previous period.
- `insights[]` additions: `hint_class`, `hint_rule` (Watchdog rules-based guess; the Diagnostic Agent confirms or overrules), `journey`, `step`, `tone`, `label`, `persona_ids`, `ranges`, `detected_hours_ago` (hours since the first affected session), `is_new`, `replays`, `causes[]`, `affected_sessions`, `window` (burst insights), `impact.per_week_value` (same number as `per_week_dollars`, kept for older readers), `impact.currency`, `impact.volume`. Scopes are now `temporal | burst | segment`. Pattern insights (who tops up large amounts, who prefers a product) and natural or steady-exit insights have severity `healthy` or `warning` and `impact.score` 0. `class` stays `null` until the Diagnostic Agent runs.
- `guardian.faults[]`: `{id, sev, kind, title, desc, impact, hours_ago, quarantine, link, share, cause, why, metric?}` plus `status`, `start`, `end`, `guardian_kind`. `guardian.findings[]` and `quarantine_windows[]` (now with optional `app_version` and `journeys`) are copied from the Guardian.
- `stuck_sessions[]`, `intents[]` (rule-based labels, not AI), `agents[]`, `ask[]` (precomputed question and answer pairs with `refs` and `keywords`; the Ask bar answers only from these).
- `hotspot` (the densest rage-tap screen) and `hotspots[]` (one card per screen with enough rage taps, here the OTP screen and Checkout and PIN): `{screen, journey, step, note, elements, spots}`. `spots` come from `tap_x` and `tap_y` (cells of 0.1; label from the dominant `target` element); `elements` is a schematic wireframe, not data.
- `product_funnels{<product>: {label, sessions, completion, steps[{id,name,sessions,exits,exit_rate}]}}`: the transaction journey per product.
- Evidence: `evidence.sessions[].events[]` are the raw source records with `user_id`, `device_info.device_id` pseudonymised (salted hash), the device model replaced by "Android phone" or "iPhone" and the OS version cut to its major number. Evidence is complete (no 40-event cut) and comes from the raw file (`--raw`).
- Known gaps against `docs/ui-results-needs.md`: no `causes[].type == "release"` rows (nothing in the data supplies one); `class` is `null` for every insight; `evidence.events[]` keys are the source's (`event_name`, not `event_type`); `intents` and the cohort labels are rule-based.

## Diagnostic Agent fields (v0.6, additive; 2026-10-14)
Written by `pipeline/diagnose.py` (called from `build_results.py --diagnose`; one command: `python pipeline/pipeline.py`). All SYNTHETIC. The old flat fields (`class`, `confidence`, `summary`, `hypothesis`, `recommendation`, `guardrail_flags`, `diagnosis_status`) are kept in step with `diagnosis`.
- `class` values: `technical_bug | ux_friction | language_cognitive_overload | natural_exit | behavior_pattern | unclassified_needs_review`. **New:** `behavior_pattern` (an expected, healthy difference between groups, for P2/P3-type findings) and `unclassified_needs_review` (never a guess). The UI needs labels for both (it currently falls back to the raw key).
- `diagnosis`: `status` = `done` (live Gemini, or a rule result), `cached` (saved Gemini output, revalidated), `failed` (no valid model output and no trusted rule: class is `unclassified_needs_review`), `pending` (diagnosis not run). Plus `source` = `gemini | cached | rules | unclassified`, `model`, `generated_at`, `source_note` (cached, rules and failed only), `class`, `confidence` (0-1, null for rules and failed), `summary`, `claims[{text, refs[]}]`, `next_steps[{kind, text}]`, `guardrail_flags`, `caveats`, `reasoning` (list of short steps: the reasoning trace to show), `rules{rule, rule_text, class, trusted, agreement, overrule_reason, flagged}`, `validation{passed, attempts, problems?}`, `cache_key`, `prompt_version`.
  - `rules.agreement`: `agree | overruled | rules_abstained | differs_untrusted_rule | n/a`. `rules.flagged` is true when the model differs from the rule table: show the overrule reason.
  - Refs: `{type: signal, metric, label}`, `{type: breakdown, dim, value, label}`, `{type: session, id, label}`, plus new `{type: stat, id, label}` (evidence statistic over the whole group, no UI target yet: render as plain text) and `{type: fact, id, label}` (a line of `facts`; plain text). Labels are made in code from the data.
  - Source `rules`: only rules that passed the ground-truth test (`RULE_TRUSTED` in `diagnose.py`); `source_note` says it is not an AI diagnosis. Source `unclassified` has `status: failed`.
- Per insight, additive: `evidence_stats{group, reference}` (whole-group counts and shares: exit rate, error, rage tap, dead tap, back, median dwell, shared-device share, night share, top error codes, top rage-tap elements). The Diagnostic Agent quotes only numbers found in the insight (signals, breakdown, evidence_stats, facts).
- `meta`: `model`, `diagnosis_source` (`live | cached | mixed | rules | unclassified | none`), `diagnosis_status` (`done | partial`), `diagnosis_stats{insights, calls, cache_hits, cache_fallbacks, rejected, errors, fallbacks}`, `prompt_version`.
- Views: `journeys[].steps[].low_sample` (true under 20 sessions: shown with tag "Few sessions", tone healthy). `signals[journey][step]` 4th value (stuck) now means no forward progress for 30 s or more (a 30 s gap between events on the screen) or 3+ taps on one target within 2 s. Hotspot spots under 0.05 (normalised) apart are merged. Persona `sari_sari` displays as "Retail" (id unchanged).
- Cache: `data/cache/<insight id>__<hash>.json`, hash of evidence + prompt text + model; a rerun serves it. Eval and accuracy: `python pipeline/eval.py` (writes `data/eval/eval_results.json`).

## Squint data v3: `audiences`, `watch`, `data_sources` (v0.8, additive; 2026-10-16; schema `ui-v3`)
Built by `pipeline/build_audiences.py`, called at the end of `build_results.py`. All SYNTHETIC. Every existing key keeps its value (`meta.schema` is now `ui-v3`; with `--offline` the saved diagnoses are labelled `cached`, nothing else changes). Each block carries `source: "calculated"` (every number is counted from the events) and `text_source: "rule"` (any sentence is a fixed rule, not AI). The two hidden user groups are left out of every number and every sampled session. What the events cannot support is listed in `audiences.gaps[]` and marked `needs_backend` (or `needs_longer_history`); the field is `null`, never a guess. Field-by-field notes: `docs/squint-data-v3.md`.
- `audiences`: `active_users`, `observed_until`.
  - `win_back.top` and `win_back.by_insight[]` (OTP window first, then the other findings with people who stalled on a screen): `{id, insight_id, insight_rank, screen, screen_label, people, sessions, states[{id: never_returned | returned_not_finished | returned_finished, label, people, share}], finished_by_journey, definition, window?}`; `top` adds `title`, `advice`.
  - `cards[]`: `{id, kind: win_back | target | keep | protect, title, size{people, share}, basis, action, source: calculated | ai_idea, insight_id}`. `ai_idea` means the size is counted but the suggested action is a fixed rule written by the builder (no LLM is called).
  - `signals.return_visits{d1, d7, d30}`: `{days, people, rate, status: ready | insufficient_window, by_group[{persona, label, people, rate}]}`, plus `note`, `caveat`, `quality`, `definition`. `d30.rate` is `null` (the sample window is 30 days).
  - `signals.repeat_purchases`: `{status: partial, buyers, buckets[{id: once | two_to_three | four_plus, label, people, share, pct}], bought_again_30d, median_days_to_second_purchase, last_14_days{buyers, buckets}, caveat, quality: "generator_floor"}`. The generator gives every registered person at least 5 purchases, so the 30-day buckets are saturated (100% "4 or more"): a method check, not a finding.
  - `signals.lifetime_value`: `{status: "needs_backend", value: null, reason}`.
  - `segments{total, items[{id, label, people, share, pct}], definition, rules}`: six groups in a fixed order; `people` adds to `total`, `pct` adds to 100.
  - `gaps[{field, status, reason}]`.
- `watch`: `footer` ("Rebuilt from tracked events, inputs masked, no video"), `sample{seed, per_insight, method}`, `idle_after_s`, `outcomes{}`, `insights[{insight_id, insight_rank, screen, screen_label, population{sessions, ended_here, finished}, sessions[15]}]`. Session: `{id, persona, platform, os, device_class, device, product, start_utc, duration_s, outcome: left | came_back_later | finished, role: affected | comparison, user (salted pseudonym as in evidence), summary, steps[{t_seconds, kind: step | tap | rage_tap | error | back | idle | exit, label, element?, error?, seconds?, screen?}], marks[{kind: rage_tap | error | back | idle | exit | done, t_seconds, t_end?}]}`. `done` (a finished session) is an extra mark kind beyond the five asked for. Raw user and device ids never appear.
- `data_sources`: `status_legend`, `signals[{id, name, source: App tracker | Backend database | Help desk, status: ready | available | partial | needs_backend | later, used_for, note}]`, `connected{app_tracker{dataset, label, synthetic, events, sessions, users}, journey_steps{matched, total, to_review}, backend_database{status, signals_locked}}`, `health{event_volume{change, now_events, before_events}, events_matched{share, unmatched_events}, trackers{firing, total, silent[]}, sessions_set_aside}`, `backend_sample{dataset, location, access, tables[{table, rows, description}]}` (no project id; the page never queries BigQuery).
- BigQuery (builder only): the build writes `data/synthetic/bq_derived/{wallet_orders,audience_members,watch_sessions}.ndjson`; `python pipeline/bq_source.py load-derived` loads them into `squint_samples`.

## Combined user-group views (v0.9, additive)
The four selectable named personas (`individual`, `individual_trader`, `large_business`, `sari_sari`) may be selected together. Across their 15 non-empty subsets, the four existing single-persona views are joined by 11 combined-persona views. `build_results.py` writes a complete `views[range|platform|persona+persona...]` record for each subset and each platform (`all`, `app`, `web`). Persona IDs in a combination key are unique and in ascending ID order. The existing view object shape is unchanged; every count, rate, cohort, insight set, and value-at-risk figure is computed from the matching clean sessions, not merged from rounded persona views. All users and Unregistered remain exclusive and keep their existing keys.

The legacy route map also includes `journeys[platform|persona+persona...]`; node and edge counts come from the matching platform and combined sessions.

## Platform and Audiences scopes (ui-v3, additive)
`meta.platforms` lists the platforms present in the sample. The App/Web control uses the same `range|platform|persona` key as `views`; selecting a platform must not fall back to the `all` view. Insight applicability is limited to the platforms represented by affected sessions.

`audiences.scopes["<platform>|<persona>"]` contains a complete Audiences block for each supported platform (`all`, `app`, `web`) and selectable persona key (including the existing combined-persona keys). `audiences` itself remains the default all-platform/all-user block for older readers. Audience metrics retain their existing 30-day sample and fixed lookback definitions; they are scoped to the selected platform and persona, not the dashboard trend-range control. A scope with no matching stalled audience returns a zero-count “No stalled audience in this scope” top block rather than borrowing another scope's result. All generated blocks remain synthetic and use the same labels and caveats as the default block.
