"""Tests for the shared limiter in app/ask_gemini.py (ip_limit), used by Ask, Fact-check and the Brief rewrite. No server, no Gemini.

  .venv/Scripts/python app/tests/limiter_test.py

Covers the all-visitors per-minute cap (ASK_GLOBAL_PER_MIN) that stops a visitor who forges X-Forwarded-For on the direct Cloud Run
address from looking like a new person on every request, and the bound on the in-memory visitor table.
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ["ASK_DATA_DIR"] = tempfile.mkdtemp(prefix="limiter-test-")
import ask_gemini as ag  # noqa: E402

fails = []


def chk(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


def reset():
    ag._hits.clear()
    ag._grate.clear()


# 1. a visitor is still limited on their own: 5 a minute
os.environ["ASK_GLOBAL_PER_MIN"] = "1000"
reset()
got = [ag.ip_limit("same", 5, 30) for _ in range(7)]
chk("one visitor gets 5 live calls a minute, then no more", got == [True] * 5 + [False] * 2, got)

# 2. every request looks like a new visitor (forged header): the all-visitors cap stops them at 10 a minute
os.environ["ASK_GLOBAL_PER_MIN"] = "10"
reset()
got = [ag.ip_limit(f"spoof{n}", 5, 30) for n in range(14)]
chk("14 requests from 14 different 'visitors' in one minute: only 10 get through", got == [True] * 10 + [False] * 4, got)
chk("the refused ones did not add visitor entries (a flood cannot grow the table)", len(ag._hits) == 10, len(ag._hits))

# 3. the minute rolls over
reset()
for n in range(10):
    ag.ip_limit(f"a{n}", 5, 30)
ag._grate.clear()
ag._grate.extend(t - 61 for t in [__import__("time").time()] * 10)       # pretend those ten calls were a minute ago
chk("after a minute the all-visitors window is open again", ag.ip_limit("fresh", 5, 30) is True)

# 4. cap 0 turns the all-visitors cap off (the limits of one visitor stay)
os.environ["ASK_GLOBAL_PER_MIN"] = "0"
reset()
got = [ag.ip_limit(f"v{n}", 5, 30) for n in range(25)]
chk("ASK_GLOBAL_PER_MIN=0 switches the all-visitors cap off", all(got), got)

# 5. the visitor table stays bounded even with the cap off
reset()
small = ag.HITS_MAX
ag.HITS_MAX = 200
try:
    for n in range(1000):
        ag.ip_limit(f"flood{n}", 5, 30)
    chk("a flood of 1,000 different visitors leaves at most 200 entries in memory", len(ag._hits) <= 200, len(ag._hits))
    chk("the newest visitors are the ones kept", "flood999" in ag._hits and "flood0" not in ag._hits)
finally:
    ag.HITS_MAX = small

# 6. a malformed setting falls back to the default
os.environ["ASK_GLOBAL_PER_MIN"] = "not a number"
reset()
got = [ag.ip_limit(f"x{n}", 5, 30) for n in range(12)]
chk("a bad ASK_GLOBAL_PER_MIN value falls back to 10 a minute", got == [True] * 10 + [False] * 2, got)

print(f"\nFAILED: {fails}" if fails else "\nALL PASSED")
sys.exit(1 if fails else 0)
