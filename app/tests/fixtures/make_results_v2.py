"""Builds app/tests/fixtures/results_v2.json: a FIXTURE for developing and testing the Squint UI before the data pipeline's
real results.json arrives. ALL NUMBERS ARE SYNTHETIC and invented here (seeded, deterministic). They are shaped like the
planted patterns in docs/smartsari-dataset-spec.md but are NOT measured from any generated events.

Field list and meaning: docs/ui-results-needs.md. Run: python app/tests/fixtures/make_results_v2.py
"""
import json
import random
import zlib
from pathlib import Path

OUT = Path(__file__).with_name("results_v2.json")
AS_OF = "2026-10-14"
RANGES = {"24h": 1 / 30, "7d": 7 / 30, "30d": 1.0}
PERSONAS = [
    ("unregistered", "Unregistered", 200), ("large_business", "Large business", 160), ("sari_sari", "Retail", 400),
    ("individual_trader", "Individual trader", 80), ("individual", "Individual", 80), ("unknown", "Unknown", 40),
    ("fraudster", "Fraudster", 40),
]
PRODUCTS = [("eload", "E-load"), ("water_bill", "Water bill"), ("electricity_bill", "Electricity bill"),
            ("game_voucher", "Game voucher"), ("cable_internet", "Cable TV and internet"), ("send_money", "Send money"),
            ("postpaid_telecom", "Post-paid telecom")]
PID = [p[0] for p in PERSONAS]

# 30-day session starts for everyone, per journey; share of those starts by persona
BASE30 = {"register_login": 5600, "topup": 4400, "transaction": 5600}
SHARE = {
    "register_login": dict(unregistered=.46, large_business=.04, sari_sari=.16, individual_trader=.04, individual=.04, unknown=.08, fraudster=.18),
    "topup": dict(large_business=.22, sari_sari=.50, individual_trader=.09, individual=.09, unknown=.05, fraudster=.05),
    "transaction": dict(large_business=.20, sari_sari=.50, individual_trader=.10, individual=.10, unknown=.05, fraudster=.05),
}
SHARE_ALL = dict(unregistered=.2, large_business=.16, sari_sari=.4, individual_trader=.08, individual=.08, unknown=.04, fraudster=.04)
# step: id, label, event, exit class, base exit rate
JOURNEYS = [
    ("register_login", "Register and login", [
        ("splash", "App open", "app_open", "natural", .03), ("phone", "Phone number", "phone_input", "ux", .04),
        ("otp", "OTP code", "otp_verify", "technical", .05), ("personal", "Personal data", "personal_data_form", "ux", .18),
        ("tin", "TIN number", "tin_input", "language", .08), ("selfie", "Selfie check", "kyc_selfie", "technical", .06),
        ("registered", "Registered", "registration_success", "natural", 0)]),
    ("topup", "Wallet top-up", [
        ("wallet", "Wallet", "wallet_view", "natural", .06), ("cashin", "Cash in", "cashin_view", "ux", .04),
        ("paymethod", "Payment method", "payment_method_select", "ux", .09), ("amount", "Enter amount", "cashin_amount", "ux", .05),
        ("onprocess", "On process", "txn_status_on_process", "technical", .04), ("success", "Success", "txn_status_success", "natural", 0)]),
    ("transaction", "Buy a product", [
        ("home", "Home", "home_view", "natural", .12), ("product", "Choose product", "product_select", "ux", .05),
        ("account", "Number or account", "account_input", "ux", .04), ("amount", "Choose amount", "amount_select", "language", .05),
        ("confirm", "Confirm with PIN", "pin_confirm", "ux", .07), ("processing", "Processing", "txn_processing", "technical", .03),
        ("success", "Success", "txn_status_success", "natural", 0)]),
]
MAPCONF = {"otp": .71, "processing": .78, "selfie": .86}
TAGS = {("register_login", "personal"): "Dropdown loop", ("register_login", "tin"): "Skip option unclear"}


def rng(*key):
    return random.Random(zlib.crc32("|".join(map(str, key)).encode()))


def view_key(r, p):
    return f"{r}|all|{p}"


