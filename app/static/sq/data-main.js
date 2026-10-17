/* Shell and Overview selectors for Squint: headline grammar, problem records, data-trust state, menus.
   Everything is computed from SQ.data (results.json). Nothing here invents a number; where results.json has no value the field is null and the template shows "n/a". */
(function () {
  'use strict';
  const SQ = window.SQ;

  /* ---- small text helpers ---- */
  const firstSentence = (s, max) => {
    let t = String(s == null ? '' : s).trim();
    const m = t.match(/^.*?[.!?](\s|$)/);
    if (m) t = m[0].trim();
    if (t.length > 80) { const c = t.indexOf(', '); if (c > 25) t = t.slice(0, c); }
    if (t.length > max) t = t.slice(0, max).replace(/\s+\S*$/, '') + '…';
    return t;
  };
  SQ.firstSentence = firstSentence;
  const lowerFirst = (s) => (s ? s.charAt(0).toLowerCase() + s.slice(1) : s);
  const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));

  /* ---- headline grammar: "<Action> <item> for <who>" ---- */
  const PLURAL = { individual_trader: 'individual traders', large_business: 'large businesses', sari_sari: 'retail users', unregistered: 'unregistered users', individual: 'individuals' };
  SQ.whoOf = (i) => {
    // when the page is filtered to one named persona, every card in view is already that persona's slice:
    // say so, instead of a finding's own broader segment (e.g. a cross-persona web-mobile problem reading "all users").
    const filtered = SQ.personaIds();
    if (filtered.length === 1) return PLURAL[filtered[0]] || (SQ.personaLabel(filtered[0]).toLowerCase() + ' users');
    const seg = i.segment || {};
    const id = seg.persona || ((i.persona_ids || []).length === 1 ? i.persona_ids[0] : null);
    if (!id) return 'all users';
    return PLURAL[id] || (SQ.personaLabel(id).toLowerCase() + ' users');
  };
  SQ.verbOf = (i) => {
    const c = i.class || '';
    const conf = i.confidence == null ? 0 : i.confidence;
    if (i.severity === 'healthy' || c === 'natural_exit' || c === 'behavior_pattern') return 'Keep';
    if (c === 'technical_bug' || c === 'technical_fault') return conf >= 0.75 ? 'Fix' : 'Investigate';
    if (c.indexOf('language') === 0) return 'Rewrite';
    if (c === 'ux_friction') return 'Simplify';
    return 'Investigate';
  };
  SQ.causeOf = (i) => {
    const c = i.class || '';
    if (c === 'technical_bug' || c === 'technical_fault') return { name: 'Bug', color: '#D93025' };
    if (c.indexOf('language') === 0) return { name: 'Wording', color: '#1A73E8' };
    if (c === 'ux_friction') return { name: 'UX', color: '#F9AB00' };
    return { name: 'Natural', color: '#BDC1C6' };
  };
  const productLabel = (id) => ((SQ.data.scope.products || []).find((p) => p.id === id) || {}).label || '';
  const utcDay = (iso) => new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
  const utcHm = (iso) => { const d = new Date(iso); return String(d.getUTCHours()).padStart(2, '0') + ':' + String(d.getUTCMinutes()).padStart(2, '0'); };
  SQ.ctxOf = (i) => {
    if (i.window && i.window.start && i.window.end) return 'spike on ' + utcDay(i.window.start) + ', ' + utcHm(i.window.start) + '–' + utcHm(i.window.end) + ' UTC';
    const p = i.segment && i.segment.product ? productLabel(i.segment.product) : '';
    if (p) return p;
    const tail = String(i.label || '').split(' · ')[1];
    return tail && /steady/i.test(tail) ? lowerFirst(tail) : '';
  };
  SQ.ageOf = (i) => {
    const h = i.detected_hours_ago;
    if (h == null) return { short: 'n/a', long: 'n/a' };
    if (h < 24) return { short: 'today', long: 'today' };
    const d = Math.round(h / 24);
    return { short: d + 'd', long: d + ' days ago' };
  };
  SQ.confOf = (i) => {
    const c = i.confidence == null ? 0 : i.confidence;
    const n = c >= 0.75 ? 3 : c >= 0.5 ? 2 : 1;
    return { n, label: ['', 'Low', 'Medium', 'High'][n] };
  };
  const isAi = (i) => ['gemini', 'cached'].indexOf((i.diagnosis || {}).source) >= 0;
  SQ.diagTag = (i) => (isAi(i) ? { cls: 'tag tag-ai', text: 'AI' } : { cls: 'tag', text: 'Calculated' });

  /* the first fact behind a diagnosis, built from measured stats (Calculated) */
  SQ.topFact = (i) => {
    const g = ((i.evidence_stats || {}).group) || {};
    const err = (g.top_error_codes || [])[0], rage = (g.top_rage_tap_elements || [])[0];
    const parts = [];
    if (err) parts.push(err.code + (/error/.test(err.code) ? '' : ' errors'));
    if (rage) parts.push(SQ.fmt(rage.taps) + ' repeated taps on ' + rage.element);
    if (parts.length) return parts.join(', then ') + '.';
    return (i.facts || [])[1] || '';
  };

  /* one open problem as the Overview shows it */
  SQ.problemRec = (i) => {
    const sig = (i.signals || [])[0] || null;
    const g = ((i.evidence_stats || {}).group) || {};
    let stat = null, base = null, baseLabel = 'no baseline';
    if (sig) { stat = sig.value * 100; base = sig.reference == null ? null : sig.reference * 100; }
    else if (g.exit_rate != null) { stat = g.exit_rate * 100; }
    const fh = (i.facts || [])[0] || '';
    if (base == null) { const m = fh.match(/first half (\d+)%/); if (m) base = Number(m[1]); }
    if (stat != null && base != null) baseLabel = 'vs ' + Math.round(base) + '%';
    const crit = i.severity === 'critical';
    const cause = SQ.causeOf(i), age = SQ.ageOf(i), conf = SQ.confOf(i), tag = SQ.diagTag(i);
    const v = i.impact && i.impact.per_week_value;
    return {
      id: i.id, rank: i.__p || '', crit,
      sev: crit ? 'Critical' : 'Warning',
      sevBg: crit ? '#FCE8E6' : '#FEF7E0', sevFg: crit ? '#C5221F' : '#B06000',
      cause: cause.name, causeColor: cause.color,
      action: SQ.verbOf(i), item: i.screen_label || i.title || 'this step', who: SQ.whoOf(i), ctx: SQ.ctxOf(i),
      statText: stat == null ? 'n/a' : Math.round(stat) + '%',
      statW: stat == null ? '0%' : clamp(stat, 0, 100) + '%',
      hasBase: base != null, baseW: base == null ? '0%' : clamp(base, 0, 100) + '%',
      baseLabel, baseTitle: sig ? 'Baseline: ' + (i.compared_with || 'reference') : (base != null ? 'Baseline: ' + (i.compared_with || 'earlier') : 'No baseline for this step'),
      barColor: crit ? '#D93025' : '#F9AB00',
      valueText: v ? SQ.money(v) : 'n/a', valueNa: !v, valueNum: v || 0,
      valueTitle: '',
      whyTag: tag.text, whyTagCls: tag.cls,
      why: firstSentence((i.diagnosis || {}).summary || i.summary, 130),
      topFact: SQ.topFact(i), fact0: fh,
      sessions: SQ.fmt(i.n_sessions), ageShort: age.short, ageLong: age.long,
      confN: conf.n, confLabel: conf.label,
      metricTitle: ({ drop_off: 'Share of sessions that end at this step', rage: 'Share of sessions with rage taps', error: 'Share of sessions with an error' })[(sig || {}).metric] || 'Share of sessions that end at this step'
    };
  };

  /* ---- data trust: green only when no open fault touches an open problem ---- */
  SQ.trust = () => {
    const g = SQ.data.guardian || {};
    const faults = (g.faults || []).filter((f) => f.status !== 'resolved' && f.sev !== 'resolved');
    const probs = SQ.problems();
    const hit = [];
    faults.forEach((f) => {
      const ps = probs.filter((p) => (f.link && f.link.journey === p.journey && f.link.step === p.step) || (p.causes || []).some((c) => c.fault_id === f.id && !c.resolved));
      if (ps.length) hit.push({ fault: f, problems: ps });
    });
    const n = faults.length, ok = hit.length === 0;
    const plural = (k, w) => k + ' ' + w + (k === 1 ? '' : 's');
    let label, sub, line;
    if (ok) {
      label = 'Data reliable'; sub = n ? '· ' + plural(n, 'note') : '';
      line = n ? plural(n, 'note') + ' in Data sources, no effect on problems ·' : 'No data faults found ·';
    } else {
      label = 'Data: ' + plural(hit.length, 'fault') + (hit.length === 1 ? ' affects' : ' affect') + ' findings'; sub = '';
      line = hit[0].fault.title + ' touches ' + hit[0].problems.map((p) => p.screen_label).join(', ') + ' ·';
    }
    return { ok, n, label, sub, line, color: ok ? '#1E8E3E' : '#F9AB00', hit };
  };

  /* ---- menus and small UI helpers ---- */
  SQ.refocus = (key) => Promise.resolve().then(() => {
    const el = document.querySelector('[data-fk="' + String(key).replace(/"/g, '') + '"]');
    if (el) el.focus();
  });
  SQ.openMenu = (name) => { SQ.state.menu = SQ.state.menu === name ? null : name; SQ.redraw(); SQ.refocus('menu-' + name); };
  SQ.closeMenu = (refocus) => { const was = SQ.state.menu; SQ.state.menu = null; SQ.redraw(); if (refocus && was) SQ.refocus('menu-' + was); };
  document.addEventListener('click', (e) => {
    if (SQ.state.menu == null) return;
    if (e.composedPath().some((n) => n.dataset && n.dataset.menu)) return;
    SQ.closeMenu(false);
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && SQ.state.menu != null) SQ.closeMenu(true); });
})();
