"""Contrast check for the tokens in app/static/app.css, both themes. Light uses the design board's exact colours (owner chose fidelity), so its pairs below 4.5:1 are listed as known exceptions and do not fail; dark must pass everything. Text pairs >= 4.5:1, meaningful graphics >= 3:1.
Usage: python app/tests/contrast_check.py app/static/app.css   (exit 1 if any pair fails)"""
import re
import sys

css = open(sys.argv[1], encoding="utf-8").read()
tok = lambda block: dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})", block))
root = css[css.index(":root {"):css.index(':root[data-theme="dark"]')]
dk = css[css.index(':root[data-theme="dark"]'):]
dk = dk[:dk.index("}")]
light = tok(root)
dark = {**light, **tok(dk)}


def lum(h):
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    x, y = sorted([lum(a), lum(b)], reverse=True)
    return (x + 0.05) / (y + 0.05)


TEXT = [("ink", s) for s in ("bg", "panel", "chip", "soft")] + [("ink-2", s) for s in ("bg", "panel", "chip", "soft")] + [("ink-3", s) for s in ("bg", "panel", "soft")]
TEXT += [("accent", s) for s in ("bg", "panel", "soft")] + [("accent-fg", "accent"), ("btn-fg", "btn"), ("code-fg", "code-bg")]
for c, bg in (("crit", "crit-bg"), ("warn", "warn-bg"), ("ok", "ok-bg"), ("pos", "pos-bg"), ("tech", "tech-bg")):
    TEXT += [(c, bg), (c, "panel"), (c, "soft")]
TEXT += [("h0-fg", "h0"), ("h1-fg", "h1"), ("h2-fg", "h2"), ("h3-fg", "h3"), ("h4-fg", "h4"), ("panel", "crit")]
# Status dots (warn, ok) and orange bars always sit next to a text label or value, so state is never colour alone; they are not held to 3:1.
GRAPHIC = [("crit-dot", "panel"), ("pos-dot", "panel"), ("tech-dot", "panel"), ("muted-dot", "panel"), ("natural", "panel")]
bad = 0
known = 0
ACCEPTED = {("accent", "bg"), ("accent", "soft"), ("ok", "ok-bg"), ("ok", "panel"), ("ok", "soft"), ("natural", "panel")}  # the board's own colours
for name, t in (("light", light), ("dark", dark)):
    for fg, bg in TEXT:
        r = ratio(t[fg], t[bg])
        if r < 4.5:
            if name == "light" and (fg, bg) in ACCEPTED:
                known += 1
                print(f"{name}: known board exception, TEXT {fg} on {bg} = {r:.2f}")
            else:
                bad += 1
                print(f"{name}: TEXT {fg} on {bg} = {r:.2f}")
    for fg, bg in GRAPHIC:
        r = ratio(t[fg], t[bg])
        if r < 3:
            if name == "light" and (fg, bg) in ACCEPTED:
                known += 1
                print(f"{name}: known board exception, GRAPHIC {fg} on {bg} = {r:.2f}")
            else:
                bad += 1
                print(f"{name}: GRAPHIC {fg} on {bg} = {r:.2f}")
    print(f"{name}: checked")
print("problems:", bad, "| light-theme pairs kept at the board's exact colours:", known)
sys.exit(1 if bad else 0)