def build_view(r, p):
    rg = rng("view", r, p)
    vol = RANGES[r]
    journeys, signals, loops = [], {}, {}
    for jid, jname, steps in JOURNEYS:
        sh = SHARE[jid].get(p) if p != "all" else 1.0
        if not sh:
            continue
        start = max(8, round(BASE30[jid] * vol * sh * (0.93 + 0.14 * rg.random())))
        count, rows = start, []
        for i, (sid, name, ev, cls, rate) in enumerate(steps):
            last = i == len(steps) - 1
            rr = rate * (0.9 + 0.2 * rg.random())
            key = (jid, sid)
            if key == ("register_login", "otp"):
                rr = {"24h": .05, "7d": .088, "30d": .062}[r]
            if key in (("register_login", "personal"), ("register_login", "tin")) and p not in ("all", "unregistered"):
                rr = 0.03
            if key == ("transaction", "confirm") and p == "individual_trader":
                rr = .125
            if key == ("transaction", "confirm") and p == "all":
                rr = .074
            if key == ("register_login", "phone") and p == "fraudster":
                rr = .22
            if key == ("register_login", "selfie") and r == "24h":
                rr = .15      # tracker silent since Oct 13 18:00 (data gap), reads as a spike
            ex = 0 if last else min(count - 1, round(count * rr))
            tone = "healthy"
            if not last:
                if key == ("register_login", "otp") and r != "24h":
                    tone = "critical"
                elif key == ("transaction", "confirm") and p in ("all", "individual_trader") and r != "24h":
                    tone = "critical"
                elif rr >= .15 or key == ("register_login", "tin") or (key == ("register_login", "phone") and p == "fraudster"):
                    tone = "warning"
                elif key == ("register_login", "selfie") and r == "24h":
                    tone = "warning"
            if key == ("transaction", "product") and p in ("all", "sari_sari"):
                tone = "positive"
            rows.append(dict(id=sid, sessions=count, exits=ex, exit_class=cls, tone=tone, _rate=rr))
            count -= ex
        for rw in rows:
            rw.pop("_rate")
            if rw is rows[-1]:
                rw["tag"] = f"{100 * rw['sessions'] / start:.1f}%"
            elif rw["tone"] == "positive":
                rw["tag"] = "Price check loop"
            elif rw["tone"] in ("critical", "warning"):
                rw["tag"] = TAGS.get((jid, rw["id"])) or f"{round(100 * rw['exits'] / max(1, rw['sessions']))}% exit"
            else:
                rw["tag"] = "Steady"
            rw["low_sample"] = rw["sessions"] < 20
            if rw["low_sample"]:
                rw["tag"], rw["tone"] = "Few sessions", "healthy"
        journeys.append(dict(id=jid, steps=rows))
        sg = {}
        for rw in rows:
            hot = rw["tone"] in ("critical", "warning")
            sg[rw["id"]] = [round(b * (1.6 if hot else 1) * (0.5 + rg.random()), 1) for b in (1.2, 1.8, 0.9, 2.5)]
        signals[jid] = sg
        ids = [x["id"] for x in rows]
        lp = []

        def add(a, b, share, kind="neg"):
            lp.append({"from": a, "to": b, "count": max(3, round(start * share)), "kind": kind})
        if "otp" in ids and r != "24h":
            add("otp", "phone", .09)
        if "tin" in ids:
            add("tin", "personal", .05)
        if "paymethod" in ids:
            add("paymethod", "cashin", .06)
        if jid == "transaction":
            add("amount", "account", .045)
            if p in ("all", "sari_sari"):
                add("product", "home", .10, "pos")
            if p in ("all", "individual_trader"):
                add("confirm", "amount", .09 if p == "all" else .2)
        loops[jid] = lp
    # insights visible in this view
    ins = [i for i in INSIGHTS if r in i["ranges"] and (p == "all" or not i["persona_ids"] or p in i["persona_ids"])]
    ins.sort(key=lambda i: -i["impact"]["score"])
    probs = [i for i in ins if i["severity"] != "healthy"]
    crit = [i for i in probs if i["severity"] == "critical"]
    value = sum(i["impact"]["per_week_value"] for i in probs)
    first = journeys[0]["steps"]
    conv = 100 * first[-1]["sessions"] / max(1, first[0]["sessions"])
    prev_conv = conv + rg.uniform(.8, 2.4) * (1 if crit else -1)

    def series(end, n=14, amp=.6, drift=0.0, integer=False):
        out = []
        for k in range(n):
            v = end - drift * (n - 1 - k) / (n - 1) + (0 if k == n - 1 else rg.uniform(-amp, amp))
            out.append(round(v) if integer else round(v, 2))
        return out
    cov = 94.1
    kpis = [
        dict(id="conversion", label="Register and login completion", format="pct1", higher_is_better=True, value=round(conv, 1), prev=round(prev_conv, 1),
             series=series(conv, drift=conv - prev_conv), prev_series=series(prev_conv, amp=.5), sub="Sessions that reach Registered"),
        dict(id="blind_spots", label="Critical blind spots", format="count", higher_is_better=False, value=len(crit), prev=max(0, len(crit) - 1),
             series=series(len(crit), amp=.5, integer=True, drift=1), prev_series=series(max(0, len(crit) - 1), amp=.5, integer=True),
             sub="Small segments hidden by the overall rate"),
        dict(id="value_at_risk", label="Value at risk", format="php_week", higher_is_better=False, value=round(value, -2), prev=round(value * .72, -2),
             series=series(value / 1000, amp=value / 1000 * .06, drift=value / 1000 * .28), prev_series=series(value * .72 / 1000, amp=value / 1000 * .05),
             sub="Assumed value, not measured"),
        dict(id="mapping_coverage", label="Event mapping coverage", format="pct1", higher_is_better=True, value=cov, prev=round(cov - 3.2, 1),
             series=series(cov, amp=.3, drift=3.2), prev_series=series(cov - 3.2, amp=.3), sub=COVSUB),
    ]
    ex = dict(ux=0, language=0, technical=0, natural=0)
    for j in journeys:
        for s in j["steps"]:
            ex[s["exit_class"]] += s["exits"]
    blind = None
    if p in ("all", "individual_trader") and r != "24h":
        bars = [dict(l1=pl, l2="Send money", value=v, hot=h) for pl, v, h in
                [("Large business", 5, False), ("Retail", 4, False), ("Trader", 55, True), ("Individual", 6, False)]]
        bars += [dict(l1="Trader", l2="E-load", value=4, hot=False), dict(l1="Retail", l2="E-load", value=3, hot=False)]
        blind = dict(journey="transaction", step="confirm", title="Blind spot: Confirm with PIN",
                     sub="Exit rate at Confirm, by persona and product, against the overall rate",
                     baseline=7.4, baseline_label="Overall rate 7.4% hides the trader and send-money cliff", badge="7.4x the overall rate", bars=bars)
    elif p in ("all", "unregistered") and r != "24h":
        bars = [dict(l1="Unregistered", l2="Inside window", value=70, hot=True), dict(l1="Unregistered", l2="Outside", value=5, hot=False),
                dict(l1="Retail", l2="Inside window", value=64, hot=True), dict(l1="Retail", l2="Outside", value=4, hot=False)]
        blind = dict(journey="register_login", step="otp", title="Blind spot: OTP code",
                     sub="OTP exit rate inside and outside the 2026-10-09 02:00 to 10:00 UTC window",
                     baseline=8.8, baseline_label="Overall rate 8.8% hides the stalled window", badge="8x the usual rate", bars=bars)
    if r == "7d":
        labels = ["Thu 8", "Fri 9", "Sat 10", "Sun 11", "Mon 12", "Tue 13", "Wed 14"]
        fb, nb = [40, 92, 44, 52, 46, 49, 53], [88, 90, 84, 79, 91, 93, 86]
        mk = [dict(index=1, label="OTP not delivered")]
    elif r == "24h":
        labels = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24", "Now"]
        fb, nb = [3, 4, 8, 9, 8, 6, 5], [11, 9, 20, 26, 24, 15, 12]
        mk = []
    else:
        labels = ["Sep 15", "Sep 19", "Sep 23", "Sep 27", "Oct 1", "Oct 5", "Oct 9"]
        fb, nb = [130, 128, 141, 134, 139, 171, 188], [370, 361, 352, 380, 366, 349, 358]
        mk = [dict(index=5, label="App 4.12 rollout")]
    k = 1 if p == "all" else SHARE_ALL.get(p, 1)
    fb = [max(1, round(x * k * (0.9 + .2 * rg.random()))) for x in fb]
    nb = [max(1, round(x * k * (0.9 + .2 * rg.random()))) for x in nb]
    chg = round(100 * (fb[-1] - fb[0]) / max(1, fb[0]))
    rhythm = dict(labels=labels, natural=nb, frustrated=fb, markers=mk,
                  note=f"Frustrated exits {'up' if chg >= 0 else 'down'} {abs(chg)}% across this period"
                  + (f"; the largest jump lines up with: {mk[0]['label']}." if mk else ", while natural exits hold steady."))
    health = dict(tiles=[
        dict(label="Event volume", value="-4.1%", sub="vs. the 7 days before", status="ok"),
        dict(label="Schema match", value="97.9%", sub="of events mapped", status="ok"),
        dict(label="Trackers firing", value="23 of 24", sub="1 tracker silent (kyc_selfie, app 4.12)", status="critical"),
        dict(label="Sessions held out", value=str(round(65 * vol)), sub="inside a telemetry fault window", status="warning" if vol > .1 else "ok")])
    return dict(sessions=sum(j["steps"][0]["sessions"] for j in journeys), kpis=kpis, insight_ids=[i["id"] for i in ins], journeys=journeys,
                signals=signals, loops=loops, blind=blind, exits=ex, rhythm=rhythm, cohorts=COHORTS[p], health=health)


