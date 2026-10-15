# SmartSari dataset spec (synthetic-v2)

**All data described here is SYNTHETIC.** Label it as such in the UI, the deck and the video.

Supersedes `synthetic-v1` (enterprise / SMB / retail onboarding); keep the v1 files as a rollback until v2 lands and passes its checks. The design mock's numbers are illustrative: the UI must show numbers measured from the generated events.

## Source of truth: the generation prompt (2026-10-14)

> right now I need sample databases to test the AI Agents, based on the possible scenarios:
>
> control: there are certain pages where most user drop off
> test register/login: only certain time range (by timestamp) register/login is problematic (because OTP is not sent/received)
> test topup: only certain user persona top up a certain amount (so certain persona tends to top up > XX peso, etc)
> test transaction: only certain user persona buys a certain product
> test transaction successful: only certain user persona dropoff before transaction is successful
> miscellaneous: weird behavior (you can determine this yourself)
>
> requirements:
> - each row is a JSON per event tracked
> - there are 1000 users in the pool (200 unregistered, 800 registered; from the 800 registered, 20% is large businesses, 50% is sari-sari store, 10% is individual traders, 10% is individuals, 5% is unknown, 5% is fraudsters)
> - 50% android, 50% IOS
> - simulate the different OS and device ID
> - Each device ID can have max 5 user ID logged in
> - simulate login, wallet top up, transaction in different timestamps for each individuals
> - products available to be transacted: e-load, water bills (pay bills for water), electricity bills, game voucher, cable TV & internet (subscriptions), Send Money (remittance), Telecoms (post-paid phone bills)
> - for each scenario, create at least 5 attempts of completed task for each user of all segments

## What that implies

Population (1,000 users):

| Persona | Users |
|---|---|
| unregistered | 200 |
| large business | 160 (20% of 800) |
| sari-sari store | 400 (50%) |
| individual trader | 80 (10%) |
| individual | 80 (10%) |
| unknown | 40 (5%) |
| fraudster | 40 (5%) |

Devices: 50% Android, 50% iOS, varied OS versions and models, each device has an id, and a device id has at most 5 user ids logged in. Fraudsters and unknowns are natural candidates for the shared-device cases.

Journeys the dashboard reads, mapped to the prompt's scenarios:

| Prompt scenario | Dashboard journey | Planted pattern (to fix in the data, see open items) |
|---|---|---|
| control | all | A few screens where most users drop off, steady over the whole window |
| register/login | Onboarding (register, login, OTP) | One timestamp range where OTP is not sent or received: attempts stall, retries, rage taps on resend, exits |
| topup | Wallet cash-in | One persona tops up above a threshold amount |
| transaction | Buy (7 products: e-load, water bills, electricity bills, game voucher, cable TV and internet, send money, post-paid telecom) | One persona buys one product |
| transaction successful | Buy, last step | One persona drops off before the transaction succeeds |
| miscellaneous | any | Weird behavior, our choice. Suggested: fraudster bursts (many failed attempts, many users on one device), plus a natural exit that must not be flagged |

Volume: at least 5 completed attempts per user, per scenario, in all segments, with login, top up and transactions spread over different timestamps per user.

## Gaps the prompt leaves open (fill before generating, or the pipeline cannot use the output)

1. **Time window.** Not stated. Use 2026-09-15 to 2026-10-14 (30 days) so 24H, 7D and 30D in the prototype all have data. The OTP-problem range needs real dates inside it, and a second, clean period before it as the baseline.
2. **Event schema.** "A JSON per event" has no field list. It needs at least what `pipeline/schema.py` has: event id, session id, user id, timestamp, platform, event type, screen, element, persona, os, os version, device model, device id, dwell, error code. The Watchdog also needs `device_class`. Add `app_version`.
3. **Web.** The prompt is app only (Android and iOS). The prototype has a Web / App / Cross-platform toggle. Either add a small web share or drop the web option from the UI.
4. **Planted values.** "XX peso" in the top-up scenario is open. Pick the amount, the persona, the product and the drop-off persona, and write them into a `ground_truth.json` before generating, so the Watchdog and Diagnostic Agent can be scored.
5. **Telemetry faults for the Guardian.** The prompt has none. The OTP time range is a product fault, not missing data; if we also want the Guardian demo (silent tracker, missing partition, unmapped property, duplicates), add them as separate, labelled faults on top. The prototype's list is the template: tracker silent on one app version, a missing 3% partition on one day, an unmapped property, a webhook 5xx, a resolved duplicate-event bug.
6. **Personas in the UI.** The prototype's personas (Unregistered, New sellers, Verified sellers) become the prompt's seven. The persona toggle needs to show them, or group them.

## Schema impact (a contract change: record the decision before editing)

