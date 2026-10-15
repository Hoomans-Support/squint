/* Squint first-visit intro: one card ("Know the why, not just the where.") that waits for a click. The animated scenes were removed.
   Wire-up from the app:  if (SquintIntro.shouldShow()) SquintIntro.show({ logo: 'logo.png', onDone: fn });
   The Squint logo and the home icon (top bar), Esc, and Enter all close it. Plain JS, no libraries. */
(function () {
  var KEY = 'squint-intro-seen';
  var SVGNS = 'http://www.w3.org/2000/svg';

  function store(fn) { try { return fn(window.localStorage); } catch (e) { return undefined; } }
  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }
  function svgEl(name, attrs) { var n = document.createElementNS(SVGNS, name); for (var k in attrs) n.setAttribute(k, attrs[k]); return n; }
  function dot(x, y, c) { return svgEl('circle', { cx: x, cy: y, r: 14, fill: c }); }
  function label(x, y, t) { var n = svgEl('text', { x: x, y: y, 'text-anchor': 'middle' }); n.textContent = t; return n; }
  function reduced() { return window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches; }

  // Storage readable and flag unset => show. Storage blocked (undefined) => never show, so the visitor lands on the app.
  function shouldShow() { return store(function (s) { return s.getItem(KEY) ? 'seen' : 'new'; }) === 'new'; }

  function layerEnd(opts, go) {
    var s = el('section', 'sx-layer sx-l3'), h = el('h2', '', 'Know the '); h.appendChild(el('em', '', 'why')); h.appendChild(document.createTextNode(', not just the where.'));
    s.appendChild(h);
    var lk = el('div', 'sx-lockup');
    if (opts.logo) { var im = el('img'); im.src = opts.logo; im.alt = ''; lk.appendChild(im); }
    lk.appendChild(el('b', '', 'Squint')); lk.appendChild(el('span', '', 'Agentic behavior analytics')); s.appendChild(lk);
    var b = el('button', 'sx-go'); b.type = 'button'; b.appendChild(el('span', '', 'Open the dashboard')); b.appendChild(el('i', 'sx-arr', '\u2192')); b.addEventListener('click', go); s.appendChild(b);
    return s;
  }
  function homeIcon() {
    var s = svgEl('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' });
    s.appendChild(svgEl('path', { d: 'M3 11l9-8 9 8' })); s.appendChild(svgEl('path', { d: 'M5 10v10h14V10' })); s.appendChild(svgEl('path', { d: 'M10 20v-6h4v6' })); return s;
  }

  function show(opts) {
    opts = opts || {};
    var prev = document.activeElement, timer, done = false;
    var root = el('div', 'sx'); root.setAttribute('role', 'dialog'); root.setAttribute('aria-modal', 'true'); root.setAttribute('aria-label', 'Squint introduction');
    function finish() {
      if (done) return; done = true; clearTimeout(timer); document.removeEventListener('keydown', onKey, true);
      store(function (s) { s.setItem(KEY, '1'); }); root.remove(); document.body.classList.remove('sx-open');
      if (prev && prev.focus && document.contains(prev)) prev.focus();
      if (opts.onDone) opts.onDone();
    }
    var bar = el('div', 'sx-bar'), brand = el('button', 'sx-brand'), home = el('button', 'sx-home');
    brand.type = 'button'; brand.setAttribute('aria-label', 'Squint, go to the dashboard'); brand.title = 'Go to the dashboard';
    if (opts.logo) { var bi = el('img'); bi.src = opts.logo; bi.alt = ''; brand.appendChild(bi); }
    brand.appendChild(el('span', '', 'Squint')); brand.addEventListener('click', finish);
    home.type = 'button'; home.setAttribute('aria-label', 'Go to the dashboard'); home.title = 'Go to the dashboard'; home.appendChild(homeIcon()); home.addEventListener('click', finish);
    bar.appendChild(brand); bar.appendChild(home);
    var end = layerEnd(opts, finish), go = end.querySelector('.sx-go');
    root.appendChild(bar); root.appendChild(end);
    function onKey(e) {
      if (e.key === 'Escape') { e.preventDefault(); finish(); }
      else if (e.key === 'Enter' && e.target === document.body) { e.preventDefault(); finish(); }
      else if (e.key === 'Tab') {
        var f = [brand, home, go].filter(function (n) { return getComputedStyle(n.closest('.sx-layer') || n).visibility !== 'hidden'; });
        var at = f.indexOf(document.activeElement);
        if (e.shiftKey && at <= 0) { e.preventDefault(); f[f.length - 1].focus(); } else if (!e.shiftKey && at === f.length - 1) { e.preventDefault(); f[0].focus(); }
      }
    }
    document.addEventListener('keydown', onKey, true);
    document.body.appendChild(root); document.body.classList.add('sx-open');
    go.focus();
    return { close: finish, root: root };
  }
  window.SquintIntro = { shouldShow: shouldShow, show: show, KEY: KEY };
})();
