#!/usr/bin/env python3
"""Squint data v3: the `audiences`, `watch` and `data_sources` blocks of results.json (schema ui-v3). ALL DATA HERE IS SYNTHETIC.

Called once from build_results.py after the insights exist (nothing here changes an existing key). Every number is counted from the
canonical events (users, sessions, timestamps, products, amounts). The few sentences written here are fixed rules, not AI: each block
says so (`source: "calculated"`, `text_source: "rule"`). What the events cannot support is not invented: it is listed in `gaps` and
marked `needs_backend` (see docs/squint-data-v3.md).

Also writes three NDJSON files next to the results (<out dir>/bq_derived/) for BigQuery (pipeline/bq_source.py load-derived):
  wallet_orders      one row per completed transaction or top-up (derived 1:1 from the events, nothing invented)
  audience_members   one row per person per audience or behaviour segment
  watch_sessions     the sampled Watch sessions, timeline as JSON
Hidden user groups (the two the dashboard never shows) are left out of every number and every sampled session, the same as the page.
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
from statistics import median

WATCH_SEED = 42                # fixed: the same sessions every build
WATCH_N, WATCH_AFFECTED = 15, 11
HIGH_TOPUP_PHP = 50_000        # the generator's "large top-up" line (P2); the Watchdog pattern reports 86% above it
LAPSE_DAYS = 7
LOYAL_SEND_MONEY = 2           # completed Send money purchases that make a loyal buyer (4 or more would be everyone: see gaps)
SHARED_DEVICE_USERS = 3        # a device used by this many people or more
LOAD_FIRST_SHARE = 0.8         # E-load share of a store owner's completed purchases
STRAIGHT_THROUGH = 0.9         # share of a person's journeys that finished
IDLE_S = 15                    # no activity for this long is shown as idle
MIN_GROUP_N = 20               # smaller groups get no rate
FOOTER = "Rebuilt from tracked events, inputs masked, no video"
SAMPLE_TABLES = {
    "wallet_orders": "One row per completed transaction or top-up, derived 1:1 from the app events (completed screens and their amounts). No refunds, no off-app payments: those need a real backend.",
    "audience_members": "Which person is in which audience or behaviour segment (state = where they are in the win-back funnel, or member).",
    "watch_sessions": "The sampled sessions shown on the Watch sessions page, with the rebuilt timeline as JSON.",
}
TAP_NAMES = {"pay": "Pay", "resend": "Resend code", "verify": "Verify", "continue": "Continue", "submit": "Submit", "confirm": "Confirm",
             "content": "the screen", "topup_btn": "Top up", "login": "Log in", "get_started": "Get started",
             "product_card": "a price card", "product": "a product"}
FIELD_NAMES = {"otp_input": "code", "phone": "phone number", "amount": "amount", "pin": "PIN", "account_no": "account number",
               "full_name": "name", "birthdate": "birthdate", "tin_input": "TIN"}


def share(n, d, nd=4):
    return round(n / d, nd) if d else None


def split_pct(counts: dict) -> dict:
    """Whole percentages that add up to exactly 100 (largest remainder)."""
    total = sum(counts.values())
    if not total:
        return {k: 0 for k in counts}
    raw = {k: v * 100 / total for k, v in counts.items()}
    out = {k: int(x) for k, x in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - out[k], reverse=True)[:100 - sum(out.values())]:
        out[k] += 1
    return out


class Ctx:
    """Everything the blocks read, gathered once."""

    def __init__(self, a: dict):
        self.__dict__.update(a)
        self.hidden = a["hidden"]
        vis = [s for s in self.clean if s["persona"] not in self.hidden]
        self.by_user = defaultdict(list)
        for s in vis:
            self.by_user[s["user"]].append(s)
        for ss in self.by_user.values():
            ss.sort(key=lambda s: s["dt"])
        self.persona_of = {u: ss[0]["persona"] for u, ss in self.by_user.items()}
        self.obs_end = max(self.parse_ts(s["end"]) for s in self.all_s)
        users_on = defaultdict(set)
        for s in self.all_s:
            users_on[s["device"]].add(s["user"])
        self.shared_users = {u for u, ss in self.by_user.items() if any(len(users_on[s["device"]]) >= SHARED_DEVICE_USERS for s in ss)}
        self.end_ts = {s["sid"]: self.parse_ts(s["end"]) for s in self.all_s}

    def finished_later(self, s: dict) -> bool:
        """The person finished the same journey (same product for a purchase) in a later session."""
        return any(x["dt"] > self.end_ts[s["sid"]] and x["completed"] and x["journey"] == s["journey"]
                   and (s["journey"] != "transaction" or x["product"] == s["product"]) for x in self.by_user[s["user"]])

    def returned(self, s: dict) -> bool:
        return any(x["dt"] > self.end_ts[s["sid"]] for x in self.by_user[s["user"]])


# ----------------------------------------------------------------------------- audiences
def win_back(cx: Ctx, ins: dict) -> tuple:
    """People whose latest session ended at the insight's screen: never came back, came back without finishing, came back and finished."""
    member = cx.members[ins["id"]][0]
    stall = {}
    for u, ss in cx.by_user.items():
        hit = [s for s in ss if member(s) and s["last"] == ins["screen"]]
        if hit:
            stall[u] = hit[-1]
    states = {"never_returned": [], "returned_not_finished": [], "returned_finished": []}
    for u, s in stall.items():
        states["returned_finished" if cx.finished_later(s) else "returned_not_finished" if cx.returned(s) else "never_returned"].append(u)
    n = len(stall)
    fin_j = Counter(stall[u]["journey"] for u in states["returned_finished"])
    labels = {"never_returned": "Never returned", "returned_not_finished": "Returned, didn't finish", "returned_finished": "Returned and finished"}
    if ins["screen"] == "otp":
        labels["returned_finished"] = "Returned and signed up or logged in"
    row = {"id": f"win_back:{ins['id']}", "insight_id": ins["id"], "insight_rank": ins["rank"], "screen": ins["screen"],
           "screen_label": ins["screen_label"], "people": n, "sessions": sum(1 for ss in cx.by_user.values() for s in ss if member(s) and s["last"] == ins["screen"]),
           "states": [{"id": k, "label": labels[k], "people": len(v), "share": share(len(v), n)} for k, v in states.items()],
           "finished_by_journey": {k: v for k, v in sorted(fin_j.items())},
           "definition": "People whose latest session in this finding ended on this screen. 'Returned' = any later session; 'finished' = a later session that completed the same journey "
                         "(same product for a purchase). Counted up to the end of the sample window.",
           "source": "calculated"}
    if ins.get("scope") == "burst":
        row["window"] = ins.get("window")
    return row, states


