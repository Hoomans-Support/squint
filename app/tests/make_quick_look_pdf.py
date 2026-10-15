import sys, base64
from pathlib import Path
from playwright.sync_api import sync_playwright
out = Path(sys.argv[1]); pdf = sys.argv[2]
U = "http://127.0.0.1:8080/"
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    c = b.new_context(viewport={"width": 1440, "height": 900}); c.add_init_script("localStorage.setItem('theme','dark')")
    pg = c.new_page()
    def shot(name):
        pg.wait_for_timeout(450); pg.screenshot(path=str(out / name))
    pg.goto(U + "#overview"); pg.wait_for_selector(".ov-head"); shot("1.png")
    pg.evaluate("document.querySelector('#overview').scrollTop = 560"); shot("2.png")
    pg.goto(U + "#journeys"); pg.wait_for_selector("#jcmp"); shot("3.png")
    pg.locator("#persona button[data-v=smb]").click()
    pg.locator("#jtools [data-mode=dropoff]").click(); pg.select_option("#jcmp", "all|all"); shot("4.png")
    pg.goto(U + "#insights"); pg.wait_for_selector(".row"); shot("5.png")
    pg.locator(".row").nth(1).click(); pg.evaluate("document.querySelector('.ws').scrollTop = 0"); shot("6.png")
    pg.locator("#drawer .btn-ticket").click(); pg.wait_for_timeout(300); shot("7.png")
    imgs = {k: base64.b64encode((out / f"{k}.png").read_bytes()).decode() for k in "1234567"}
    def page(img, title, text):
        return f'<section><h2>{title}</h2><p>{text}</p><img src="data:image/png;base64,{imgs[img]}"></section>'
    html = f"""<!doctype html><meta charset=utf-8><style>
@page {{ size: 1440px 1000px; margin: 0 }}
body {{ margin:0; background:#0B1317; color:#EDF3F3; font: 18px/1.5 system-ui, Segoe UI, Arial, sans-serif }}
section {{ width:1440px; height:1000px; box-sizing:border-box; padding:40px 56px; page-break-after:always; display:flex; flex-direction:column }}
h1 {{ font-size:56px; margin:140px 0 12px; letter-spacing:-.02em }} h2 {{ font-size:30px; margin:0 0 6px; letter-spacing:-.01em }}
p {{ margin:0 0 14px; color:#B6C7CB; max-width:1100px }} img {{ width:1328px; border:1px solid #25363D; border-radius:6px; margin-top:auto }}
.big p {{ font-size:22px }} .tag {{ display:inline-block; border:1px solid #93A6AB; border-radius:4px; padding:4px 10px; font-size:15px; color:#EDF3F3 }}
li {{ margin:6px 0; color:#B6C7CB }} ul {{ max-width:1100px; font-size:20px }}
</style>
<section class=big><h1>Squint</h1>
<p>A dashboard that tells a product manager where users get stuck and why, so they do not have to dig through raw logs. Built by Team Hoomans Support for the AI Builder Cup 2026, on Google Cloud with Gemini.</p>
<p><span class=tag>Everything in this document is synthetic sample data, not real users</span></p>
<ul><li><b style="color:#EDF3F3">Checks the data first.</b> If tracking broke, it says so and leaves that period out.</li>
<li><b style="color:#EDF3F3">Finds the trouble spots</b> by comparing screens and user groups against normal.</li>
<li><b style="color:#EDF3F3">Ranks them by estimated cost</b> and shows the proof: what changed, when, who, and the original log records.</li>
<li><b style="color:#EDF3F3">Explains why</b> in plain English with AI: next on the list, not built yet.</li></ul></section>
{page('1','Overview: what is wrong right now','Two findings need attention. The funnel from Signup to Dashboard converts 71%, down 11 points. Dollar figures use a placeholder of $20 per signup.')}
{page('2','Overview: where it shows up','Funnel stages as columns (KYC Identity loses the most), sessions per day (the Oct 4 dip is missing data, not users), and which groups convert worst.')}
{page('3','Journeys: the path and where it hurts','Each stage with sessions, how many continue and how many leave. The curve reads how smooth each screen is, taken from the findings.')}
{page('4','Journeys: compare two groups','SMB users against everyone, in Drop-off mode. The red outline marks the biggest gap: SMB users leave far more often at Connect Bank.')}
{page('5','Insights: investigate one finding','Headline, key numbers with the comparison, a daily chart showing when it started (an estimate), and the groups it concentrates in. The AI panel says "Not diagnosed yet" instead of guessing.')}
{page('6','Insights: a hidden problem','A small group (SMB users on small-screen Android) fails at Connect Bank 57% of the time versus 4% for everyone else, while the overall funnel still looks healthy. A normal dashboard misses this.')}
{page('7','Draft ticket','One click builds a Markdown ticket from the measured facts, the cost with its assumption, and the evidence sessions. It never invents a cause.')}
<section><h2>Honest status</h2><ul>
<li>Planted in the sample data on purpose: a confusing ID-upload screen, a hidden small-group failure, a normal exit page that is correctly not flagged, and a 12-hour tracking outage. All four were caught.</li>
<li>Not built yet: the AI explanation of why, wiring it into the side panel, deployment on Google Cloud, and the real dataset (arrives next).</li>
<li>Dollar figures rest on a placeholder, not a measured value.</li></ul></section>"""
    pg2 = c.new_page(); pg2.set_content(html); pg2.wait_for_timeout(500)
    pg2.pdf(path=pdf, width="1440px", height="1000px", print_background=True)
    b.close()
