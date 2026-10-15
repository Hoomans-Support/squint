"""Tests for /api/brief-ai without any network: BRIEF_AI_MOCK=1 answers from a canned output.

    .venv/Scripts/python app/tests/brief_ai_test.py

Covers: off by default (nothing is called), the status route, a mocked answer, the saved first answer, the cooldown and the hourly limit,
bad input, hidden groups and unknown findings, and that an answer with an invented number (or a link, or a wrong count) is thrown away.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ["ASK_DATA_DIR"] = tempfile.mkdtemp()
for k in ("BRIEF_AI_ENABLED", "BRIEF_AI_MOCK"):
    os.environ.pop(k, None)

import brief_ai  # noqa: E402
import server  # noqa: E402

fails = []


def chk(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (("  " + str(extra)) if (extra and not ok) else ""))
    if not ok:
        fails.append(name)


results = json.loads((HERE.parent / "static" / "results.json").read_text(encoding="utf-8"))
view = results["views"]["7d|all|all"]
ids = [i for i in view["insight_ids"] if next(x for x in results["insights"] if x["id"] == i)["severity"] != "healthy"
       and not all(p in ("fraudster", "unknown") for p in (next(x for x in results["insights"] if x["id"] == i).get("persona_ids") or ["x"]))][:3]
# The published results file no longer holds any finding about a hidden group (pipeline/strip_hidden.py), so take such a finding's id from the
# unstripped build when it is there (data/ is git-ignored), else use the id the wallet build always has. Either way the endpoint must answer 404.
_full = HERE.parent.parent / "data" / "synthetic" / "results_v2.json"
hidden_id = "segment:txn_checkout:persona=fraudster"
if _full.exists():
    hidden_id = next((i["id"] for i in json.loads(_full.read_text(encoding="utf-8"))["insights"] if (i.get("persona_ids") or []) and all(p in ("fraudster", "unknown") for p in i["persona_ids"])), hidden_id)
cl = server.app.test_client()
BODY = {"range": "7d", "platform": "all", "persona": "all", "ids": ids}


def post(body, **headers):
    return cl.post("/api/brief-ai", data=json.dumps(body), content_type="application/json", headers=headers)


# 1. off by default, with and without the mock flag unset
r = post(BODY); j = r.get_json()
chk("off by default: standard wording, reason off", r.status_code == 200 and j["source"] == "standard" and j["reason_code"] == "off", j)
chk("status says disabled by default", cl.get("/api/brief-ai/status").get_json() == {"enabled": False})
os.environ["BRIEF_AI_MOCK"] = "1"
chk("the mock flag alone does not switch it on", post(BODY).get_json()["reason_code"] == "off" and cl.get("/api/brief-ai/status").get_json()["enabled"] is False)

# 2. on + mock
os.environ["BRIEF_AI_ENABLED"] = "1"
chk("status says enabled when switched on", cl.get("/api/brief-ai/status").get_json()["enabled"] is True)
r = post(BODY, **{"X-Forwarded-For": "10.0.0.1"}); j = r.get_json()
chk("mock: a gemini-style answer", r.status_code == 200 and j["source"] == "gemini" and j["cached"] is False and j["notice"].startswith("Wording by Gemini"), j)
chk("mock: headline, sub, one line per driver (max 2), steps with owners", bool(j["headline"]) and bool(j["sub"]) and len(j["drivers"]) == min(2, len(ids)) and all(s["owner"] in brief_ai.OWNERS for s in j["steps"]), j)
r = post(BODY, **{"X-Forwarded-For": "10.0.0.2"}); j2 = r.get_json()
chk("the first answer is saved and served to the next visitor at no cost", j2["source"] == "gemini" and j2["cached"] is True, j2)

# 3. cooldown, then the hourly limit
r = post({**BODY, "again": True}, **{"X-Forwarded-For": "10.0.0.1"}); j = r.get_json()
chk("rewrite again right away is held back by the cooldown", j["source"] == "standard" and j["reason_code"] == "cooldown" and j["retry_in_s"] > 0, j)
key = "7d|all|all|" + ",".join(ids)
brief_ai._recent[("v", key)] = [time.time() - 3000 + n for n in range(brief_ai.LIVE_PER_HOUR)]
ok, retry, left = brief_ai.take_slot("v", key)
chk("after the hourly allowance a visitor gets no more live calls for that view", ok is False and retry == 0 and left == 0, (ok, retry, left))

# 4. bad input and unavailable views
chk("empty ids is a 400", post({**BODY, "ids": []}).status_code == 400)
chk("too many ids is a 400", post({**BODY, "ids": ["a", "b", "c", "d"]}).status_code == 400)
chk("duplicate ids is a 400", post({**BODY, "ids": [ids[0], ids[0]]}).status_code == 400)
chk("a non-string range is a 400", post({**BODY, "range": 7}).status_code == 400)
chk("an unknown range is a 404", post({**BODY, "range": "90d"}).status_code == 404)
chk("a hidden group is a 404", post({**BODY, "persona": "fraudster"}).status_code == 404)
chk("an unknown finding is a 404", post({**BODY, "ids": ["nope"]}).status_code == 404)
chk("a finding about a hidden group is a 404", post({**BODY, "ids": [hidden_id]}).status_code == 404)
chk("a finding from another view is a 404", post({**BODY, "persona": "unregistered", "ids": [i for i in ids if i not in results["views"]["7d|all|unregistered"]["insight_ids"]][:1] or ["x"]}).status_code == 404)
chk("GET is refused", cl.get("/api/brief-ai").status_code == 405)
chk("an oversized body is refused", cl.post("/api/brief-ai", data="x" * 3000, content_type="application/json").status_code in (400, 413))

# 4b. datasets: the request names the dataset and the facts come from that file
dres = json.loads((HERE.parent / "static" / "results_dining.json").read_text(encoding="utf-8"))
dv = dres["views"]["7d|all|all"]
dids = [i["id"] for i in dres["insights"] if i["id"] in dv["insight_ids"] and i["severity"] != "healthy" and i["id"] not in results["views"]["7d|all|all"]["insight_ids"]
        and not all(p in ("fraudster", "unknown") for p in (i.get("persona_ids") or ["x"]))][:2]
DBODY = {"range": "7d", "platform": "all", "persona": "all", "ids": dids, "dataset": "dining"}
r = post(DBODY); j = r.get_json()
chk("dining: a rewrite is answered from the dining file", r.status_code == 200 and j.get("source") == "gemini" and j.get("ids") == dids, j)
chk("dining: those findings are unknown to the wallet dataset", post({**DBODY, "dataset": "wallet"}).status_code == 404)
chk("an unknown dataset is a 400", post({**DBODY, "dataset": "nope"}).status_code == 400 and post({**DBODY, "dataset": ["dining"]}).status_code == 400)

# 5. verification: an invented number, a link, a wrong count, a bad owner
facts, used = brief_ai.brief_facts(results, "7d", "all", "all", ids)
allowed = brief_ai.ask.allowed_numbers(json.dumps(facts))
good = brief_ai._mock_out(facts)
chk("the canned answer verifies", brief_ai.verify(good, facts, allowed) is not None)
chk("an invented number throws the answer away", brief_ai.verify({**good, "headline": "Exactly 98765 people left."}, facts, allowed) is None)
chk("an invented number in a step throws the answer away", brief_ai.verify({**good, "steps": [{"owner": "Engineering", "text": "Fix 4242 errors."}]}, facts, allowed) is None)
chk("a link throws the answer away", brief_ai.verify({**good, "sub": "see http://x.y"}, facts, allowed) is None)
chk("too few drivers throws the answer away", brief_ai.verify({**good, "drivers": good["drivers"][:-1]}, facts, allowed) is None)
v_extra = brief_ai.verify({**good, "drivers": good["drivers"] + ["extra"]}, facts, allowed)
chk("an extra driver line is dropped, the wording of the others is untouched", v_extra is not None and v_extra["drivers"] == good["drivers"])
v_steps = brief_ai.verify({**good, "steps": good["steps"] + [{"owner": "Design", "text": "One step too many."}] * 4}, facts, allowed)
chk("extra steps are dropped beyond one per finding with saved steps", v_steps is not None and len(v_steps["steps"]) <= 3)
chk("a bad owner throws the answer away", brief_ai.verify({**good, "steps": [{"owner": "Marketing", "text": "Do a thing."}]}, facts, allowed) is None)
real = facts["findings"][0]
if real["estimated_value_php_per_week"]:
    money = f"PHP {real['estimated_value_php_per_week']:,} a week (estimated)"
    chk("a number that is in the facts is accepted", brief_ai.verify({**good, "headline": f"About {money} is at risk."}, facts, allowed) is not None)

print("FAILED:", fails)
sys.exit(1 if fails else 0)