def audience_blocks(cx: Ctx, pin_otp: bool = True) -> tuple:
    members_rows = []      # BigQuery audience_members
    active = list(cx.by_user)
    n_active = len(active)
    gaps = []

    def add(aud, users, state="member", kind=None):
        for u in users:
            members_rows.append({"user_id": u, "audience_id": aud, "audience_kind": kind, "state": state, "synthetic": True})

    # ---- (a) win-back audiences, one per finding that has people who stalled on a screen
    wb = []
    for ins in cx.insights:
        if ins["severity"] == "healthy" or ins.get("persona_ids") and all(p in cx.hidden for p in ins["persona_ids"]):
            continue
        row, st = win_back(cx, ins)
        wb.append(row)
        for k, v in st.items():
            add(row["id"], v, k, "win_back")
    # the planted OTP outage is the flagship story for the unscoped view; a single named persona (or combo)
    # gets its own top-ranked win-back pick instead, so the four persona views aren't all forced to OTP.
    wb.sort(key=lambda r: ((r["screen"] != "otp") if pin_otp else False, r["insight_rank"]))
    if wb:
        top = dict(wb[0])
        top["title"] = f"Win back {'sign-in and sign-up' if top['screen'] == 'otp' else 'the finish'} for {top['people']} people who stalled at {top['screen_label']}"
        top["advice"] = (f"They stopped at {top['screen_label']}. Send once the fix ships, so they don't hit it again." if top["screen"] == "otp"
                         else f"They stopped at {top['screen_label']}. Fix the step first, then invite them back.")
    else:
        top = {"id": "win_back:none", "insight_id": None, "insight_rank": 0, "screen": "", "screen_label": "a tracked step",
               "people": 0, "sessions": 0, "states": [{"id": k, "label": label, "people": 0, "share": None} for k, label in
                                                         (("never_returned", "Never returned"), ("returned_not_finished", "Returned, didn't finish"),
                                                          ("returned_finished", "Returned and finished"))],
               "title": "No stalled audience in this scope", "advice": "Choose another platform or user group to see a matching audience.",
               "finished_by_journey": {}, "definition": "No matching people in this scope.", "source": "calculated"}
    top["text_source"] = "rule"

    # ---- behaviour facts per person
    buys, topups, send_money = {}, {}, {}
    for u, ss in cx.by_user.items():
        done = [s for s in ss if s["completed"]]
        buys[u] = [s for s in done if s["journey"] == "transaction"]
        topups[u] = [s for s in done if s["journey"] == "topup"]
        send_money[u] = [s for s in buys[u] if s["product"] == "send_money"]
    top_users = {m["user_id"] for m in members_rows if m["audience_id"] == top["id"]}
    big = {u for u, t in topups.items() if any((s["amount"] or 0) >= HIGH_TOPUP_PHP for s in t)}
    shared = set(cx.shared_users)
    buyers = [u for u in active if buys[u]]
    lapsing = [u for u in buyers if max(s["dt"] for s in buys[u]) < cx.obs_end - timedelta(days=LAPSE_DAYS)]
    loyal_sm = [u for u in active if len(send_money[u]) >= LOYAL_SEND_MONEY]
    one_time = [u for u in buyers if len(buys[u]) == 1]
    otp_ins = next((r for r in wb if r["screen"] == "otp"), top)
    sm_ins = next((r for r in wb if r["screen"] == "txn_checkout"), None)

    def size(users):
        return {"people": len(users), "share": share(len(users), n_active)}

    cards = [
        {"id": "win_back_stalled", "kind": "win_back", "title": top["title"], "size": {"people": top["people"], "share": share(top["people"], n_active)},
         "basis": f"Stalled at {top['screen_label']}; {top['states'][0]['people']} never came back, {top['states'][1]['people']} came back without finishing",
         "action": top["advice"], "source": "calculated", "insight_id": top["insight_id"]},
        {"id": "win_back_lapsing_buyers", "kind": "win_back", "title": f"Win back buyers who have not bought in {LAPSE_DAYS} days", "size": size(lapsing),
         "basis": f"Bought at least once, none in the last {LAPSE_DAYS} days of the sample ({round(100 * len(lapsing) / max(1, len(buyers)))}% of buyers)",
         "action": "A reminder with their last product, sent once. Skip anyone still stalled at a broken step.", "source": "calculated", "insight_id": None},
        {"id": "target_big_topups", "kind": "target", "title": "Top-up promos for large businesses", "size": size(big),
         "basis": f"Completed a top-up of PHP {HIGH_TOPUP_PHP:,} or more; large businesses top up far more than everyone else",
         "action": "Idea (rule-based, not AI): a bonus on large top-ups. Check the margin before offering it.", "source": "ai_idea", "insight_id": next((i["id"] for i in cx.insights if i["id"].startswith("pattern:topup_amount")), None)},
        {"id": "keep_send_money", "kind": "keep", "title": "Keep Send money reliable for loyal buyers", "size": size(loyal_sm),
         "basis": f"Completed Send money {LOYAL_SEND_MONEY} or more times",
         "action": "Fix checkout failures before promoting Send money to them.", "source": "calculated", "insight_id": sm_ins["insight_id"] if sm_ins else None},
        {"id": "protect_shared_devices", "kind": "protect", "title": "Protect accounts on shared devices", "size": size(shared),
         "basis": f"Use a device that {SHARED_DEVICE_USERS} or more people log in on",
         "action": "Idea (rule-based, not AI): ask for the PIN again on these devices before large payments.", "source": "ai_idea", "insight_id": None},
    ]
    for aud, users, kind in (("win_back_lapsing_buyers", lapsing, "win_back"), ("target_big_topups", big, "target"), ("keep_send_money", loyal_sm, "keep"),
                             ("protect_shared_devices", shared, "protect")):
        add(aud, users, "member", kind)
    if not one_time:
        gaps.append({"field": "cards.win_back_lapsing_buyers", "status": "rule_changed",
                     "reason": f"One-time buyers cannot be counted: every registered person in this sample has {min((len(buys[u]) for u in buyers), default=0)} or more completed purchases "
                               "(the generator guarantees at least 5). The card counts buyers who stopped buying instead."})

    # ---- (c) people signals
    def returns(days):
        """Share of people who left a journey (first unfinished session, price checks excluded) and opened the app again within `days`."""
        rows = defaultdict(lambda: [0, 0])
        for u, ss in cx.by_user.items():
            leave = next((s for s in ss if not s["completed"] and s["journey"] != "browse"), None)
            if leave is None or cx.end_ts[leave["sid"]] + timedelta(days=days) > cx.obs_end:
                continue
            back = any(cx.end_ts[leave["sid"]] < x["dt"] <= cx.end_ts[leave["sid"]] + timedelta(days=days) for x in ss)
            for key in ("all", cx.persona_of[u]):
                rows[key][0] += 1
                rows[key][1] += back
        return rows

    order = ["unregistered", "large_business", "sari_sari", "individual_trader", "individual"]
    ret = {}
    for d in (1, 7, 30):
        r = returns(d)
        n_all, b_all = r["all"]
        ret[f"d{d}"] = {"days": d, "people": n_all, "rate": share(b_all, n_all, 3) if n_all >= MIN_GROUP_N else None,
                        "status": "ready" if n_all >= MIN_GROUP_N else "insufficient_window",
                        "by_group": [{"persona": p, "label": cx.persona_labels[p], "people": r[p][0], "rate": share(r[p][1], r[p][0], 3) if r[p][0] >= MIN_GROUP_N else None}
                                     for p in order]}
    if ret["d30"]["status"] != "ready":
        gaps.append({"field": "signals.return_visits.d30", "status": "needs_longer_history",
                     "reason": "The sample window is 30 days, so almost nobody has been watched for 30 days after leaving. Shown as null instead of a guess."})
    low = min((g for g in ret["d7"]["by_group"] if g["rate"] is not None), key=lambda g: g["rate"], default=None)
    ret["note"] = (f"{low['label']} come back least within 7 days ({round(low['rate'] * 100)}%)." if low else None)
    ret["note_source"] = "rule"
    ret["caveat"] = ("Synthetic sample: the generator gives every person many sessions across the 30 days, so 7-day returns are close to 100% for everyone. "
                     "The 1-day rate varies more; real return rates need real history.")
    ret["quality"] = "generator_floor"
    ret["definition"] = ("People whose first unfinished journey (price checks excluded) is at least N days before the end of the sample, "
                         "who opened the app again within N days. Counted per person.")

    def buckets(counts: dict):
        b = {"once": sum(1 for v in counts.values() if v == 1), "two_to_three": sum(1 for v in counts.values() if 2 <= v <= 3),
             "four_plus": sum(1 for v in counts.values() if v >= 4)}
        nb = sum(b.values())
        pc = split_pct(b)
        return {"buyers": nb, "buckets": [{"id": k, "label": {"once": "Once", "two_to_three": "2-3 times", "four_plus": "4 or more"}[k], "people": v,
                                           "share": share(v, nb), "pct": pc[k]} for k, v in b.items()]}

    cnt30 = {u: len(buys[u]) for u in active if buys[u]}
    win14 = cx.obs_end - timedelta(days=14)
    cnt14 = {u: sum(1 for s in buys[u] if s["dt"] >= win14) for u in active}
    cnt14 = {u: v for u, v in cnt14.items() if v}
    second = []
    for u in active:
        t = sorted(s["dt"] for s in buys[u])
        if len(t) >= 2:
            second.append((t[1] - t[0]).total_seconds() / 86400)
    rep = {"status": "partial", **buckets(cnt30),
           "bought_again_30d": share(sum(1 for v in cnt30.values() if v >= 2), len(cnt30)),
           "median_days_to_second_purchase": round(median(second), 1) if second else None,
           "last_14_days": buckets(cnt14),
           "definition": "A purchase is a completed Transaction. Buckets count purchases per person over the 30-day sample (last_14_days: the final 14 days).",
           "caveat": "Misses refunds and payments made off the app (needs a backend orders table). In this synthetic sample the generator gives every registered person at least 5 completed purchases, "
                     "so the 30-day buckets are saturated: read them as a check of the method, not as a finding.",
           "quality": "generator_floor"}
    gaps += [{"field": "signals.repeat_purchases", "status": "needs_backend",
              "reason": "Exact repeat purchases need an orders table (refunds, off-app payments). The buckets above come from completed Transaction events only, and the sample generator floors every registered person at 5 purchases."},
             {"field": "signals.lifetime_value", "status": "needs_backend",
              "reason": "Lifetime value in pesos needs payments or ledger data (fees, margin, refunds). The events carry gross amounts of the attempts only, so no figure is shown."}]
    ltv = {"status": "needs_backend", "source": "Backend database", "value": None,
           "reason": "Needs payments or ledger data. Not computed, not estimated."}

    # ---- (d) behaviour segments: every active person lands in exactly one, first match wins
    load_first = set()
    for u in active:
        t = buys[u]
        if cx.persona_of[u] == "sari_sari" and len(t) >= 5 and sum(s["product"] == "eload" for s in t) / len(t) >= LOAD_FIRST_SHARE:
            load_first.add(u)
    straight = set()
    for u, ss in cx.by_user.items():
        j = [s for s in ss if s["journey"] != "browse"]
        if j and sum(s["completed"] for s in j) / len(j) >= STRAIGHT_THROUGH:
            straight.add(u)
    seg_rules = [("stalled_otp", "Stalled at OTP code", lambda u: u in top_users and top["screen"] == "otp"),
                 ("high_value_topup", "High-value top-uppers", lambda u: u in big),
                 ("shared_device", "Shared devices", lambda u: u in shared),
                 ("load_first", "Load-first store owners", lambda u: u in load_first),
                 ("straight_through", "Straight-through completers", lambda u: u in straight)]
    seg_of = {}
    for u in active:
        seg_of[u] = next((sid for sid, _, f in seg_rules if f(u)), "not_grouped")
    seg_count = Counter(seg_of.values())
    labels = {sid: lab for sid, lab, _ in seg_rules}
    labels["not_grouped"] = "Not yet grouped"
    sid_order = ["straight_through", "high_value_topup", "stalled_otp", "load_first", "shared_device", "not_grouped"]
    pc = split_pct({k: seg_count.get(k, 0) for k in sid_order})
    segments = {"total": n_active, "items": [{"id": k, "label": labels[k], "people": seg_count.get(k, 0), "share": share(seg_count.get(k, 0), n_active), "pct": pc[k]} for k in sid_order],
                "definition": "Each active person is in exactly one group; the first rule that matches wins: stalled at OTP, high-value top-up, shared device, load-first store owner, straight-through, otherwise not yet grouped.",
                "rules": {"high_value_topup_php": HIGH_TOPUP_PHP, "shared_device_users": SHARED_DEVICE_USERS, "load_first_eload_share": LOAD_FIRST_SHARE, "straight_through_share": STRAIGHT_THROUGH}}
    for u, sid in seg_of.items():
        members_rows.append({"user_id": u, "audience_id": f"segment:{sid}", "audience_kind": "segment", "state": "member", "synthetic": True})

    block = {
        "source": "calculated", "text_source": "rule", "synthetic": True, "as_of": cx.as_of, "observed_until": cx.obs_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "active_users": n_active, "active_definition": "People with at least one session in the 30-day sample, outside the two hidden user groups.",
        "win_back": {"top": top, "by_insight": wb}, "cards": cards,
        "signals": {"return_visits": ret, "repeat_purchases": rep, "lifetime_value": ltv},
        "segments": segments, "gaps": gaps,
    }
    return block, members_rows


