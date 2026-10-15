"""Tests for /api/factcheck without any network: FACTCHECK_MOCK=1 answers from canned outputs.

    .venv/Scripts/python app/tests/factcheck_test.py

Covers: the code-check fallback (switched off), a mocked Gemini answer, the saved first answer, the cooldown and the per-finding limit,
unknown and hidden findings, bad input, and that a note with an invented number is blanked.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ["ASK_DATA_DIR"] = tempfile.mkdtemp()

import factcheck  # noqa: E402
import server  # noqa: E402

fails = []


def chk(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (("  " + str(extra)) if (extra and not ok) else ""))
    if not ok:
        fails.append(name)


results = json.loads((HERE.parent / "static" / "results.json").read_text(encoding="utf-8"))
vis = next(i for i in results["insights"] if (i.get("diagnosis") or {}).get("claims") and not all(p in ("fraudster", "unknown") for p in (i.get("persona_ids") or ["x"])))
# The published results file no longer holds any finding about a hidden group (pipeline/strip_hidden.py), so take such a finding's id from the
# unstripped build when it is there (data/ is git-ignored), else use the id the wallet build always has. Either way the endpoint must answer 404.
_full = HERE.parent.parent / "data" / "synthetic" / "results_v2.json"
hidden_id = "segment:txn_checkout:persona=fraudster"
if _full.exists():
    hidden_id = next((i["id"] for i in json.loads(_full.read_text(encoding="utf-8"))["insights"] if (i.get("persona_ids") or []) and all(p in ("fraudster", "unknown") for p in i["persona_ids"])), hidden_id)
cl = server.app.test_client()


def post(body, **headers):
    return cl.post("/api/factcheck", data=json.dumps(body), content_type="application/json", headers=headers)


# 1. switched off: plain code check
os.environ["FACTCHECK_ENABLED"] = "0"
r = post({"id": vis["id"]}); j = r.get_json()
chk("off: answers with a code check", r.status_code == 200 and j["source"] == "code" and j["reason_code"] == "off" and len(j["claims"]) == len(vis["diagnosis"]["claims"]), j)
chk("code check marks lines it can verify", any(c["verdict"] in ("supported", "partly") for c in j["claims"]), j["claims"])

# 2. on + mock
os.environ["FACTCHECK_ENABLED"] = "1"; os.environ["FACTCHECK_MOCK"] = "1"
r = post({"id": vis["id"]}, **{"X-Forwarded-For": "10.0.0.1"}); j = r.get_json()
chk("mock: a gemini-style answer", r.status_code == 200 and j["source"] == "gemini" and j["cached"] is False and j["notice"].startswith("AI can make mistakes"), j)
chk("mock: every claim has a verdict", all(c["verdict"] in ("supported", "partly", "not_supported", "cannot_check") for c in j["claims"]))
r = post({"id": vis["id"]}, **{"X-Forwarded-For": "10.0.0.2"}); j2 = r.get_json()
chk("the first answer is saved and served to the next visitor at no cost", j2["source"] == "gemini" and j2["cached"] is True, j2)

# 3. cooldown, then the limit
r = post({"id": vis["id"], "again": True}, **{"X-Forwarded-For": "10.0.0.1"}); j = r.get_json()
chk("check again right away is held back by the cooldown", j["source"] == "code" and j["reason_code"] == "cooldown" and j["retry_in_s"] > 0, j)
factcheck._recent.clear()
for n in range(factcheck.AGAIN_PER_HOUR + 1):
    factcheck._recent.setdefault(("v", vis["id"]), []).append(0)    # pretend the hour's calls were used long ago... but within the hour
import time
factcheck._recent[("v", vis["id"])] = [time.time() - 3000 + n for n in range(factcheck.AGAIN_PER_HOUR + 1)]
ok, retry, left = factcheck.take_finding_slot("v", vis["id"], True)
chk("after the hourly allowance a visitor gets no more live checks for that finding", ok is False and retry == 0 and left == 0, (ok, retry, left))

# 4. bad input
chk("unknown finding is a 404", post({"id": "nope"}).status_code == 404)
chk("a finding about a hidden group is a 404", post({"id": hidden_id}).status_code == 404)
chk("missing id is a 400", post({}).status_code == 400)
chk("GET is refused", cl.get("/api/factcheck").status_code == 405)
chk("an oversized body is refused", cl.post("/api/factcheck", data="x" * 2000, content_type="application/json").status_code in (400, 413))

# 4b. datasets: the request names the dataset and each one is grounded on its own file
dres = json.loads((HERE.parent / "static" / "results_dining.json").read_text(encoding="utf-8"))
wallet_ids = {i["id"] for i in results["insights"]}
dvis = next(i for i in dres["insights"] if i["id"] not in wallet_ids and (i.get("diagnosis") or {}).get("claims")
            and not all(p in ("fraudster", "unknown") for p in (i.get("persona_ids") or ["x"])))
os.environ["FACTCHECK_ENABLED"] = "0"
r = post({"id": dvis["id"], "dataset": "dining"}); j = r.get_json()
chk("dining: a dining finding is answered when the dataset is dining", r.status_code == 200 and len(j["claims"]) == len(dvis["diagnosis"]["claims"]), j)
chk("dining: that finding is unknown to the wallet dataset", post({"id": dvis["id"]}).status_code == 404 and post({"id": dvis["id"], "dataset": "wallet"}).status_code == 404)
chk("an unknown dataset is a 400", post({"id": vis["id"], "dataset": "nope"}).status_code == 400 and post({"id": vis["id"], "dataset": 5}).status_code == 400)
chk("a path is not a dataset", post({"id": vis["id"], "dataset": "../results"}).status_code == 400)

# 5. an invented number in a note is blanked
facts, claims = factcheck.finding_facts(results, vis["id"])
allowed = factcheck.ask.allowed_numbers(json.dumps(facts))
rows, missed = factcheck.verify({"claims": [{"index": n, "verdict": "supported", "number": "98765", "note": "Exactly 98765 sessions."} for n in range(len(claims))], "missed": ["Also 4242 happened."]}, claims, allowed)
chk("an invented number is blanked, not shown", rows is not None and all(r["note"] == "" and r["number"] == "" for r in rows) and missed == [], (rows, missed))
chk("a link in the answer makes it unusable", factcheck.verify({"claims": [{"index": n, "verdict": "supported", "number": "", "note": "see http://x.y"} for n in range(len(claims))], "missed": []}, claims, allowed)[0] is None)
chk("a missing claim makes it unusable", factcheck.verify({"claims": [], "missed": []}, claims, allowed)[0] is None)

print("FAILED:", fails)
sys.exit(1 if fails else 0)
