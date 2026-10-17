"""Smoke check for the redesigned Squint routes at desktop, tablet and mobile widths.

Start the app with .venv/Scripts/python app/server.py, then run:
    .venv/Scripts/python app/tests/squint_smoke.py
Screenshots are written under data/squint_shots/ (git-ignored).
"""
import re
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8080/"
ORIGIN = urlparse(URL)
ROUTES = ("Main", "FlowPrototype", "Audiences", "Ask", "Brief", "DataSources",
          "ProblemDetail", "SessionPlayer", "AskFlow2", "AskFlow5")
WIDTHS = (1440, 1280, 390)
OUT = Path(__file__).resolve().parents[2] / "data" / "squint_shots"
OUT.mkdir(parents=True, exist_ok=True)
ALLOWED_HOSTS = {"fonts.googleapis.com", "fonts.gstatic.com"}
BAD_TEXT = re.compile(r"\b(?:null|undefined|NaN)\b|\[missing ")
results = []


def check(name, passed, detail=""):
    results.append(bool(passed))
    print(("PASS  " if passed else "FAIL  ") + name + (f" [{detail}]" if detail else ""))


def inspect(page, label, route, errors, external):
    page.wait_for_load_state("networkidle", timeout=15000)
    active = page.evaluate("""(route) => !!window.SQ.classes[route] && document.title.endsWith(window.SQ.titles[route] || route)""", route)
    check(label + " opens the requested route", active)
    text = page.locator("body").inner_text()
    bad = BAD_TEXT.findall(text)
    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    check(label + " has no console or page errors", not errors, "; ".join(errors[:2]))
    check(label + " has no unexpected external requests", not external, "; ".join(external[:2]))
    check(label + " has no null, undefined, NaN or missing component text", not bad, ", ".join(bad))
    check(label + " has no horizontal page scroll", not overflow,
          f"scrollWidth={page.evaluate('document.documentElement.scrollWidth')}, viewport={page.viewport_size['width']}" if overflow else "")


def watch(page):
    errors, external = [], []
    page.on("console", lambda msg: errors.append("console: " + msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda err: errors.append("page: " + str(err)))
    def check_request(req):
        target = urlparse(req.url)
        if (target.scheme, target.netloc) != (ORIGIN.scheme, ORIGIN.netloc) and target.hostname not in ALLOWED_HOSTS:
            external.append(req.url)
    page.on("request", check_request)
    return errors, external


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for width in WIDTHS:
            for route in ROUTES:
                page = browser.new_page(viewport={"width": width, "height": 1000 if width > 500 else 844})
                errors, external = watch(page)
                page.goto(URL + "#" + route, wait_until="domcontentloaded")
                page.locator("#app").wait_for()
                inspect(page, f"{route} @ {width}px", route, errors, external)
                if route == "Audiences" and width == 1440:
                    page.get_by_role("button", name="Copy audience summary").click()
                    page.wait_for_function("() => document.body.innerText.includes('No person IDs are available') || document.body.innerText.includes('Copy is unavailable here')")
                    check("audience copy explains counts only", "person IDs" in page.locator("body").inner_text() or "counts only" in page.locator("body").inner_text())
                    check("audience copy has no page errors", not errors, "; ".join(errors[:2]))
                if route == "DataSources" and width == 1440:
                    # The note and refocus land after a microtask plus setTimeout(0) re-render,
                    # so give each click a beat before reading document.activeElement.
                    page.get_by_role("button", name="Connect database").click()
                    page.wait_for_timeout(100)
                    check("database connect stays disabled", "Ping us to unlock" in page.locator("body").inner_text() and page.evaluate("document.activeElement.dataset.fk") == "connect-db")
                    snowflake = page.get_by_label("Snowflake")
                    check("Snowflake stays locked", snowflake.is_visible() and not snowflake.is_enabled() and "Ping us to unlock" in page.locator("body").inner_text())
                    check("Upload is not offered", page.get_by_role("button", name="Upload").count() == 0)
                    check("local data-source actions have no page errors", not errors, "; ".join(errors[:2]))
                page.screenshot(path=str(OUT / f"{route.lower()}-{width}.png"), full_page=True)
                page.close()

        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, external = watch(page)
        page.goto(URL + "#Main", wait_until="networkidle")
        for value in ("30d", "24h", "7d"):
            page.locator('[data-fk="menu-range"]').click()
            page.locator(f'[data-fk="opt-{value}"]').click()
            page.wait_for_timeout(100)
            expected = {"30d": "Last 30 days", "24h": "Last 24 hours", "7d": "Last 7 days"}[value]
            check("scope range selects " + value, expected in page.locator('[data-fk="menu-range"]').inner_text())
        page.locator('[data-fk="menu-user"]').click()
        group = page.locator('input[data-fk^="opt-"]:not([data-fk="opt-all"])').first
        check("scope menu offers a user group", group.count() > 0)
        if group.count():
            # Selecting a group applies it and closes the menu immediately (no Cancel/Apply
            # footer, unlike the prototype), so the checkbox is gone right after the click:
            # click it rather than check() it, and read the result off the closed menu button.
            group.click(force=True, timeout=5000)
            page.wait_for_timeout(150)
            check("scope menu selects a user group", "All users" not in page.locator('[data-fk="menu-user"]').inner_text())
        inspect(page, "Main after scope changes @ 1440px", "Main", errors, external)
        page.screenshot(path=str(OUT / "main-scoped-1440.png"), full_page=True)
        browser.close()

    failed = len(results) - sum(results)
    print(f"\n{'PASS' if failed == 0 else 'FAIL'}  {sum(results)}/{len(results)} checks; screenshots: {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