_ALL = [x for _, _, st in JOURNEYS for x in st]
COVSUB = f"{len(_ALL) - 2} of {len(_ALL)} steps matched, 2 to review"


def cohort(*items, note):
    return dict(items=[dict(name=n, share=s, tone=t, is_new=nw) for n, s, t, nw in items], note=note)


COHORTS = {
    "all": cohort(("Straight-through completers", 38, "accent", False), ("Load-first store owners", 21, "accent", False), ("Price-checkers, register later", 14, "info", False),
                  ("Stalled at the OTP code", 9, "warn", False), ("Shared-device bursts", 5, "crit", True), ("High-value top-uppers", 6, "accent", False), ("Other", 7, "muted", False),
                  note="Anomaly: Shared-device bursts emerged this week (+2.1 points), concentrated on fraudster accounts with 3 or more users on one device."),
    "unregistered": cohort(("Price-checkers, register later", 52, "info", False), ("Stalled at the OTP code", 22, "warn", False), ("Straight-through completers", 16, "accent", False), ("Other", 10, "muted", False),
                           note="Unregistered users open prices repeatedly before registering. That is a natural exit and is not flagged."),
    "large_business": cohort(("High-value top-uppers", 41, "accent", False), ("Straight-through completers", 44, "accent", False), ("Stalled at the OTP code", 6, "warn", False), ("Other", 9, "muted", False),
                             note="Large businesses top up above 50,000 pesos in most top-ups; every other persona stays under 5,000."),
    "sari_sari": cohort(("Load-first store owners", 52, "accent", False), ("Straight-through completers", 35, "accent", False), ("Stalled at the OTP code", 7, "warn", False), ("Other", 6, "muted", False),
                        note="Retail buys e-load in about 70% of its transactions. Expected behavior, not a problem."),
    "individual_trader": cohort(("Straight-through completers", 55, "accent", False), ("Abandon at PIN confirm", 24, "crit", True), ("Send-money regulars", 14, "info", False), ("Other", 7, "muted", False),
                                note="Anomaly: Abandon at PIN confirm is concentrated on Send money."),
    "individual": cohort(("Straight-through completers", 71, "accent", False), ("Stalled at the OTP code", 8, "warn", False), ("Bill payers", 14, "info", False), ("Other", 7, "muted", False),
                         note="No unusual cohort for this persona."),
    "unknown": cohort(("Straight-through completers", 46, "accent", False), ("Shared-device bursts", 18, "crit", True), ("Stalled at the OTP code", 12, "warn", False), ("Other", 24, "muted", False),
                      note="Unknown accounts sometimes share a device with a fraudster account."),
    "fraudster": cohort(("Shared-device bursts", 61, "crit", True), ("Failed-attempt bursts at odd hours", 27, "warn", False), ("Other", 12, "muted", False),
                        note="Fraudsters: bursts of failed attempts and up to 5 users on one device. Needs review; not classified as a UX problem."),
}


def raw(sid, persona, t, typ, screen, el=None, dwell=None, err=None, extra=None):
    d = dict(event_id=f"e_{sid}_{t}", session_id=sid, timestamp=f"2026-10-09T0{3 + t // 3600000}:{(t // 60000) % 60:02d}:{(t // 1000) % 60:02d}Z",
             event_type=typ, screen=screen, element=el, persona=persona, platform="app", os="android", app_version="4.11.2", dwell_ms=dwell, error_code=err)
    if extra:
        d.update(extra)
    return d


def ev_session(sid, persona, role, evs):
    return dict(session_id=sid, role=role, platform="app", persona=persona, path=list(dict.fromkeys(e["screen"] for e in evs)), events=evs)


