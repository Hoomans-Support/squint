/* Finding drawer and Watch sessions selectors for Squint. Everything comes from SQ.data (results.json, insights and watch.insights).
   Nothing here invents a session or a number; a missing value shows as "n/a" and a missing sample shows a calm empty state. */
(function () {
  'use strict';
  const SQ = window.SQ;
  const DRAWER = /^(ProblemDetail|ProblemDetailP2|ProblemDetailP3)$/;
  const WATCH = /^(SessionPlayer|SessionPlayerOTP|SessionPlayerForm)$/;
  const routeOf = (h) => decodeURIComponent(String(h || '').replace(/^#/, ''));

  /* ---- where a close button goes back to ---- */
  window.addEventListener('hashchange', (e) => {
    const from = routeOf((e.oldURL || '').split('#')[1]), to = routeOf(location.hash);
    if (!from || DRAWER.test(from) || WATCH.test(from)) {
      if (WATCH.test(to) && DRAWER.test(from)) SQ.state.watchFrom = from;
      return;
    }
    if (DRAWER.test(to) || WATCH.test(to)) {
      // Remember what had focus on the page that opened us, so the close control can put it
      // back once we eventually return (opener elements that carry a data-fk only; others fall
      // back to the page's own default focus, same as before).
      const opener = document.activeElement;
      SQ.state.returnFocusFk = opener && opener.getAttribute ? opener.getAttribute('data-fk') : null;
    }
    if (DRAWER.test(to)) SQ.state.drawerFrom = from === 'FlowPrototype' ? 'Journeys' : from;
    if (WATCH.test(to)) { SQ.state.watchFrom = from === 'FlowPrototype' ? 'Journeys' : from; }
  });
  const returnHome = (route) => {
    if (SQ.state.returnFocusFk) { SQ.state.pendingRefocus = SQ.state.returnFocusFk; delete SQ.state.returnFocusFk; }
    SQ.go(route);
  };
  SQ.closeDrawer = () => returnHome(SQ.state.drawerFrom || 'Overview');
  SQ.closeWatch = () => returnHome(SQ.state.watchFrom || SQ.state.drawerFrom || 'Overview');

  /* ---------- the ticket popup: opens over the current page, no route change ---------- */
  SQ.openTicketModal = (id) => {
    if (SQ.state.ticketModalOpen) { SQ.state.returnFocusFk = null; }
    else { const a = document.activeElement; SQ.state.returnFocusFk = a && a.getAttribute ? a.getAttribute('data-fk') : null; }
    if (id) SQ.state.drawerInsight = id;
    SQ.state.ticketOpen = false;
    SQ.state.ticketModalOpen = true;
    SQ.redraw();
  };
  SQ.closeTicketModal = () => {
    SQ.state.ticketModalOpen = false;
    SQ.state.ticketOpen = false;
    SQ.redraw();
    if (SQ.state.returnFocusFk) { const fk = SQ.state.returnFocusFk; delete SQ.state.returnFocusFk; SQ.refocus(fk); }
  };

  /* keep keyboard focus on the same control across a re-render (a render replaces the DOM) */
  SQ.keepFocus = (fn) => {
    const a = document.activeElement;
    const fk = a && a.getAttribute ? a.getAttribute('data-fk') : null;
    fn();
    if (fk) SQ.refocus(fk);
  };

  /* pick the insight a page shows: explicit pid (route wrappers), then the handoff state, then the top problem */
  SQ.pickInsight = (stateKey, pid) => {
    const probs = SQ.problems();
    if (pid) { const hit = probs.find((p) => p.__p === pid); if (hit) return hit; }
    const want = SQ.state[stateKey] || (stateKey === 'watchInsight' ? SQ.state.drawerInsight : null);
    return (want && SQ.insight(want)) || probs[0] || null;
  };

  /* ---------- the finding drawer ---------- */
  const SIGNAL = {
    drop_off: ['Leave here', 'Share of sessions that end on this screen'],
    rage: ['Repeated taps', 'Share of sessions with rage taps'],
    error: ['Errors', 'Share of sessions with an error'],
    dead_tap: ['Taps that did nothing', 'Share of sessions with a dead tap'],
    stuck: ['Stuck over 30s', 'Share of sessions stuck over 30 seconds']
  };
  const pctTxt = (f) => (f == null ? 'n/a' : (f * 100 >= 10 ? Math.round(f * 100) : (f * 100).toFixed(1)) + '%');
  const KIND = { check: 'Investigate', fix: 'Fix', monitor: 'Monitor', test: 'Test', rewrite: 'Rewrite' };
  const cap1 = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

  function evidenceRows(i) {
    const rows = [];
    (i.signals || []).forEach((s) => {
      const lab = (SIGNAL[s.metric] || [s.metric, ''])[0];
      const max = Math.max(s.value || 0, s.reference || 0, 0.01);
      rows.push({
        label: lab, now: pctTxt(s.value), usual: s.reference == null ? 'n/a' : pctTxt(s.reference),
        nowW: Math.min(100, (s.value || 0) / max * 100).toFixed(1) + '%', usualW: Math.min(100, (s.reference || 0) / max * 100).toFixed(1) + '%',
        ratio: s.ratio ? (s.ratio >= 10 ? Math.round(s.ratio) : s.ratio.toFixed(1)) + '×' : '', hasRatio: !!s.ratio
      });
    });
    if (!rows.length) {
      const st = i.evidence_stats || {}, g = st.group, r = st.reference;
      if (g && g.exit_rate != null) {
        const max = Math.max(g.exit_rate, (r || {}).exit_rate || 0, 0.01);
        rows.push({ label: 'Leave here', now: pctTxt(g.exit_rate), usual: r && r.exit_rate != null ? pctTxt(r.exit_rate) : 'n/a', nowW: (g.exit_rate / max * 100).toFixed(1) + '%', usualW: r && r.exit_rate != null ? (r.exit_rate / max * 100).toFixed(1) + '%' : '0%', ratio: '', hasRatio: false });
      }
    }
    return rows;
  }

  function timelineBars(i) {
    const tl = i.timeline;
    if (!tl || !(tl.series || []).length) return null;
    const ser = tl.series.filter((p) => p.rate != null);
    if (!ser.length) return null;
    const max = Math.max.apply(null, ser.map((p) => p.rate)) || 1;
    const bars = tl.series.map((p) => {
      const on = tl.onset && p.d === tl.onset;
      return { h: p.rate == null ? '2px' : Math.max(2, p.rate / max * 70).toFixed(0) + 'px', c: p.rate == null ? '#E8EAED' : (on ? '#D93025' : '#9AA0A6'), title: p.d + ': ' + pctTxt(p.rate) + (p.n ? ' of ' + p.n + ' sessions' : '') };
    });
    const first = tl.series[0].d, last = tl.series[tl.series.length - 1].d;
    const fd = (d) => new Date(d + 'T00:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
    return { bars, first: fd(first), last: fd(last), metric: tl.metric_label || 'Share of sessions that end here', onset: tl.onset ? 'Jump on ' + fd(tl.onset) : '' };
  }

  function whoGroups(i) {
    const rows = i.breakdown || [];
    const groups = [], by = {};
    rows.forEach((r) => {
      if (['persona', 'device_class', 'app_version', 'product', 'network'].indexOf(r.dim) < 0 && !r.dim_label) return;
      if (!by[r.dim]) { by[r.dim] = { title: r.dim_label || r.dim, rows: [] }; groups.push(by[r.dim]); }
      by[r.dim].rows.push(r);
    });
    return groups.filter((g) => g.rows.length > 1).slice(0, 4).map((g) => {
      const top = Math.max.apply(null, g.rows.map((r) => r.rate || 0));
      const max = Math.max(top * 1.15, 0.05);
      const list = g.rows.slice().sort((a, b) => (b.rate || 0) - (a.rate || 0)).slice(0, 6);
      return {
        title: g.title,
        rows: list.map((r) => ({
          label: r.label, pct: pctTxt(r.rate), n: SQ.fmt(r.n) + ' sess.', w: Math.min(100, (r.rate || 0) / max * 100).toFixed(1) + '%',
          color: r.in_segment || r.rate === top ? '#D93025' : '#BDC1C6', labelStyle: r.in_segment || r.rate === top ? 'font-weight: 500; color: #202124' : 'color: #3C4043'
        }))
      };
    });
  }

  function ticketText(i, rec, m) {
    const L = [];
    L.push('# ' + rec.action + ' ' + rec.item + ' for ' + rec.who, '');
    L.push('> Draft from Squint on synthetic sample data.', '');
    L.push('- Priority: ' + (i.__p || 'n/a') + ' (' + rec.sev + ', ' + rec.cause + ')');
    L.push('- Value at risk: ' + (rec.valueNa ? 'n/a' : m.valueText + ' per week'));
    L.push('- Sessions: ' + rec.sessions);
    L.push('- Confidence: ' + rec.confLabel);
    if (rec.ctx) L.push('- When or where: ' + rec.ctx);
    L.push('', '## What we see (calculated)');
    (i.facts || []).forEach((f) => L.push('- ' + f));
    if (!(i.facts || []).length) L.push('- n/a');
    L.push('', '## Likely reason (' + rec.whyTag + ')', (i.diagnosis || {}).summary || i.summary || 'n/a');
    if (m.ruledOut.length) { L.push('', '## Ruled out'); m.ruledOut.forEach((r) => L.push('- ' + r.title)); }
    L.push('', '## Next steps');
    m.next.forEach((n, k) => L.push((k + 1) + '. ' + n.text));
    if (m.caveats.length) { L.push('', '## Caveat'); m.caveats.forEach((c) => L.push('- ' + c)); }
    L.push('', '## Open in Squint', 'Finding: ' + i.id);
    return L.join('\n');
  }

  SQ.drawerModel = (i) => {
    const rec = SQ.problemRec(i);
    const healthy = i.severity === 'healthy';
    if (healthy) { rec.sev = 'Healthy'; rec.sevBg = '#E6F4EA'; rec.sevFg = '#137333'; rec.causeColor = '#1E8E3E'; rec.cause = 'Expected'; }
    const dg = i.diagnosis || {};
    const probs = SQ.problems();
    const idx = probs.findIndex((p) => p.id === i.id);
    const imp = i.impact || {};
    const causes = (i.causes || []);
    const ruledIn = causes.filter((c) => !c.resolved && c.share > 0).map((c) => ({ title: c.title, why: c.why, share: Math.round(c.share * 100) + '%' }));
    const ruledOut = causes.filter((c) => c.resolved || !(c.share > 0)).map((c) => ({ title: c.title, why: c.why }));
    const next = (dg.next_steps || []).map((n) => ({ kind: KIND[n.kind] || cap1(n.kind || 'Next'), text: n.text }));
    if (!next.length && i.recommendation) next.push({ kind: 'Next', text: i.recommendation });
    const caveats = dg.caveats || [];
    const whoTitle = healthy ? 'Where it happens' : 'Who is affected';
    const m = {
      i, rec, healthy, idx, total: probs.length,
      hasNav: idx >= 0 && probs.length > 1,
      pidLabel: idx >= 0 ? (i.__p || 'P' + (idx + 1)) + ' · problem ' + (idx + 1) + ' of ' + probs.length : (healthy ? 'Healthy · nothing to fix' : (i.__p || '')),
      sub: i.concentration || i.segment_text || '',
      valueText: rec.valueText, valueUnit: rec.valueNa ? '' : ' /wk',
      valueTitle: '',
      valueNote: '',
      reason: dg.summary || i.summary || '', reasonTag: rec.whyTag, reasonCls: rec.whyTagCls,
      claims: (dg.claims || []).map((c) => ({ text: c.text })),
      evidence: evidenceRows(i), tl: timelineBars(i), who: whoGroups(i), whoTitle,
      ruledIn, ruledOut, next, caveats,
      sourceNote: dg.source_note || '',
      raw: null
    };
    m.ticket = ticketText(i, rec, m);
    return m;
  };

  SQ.downloadText = (name, text) => {
    try {
      const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' }));
      const a = document.createElement('a');
      a.href = url; a.download = name; a.style.display = 'none';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      return true;
    } catch (e) { return false; }
  };
  SQ.ticketFile = (i) => 'squint-ticket-' + String(i.id).replace(/[^A-Za-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) + '.md';

  /* Esc closes the whole drawer/page, same as the ticket's own "Ticket created" button and the X */
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || e.defaultPrevented) return;
    const r = routeOf(location.hash);
    if (SQ.state.menu != null) return;
    if (SQ.state.ticketModalOpen) { SQ.closeTicketModal(); return; }
    if (DRAWER.test(r)) SQ.closeDrawer();
    else if (WATCH.test(r)) SQ.closeWatch();
  });

  /* ---------- watch sessions ---------- */
  const PERSONA_DOT = { 'Individual trader': '#D93025', Retail: '#F9AB00', 'Large business': '#1A73E8', Individual: '#1E8E3E', Unregistered: '#9AA0A6' };
  const OUT = { left: ['Left', '#FCE8E6', '#C5221F'], came_back_later: ['Came back later', '#E8F0FE', '#174EA6'], finished: ['Finished', '#E6F4EA', '#137333'] };
  const fmtT = (t) => { t = Math.max(0, Math.round(t)); return Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0'); };
  const EV = {
    rage_tap: { c: '#D93025', r: '1px', name: 'Repeated taps' }, error: { c: '#F9AB00', r: '2px', name: 'Error' }, back: { c: '#1A73E8', r: '5px', name: 'Went back' },
    idle: { c: '#BDC1C6', r: '2px', name: 'Idle' }, exit: { c: '#202124', r: '2px', name: 'Left' }, done: { c: '#1E8E3E', r: '5px', name: 'Done' },
    step: { c: '#DADCE0', r: '5px', name: 'Step' }, tap: { c: '#5F6368', r: '5px', name: 'Tap' }
  };
  SQ.watchEV = EV;
  SQ.watchMark = (m, dur) => {
    const left = Math.min(100, m.t_seconds / dur * 100).toFixed(1) + '%';
    if (m.kind === 'rage_tap') return { left, top: '12px', w: '3px', h: '22px', r: '1px', c: '#D93025', name: 'Repeated taps at ' + fmtT(m.t_seconds) };
    if (m.kind === 'error') return { left, top: '17px', w: '10px', h: '10px', r: '2px', c: '#F9AB00', name: 'Error at ' + fmtT(m.t_seconds) };
    if (m.kind === 'back') return { left, top: '17px', w: '10px', h: '10px', r: '5px', c: '#1A73E8', name: 'Went back at ' + fmtT(m.t_seconds) };
    if (m.kind === 'exit') return { left: 'calc(' + left + ' - 10px)', top: '15px', w: '12px', h: '12px', r: '2px', c: '#202124', name: 'Left at ' + fmtT(m.t_seconds) };
    if (m.kind === 'done') return { left: 'calc(' + left + ' - 10px)', top: '15px', w: '12px', h: '12px', r: '6px', c: '#1E8E3E', name: 'Done at ' + fmtT(m.t_seconds) };
    return null;
  };
  SQ.watchFor = (id) => ((SQ.data.watch || {}).insights || []).find((w) => w.insight_id === id) || null;
  SQ.watchOut = (o) => OUT[o] || [o, '#F1F3F4', '#3C4043'];
  SQ.watchDot = (p) => PERSONA_DOT[p] || '#9AA0A6';
  SQ.fmtT = fmtT;

  /* up to n sample sessions for a finding's ticket, one line each: time, device, outcome */
  SQ.sessionSummaries = (i, n) => {
    const w = SQ.watchFor(i.id);
    const sessions = (w && w.sessions) || [];
    return sessions.slice(0, n || 3).map((s) => {
      const when = s.start_utc ? new Date(s.start_utc).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone: 'UTC' }) : 'n/a';
      const o = SQ.watchOut(s.outcome);
      return { id: s.id, label: when + ' · ' + (s.device || s.persona || 'n/a') + ' · ' + o[0] };
    });
  };
})();
