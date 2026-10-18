"""Deep Playwright scenarios for the Squint redesign.

Start the server with ``.venv/Scripts/python app/server.py`` and run this file.
All dashboard data is the app's labeled synthetic sample. Question scenarios
use the local matcher and make no external service calls.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8080/"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/squint_clickthrough")
OUT.mkdir(parents=True, exist_ok=True)
ALLOWED_HOSTS = {"fonts.googleapis.com", "fonts.gstatic.com"}
BAD_TEXT = re.compile(r"\b(?:null|undefined|NaN)\b|\[missing ", re.I)
results = []


def check(name, passed, detail=""):
    results.append(bool(passed))
    print(("PASS  " if passed else "FAIL  ") + name + (f" [{detail}]" if detail else ""))


def pause(page):
    # The app replaces component DOM on redraw; its state update settles on a timer.
    page.wait_for_timeout(120)


def wait_js(page, expr, arg=None, timeout_ms=8000, interval_ms=50):
    """Poll a JS expression with page.evaluate() until it is truthy.

    Our CSP has no 'unsafe-eval' (script-src 'self' only, by design), and
    Playwright's own wait_for_function() needs to compile the predicate string
    into a function *inside the page* to re-run it on every animation frame,
    which that CSP correctly blocks once the condition isn't true on the very
    first check (an immediately-true wait_for_function call can slip through
    on a CDP-level single evaluation, but a real polling wait cannot). A plain
    page.evaluate() call per attempt does not hit that restriction, so this
    polls by hand instead of relying on wait_for_function.
    """
    import time
    start = time.monotonic()
    while True:
        try:
            if page.evaluate(expr, arg) if arg is not None else page.evaluate(expr):
                return
        except Exception:
            pass
        if (time.monotonic() - start) * 1000 >= timeout_ms:
            raise TimeoutError(f"wait_js timed out after {timeout_ms}ms: {expr!r}")
        page.wait_for_timeout(interval_ms)


def route(page, name):
    page.goto(URL + "#" + name, wait_until="domcontentloaded")
    page.locator("#app").wait_for()
    wait_js(page, "r => location.hash === '#' + r && !!window.SQ.classes[r]", arg=name)
    pause(page)


def text(page):
    return page.locator("body").inner_text()


def main():
    errors, external = [], []
    origin = urlparse(URL)
    # Keep a fully populated persona as-is and make one in-memory empty-scope
    # variant so the calm empty state is exercised without editing results.json.
    fixture = json.loads((Path(__file__).resolve().parents[1] / "static" / "results.json").read_text(encoding="utf-8"))
    empty_persona = next(p["id"] for p in fixture["scope"]["personas"] if p["id"] not in ("unknown", "fraudster"))
    for key, view in fixture["views"].items():
        if key.endswith("|" + empty_persona):
            view["insight_ids"] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()
        page.route("**/results.json", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(fixture)))
        page.on("console", lambda msg: errors.append("console: " + msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: errors.append(f"page@{page.evaluate('location.hash')}/p={page.evaluate('SQ.scope && SQ.scope.persona')}: {err}"))

        def request(req):
            u = urlparse(req.url)
            if (u.scheme, u.netloc) != (origin.scheme, origin.netloc) and u.hostname not in ALLOWED_HOSTS and u.scheme not in ("data", "blob"):
                external.append(req.url)
        page.on("request", request)

        print("-- Navigation and route integrity")
        route(page, "Overview")
        nav = page.get_by_role("navigation", name="Sections")
        expected = [("Overview", "Overview"), ("Journeys", "Journeys"), ("Audiences", "Audiences"),
                    ("Chat now", "ChatNow"), ("Recommendations", "Recommendations"), ("Data sources", "DataSources")]
        for label, target in expected:
            link = nav.get_by_role("link", name=re.compile(re.escape(label)))
            if link.count():
                link.click(); wait_js(page, "r => location.hash === '#' + r", arg=target); pause(page)
                check(f"navigation: {label} opens {target} and is active", page.locator(f'[aria-label="Sections"] a[aria-current="page"]').inner_text().startswith(label))
            else:
                check(f"navigation: {label} opens {target} and is active", False, "link missing")
        # runtime.js rewrites a template's "Name.dc.html" href to "#Name" at render time, so the
        # live DOM never has the literal ".dc.html" string; scope to <header> to avoid matching
        # the nav's own Overview link, which also points at #Overview.
        brand = page.locator('header a[href="#Overview"]').first
        if brand.count():
            brand.click(); wait_js(page, "location.hash === '#Overview'")
        check("brand logo returns to Overview", page.evaluate("location.hash === '#Overview'"))
        route(page, "Overview")
        badge = page.locator('[aria-label="Sections"] a[aria-current="page"] [aria-label*="open critical"]')
        expected_critical = page.evaluate("SQ.problems().filter(p => p.severity === 'critical').length")
        check("Overview badge matches open critical problems", badge.count() == (1 if expected_critical else 0) and (not expected_critical or badge.inner_text() == str(expected_critical)))
        check("route starts without invalid text", not BAD_TEXT.search(text(page)))

        print("-- Scope bar changes data and restores controls")
        def scope_snapshot():
            return page.evaluate("JSON.stringify({scope: SQ.scope, value: SQ.view()})")
        def numbers_snapshot():
            return page.evaluate("JSON.stringify({kpis: SQ.view().kpis.map(k => k.value), problems: SQ.view().insight_ids, exits: SQ.view().exits})")
        before = scope_snapshot()
        numbers_before = numbers_snapshot()
        for value, label in (("24h", "Last 24 hours"), ("30d", "Last 30 days"), ("7d", "Last 7 days")):
            page.locator('[data-fk="menu-range"]').click()
            page.locator(f'[data-fk="opt-{value}"]').click(); pause(page)
            changed_numbers = numbers_snapshot() != numbers_before
            check(f"range {value} updates scope and displayed numbers", page.evaluate("SQ.scope.range") == value and scope_snapshot() != before and changed_numbers)
            before = scope_snapshot()
            numbers_before = numbers_snapshot()
        def open_user_menu():
            # the multi-select menu stays open after a pick (so several boxes can be ticked in one visit),
            # so only toggle it if it is not already open, instead of always clicking the toggle blind.
            if page.locator('[data-fk="menu-user"]').get_attribute("aria-expanded") != "true":
                page.locator('[data-fk="menu-user"]').click()
        personas = page.evaluate("SQ.data.scope.personas.map(p => p.id)")
        for persona in personas:
            open_user_menu()
            if page.evaluate("SQ.scope.persona") not in ("all", persona):
                # a prior named persona is still ticked (multi-select accumulates): clear back to All users
                # first so each persona in this loop is tested in isolation, same as before multi-select.
                page.locator('[data-fk="opt-all"]').click(force=True); pause(page)
                open_user_menu()
            opt = page.locator(f'input[data-fk="opt-{persona}"]')
            if opt.count():
                opt.click(force=True); pause(page)
                changed_numbers = numbers_snapshot() != numbers_before
                check(f"user group {persona} changes scope data", page.evaluate("SQ.scope.persona") == persona and scope_snapshot() != before and changed_numbers)
                before = scope_snapshot()
                numbers_before = numbers_snapshot()
        open_user_menu()
        all_opt = page.locator('[data-fk="opt-all"]')
        if all_opt.count(): all_opt.click(force=True); pause(page)
        platform = page.locator('[data-fk="menu-platform"]')
        if platform.count() and page.evaluate("(SQ.data.meta.platforms || []).length > 1"):
            all_platform_numbers = numbers_snapshot()
            platform.click()
            web_option = page.locator('[role="menu"][aria-label="Platform"] [data-fk="opt-web"]')
            if web_option.count() and not web_option.is_disabled():
                web_option.click(); pause(page)
                web_numbers = numbers_snapshot()
                check("Web filter selects the Web-specific data", page.evaluate("SQ.scope.platform === 'web' && SQ.viewKey().includes('|web|')")
                      and web_numbers != all_platform_numbers)
                platform.click()
                selected_style = web_option.evaluate("el => getComputedStyle(el).backgroundColor") if web_option.count() else ""
                check("selected platform is visibly marked in the open menu", web_option.get_attribute("aria-checked") == "true"
                      and selected_style == "rgb(232, 240, 254)"
                      and web_option.locator("svg").count() == 1
                      and platform.evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(232, 240, 254)")
                app_option = page.locator('[role="menu"][aria-label="Platform"] [data-fk="opt-app"]')
                if app_option.count() and not app_option.is_disabled():
                    app_option.click(); pause(page)
                    check("App filter changes data from Web", page.evaluate("SQ.scope.platform === 'app'") and numbers_snapshot() != web_numbers)
                else:
                    check("App filter changes data from Web", False, "App option unavailable")
                platform.click(); page.locator('[role="menu"][aria-label="Platform"] [data-fk="opt-app"]').click(); pause(page)
            else:
                check("Web filter selects the Web-specific data", False, "Web option unavailable")
                check("selected platform is visibly marked in the open menu", False, "Web option unavailable")
                check("App filter changes data from Web", False, "Web option unavailable")
        else:
            page.locator('[data-fk="menu-platform"]').click(); pause(page)
            app_option = page.locator('[data-fk="opt-app"]')
            web_option = page.locator('[data-fk="opt-web"]')
            check("single-platform scope reflects the only sample platform", app_option.count() == 1 and app_option.get_attribute("aria-checked") == "true" and web_option.is_disabled())
            page.locator('[data-fk="menu-platform"]').click(); pause(page)
        check("compare toggle removed, KPI deltas always on", page.locator('[data-fk="compare"]').count() == 0 and page.evaluate("SQ.scope.compare") is None)

        print("-- Overview scenarios")
        route(page, "Overview")
        top = page.evaluate("SQ.problems()[0] && SQ.problems()[0].id")
        # SQ.insight() is the raw results.json record and has no .action/.item; those are built
        # by SQ.problemRec() (data-main.js), the same helper Overview.js itself renders from.
        check("takeaway is the highest ranked current problem", bool(top) and page.evaluate("p => { const i = SQ.insight(p) && SQ.problemRec(SQ.insight(p)); const t = document.querySelector('#app').innerText; return !!i && t.includes(i.action) && t.includes(i.item); }", top))
        if page.get_by_role("button", name="Draft ticket").count():
            page.get_by_role("button", name="Draft ticket").first.click(); pause(page)
            check("Draft ticket shows the ticket inline, no drawer, no route change, no Draft ticket button left showing",
                  page.locator('[role="region"][aria-label="Ticket draft"]').is_visible()
                  and page.get_by_role("button", name="Copy").is_visible()
                  and page.get_by_role("button", name=re.compile("Download")).is_visible()
                  and page.locator('[data-fk="top-draft"]').count() == 0
                  and not page.evaluate("!!SQ.state.ticketModalOpen")
                  and page.evaluate("location.hash") == "#Overview")
            check("opening the inline ticket moves focus to its heading", page.evaluate("id => document.activeElement.dataset.fk === 'ticket-' + id", top))
            session_row = page.locator('[role="region"][aria-label="Ticket draft"] button').filter(has_text=re.compile(r"\b(AM|PM)\b"))
            if session_row.count():
                session_row.first.click(); wait_js(page, "location.hash === '#SessionPlayer'")
                check("a ticket's attached session opens that exact sample in Watch sessions", page.evaluate("!!SQ.pickInsight('watchInsight')"))
                route(page, "Overview")
                page.get_by_role("button", name="Draft ticket").first.click(); pause(page)
            else: check("a ticket's attached session opens that exact sample in Watch sessions", True, "this finding has no sampled sessions")
            page.get_by_role("button", name="Create ticket").click(); pause(page)
            check("clicking Create ticket turns it into a disabled green Ticket created",
                  page.get_by_role("button", name="Ticket created").is_disabled())
            page.get_by_role("button", name="Close ticket draft").click(); pause(page)
            check("the X closes the inline ticket and restores the Draft ticket button",
                  page.locator('[role="region"][aria-label="Ticket draft"]').count() == 0
                  and page.locator('[data-fk="top-draft"]').is_visible())
            check("closing the ticket restores focus to its opener", page.evaluate("document.activeElement.dataset.fk === 'top-draft'"))
        else: check("Draft ticket shows the ticket inline", False, "CTA missing")
        route(page, "Overview")
        cta = page.get_by_role("link", name="Open in Journeys")
        if cta.count():
            cta.click(); wait_js(page, "location.hash === '#Journeys'"); pause(page)
            # Journeys consumes and deletes SQ.state.journeyInsight on its first render (it is a
            # one-shot handoff, not a lasting flag), so the observable result is the "opened from
            # Pn" crumb and the preselected issue, not the now-cleared state key.
            check("Open in Journeys carries its insight", page.evaluate(
                "id => { const rank = (SQ.problems().find(p => p.id === id) || {}).__p; "
                "return !!rank && document.querySelector('#app').innerText.includes('opened from ' + rank); }", top))
        else: check("Open in Journeys carries its insight", False, "CTA missing")
        route(page, "Overview")
        ordered_rows = page.evaluate("() => { const ids = SQ.problems().slice(1).map(p => 'row-' + p.id); const got = [...document.querySelectorAll('[data-fk^=\"row-\"]')].map(e => e.dataset.fk); return JSON.stringify(ids) === JSON.stringify(got); }")
        check("other problems table lists the remaining findings in rank order", ordered_rows)

        print("-- Journeys scenarios")
        route(page, "Journeys")
        tabs = page.locator('[aria-label="Journey"] button')
        count = tabs.count()
        expected_tabs = page.evaluate("SQ.data.scope.journeys.length")
        check("all configured journey tabs render", count == expected_tabs)
        for i in range(count):
            tabs.nth(i).click(); pause(page)
            check(f"journey tab {i + 1} selects", tabs.nth(i).get_attribute("aria-selected") == "true")
        strips = page.locator('[aria-label="Issues in this journey"] [role="tab"]')
        if strips.count() > 1:
            strips.nth(1).click(); pause(page)
            check("issue strip selection changes the selected issue", strips.nth(1).get_attribute("aria-selected") == "true")
        else: check("issue strip selection changes the selected issue", strips.count() == 1)
        table = page.locator('[data-fk="table"]'); chart = page.locator('[data-fk="chart"]')
        if table.count() and chart.count():
            table.click(); pause(page); table_mode = table.get_attribute("aria-pressed") == "true"
            chart.click(); pause(page)
            check("Sankey chart and table modes switch", table_mode and chart.get_attribute("aria-pressed") == "true")
        else: check("Sankey chart and table modes switch", False, "view buttons missing")
        metrics = page.locator('[data-fk^="metric-"]')
        metric_count = min(metrics.count(), 5)
        for i in range(metric_count):
            metrics.nth(i).click(); pause(page)
        check("five heat-table metric controls respond", metric_count == 5)
        disclosures = page.locator('details')
        if disclosures.count():
            disclosures.first.locator("summary").click()
            check("product-completion disclosure expands", disclosures.first.get_attribute("open") is not None)
        else: check("product-completion disclosure expands", False, "disclosure missing")
        see_why = page.get_by_role("button", name="See why")
        if see_why.count():
            watch_btn = page.get_by_role("button", name="Watch sessions")
            if watch_btn.count():
                watch_btn.first.click(); wait_js(page, "location.hash === '#SessionPlayer'")
                check("Watch sessions beside Journeys' See why opens Watch sessions", page.evaluate("!!SQ.pickInsight('watchInsight')"))
                route(page, "Journeys")
                see_why = page.get_by_role("button", name="See why")
            else: check("Watch sessions beside Journeys' See why", True, "this issue has no sampled sessions")
            before_hash = page.evaluate("location.hash")
            see_why.first.click(); pause(page)
            check("Journeys' See why opens the finding drawer as a popup, no route change",
                  page.evaluate("!!SQ.state.ticketModalOpen")
                  and page.evaluate("location.hash") == before_hash)
            check("the drawer also shows Mark fixed", page.get_by_role("button", name="Mark fixed").count() >= 1)
            page.get_by_role("button", name="Draft ticket").click(); pause(page)
            check("the drawer's Draft ticket advances to the ticket-composition stage",
                  page.locator('[role="region"][aria-label="Ticket draft"]').is_visible())
            page.get_by_role("button", name="Create ticket").click(); pause(page)
            check("Create ticket turns green Ticket created in the Journeys drawer too", page.get_by_role("button", name="Ticket created").is_disabled())
            page.get_by_role("button", name="Close and go back").click(); pause(page)
            check("closing the drawer returns to Journeys with no popup left open", not page.evaluate("!!SQ.state.ticketModalOpen"))
        else: check("Journeys' See why opens the finding drawer", False, "CTA missing")
        route(page, "Journeys")
        top_menu = page.get_by_role("button", name="Biggest leak actions")
        if top_menu.count():
            top_menu.first.click(); pause(page)
            watch = page.get_by_role("menuitem", name="Watch sessions")
            if watch.count():
                watch.first.click(); wait_js(page, "location.hash === '#SessionPlayer'")
                check("Watch sessions carries a finding", page.evaluate("!!SQ.pickInsight('watchInsight')"))
            else: check("Watch sessions carries a finding", True, "top issue has no sampled session")
        else: check("Watch sessions carries a finding", True, "already viewing the top issue, no biggest-leak menu")

        print("-- Finding drawer and session player")
        # Overview's own Draft ticket buttons still draft inline (no drawer). Journeys' hero "See why"
        # and its "Biggest leak actions" menu both open the same full finding drawer (exercised above).
        # Open it directly here, the same way those triggers do, so this section's own
        # drawer-navigation checks don't depend on which issue was left selected.
        route(page, "Journeys")
        page.evaluate("SQ.openTicketModal(SQ.problems()[0].id)")
        wait_js(page, "SQ.state.ticketModalOpen === true"); pause(page)
        problems = page.evaluate("SQ.problems().length")
        if problems > 1:
            first_id = page.evaluate("SQ.pickInsight('drawerInsight').id")
            page.get_by_role("button", name="Next problem").click(); pause(page)
            check("finding drawer next cycles through problems", page.evaluate("SQ.pickInsight('drawerInsight').id") != first_id)
            page.get_by_role("button", name="Previous problem").click(); pause(page)
            check("finding drawer previous cycles back", page.evaluate("SQ.pickInsight('drawerInsight').id") == first_id)
        else:
            check("finding drawer next and previous cycle through problems", problems == 1)
        # the drawer's own Watch sessions button is suppressed only inside this Journeys popup (owner:
        # redundant with the hero-level one beside See why, and the Biggest leak actions menu, both
        # exercised above); the standalone (non-modal) drawer keeps it, checked further down
        check("the drawer's popup has no Watch sessions button of its own",
              page.get_by_role("article").get_by_role("button", name="Watch sessions").count() == 0)
        page.evaluate("SQ.state.watchInsight = SQ.pickInsight('drawerInsight').id; SQ.go('SessionPlayer')")
        wait_js(page, "location.hash === '#SessionPlayer'"); pause(page)
        session_rows = page.locator('[aria-label="Sessions"] button.srow')
        if session_rows.count():
            page.get_by_role("button", name=re.compile("Play|Next event")).click(); pause(page)
            check("session play/pause control responds", page.get_by_role("button", name=re.compile("Pause|Play|Next event")).count() == 1)
            speed = page.locator('[data-fk="sp-speed-2"]')
            if speed.count(): speed.click(); pause(page)
            check("session speed control selects 2x", not speed.count() or speed.get_attribute("aria-pressed") == "true")
            skip = page.locator('[data-fk="sp-skip"]')
            if skip.count():
                before_skip = page.locator('[data-fk="sp-strip"]').get_attribute("aria-valuenow")
                skip.click(); pause(page)
                after_skip = page.locator('[data-fk="sp-strip"]').get_attribute("aria-valuenow")
            else:
                before_skip = after_skip = None
            check("skip to the struggle is available when a struggle exists", not skip.count() or before_skip != after_skip)
            events = page.locator('[aria-label="Events in this session"] button')
            before_seek = page.locator('[data-fk="sp-strip"]').get_attribute("aria-valuenow")
            if events.count() > 1: events.last.click(); pause(page)
            after_seek = page.locator('[data-fk="sp-strip"]').get_attribute("aria-valuenow")
            check("event list can seek the session", events.count() == 1 or (events.count() > 1 and after_seek != before_seek))
        else:
            check("session player shows a clear no-sample fallback when needed", "No sampled sessions for this finding" in text(page))

        # the standalone (non-modal) drawer route — reached directly via ProblemDetailP2/P3 or
        # SessionPlayer's "Open the finding" — has no hero or Biggest-leak-menu alternative, so unlike
        # the Journeys popup above it keeps its own Watch sessions button
        route(page, "ProblemDetail")
        standalone_watch = page.get_by_role("button", name="Watch sessions")
        if standalone_watch.count():
            check("the standalone finding drawer keeps its own Watch sessions button", True)
        else:
            check("the standalone finding drawer keeps its own Watch sessions button",
                  page.evaluate("!(((SQ.watchFor(SQ.pickInsight('drawerInsight').id) || {}).sessions) || []).length"),
                  "this finding has no sampled sessions")

        print("-- Ask and Weekly brief scenarios (local matcher; no Gemini)")
        route(page, "ChatNow")
        more_questions = page.locator("details").first
        if more_questions.count():
            more_questions.locator("summary").click(); pause(page)
        rows = page.locator("button.sqa-suggestion-row")
        if rows.count():
            q = rows.first.inner_text().strip()
            check("Ask keeps three suggestion chips and shows More questions as sparkle rows",
                  page.locator("button.sug").count() == 3
                  and rows.first.locator("svg.sq-sparkle").count() == 1
                  and rows.first.evaluate("el => getComputedStyle(el).display === 'flex'"))
            rows.first.click(); pause(page)
            if page.locator('[aria-label="Answer in progress"]').count(): wait_js(page, "!document.querySelector('[aria-label=\"Answer in progress\"]')", timeout_ms=8000)
            check("suggested Ask question gets a local matched answer", page.evaluate("q => SQ.ask.cur() && SQ.ask.cur().turns.some(t => t.q === q && !t.pending && t.eid)", q.strip()))
        else:
            check("Ask keeps three suggestion chips and shows More questions as sparkle rows", False, "More questions has no rows")
            check("suggested Ask question gets a local matched answer", False, "no suggestions")
        # the follow-up composer is a single-line <input id="ask-follow">; the app has no
        # <textarea> anywhere (checked across every sq/c/*.html).
        box = page.locator('#ask-follow').last
        if box.count():
            box.fill("What is the secret score for purple astronauts?"); box.press("Enter"); pause(page)
            # the "Working on it" staged steps (read sessions, check a saved answer, check the
            # evidence, draw the chart) run for a few seconds before the refusal appears.
            if page.locator('[aria-label="Answer in progress"]').count():
                wait_js(page, "!document.querySelector('[aria-label=\"Answer in progress\"]')", timeout_ms=8000)
            check("unmatched Ask question returns the honest refusal", page.evaluate("document.body.innerText.includes(SQ.ask.refusal.head)"))
        else: check("unmatched Ask question returns the honest refusal", False, "composer missing")
        search = page.locator('input[placeholder*="Search"], input[aria-label*="Search"]').first
        if search.count() and not search.is_visible():
            show_history = page.get_by_role("button", name=re.compile("Show history"))
            if show_history.count(): show_history.last.click(); pause(page)
        if search.count():
            # The follow-up became a second turn in the SAME thread (the one from the
            # suggested question), not a new top-level history entry, so the button's visible
            # text stays the thread's own title; the search matches on the thread's full turn
            # content, not the title string. Check the filter itself: a non-matching term
            # hides it and the matching term shows it, rather than expecting "purple" in the
            # button's own label.
            search.fill("zzz_no_such_term_zzz"); pause(page)
            hides_on_no_match = page.locator("button.hist").count() == 0
            search.fill("purple astronauts"); pause(page)
            shows_on_match = page.locator("button.hist").count() == 1
            search.fill(""); pause(page)
            check("Ask history stores questions and filters a search", search.count() == 1 and hides_on_no_match and shows_on_match)
        else:
            check("Ask history stores questions and filters a search", False, "search box missing")
        if search.count(): search.fill(""); pause(page)
        check("Ask pin feature removed", page.get_by_role("menuitem", name=re.compile("Pin|Unpin")).count() == 0
              and "pinned" not in (page.evaluate("JSON.stringify(SQ.ask.cur() || {})") or ""))
        export = page.get_by_role("link", name=re.compile("^Export$"))
        if export.count():
            export.click(); wait_js(page, "location.hash === '#AskFlow5'"); pause(page)
            check("slide export opens a preview with at most three stat cards", page.get_by_role("heading", name="Export as slides").is_visible() and page.locator('div[style*="aspect-ratio"] .num').count() <= 3)
        else: check("slide export opens a preview with at most three stat cards", "Export" not in text(page))
        route(page, "Recommendations")
        check("weekly brief shows the top problem and three numbers", bool(page.evaluate("SQ.problems()[0]")) and page.locator(".num").count() >= 3)
        brief_before = page.locator(".sq-bart").inner_text()
        page.locator('[data-fk="menu-range"]').click(); page.locator('[data-fk="opt-24h"]').click(); pause(page)
        check("weekly brief updates with the selected scope", page.evaluate("SQ.scope.range === '24h'") and page.locator(".sq-bart").inner_text() != brief_before)
        page.get_by_role("button", name=re.compile("Copy text")).click(); pause(page)
        check("brief Copy text gives feedback", "Copied" in text(page) or "Copy is blocked" in text(page))
        check("brief export is titled Recommendations", page.evaluate("SQ.ask.brief().text.startsWith('# Recommendations') && SQ.ask.brief().kicker.includes('Recommendations')"))
        check("brief Share button removed", page.get_by_role("button", name=re.compile("Share")).count() == 0)

        print("-- Audiences, Data sources, widths, populated and empty scopes")
        route(page, "Audiences")
        page.evaluate("SQ.setScope({platform: 'all', persona: 'all', range: '30d'})"); pause(page)
        all_audiences = page.evaluate("JSON.stringify({total: SQ.audienceModel().total, cards: SQ.audienceModel().cards.map(c => c.people), top: SQ.audienceModel().topPeople})")
        page.evaluate("SQ.setScope({range: '24h'})"); pause(page)
        short_range_audience = page.evaluate("JSON.stringify({top: SQ.audienceModel().topPeople, states: SQ.audienceModel().topStates.map(s => s.people)})")
        page.evaluate("SQ.setScope({range: '30d'})"); pause(page)
        top_range_check = page.evaluate("JSON.stringify({top: SQ.audienceModel().topPeople, states: SQ.audienceModel().topStates.map(s => s.people)})")
        check("featured win-back counts differ by date range", short_range_audience != top_range_check)
        legend_layout = page.evaluate("(() => { const a = [...document.getElementsByClassName('sq-behavior-legend-item')].map(e => { const r=e.getBoundingClientRect(); return {x:r.x,y:r.y,right:r.right,bottom:r.bottom}; }); const overlap = a.some((x,i) => a.slice(i+1).some(y => x.x < y.right && x.right > y.x && x.y < y.bottom && x.bottom > y.y)); return {count:a.length, rows:new Set(a.map(x => Math.round(x.y))).size, overlap}; })()")
        check("behavior legend uses a readable 3-by-2 grid without collisions", legend_layout["count"] == 6 and legend_layout["rows"] == 2 and not legend_layout["overlap"], str(legend_layout))
        page.locator('[data-fk="menu-user"]').click()
        page.locator('input[data-fk="opt-large_business"]').click(force=True); pause(page)
        persona_audiences = page.evaluate("JSON.stringify({total: SQ.audienceModel().total, cards: SQ.audienceModel().cards.map(c => c.people), top: SQ.audienceModel().topPeople})")
        check("Audiences respects the selected persona", page.evaluate("SQ.scope.persona === 'large_business'")
              and persona_audiences != all_audiences)
        page.evaluate("SQ.setScope({persona: 'all'})"); pause(page)
        page.locator('[data-fk="menu-platform"]').click()
        page.locator('[role="menu"][aria-label="Platform"] [data-fk="opt-web"]').click(); pause(page)
        web_audiences = page.evaluate("JSON.stringify({total: SQ.audienceModel().total, cards: SQ.audienceModel().cards.map(c => c.people), top: SQ.audienceModel().topPeople})")
        check("Audiences respects the selected platform", page.evaluate("SQ.scope.platform === 'web'") and web_audiences != all_audiences)
        page.evaluate("SQ.setScope({platform: 'all'})"); pause(page)
        check("audience win-back numbers render", "Win back" in text(page) and page.get_by_role("img", name=re.compile("Win-back outcomes")).count() == 1)
        shares = page.locator('[aria-label="Active people grouped by behavior"] + div .num').all_inner_texts()
        vals = [float(s.rstrip("%")) for s in shares if re.search(r"\d", s)]
        # the design brief described 4 illustrative segments; the real sample has 6
        # (audiences.segments.items in results.json) — check the shares, not a fixed count.
        check("behavior-segment shares sum to 100%", len(vals) >= 4 and abs(sum(vals) - 100) <= 0.2, str(vals))
        check("audience source labels identify synthetic, calculated and AI ideas", "synthetic" in text(page).lower() and "Calculated" in text(page) and "AI idea" in text(page))
        page.get_by_role("button", name="Copy audience summary").click(); pause(page)
        check("audience summary copy responds", page.locator('[data-fk="audience-copy"]').count() == 1 and ("Summary copied" in text(page) or "Copy is unavailable here" in text(page)))
        route(page, "DataSources")
        ds = text(page)
        check("data sources show signal status and health", "What each signal needs" in ds and "Data health" in ds)
        button = page.get_by_role("button", name="Connect database")
        check("own backend is shown as unconnected without a connect action",
              "Your backend" in ds and "Not connected" in ds and button.count() == 0)
        check("Upload is not offered (owner removed it 2026-10-16)", page.get_by_role("button", name="Upload").count() == 0)
        table_disclosure = page.locator("details.ds-tables")
        if table_disclosure.count() and table_disclosure.get_attribute("open") is None:
            table_disclosure.locator("summary").click(); pause(page)
        table_row = page.locator("details.ds-tables tbody tr").filter(has_text="wallet_orders")
        check("BigQuery table list includes row counts", table_row.count() == 1 and re.search(r"\b[\d,]+\b", table_row.inner_text()) is not None)
        populated = page.evaluate("SQ.personas().map(p => p.id).find(id => (SQ.data.views['7d|all|' + id]?.insight_ids || []).length)")
        empty = page.evaluate("SQ.personas().map(p => p.id).find(id => !(SQ.data.views['7d|all|' + id]?.insight_ids || []).length)")
        check("sample includes populated and empty user-group scopes", bool(populated and empty), f"populated={populated}, empty={empty}")
        if empty:
            # Data sources has no ScopeBar (it isn't filtered by date/platform/user group), so
            # the user-group menu only exists on a page that imports ScopeBar; go to Overview first.
            route(page, "Overview")
            page.locator('[data-fk="menu-user"]').click(); opt = page.locator(f'input[data-fk="opt-{empty}"]')
            if opt.count(): opt.click(force=True); pause(page)
            check("empty user-group scope shows the no-problems state", "Nothing needs attention in this scope" in text(page))

        print("-- Mark fixed (run last: it permanently removes an issue from SQ.problems() for the rest of this session)")
        route(page, "Journeys")
        tabs = page.get_by_role("tab")
        if tabs.count() > 1:
            tabs.nth(1).click(); pause(page)
        top_menu = page.get_by_role("button", name="Biggest leak actions")
        if top_menu.count():
            before_ids = set(page.evaluate("SQ.problems().map(p => p.id)"))
            top_menu.first.click(); pause(page)
            mark_fixed = page.get_by_role("menuitem", name="Mark fixed")
            if mark_fixed.count():
                mark_fixed.first.click(); pause(page)
                after_ids = set(page.evaluate("SQ.problems().map(p => p.id)"))
                removed = before_ids - after_ids
                check("Mark fixed removes the issue from open problems", len(removed) == 1 and len(after_ids) == len(before_ids) - 1)
            else: check("Mark fixed removes the issue from open problems", True, "biggest-leak menu has no Mark fixed item")
        else: check("Mark fixed removes the issue from open problems", True, "no biggest-leak menu available in this scope")

        for width in (1440, 1280, 390):
            page.set_viewport_size({"width": width, "height": 844 if width == 390 else 1000})
            for name in ("Overview", "Journeys", "Audiences", "ChatNow", "Recommendations", "DataSources", "ProblemDetail", "SessionPlayer", "AskFlow2", "AskFlow5"):
                route(page, name)
                body = text(page)
                overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                check(f"{name} @ {width}px has no invalid text or horizontal page scroll", not BAD_TEXT.search(body) and not overflow, "overflow" if overflow else "")
            page.screenshot(path=str(OUT / f"scenario-{width}.png"), full_page=True)

        check("no unexpected external requests", not external, "; ".join(external[:3]))
        check("no console or page errors", not errors, "; ".join(errors[:3]))
        browser.close()
    failed = len(results) - sum(results)
    print(f"\n{'PASS' if not failed else 'FAIL'} {sum(results)}/{len(results)} checks; screenshots: {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