def diag(status, cls, conf, summary, steps, caveats=None):
    if status == "pending":
        return dict(status="pending", model=None, generated_at=None, source_note=None, **{"class": None}, confidence=None, summary=None,
                    claims=[], next_steps=[], guardrail_flags=[], caveats=[])
    return dict(status=status, model="fixture text, not model output", generated_at="2026-10-14T10:00:00Z",
                source_note="Saved result from 2026-10-14" if status == "cached" else None, **{"class": cls}, confidence=conf, summary=summary,
                claims=[], next_steps=[dict(kind="check", text=t) for t in steps], guardrail_flags=[], caveats=caveats or [])


def insight(id, rank, sev, cls, title, journey, step, tone, label, personas, ranges, hours, new, replays, n, causes, hyp, rec, impact, evs, seg_text, status="done", conf=.85):
    sc, vol, val, assumption = impact
    return {
        "id": id, "rank": rank, "severity": sev, "class": cls, "title": title, "summary": hyp, "hypothesis": hyp, "confidence": conf,
        "recommendation": rec, "guardrail_flags": [], "diagnosis_status": status,
        "diagnosis": diag(status, cls, conf, hyp, [rec] if rec else []),
        "journey": journey, "step": step, "tone": tone, "label": label, "persona_ids": personas, "ranges": ranges,
        "detected_hours_ago": hours, "is_new": new, "replays": replays, "n_sessions": n, "segment_text": seg_text, "causes": causes,
        "impact": dict(score=sc, severity=round(min(1, sc / 100), 2), volume=vol, value_per_session=val, per_week_value=round(vol * val), assumption=assumption),
        "evidence": dict(affected_session_ids=[e["session_id"] for e in evs], sessions=evs),
    }


def cause(type, share, title, why, fault_id=None, resolved=False, quarantine=False):
    return dict(type=type, share=share, title=title, why=why, fault_id=fault_id, resolved=resolved, quarantine=quarantine)


ASSUME150 = "Assumed value: PHP 150 per completed registration. Not measured; replace with the real figure before quoting pesos."
ASSUME200 = "Assumed value: PHP 200 per completed remittance. Not measured; replace with the real figure before quoting pesos."
ASSUME0 = "No value assumed: these may be fraud attempts or expected behavior, not lost customers."

otp_ev = [ev_session("s_p1_0412", "unregistered", "affected", [
    raw("s_p1_0412", "unregistered", 0, "screen_view", "phone_input"), raw("s_p1_0412", "unregistered", 21000, "click", "phone_input", "send_code"),
    raw("s_p1_0412", "unregistered", 24000, "screen_view", "otp_verify"), raw("s_p1_0412", "unregistered", 61000, "rage_click", "otp_verify", "resend_code", err="OTP_NOT_RECEIVED"),
    raw("s_p1_0412", "unregistered", 95000, "session_end", "otp_verify", dwell=71000)])]
trader_ev = [ev_session("s_p4_0188", "individual_trader", "affected", [
    raw("s_p4_0188", "individual_trader", 0, "screen_view", "product_select", extra=dict(product="send_money")),
    raw("s_p4_0188", "individual_trader", 18000, "click", "amount_select", "amount_5000", extra=dict(product="send_money", amount_php=5000)),
    raw("s_p4_0188", "individual_trader", 33000, "screen_view", "pin_confirm", extra=dict(product="send_money")),
    raw("s_p4_0188", "individual_trader", 61000, "click", "pin_confirm", "back", extra=dict(product="send_money")),
    raw("s_p4_0188", "individual_trader", 88000, "session_end", "pin_confirm", dwell=55000, extra=dict(product="send_money"))])]
frd_ev = [ev_session("s_m1_0031", "fraudster", "affected", [
    raw("s_m1_0031", "fraudster", 0, "screen_view", "phone_input", extra=dict(device_id="d_0091")),
    raw("s_m1_0031", "fraudster", 2000, "error", "phone_input", err="LOGIN_FAILED", extra=dict(device_id="d_0091")),
    raw("s_m1_0031", "fraudster", 4000, "error", "phone_input", err="LOGIN_FAILED", extra=dict(device_id="d_0091")),
    raw("s_m1_0031", "fraudster", 7000, "session_end", "phone_input", extra=dict(device_id="d_0091"))])]
pd_ev = [ev_session("s_c_0711", "unregistered", "affected", [
    raw("s_c_0711", "unregistered", 0, "screen_view", "personal_data_form"), raw("s_c_0711", "unregistered", 9000, "click", "personal_data_form", "business_type_dropdown"),
    raw("s_c_0711", "unregistered", 22000, "click", "personal_data_form", "business_type_dropdown"), raw("s_c_0711", "unregistered", 41000, "session_end", "personal_data_form", dwell=41000)])]
tin_ev = [ev_session("s_c_0833", "unregistered", "affected", [
    raw("s_c_0833", "unregistered", 0, "screen_view", "tin_input"), raw("s_c_0833", "unregistered", 12000, "click", "tin_input", "no_tin"),
    raw("s_c_0833", "unregistered", 15000, "screen_view", "tin_input", "confirm_modal"), raw("s_c_0833", "unregistered", 39000, "session_end", "tin_input", dwell=39000)])]
heal_ev = [ev_session("s_h_0101", "sari_sari", "affected", [
    raw("s_h_0101", "sari_sari", 0, "screen_view", "product_select", extra=dict(product="eload")),
    raw("s_h_0101", "sari_sari", 12000, "click", "product_select", "eload", extra=dict(product="eload"))])]

