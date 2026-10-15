"""Checks the first-visit intro wired into the app (real Chrome via Playwright). Start the server first:
    .venv/Scripts/python app/server.py
Run:  .venv/Scripts/python app/tests/intro_test.py
Automated browsers skip the intro unless the URL has ?intro, so the click-through is unaffected; this file covers the intro itself."""
import sys
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8080/"
fails = []


def chk(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1280, "height": 800})
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto(URL); pg.wait_for_timeout(800)
    chk("automated browser skips the intro by default", pg.locator(".sx").count() == 0)
    chk("dashboard renders underneath", pg.locator("#view").inner_text().strip() != "")
    pg.goto(URL + "?intro"); pg.wait_for_timeout(500)
    chk("?intro shows the intro over the dashboard", pg.locator(".sx").count() == 1)
    chk("intro covers the page (topmost element is inside it)", pg.evaluate("!!document.elementFromPoint(640,400).closest('.sx')"))
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    chk("Esc closes it and the dashboard is usable", pg.locator(".sx").count() == 0 and pg.locator("#navlist a, #navlist button").first.is_visible())
    pg.goto(URL + "?intro"); pg.wait_for_timeout(300)
    pg.click(".sx-brand"); pg.wait_for_timeout(300)
    chk("clicking the Squint logo closes it", pg.locator(".sx").count() == 0)
    pg.goto(URL + "?intro"); pg.wait_for_timeout(300); pg.click(".sx-home"); pg.wait_for_timeout(300)
    chk("home icon closes it", pg.locator(".sx").count() == 0)
    pg.goto(URL + "?intro"); pg.wait_for_timeout(1500)
    chk("the card is there from the start with the Open button visible and focused", pg.evaluate("document.activeElement.className")=="sx-go" and pg.locator(".sx-go").is_visible())
    pg.click(".sx-go", force=True); pg.wait_for_timeout(300)  # the button bobs forever, so Playwright never sees it as stable
    chk("Open the dashboard closes it", pg.locator(".sx").count() == 0)
    chk("no page errors or CSP violations", not errs)
    if errs: print(errs[:5])
    ctx.close()
    ctx = b.new_context(viewport={"width": 390, "height": 800}); pg = ctx.new_page()
    pg.goto(URL + "?intro"); pg.wait_for_timeout(500)
    chk("phone: no sideways scroll with intro open", pg.evaluate("document.documentElement.scrollWidth<=innerWidth"))
    ctx.close(); b.close()
print("FAILED:", fails)
sys.exit(1 if fails else 0)