# ----------------------------------------------------------------------------- events of the sessions we need
def events_for(path: Path, ids: set) -> dict:
    out = defaultdict(list)
    seen = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            e = json.loads(line)
            if e["session_id"] in ids:
                eid = e.get("event_id")
                if eid in seen:        # the same duplicate rule as the rest of the build
                    continue
                seen.add(eid)
                out[e["session_id"]].append(e)
    for evs in out.values():
        evs.sort(key=lambda e: e["ts"])
    return out


def tap_name(el: str, product_labels: dict) -> str:
    if el in TAP_NAMES:
        return TAP_NAMES[el]
    if el.startswith("product_") and el[8:] in product_labels:
        return product_labels[el[8:]]
    return el.replace("_", " ").capitalize()


def timeline(cx: Ctx, s: dict, evs: list) -> tuple:
    """Plain-English steps and the strip marks of one session, rebuilt from its events."""
    t0 = cx.parse_ts(evs[0]["ts"])
    sec = lambda e: round((cx.parse_ts(e["ts"]) - t0).total_seconds(), 1)
    items, marks, run, runs, prev_t = [], [], None, [], None
    for e in evs:
        t, et, el = sec(e), e["event_type"], e.get("element")
        if prev_t is not None and t - prev_t >= IDLE_S and et != "session_end":
            items.append({"t_seconds": prev_t, "kind": "idle", "label": f"No activity for {round(t - prev_t)} s", "seconds": round(t - prev_t)})
            marks.append({"kind": "idle", "t_seconds": prev_t, "t_end": t})
        prev_t = t
        if et in ("click", "rage_click", "dead_tap") and el:
            if run and run["el"] == el and t - run["t1"] <= 2.0:
                run["t1"] = t
                run["n"] += 1
                run["rage"] |= et == "rage_click"
                run["dead"] += et == "dead_tap"
            else:
                run = {"el": el, "t0": t, "t1": t, "n": 1, "rage": et == "rage_click", "dead": int(et == "dead_tap"), "item": {"t_seconds": t, "element": el}}
                items.append(run["item"])
                runs.append(run)
            name = tap_name(el, cx.product_labels)
            it, n = run["item"], run["n"]
            if n == 1 and run["rage"]:       # the tracker flagged rapid taps but logged one event: say that, not a count
                it.update(kind="rage_tap", label=f"Tapped {name} repeatedly")
            elif n >= 3 or run["rage"]:
                it.update(kind="rage_tap", label=f"Tapped {name} {n} times in {max(1, round(run['t1'] - run['t0']))}s")
            elif run["dead"] == n:
                it.update(kind="tap", label=f"Tapped {name}, nothing happened")
            else:
                it.update(kind="tap", label=f"Tapped {name}" + (f" {n} times" if n > 1 else ""))
            continue
        run = None
        if et == "screen_view" and e.get("screen"):
            items.append({"t_seconds": t, "kind": "step", "label": f"Opened {cx.humanize(e['screen'])}"})
        elif et == "form_focus" and el:
            items.append({"t_seconds": t, "kind": "tap", "label": f"Selected the {FIELD_NAMES.get(el, el.replace('_', ' '))} field", "element": el})
        elif et == "error":
            code = e.get("error_code") or "unknown"
            items.append({"t_seconds": t, "kind": "error", "label": f"Error: {code}", "error": code, **({"element": el} if el else {})})
            marks.append({"kind": "error", "t_seconds": t})
        elif et == "back":
            items.append({"t_seconds": t, "kind": "back", "label": "Went back"})
            marks.append({"kind": "back", "t_seconds": t})
    for r in runs:
        if r["item"]["kind"] == "rage_tap":
            marks.append({"kind": "rage_tap", "t_seconds": r["t0"], "t_end": round(max(r["t1"], r["t0"] + 1), 1)})
    end_t = sec(evs[-1])
    if s["completed"]:
        marks.append({"kind": "done", "t_seconds": end_t})
    else:
        items.append({"t_seconds": end_t, "kind": "exit", "label": "Left the app", "screen": cx.humanize(s["last"])})
        marks.append({"kind": "exit", "t_seconds": end_t})
    items.sort(key=lambda i: i["t_seconds"])
    marks.sort(key=lambda m: (m["t_seconds"], m["kind"]))
    return items, marks, end_t


