# Dining sample dataset (`synthetic-dining-v1`)

A second sample dataset next to the wallet one: a food ordering and table booking app. **All of it is synthetic.** It exists to show that Squint is not tied to one product: the same pipeline and the same dashboard run on a different app with a different story.

## What "re-skinned twin" means
- **Same internal ids.** Screens, journeys, personas, products and steps keep the ids of the wallet dataset (`otp`, `txn_checkout`, `sari_sari`, `eload`, ...), so the Guardian, the Watchdog, the Diagnostic Agent and the whole dashboard work unchanged.
- **Own raw events.** The dining app logs different field and event names (`action`, `page`, `component`, `profile.tier`, `view`, `frantic_press`, `MenuBrowse`, ...). `pipeline/mapping_dining.json` translates them, which is exactly the job of the mapping layer. Normalizing 208,355 events gives no schema problems; the only unmapped value is the planted property.
- **Own labels and wording.** `pipeline/profiles/dining.py` holds every label and sentence that differs (screen, journey, group and dish names, cohort names, the prepared Ask questions, the intent examples, assumed value per task). The wallet defaults live in `schema.py` and `build_results.py`; the wallet output is byte-identical to before the profile layer was added.
- **Own story.** Different dates, magnitudes, versions and planted problems (below).

## The app
Journeys: **Sign up and login** (Browse menu, App open, Phone number, OTP code, Name, Dietary preferences, Signed in), **Table booking** (Pick a restaurant, Party size and deposit, Add payment method, Confirm booking, Booking confirmed; the payment method is asked after sign-up, when a deposit is due) and **Order food** (Choose a dish category, Cart, Checkout and payment, Order placed). Amounts are in PHP.

User groups (internal id in brackets): Guests (`unregistered`), Office groups (`large_business`), Students (`sari_sari`), Families (`individual_trader`), Couples or solo (`individual`), Unknown (`unknown`, hidden in the UI) and Promo abusers (`fraudster`, hidden in the UI). Dish categories: Rice meals (`eload`), Noodles and soups (`water_bill`), Burgers and fries (`electricity_bill`), Pizza (`game_voucher`), Coffee and tea (`cable_internet`), Group platters (`send_money`), Desserts (`postpaid_telecom`).

## Planted patterns (ground truth in `data/dining/ground_truth.json`)
| ID | What | Expected call |
|---|---|---|
| P1 | OTP codes not delivered 2026-10-10, 10:00 to 18:00 UTC (the evening rush): about 70% of attempts stall | Technical bug |
| P2 | Office groups put down booking deposits above PHP 50,000; everyone else stays under PHP 5,000 | Behavior pattern, not a problem |
| P3 | Students order Rice meals in about 72% of orders | Behavior pattern, not a problem |
| P4 | Families abandon Group platters at checkout about 55% of the time (gateway timeouts, rage taps) | Technical bug or UX friction |
| M1 | Promo abusers: night bursts, failed attempts, up to 5 users per device | Unclassified, needs review |
| M2 | Guests browse the menu repeatedly before signing up | Natural exit |
| control | A steady drop at Party size and deposit (about 14%, error `reservation_failed`: no table for that party size), every group; Name and Dietary preferences lose the normal 4 to 5% | UX friction (shown as a steady drop-off; the agent reads the errors as a technical bug) |
| G1-G4 | Payment-method tracker silent on app 5.3 from 2026-10-12, 2.4% row loss on 2026-10-08, unmapped property `sms_route_v2`, checkout double-firing on Android 2026-09-24 to 2026-09-28 | Guardian faults |

## Checks (seed 42)
- Guardian: all ground-truth checks pass. Watchdog: all pass, with no extra candidates.
- Diagnostic Agent (Gemini, prompt tuned only on the wallet dataset): **9 of 9** findings match the planted truth, 13 live calls, 0 fallbacks.
- Two more seeds (7 and 123) also pass the Guardian and Watchdog checks.

## Adding another sample
A new sample needs: a profile in `pipeline/profiles/` (and its name in `NAMES` in `profiles/__init__.py`), a generator and mapping, an entry in `PROFILES` in `pipeline/pipeline.py`, the file name in `DATASETS` in `app/ask_gemini.py`, and an entry with its `ui` block in `app/static/datasets.json`. These four places must be kept in step.

## Sample flows and the mismatch check
Onboarding lets a visitor pick a dataset and, separately, a flow. A flow is what a customer tells Squint about their app: journeys, steps, and the raw source event (screen name) each step reads. Squint checks the chosen flow against the events the chosen dataset really logs. A flow written for the other app finds none of its events (measured: each sample flow matches its own data 18 of 18 and the other app's data 0 of 18), so it is flagged and Squint suggests the flow that does match. The check runs in the browser; nothing is uploaded.

`pipeline/make_flows.py` writes `app/static/flows/wallet.json`, `dining.json` and `source_events.json`, derived from each dataset's results file and mapping file (not hand-written).

## Run it
```bash
# the whole chain in one command (generate, normalize, Guardian, Watchdog, Diagnostic Agent, results)
python pipeline/pipeline.py --profile dining --generate --seed 42            # needs Gemini access for the diagnoses
python pipeline/pipeline.py --profile dining --offline                       # no network: cached diagnoses only
python pipeline/pipeline.py --profile dining --publish                       # also copies to app/static/results_dining.json

# or stage by stage (the profile is chosen with SQUINT_PROFILE)
SQUINT_PROFILE=dining python pipeline/generate_dining.py --seed 42 --out data/dining
SQUINT_PROFILE=dining python pipeline/normalize.py --mapping pipeline/mapping_dining.json --input data/dining/events_raw.jsonl --out data/dining/canonical_events.jsonl
```
Generated data stays in `data/dining/` (git-ignored). The dashboard reads `app/static/results_dining.json`; the guarded Ask, Fact-check and Brief endpoints take a `dataset` field (`wallet` or `dining`) and ground on that file only.