INSIGHTS = [
    insight("temporal:otp:2026-10-09", 1, "critical", "technical_bug", "OTP codes did not arrive on Oct 9, 02:00 to 10:00 UTC, so sign-ups stalled",
            "register_login", "otp", "critical", "Critical · Blind spot", [], ["7d", "30d"], 122, False, 5, 410,
            [cause("technical", .72, "OTP not delivered in one time window", "70% of attempts stalled on the OTP screen inside the window, against 5% outside it. Resend taps and exits followed."),
             cause("technical", .18, "otp_channel_v2 property is unmapped", "Some retries through the SMS fallback land as unknown events, so progress is under-counted.", "g3"),
             cause("behavior", .10, "Users wait out the resend timer, then leave", "Normal reaction to a code that never arrives.")],
            "Between 02:00 and 10:00 UTC on Oct 9 the OTP step stalled for about 70% of attempts, with resend rage taps and exits. Outside that window the OTP exit rate is about 5%. The pattern points to the code not being sent or received, not to how users behave.",
            "Check the SMS provider logs for Oct 9, 02:00 to 10:00 UTC, and send fresh codes to users who stalled in the window.",
            (91, 45, 150, ASSUME150), otp_ev, "All users, Oct 9 02:00 to 10:00 UTC", conf=.87),
    insight("segment:confirm:send_money:individual_trader", 2, "critical", "ux_friction", "Individual traders abandon Send money at the PIN confirm step 55% of the time",
            "transaction", "confirm", "critical", "Critical · Blind spot", ["individual_trader"], ["7d", "30d"], 70, True, 4, 84,
            [cause("behavior", .62, "Trader flow loops back from PIN confirm to the amount", "Back taps and 55% exits at confirm for Send money, against about 5% for others."),
             cause("technical", .28, "Possible confirm error on this product", "Cannot be ruled out from events alone; the data holds no server logs."),
             cause("technical", 0, "Duplicate checkout events on Android", "Double-firing was fixed in app 4.11.2, so it is ruled out for these numbers.", "g4", True)],
            "Individual traders abandon Send money at the PIN confirm step about 55% of the time, against about 5% for everyone else. The overall confirm rate (7.4%) hides it.",
            "Reproduce the Send money confirm for a trader account, and compare the amount and fee display with other products.",
            (84, 11, 200, ASSUME200), trader_ev, "Individual traders, Send money", conf=.79),
    insight("segment:personal:control", 3, "warning", "ux_friction", "Personal data loses 18% of sessions every day of the window",
            "register_login", "personal", "warning", "Warning", ["unregistered"], ["24h", "7d", "30d"], 700, False, 3, 230,
            [cause("behavior", .8, "Business type list does not fit how stores describe themselves", "Repeated dropdown opens with no selection before exit."),
             cause("technical", .2, "Unclear: no fault found", "No tracker or pipeline fault touches this step.")],
            "About 18% of sessions leave on Personal data, steady across the whole window. Repeated dropdown opens suggest the business type list is hard to use.",
            "Add Retail as a default option and let users search the list.",
            (58, 38, 150, ASSUME150), pd_ev, "Unregistered, whole window", conf=.72),
    insight("segment:tin:control", 4, "warning", "language_cognitive_overload", "TIN number loses 8% of sessions; the no-TIN option and the mandatory message disagree",
            "register_login", "tin", "warning", "Warning", ["unregistered"], ["24h", "7d", "30d"], 700, False, 2, 120,
            [cause("behavior", 1, "Copy conflict at the confirm modal", "Users who tap I do not have a TIN see a message that says the field is mandatory.")],
            "Users who choose the no-TIN option then see a message that says the TIN field is mandatory. About 8% of sessions end here.",
            "Rewrite the no-TIN path so it says the TIN can be added later.", (44, 20, 150, ASSUME150), tin_ev, "Unregistered, whole window", conf=.83),
    insight("segment:phone:fraudster", 5, "warning", None, "Fraudster accounts show bursts of failed logins, up to 5 users on one device",
            "register_login", "phone", "warning", "Needs review", ["fraudster", "unknown"], ["24h", "7d", "30d"], 30, True, 3, 40,
            [cause("behavior", .7, "Burst pattern at odd hours across shared devices", "Failed attempts cluster in short bursts, many users on one device."),
             cause("technical", .3, "Cannot be separated from a login bug", "Not classified. Needs a person to review the evidence.")],
            None, "Review the evidence sessions before acting. Do not treat these as lost customers.",
            (40, 38, 0, ASSUME0), frd_ev, "Fraudster and unknown accounts", status="pending", conf=None),
    insight("segment:product:sari_sari:eload", 6, "healthy", "natural_exit", "Retail buys e-load in about 70% of its transactions",
            "transaction", "product", "positive", "Healthy", ["sari_sari"], ["24h", "7d", "30d"], 400, False, 0, 280, [],
            "This is expected behavior for retail: they resell e-load. No action is needed.", "Do not add pop-ups or forced steps here.",
            (0, 0, 0, ASSUME0), heal_ev, "Retail, e-load"),
    insight("segment:topup:large_business", 7, "healthy", "natural_exit", "Large businesses top up above PHP 50,000; every other persona stays under PHP 5,000",
            "topup", "amount", "positive", "Healthy", ["large_business"], ["7d", "30d"], 400, False, 0, 60, [],
            "Large businesses move bigger amounts. This is a pattern, not a fault.", "No action needed.", (0, 0, 0, ASSUME0), heal_ev, "Large businesses, top-up"),
    insight("segment:splash:unregistered", 8, "healthy", "natural_exit", "Unregistered users open prices several times before registering",
            "register_login", "splash", "healthy", "Healthy", ["unregistered"], ["24h", "7d", "30d"], 400, False, 0, 300, [],
            "Comparing prices before signing up is a natural exit. No nudge is recommended.", "No action needed. Do not interrupt these users.",
            (0, 0, 0, ASSUME0), heal_ev, "Unregistered users"),
]
def _diag(ins_id, **kw):
    ins = next(i for i in INSIGHTS if i["id"] == ins_id)
    ins["diagnosis"] = kw.pop("whole") if "whole" in kw else {**ins["diagnosis"], **kw}
    d = ins["diagnosis"]
    if "class" in d:
        ins["class"] = d["class"]
    if "confidence" in d:
        ins["confidence"] = d["confidence"]