def one_liner(items, outcome, dur):
    hot = next((i["label"] for i in items if i["kind"] == "rage_tap"), None) or next((i["label"] for i in items if i["kind"] == "error"), None)
    end = {"finished": f"finished in {dur:.0f} s", "left": f"left after {dur:.0f} s", "came_back_later": f"left after {dur:.0f} s, finished on a later visit"}[outcome]
    return f"{hot}, then {end}." if hot else f"{end[0].upper()}{end[1:]}."


def watch_block(cx: Ctx) -> tuple:
    picks = []       # (insight, session, outcome, role)
    pops = {}
    for ins in cx.insights:
        if ins["severity"] == "healthy" or ins.get("persona_ids") and all(p in cx.hidden for p in ins["persona_ids"]):
            continue
        member = cx.members[ins["id"]][0]
        pop = sorted((s for s in cx.clean if member(s) and s["persona"] not in cx.hidden), key=lambda s: s["sid"])
        aff = [s for s in pop if s["last"] == ins["screen"]]
        comp = [s for s in pop if s["completed"]]
        rng = random.Random(f"watch:{WATCH_SEED}:{ins['id']}")
        take_a = rng.sample(aff, min(WATCH_AFFECTED, len(aff)))
        take_c = rng.sample(comp, min(WATCH_N - len(take_a), len(comp)))
        pops[ins["id"]] = (ins, len(pop), len(aff), len(comp))
        for s in take_a:
            picks.append((ins, s, "came_back_later" if cx.finished_later(s) else "left", "affected"))
        for s in take_c:
            picks.append((ins, s, "finished", "comparison"))
    evs = events_for(cx.canon_path, {s["sid"] for _, s, _, _ in picks})
    groups = []
    rows = []
    for iid, (ins, n_pop, n_aff, n_comp) in pops.items():
        sess = []
        for i2, s, outcome, role in sorted((p for p in picks if p[0]["id"] == iid), key=lambda p: p[1]["start"]):
            items, marks, dur = timeline(cx, s, evs[s["sid"]])
            os_ = "iOS" if s["os"] == "ios" else "Android"
            rec = {"id": s["sid"], "persona": cx.persona_labels[s["persona"]], "platform": "App", "os": os_, "device_class": s["device_class"],
                   "device": cx.device_labels.get(s["device_class"], s["device_class"]), "product": cx.product_labels.get(s["product"]) if s["product"] else None,
                   "start_utc": s["start"][:19] + "Z", "duration_s": round(dur), "outcome": outcome, "role": role, "user": cx.pseudo("u_", s["user"]),
                   "summary": one_liner(items, outcome, dur), "steps": items, "marks": marks}
            sess.append(rec)
            rows.append({"session_id": s["sid"], "insight_id": iid, "user_id": s["user"], "persona": s["persona"], "os": os_, "device_class": s["device_class"],
                         "product": s["product"], "start_ts": s["start"][:19].replace("T", " "), "duration_s": round(dur), "outcome": outcome, "role": role,
                         "summary": rec["summary"], "timeline": json.dumps(items, separators=(",", ":")), "marks": json.dumps(marks, separators=(",", ":")), "synthetic": True})
        groups.append({"insight_id": iid, "insight_rank": ins["rank"], "screen": ins["screen"], "screen_label": ins["screen_label"],
                       "population": {"sessions": n_pop, "ended_here": n_aff, "finished": n_comp}, "sessions": sess})
    groups.sort(key=lambda g: g["insight_rank"])
    block = {"source": "calculated", "text_source": "rule", "synthetic": True, "footer": FOOTER,
             "sample": {"seed": WATCH_SEED, "per_insight": WATCH_N,
                        "method": f"Per finding, {WATCH_AFFECTED} random sessions that ended on the screen plus finished sessions that passed it (random, fixed seed, sorted by start time). "
                                  "Sessions of the two hidden user groups are never sampled."},
             "idle_after_s": IDLE_S, "outcomes": {"left": "Left and did not finish later", "came_back_later": "Left, finished the same journey on a later visit", "finished": "Finished in this session"},
             "insights": groups}
    return block, rows


