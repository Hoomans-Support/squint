// Evaluated inside the page by app/tests/clickthrough.py (and by ad-hoc sweeps). Returns a list of layout problems for what is
// currently on screen: the open drawer if there is one, otherwise the current view.
(() => {
  const out = [];
  const vis = (e) => e.offsetParent !== null || e === document.body;
  if (document.documentElement.scrollWidth - innerWidth > 0) out.push('page scrolls sideways by ' + (document.documentElement.scrollWidth - innerWidth) + 'px');
  const drawer = document.querySelector('#drawer:not([hidden])');
  const root = drawer || document.getElementById('view');
  const all = (sel) => [...root.querySelectorAll(sel)].filter(vis);
  // 1. text containers too narrow for the words in them (a one-word-per-line column)
  for (const e of root.querySelectorAll('*')) {
    if (!vis(e) || e.children.length || e.closest('svg,pre,table,.sk-tip,select,option,code,.heat,.rep,.arcs,.sr')) continue;
    const t = (e.textContent || '').trim();
    if (t.length < 16 || t.split(/\s+/).filter(Boolean).length < 3) continue;
    const fs = parseFloat(getComputedStyle(e).fontSize) || 14;
    const w = e.getBoundingClientRect().width;
    if (w < 6.5 * fs) out.push('narrow text ' + Math.round(w) + 'px in .' + String(e.className).split(' ')[0] + ': ' + t.slice(0, 28));
  }
  // 2. cards and rows with a lot of empty space inside (stretched)
  for (const e of all('.ins,.kpi,.cause,.cause-row,.tile,.banner,.jcard,.flowfile')) {
    const r = e.getBoundingClientRect();
    let bottom = r.top;
    for (const c of e.children) { if (getComputedStyle(c).position !== 'absolute') bottom = Math.max(bottom, c.getBoundingClientRect().bottom); }
    const gap = r.bottom - bottom - (parseFloat(getComputedStyle(e).paddingBottom) || 0);
    if (gap > 130) out.push('empty space ' + Math.round(gap) + 'px inside .' + String(e.className).split(' ')[0]);
  }
  for (const e of all('.cause')) { const h = e.getBoundingClientRect().height; if (h > (innerWidth < 700 ? 230 : 160)) out.push('cause row ' + Math.round(h) + 'px tall'); }
  // 3. anything poking out of its card
  for (const card of (drawer ? [drawer] : all('.card,.ins,.kpi'))) {
    const cr = card.getBoundingClientRect();
    for (const e of card.querySelectorAll('*')) {
      if (!vis(e) || e.closest('.scroller,pre,svg')) continue;
      const r = e.getBoundingClientRect();
      if (r.width > 0 && r.right > cr.right + 1) { out.push('overflows its card by ' + Math.round(r.right - cr.right) + 'px: .' + String(e.className).split(' ')[0]); break; }
    }
  }
  return out;
})()