# one insight per diagnosis state of results contract v0.6 (FIXTURE text, not model output)
_diag("temporal:otp:2026-10-09", status="done", source="gemini", confidence=0.87, **{"class": "technical_bug"},
      summary="Between 02:00 and 10:00 UTC on Oct 9 the share of attempts that stalled was 0.6912, against 0.05 outside that window. The pattern points to the code not being delivered.",
      claims=[dict(text="About 0.6912 of attempts stalled at the OTP screen inside the window.", refs=[dict(type="signal", metric="drop_off", label="drop off 69% vs 5%"), dict(type="stat", id="stat:window", label="stalled share in window 0.6912")]),
              dict(text="Resend taps and exits followed.", refs=[dict(type="fact", id="fact:1", label="68% of them showed rage taps"), dict(type="session", id="s_p1_0412", label="session s_p1_0412")])],
      reasoning=["Exits at the OTP screen jump inside one time window.", "The jump is the same for every persona.", "That points away from user behavior."],
      rules=dict(rule="r_otp", rule_text="High exits with errors point to a UX problem", **{"class": "ux_friction"}, trusted=True, agreement="overruled",
                 overrule_reason="Errors cluster in one time window, which a UX rule cannot explain; the exit rate was 0.0884 against 0.05.", flagged=True),
      next_steps=[dict(kind="check", text="Check the SMS provider logs for Oct 9, 02:00 to 10:00 UTC.")], caveats=["Events alone cannot show why the code was not delivered."])
_diag("segment:confirm:send_money:individual_trader", status="cached", source="cached", source_note="Saved result from 2026-10-14, not a live call", confidence=0.79, **{"class": "ux_friction"},
      claims=[dict(text="Traders abandon Send money at confirm 55% of the time.", refs=[dict(type="fact", id="fact:0", label="55% end at confirm")])], reasoning=["Back taps and exits cluster at confirm for one product."],
      rules=dict(rule="r_confirm", rule_text="Back taps point to UX friction", **{"class": "ux_friction"}, trusted=True, agreement="agree", overrule_reason=None, flagged=False))
_diag("segment:personal:control", status="done", source="rules", confidence=None, **{"class": "ux_friction"}, claims=[], reasoning=[],
      summary="Rule ux_friction: a steady exit rate with repeated dropdown opens.", source_note="A fixed rule that passed the ground-truth test produced this class.",
      rules=dict(rule="r_dropdown", rule_text="Repeated opens point to UX friction", **{"class": "ux_friction"}, trusted=True, agreement="n/a", overrule_reason=None, flagged=False))
_diag("segment:tin:control", status="failed", source="unclassified", confidence=None, **{"class": "unclassified_needs_review"}, summary=None, claims=[], reasoning=[],
      source_note="No valid model output and no trusted rule, so nothing was generated.")
_diag("segment:product:sari_sari:eload", status="done", source="gemini", confidence=0.9, **{"class": "behavior_pattern"},
      summary="Retail buys e-load in about 70% of its transactions. This is an expected pattern, not a problem.", claims=[], reasoning=["The product share differs by group in a stable, healthy way."])
_diag("segment:topup:large_business", whole={"status": "done"})   # a partial object: the page must not break
_diag("segment:splash:unregistered", status="done", source="gemini", confidence=0.9, **{"class": "natural_exit"})

FAULTS = [
    dict(id="g1", sev="critical", kind="Tracker", title="Tracker not firing", desc="kyc_selfie stopped firing on app 4.12 from Oct 13, 18:00 (-94% against the 7-day average).",
         impact="Selfie step exits are unreliable, so they are held out of AI diagnosis until the tracker is fixed.", hours_ago=18, quarantine=True,
         link=dict(journey="register_login", step="selfie"), share=.6, cause="Selfie tracker silent on app 4.12",
         why="kyc_selfie fell 94% since Oct 13, so completed selfies may not be recorded at all."),
    dict(id="g2", sev="critical", kind="Database", title="Missing rows on one day", desc="The partition for 2026-10-11 is missing about 3.2% of rows.",
         impact="Numbers for Sun 11 are understated by about 3%.", hours_ago=84, quarantine=True, link=None, share=.3,
         metric=dict(title="Sun 11 exit spike", sub="Exit rhythm, all journeys", value="+31% frustrated exits", beh="Normal weekend pattern", behType="behavior",
                     behWhy="Weekend traffic is different from weekdays.",
                     rhythmNote="Sun 11 is also missing about 3.2% of rows (a data fault), so the real spike may be slightly larger."),
         cause="Missing rows on Oct 11", why="Sun 11 is understated; the true spike may be a little larger."),
    dict(id="g3", sev="warning", kind="Schema", title="Unmapped property", desc="Property otp_channel_v2 is not in the event mapping; about 1,240 events per hour (scaled to this dataset) land as unknown.",
         impact="OTP progress is under-counted by about 1.8 points.", hours_ago=30, quarantine=False, link=dict(journey="register_login", step="otp"), share=.18,
         cause="otp_channel_v2 is unmapped", why="Events land as unknown, so some SMS fallbacks are not counted as progress."),
    dict(id="g4", sev="resolved", kind="Tracker", title="Duplicate events", desc="checkout events double-fired on Android, Sep 22 to Sep 26. Fixed in app 4.11.2 and deduplicated.",
         impact="Counts for Sep 22 to 26 were corrected.", hours_ago=430, quarantine=False, link=dict(journey="transaction", step="confirm"), share=0,
         cause="Duplicate checkout events", why="Double-firing was fixed in app 4.11.2, so it is ruled out for these numbers."),
]
SESSIONS = [
    dict(id="x1", persona="unregistered", journey="register_login", who="Unregistered, Android", outcome="Exited after 98 s", good=False,
         bands=[[0, 12, "Phone number"], [12, 52, "OTP code"], [52, 60, "Phone number"], [60, 98, "OTP code"]],
         marks=[["tap", 5], ["tap", 11], ["idle", 14, 43], ["rage", 45, 49], ["back", 52], ["tap", 56], ["tap", 59], ["idle", 62, 90], ["rage", 91, 95], ["exit", 98]]),
    dict(id="x2", persona="individual_trader", journey="transaction", who="Individual trader, Send money", outcome="Exited after 88 s", good=False,
         bands=[[0, 18, "Choose amount"], [18, 33, "Confirm with PIN"], [33, 52, "Choose amount"], [52, 88, "Confirm with PIN"]],
         marks=[["tap", 6], ["tap", 16], ["tap", 34], ["back", 52], ["tap", 58], ["idle", 62, 84], ["exit", 88]]),
    dict(id="x3", persona="fraudster", journey="register_login", who="Fraudster, shared device", outcome="Exited after 12 s", good=False,
         bands=[[0, 12, "Phone number"]], marks=[["tap", 2], ["tap", 3], ["rage", 4, 7], ["exit", 12]]),
    dict(id="x4", persona="unregistered", journey="register_login", who="Unregistered, Android", outcome="Exited after 75 s", good=False,
         bands=[[0, 75, "Personal data, business type opened 4 times"]],
         marks=[["tap", 4], ["idle", 6, 30], ["tap", 32], ["tap", 34], ["tap", 36], ["idle", 38, 62], ["tap", 66], ["exit", 75]]),
    dict(id="x5", persona="sari_sari", journey="transaction", who="Retail, E-load", outcome="Completed in 36 s", good=True,
         bands=[[0, 6, "Home"], [6, 10, "Choose product"], [10, 18, "Choose amount"], [18, 24, "Confirm with PIN"], [24, 31, "Processing"], [31, 36, "Success"]],
         marks=[["tap", 3], ["tap", 8], ["tap", 13], ["tap", 17], ["tap", 22], ["done", 36]]),
]
HOTSPOT = dict(
    screen="OTP code", journey="register_login", step="otp",
    note="Users without a code tap the resend button and the empty code boxes while the countdown runs.",
    elements=[[0, 0, 100, 11, "bar", "< Verify your phone"], [14, 6, 62, 3, "line"], [19, 6, 48, 3, "line"], [28, 6, 15, 8, "box"], [28, 24, 15, 8, "box"],
              [28, 42, 15, 8, "box"], [28, 60, 15, 8, "box"], [28, 78, 15, 8, "box"], [42, 6, 60, 6, "btnLight", "Resend code in 00:29"], [66, 0, 100, 34, "keypad", "Keypad"]],
    spots=[[44.5, 34, 70, 640, "Disabled resend button"], [32, 50, 60, 410, "Empty code boxes, nothing to paste"], [5.5, 10, 36, 150, "Back arrow"]])