# ----------------------------------------------------------------------------- orders (BigQuery only)
def orders(cx: Ctx) -> list:
    done = [s for s in cx.clean if s["completed"] and s["journey"] in ("transaction", "topup")]
    evs = events_for(cx.canon_path, {s["sid"] for s in done})
    out = []
    for s in sorted(done, key=lambda s: s["sid"]):
        e = evs[s["sid"]]
        amt = next((x["amount_php"] for x in reversed(e) if x.get("amount_php") is not None), None)
        out.append({"order_id": f"o_{s['sid']}", "user_id": s["user"], "product": s["product"] if s["journey"] == "transaction" else "topup",
                    "amount_php": amt, "ts": e[-1]["ts"][:-1].replace("T", " "), "status": "completed", "session_id": s["sid"], "synthetic": True})
    return out


# ----------------------------------------------------------------------------- data sources
def data_sources_block(cx: Ctx, aud: dict, counts: dict) -> dict:
    res, em, g = cx.results, cx.em, cx.guardian
    steps = [st for j in res["scope"]["journeys"] for st in j["steps"]]
    matched = sum(1 for st in steps if st["status"] == "matched")
    unm = sum(em["unmapped_by_screen"].values())
    silent = [f for f in g["faults"] if f["kind"] == "tracker_silent" and f["status"] == "active"]
    screens = len(em["events_by_screen"])
    days = em["daily_events"]
    e = cx.t_end.date()      # same convention as views[...].health: whole days from the range start up to, not including, the end date
    ev_between = lambda a, b: sum(c for d, c in days.items() if a.isoformat() <= d < b.isoformat())
    now_ev, prev_ev = ev_between(e - timedelta(days=7), e), ev_between(e - timedelta(days=14), e - timedelta(days=7))
    chg = round(now_ev / prev_ev - 1, 4) if prev_ev else None
    rr = aud["signals"]["return_visits"]
    ret_ok = any(rr[k]["status"] == "ready" for k in ("d1", "d7"))
    sig = [
        {"id": "drop_offs", "name": "Drop-offs and friction", "source": "App tracker", "status": "ready" if res["insights"] else "partial",
         "used_for": "Findings, journeys, replays", "note": "Counted from screens, taps and errors."},
        {"id": "return_visits", "name": "Return visits", "source": "App tracker", "status": "ready" if ret_ok else "partial",
         "used_for": "Win-back audiences", "note": "Counted from sessions per person; 30-day returns need a longer sample." if rr["d30"]["status"] != "ready" else "Counted from sessions per person."},
        {"id": "repeat_purchases", "name": "Repeat purchases", "source": "App tracker", "status": "partial",
         "used_for": "Loyal and one-time buyers", "note": "From completed-transaction events; misses refunds and off-app payments. Orders data would make it exact."},
        {"id": "lifetime_value", "name": "Lifetime value", "source": "Backend database", "status": "needs_backend",
         "used_for": "High-value audiences by real pesos", "note": "Needs payments or ledger data."},
        {"id": "value_at_risk", "name": "Value at risk", "source": "Backend database", "status": "partial",
         "used_for": "Impact of findings in pesos", "note": "Uses assumed pesos per completed task (see meta.value_assumption) until a backend database is connected."},
        {"id": "support", "name": "Support tickets and reviews", "source": "Help desk", "status": "later",
         "used_for": "Why people leave, in their words", "note": "Not connected; planned."},
    ]
    return {
        "source": "calculated", "text_source": "rule", "synthetic": True,
        "status_legend": {"ready": "Computed here from the app tracker", "available": "The source has it; not computed yet", "partial": "Computed, with known limits",
                          "needs_backend": "Cannot be computed without a backend database", "later": "Planned, not connected"},
        "signals": sig,
        "connected": {
            "app_tracker": {"status": "connected", "dataset": res["meta"]["dataset"], "label": res["meta"]["dataset_label"], "synthetic": res["meta"]["synthetic"],
                            "events": counts["events"], "sessions": counts["sessions"], "users": counts["users"]},
            "journey_steps": {"matched": matched, "total": len(steps), "to_review": len(steps) - matched},
            "backend_database": {"status": "not_connected", "signals_locked": [s["name"] for s in sig if s["status"] == "needs_backend"]},
        },
        "health": {
            "event_volume": {"change": chg, "now_events": now_ev, "before_events": prev_ev, "compared_with": "the 7 days before", "status": "ok" if chg is not None and abs(chg) < 0.15 else "warning"},
            "events_matched": {"share": round(1 - unm / em["events"], 4), "unmatched_events": unm, "events": em["events"], "label": "fully matched to a step"},
            "trackers": {"firing": screens - len(silent), "total": screens,
                         "silent": [{"title": f["title"], "screen": f.get("screen"), "app_version": f.get("app_version")} for f in silent]},
            "sessions_set_aside": counts["sessions_quarantined"],
        },
    }