- `persona` enum: `unregistered | large_business | sari_sari | individual_trader | individual | unknown | fraudster`.
- New fields: `device_id`, `app_version`. `event_type` may need `back` and `dead_tap` for the prototype's loop arcs and dead-tap heatmap column.
- `PLATFORMS` stays `web | app` unless gap 3 is closed as app only (then the Watchdog's platform dimension has one value; harmless).
- Watchdog `DIMS`: add `os` or `device_class` as already present; persona values change throughout `watchdog.py` and its ground-truth checks (`smb`, `android_small` are hard-coded).

## Ground-truth checks (same pattern as v1, five seeds 42, 7, 123, 2024, 99)

`must_flag` for the planted patterns above, `must_not_flag_as_problem` for the natural exit, `guardian_must_catch` for any telemetry faults added, no extra candidates. Each flagged item names its segment and its expected class.

## Gating for the demo

Visitors cannot upload a flow or connect a database. The dashboard opens already applied to this sample dataset. Settings is a read-only view of the mapped journeys and events: no file chooser, no "Test & connect", no Replace / Disconnect / Reset to demo, and no live-looking claims ("Live · events_raw", "Updated 2 min ago", "52 tables", "2.4M events / day"). Use a label such as "Sample dataset (synthetic)".

## Decided defaults (2026-10-14, defaults chosen for the open gaps; any of them can change)

All values are planted by the generator and written into `ground_truth.json`. All SYNTHETIC.

- **Window:** 2026-09-15 00:00 to 2026-10-15 00:00 UTC (30 days). Product name in the UI: Squint (will change; keep it in one constant).
- **Platform:** app only, Android 50% / iOS 50%. The UI hides the platform toggle when the data has one platform.
- **Persona ids (exact strings):** `unregistered`, `large_business`, `sari_sari`, `individual_trader`, `individual`, `unknown`, `fraudster`. Display labels: Unregistered, Large business, Retail (id stays `sari_sari`), Individual trader, Individual, Unknown, Fraudster.
- **Product ids:** `eload`, `water_bill`, `electricity_bill`, `game_voucher`, `cable_internet`, `send_money`, `postpaid_telecom`.
- **Extra event fields:** `device_id`, `app_version` (4.11.2 until 2026-10-06, then 4.12 for 60% of devices), `device_class` (`android_low`, `android_mid`, `ios`), `product`, `amount_php`, `step` (journey step id).
- **Control:** the Personal data and TIN screens lose about 18% and 8% of sessions all through the window, every persona.
- **Register/login OTP (planted P1):** 2026-10-09 02:00 to 10:00 UTC, OTP not delivered. In that window about 70% of register/login attempts stall on the OTP screen, with resend rage taps and exits; outside it OTP exit is about 5%.
- **Top up (P2):** `large_business` tops up above PHP 50,000 in most top-ups; every other persona stays under PHP 5,000.
- **Transaction product (P3):** `sari_sari` buys `eload` in about 70% of its transactions (expected behavior, positive); other personas spread across products. Must not be flagged as a problem.
- **Transaction success (P4):** `individual_trader` abandons `send_money` before success about 55% of the time at the PIN/confirm step (others about 5%). Class: technical bug or UX, expected to be flagged for that persona + product.
- **Misc (M1):** fraudsters: bursts of failed attempts, many users per device (up to 5), odd hours. Expected: flagged as a segment, class "unclassified / needs review" unless evidence supports more. **M2:** unregistered users open prices repeatedly before registering (natural exit, must NOT be flagged).
- **Guardian faults (labelled):** G1 `kyc_selfie` tracker silent on app 4.12 from 2026-10-13 18:00 (-94%); G2 2026-10-11 loses 3.2% of rows; G3 property `otp_channel_v2` unmapped (about 1,240 events/hr scaled to this volume); G4 `checkout` events double-fired on Android, 2026-09-22 to 09-26, fixed in 4.11.2 (shown as resolved).
- **Attempts:** each user has at least 5 completed attempts per scenario that applies to their persona (unregistered users: register/login only), at different timestamps.
- **Raw format:** the generator writes source-shaped raw events (not canonical) so `normalize.py` stays a real step; canonical output follows `schema.py` plus the extra fields above.

## What was built (2026-10-14): deviations from the decided defaults
Generator `pipeline/generate_v2.py`, mapping `pipeline/mapping_synthetic_v2.json`, checks in `guardian.py` and `watchdog.py`. All SYNTHETIC.
- **Same as the defaults:** window 2026-09-15 to 2026-10-15 UTC, app only, personas and product ids, 1,000 users in the 200 / 160 / 400 / 80 / 80 / 40 / 40 split, 500 Android and 500 iOS users, at most 5 users per device (fraudsters 5 per device), control (about 17% at personal_data, 7% at tin), P1 (stall about 67-70% in the window, 5-6% outside), P2, P3, P4 (about 48-57% against 8%), M1, M2, G1 to G4, extra fields.
- **Deviations:** (1) `app_version`: Android runs 4.11.1 until 2026-09-27 and 4.11.2 after, iOS 4.11.2 throughout, 60% of devices move to 4.12 on 2026-10-06; this makes G4 ("fixed in 4.11.2") consistent. (2) Registered users also have one register-flow session anywhere in the window (a re-verification on a new device) so the control drop-offs apply to every persona; unregistered users complete at least 5 register attempts and 3 to 5 price-check sessions before the first one. (3) Individual traders have 10 to 14 completed transactions (others 5 or 6) so the P4 segment has enough sessions. (4) G1 is detected from the first silent session, not from the planted 18:00 start, because there is no traffic overnight; the planted drop is 94%, the measured drop is in `ground_truth.json`. (5) G3 is planted on OTP-screen events of 4.12 devices (about 3 to 4 events per hour), the same share of events as the prototype's 1,240 per hour at its scale. (6) P2 and P3 are patterns (the Watchdog lists them under `patterns`), never problems. (7) Added event types `back` and `dead_tap`, `tap_x` and `tap_y` on taps (planted tight clusters on the OTP resend button for P1 and the Pay button for P4), unified `otp` screen for register and login, no top-up method screen.
- **Size:** raw 78 MB, canonical 75 MB (no `raw` copy inside), about 187,000 events, 18,700 sessions; 147 MB with the reports and results.