INTENTS = [
    dict(raw="otp_verify idle_ms=31000", intent="Waiting for a code that has not arrived", meta="App, sample", flagged=False),
    dict(raw="tap btn_no_tin", intent="Registering without a tax ID", meta="App, sample", flagged=False),
    dict(raw="tap see_price (unregistered)", intent="Checking prices before signing up", meta="App, sample", flagged=False),
    dict(raw="product=send_money back x2", intent="Unsure about the amount before confirming", meta="App, sample", flagged=False),
    dict(raw="evt_x91_unmapped", intent="Flagged for review", meta="App, sample", flagged=True),
]
AGENTS = [
    dict(tier="0", name="Telemetry Guardian", sub="Schema and volume checks: 2 faults, 65 sessions held out", status="warn"),
    dict(tier="1", name="The Watchdog", sub="5 deviations found, 3 natural patterns kept out of the feed", status="warn"),
    dict(tier="2", name="Diagnostic Agent", sub="Hypotheses saved for 4 of 5 findings (fixture text)", status="ok"),
]
ASK = [
    dict(id="a1", question="Why do sign-ups stall on Oct 9?", chip=False,
         keywords=["otp", "code", "oct", "stall", "sign", "register", "login", "october", "sms", "timestamp"],
         answer="Between 02:00 and 10:00 UTC on Oct 9 about 70% of register and login attempts stalled on the OTP screen (about 5% outside that window). Resend taps and exits followed. The pattern points to codes not being delivered.",
         refs=[dict(type="insight", id="temporal:otp:2026-10-09", label="OTP codes did not arrive")]),
    dict(id="a2", question="Which persona drops off before a transaction succeeds?", chip=False,
         keywords=["persona", "transaction", "succeed", "success", "send", "money", "trader", "confirm", "pin", "abandon", "drop"],
         answer="Individual traders abandon Send money at the PIN confirm step about 55% of the time, against about 5% for other personas.",
         refs=[dict(type="insight", id="segment:confirm:send_money:individual_trader", label="Individual traders abandon Send money")]),
    dict(id="a3", question="Who tops up large amounts?", chip=False, keywords=["top", "topup", "amount", "large", "business", "50000", "peso", "cash"],
         answer="Large businesses top up above PHP 50,000 in most top-ups; every other persona stays under PHP 5,000. It is a pattern, not a problem.",
         refs=[dict(type="insight", id="segment:topup:large_business", label="Large business top-ups")]),
    dict(id="a4", question="What do retail buy?", chip=False, keywords=["sari", "store", "buy", "product", "eload", "load", "transaction"],
         answer="About 70% of retail transactions are e-load. This is expected behavior for stores that resell load.",
         refs=[dict(type="insight", id="segment:product:sari_sari:eload", label="Retail buy e-load")]),
    dict(id="a5", question="Which screens lose the most users?", chip=False, keywords=["screen", "lose", "drop", "off", "most", "personal", "data", "tin", "page"],
         answer="Personal data loses about 18% of sessions and TIN number about 8%, steady across the whole window.",
         refs=[dict(type="view", id="journeys", label="Open Journeys")]),
    dict(id="a6", question="Are the fraudster accounts a UX problem?", chip=False, keywords=["fraud", "fraudster", "shared", "device", "burst", "failed", "attempt"],
         answer="Not classified. Fraudster accounts show bursts of failed logins and up to 5 users on one device. It needs a person to review the evidence.",
         refs=[dict(type="insight", id="segment:phone:fraudster", label="Fraudster bursts")]),
    dict(id="a11", question="Show the journey of the users who abandoned after payment", chip=True,
         keywords=["journey", "abandoned", "payment", "checkout", "transaction"],
         answer="In this synthetic fixture, 120 of 3,800 active sessions reached payment without success.", refs=[],
         viz=dict(type="sankey", title="After payment: where sessions go", subtitle="Synthetic fixture data · 7-day window · 3.2% of eligible active sessions.", unit="sessions",
                  source=dict(id="source", label="Payment reached, no success", value=120, share_of_active=.0316, sub="Synthetic fixture · 7-day active sessions"),
                  branches=[dict(id="error", label="Error loop", value=24, tone="negative", call="negative friction", note="Synthetic fixture: errors or resend loop"), dict(id="back", label="Returned to plans", value=36, tone="positive", call="comparing · positive", note="Synthetic fixture: returned to prices"), dict(id="quiet", label="Left quietly", value=60, tone="neutral", call="natural exit", note="Synthetic fixture: no error or return observed")],
                  ticket=dict(insight_id=None, title="Payment abandonment review", persona="All eligible users", hypothesis="Hypothesis: payment errors account for part of the observed abandonment; validate with provider logs.", evidence_json=dict(synthetic_fixture=True, cohort_sessions=120, branches=dict(error=24, returned=36, quiet=60), session_ids=["FIXTURE-session-0001", "FIXTURE-session-0002"])))),
    dict(id="a12", question="Where do people go after the OTP step fails?", chip=True, keywords=["otp", "code", "step", "fails", "exit"],
         answer="In this synthetic fixture, 88 sessions exited at OTP.", refs=[], viz=dict(type="sankey", title="After OTP: where sessions go", subtitle="Synthetic fixture data · 7-day window · eligible active-session denominator.", unit="sessions",
                  source=dict(id="source", label="OTP exits", value=88, share_of_active=.0232, sub="Synthetic fixture"), branches=[dict(id="error", label="Error or resend loop", value=48, tone="negative", call="negative friction", note="Synthetic fixture"), dict(id="back", label="Returned to phone", value=12, tone="positive", call="comparing · positive", note="Synthetic fixture"), dict(id="quiet", label="Left quietly", value=28, tone="neutral", call="natural exit", note="Synthetic fixture")],
                  ticket=dict(insight_id=None, title="OTP exit review", persona="All eligible users", hypothesis="Hypothesis: OTP delivery friction is contributing to exits; validate provider delivery.", evidence_json=dict(synthetic_fixture=True, cohort_sessions=88, session_ids=["FIXTURE-session-0003"])))),
    dict(id="a13", question="What happens to Retail buyers who leave before success?", chip=True, keywords=["retail", "buyers", "leave", "success", "sari", "sari_sari"],
         answer="In this synthetic fixture, 32 Retail transaction sessions left before success.", refs=[], viz=dict(type="sankey", title="Retail buyers before success", subtitle="Synthetic fixture data · 7-day window · eligible active-session denominator.", unit="sessions",
                  source=dict(id="source", label="Retail transactions, no success", value=32, share_of_active=.0084, sub="Synthetic fixture"), branches=[dict(id="quiet", label="Left quietly", value=32, tone="neutral", call="natural exit", note="Synthetic fixture; other branches unsupported")],
                  ticket=dict(insight_id=None, title="Retail transaction review", persona="Retail", hypothesis="Hypothesis: these exits may be ordinary comparison; inspect journeys before making changes.", evidence_json=dict(synthetic_fixture=True, cohort_sessions=32, session_ids=["FIXTURE-session-0004"])))),
]