def backend_sample(tables: dict, events_rows) -> dict:
    return {"synthetic": True, "dataset": "squint_samples", "location": "us-central1", "access": "Builder credentials only. The page never queries it; visitors do not log in.",
            "tables": [{"table": "wallet_events", "rows": events_rows, "description": "Every raw app event (the source of this whole build)."}] +
                      [{"table": t, "rows": n, "description": SAMPLE_TABLES[t]} for t, n in tables.items()]}


def build(a: dict) -> dict:
    """a: ctx dict from build_results.main. Returns {'audiences','watch','data_sources'} and writes the BigQuery NDJSON files."""
    cx = Ctx(a)
    aud, member_rows = audience_blocks(cx)
    persona_keys = list(dict.fromkeys(key.rsplit("|", 1)[1] for key in a["results"]["views"]))
    persona_keys = [key for key in persona_keys if not set(key.split("+")).intersection(cx.hidden)]
    audience_scopes = {}
    for platform in ["all"] + a["results"]["meta"]["platforms"]:
        platform_sessions = [s for s in cx.clean if platform == "all" or s["platform"] == platform]
        platform_all = [s for s in cx.all_s if platform == "all" or s["platform"] == platform]
        for persona in persona_keys:
            selected = None if persona == "all" else set(persona.split("+"))
            scoped_clean = [s for s in platform_sessions if selected is None or s["persona"] in selected]
            scoped_insights = [i for i in a["insights"]
                               if (not i["persona_ids"] or selected is None or bool(selected.intersection(i["persona_ids"])))
                               and (platform == "all" or not i.get("platform_ids") or platform in i["platform_ids"])]
            scoped = dict(a, clean=scoped_clean, all_s=platform_all, insights=scoped_insights)
            block, _ = audience_blocks(Ctx(scoped), pin_otp=(persona == "all"))
            audience_scopes[f"{platform}|{persona}"] = block
    aud["scopes"] = audience_scopes
    watch, watch_rows = watch_block(cx)
    order_rows = orders(cx)
    out_dir = Path(a["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = {"wallet_orders": order_rows, "audience_members": member_rows, "watch_sessions": watch_rows}
    for name, rows in tables.items():
        (out_dir / f"{name}.ndjson").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    ds = data_sources_block(cx, aud, a["results"]["meta"]["counts"])
    rep_file = Path(str(a["canon_path"]) + ".report.json")      # the normalize report: records read = rows in the wallet_events table
    events_rows = json.loads(rep_file.read_text(encoding="utf-8")).get("records_read") if rep_file.exists() else None
    ds["backend_sample"] = backend_sample({t: len(r) for t, r in tables.items()}, events_rows)
    return {"audiences": aud, "watch": watch, "data_sources": ds}