def settings_journeys():
    out = []
    for jid, jname, steps in JOURNEYS:
        out.append(dict(id=jid, name=jname, steps=[
            dict(id=s[0], name=s[1], event=s[2], conf=MAPCONF.get(s[0], round(.9 + (zlib.crc32(s[0].encode()) % 9) / 100, 2)),
                 status="review" if MAPCONF.get(s[0], 1) < .8 else "matched") for s in steps]))
    return out


def main():
    views = {}
    for r in RANGES:
        for p in ["all"] + PID:
            views[view_key(r, p)] = build_view(r, p)
    data = {
        "meta": {"dataset": "fixture-v2 (synthetic, invented numbers, not measured)", "dataset_label": "Sample dataset (synthetic)", "synthetic": True, "schema": "ui-v2",
                 "generated_at": "2026-10-14T12:00:00Z", "as_of": AS_OF, "window": {"start": "2026-09-15", "end": "2026-10-14"}, "currency": "PHP",
                 "value_assumption": "Placeholder values per completed task (PHP 150 registration, PHP 200 remittance). Not measured.",
                 "counts": {"events": 412000, "sessions": 15600, "users": 1000, "sessions_quarantined": 65},
                 "platforms": ["app"], "model": "gemini-2.5-flash", "diagnosis_source": "cached", "diagnosis_status": "done"},
        "scope": {"personas": [dict(id=i, label=l, users=u) for i, l, u in PERSONAS], "products": [dict(id=i, label=l) for i, l in PRODUCTS],
                  "journeys": settings_journeys(), "ranges": ["24h", "7d", "30d"]},
        "guardian": {"status": "fail", "checks": [dict(check="volume_gap", status="fail"), dict(check="schema", status="warn")],
                     "faults": FAULTS, "quarantine_windows": [], "findings": []},
        "insights": INSIGHTS, "views": views, "stuck_sessions": SESSIONS, "hotspot": HOTSPOT, "intents": INTENTS, "agents": AGENTS, "ask": ASK,
    }
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print("wrote", OUT, OUT.stat().st_size, "bytes,", len(views), "views")


if __name__ == "__main__":
    main()
