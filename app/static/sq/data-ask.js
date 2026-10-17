/* Ask, export-as-slides and Weekly brief selectors. Owned by the Ask/Brief lane; reads SQ.data only (results.json) for
   matched questions. An unmatched question also tries the live, guarded /api/ask (off unless ASK_GEMINI_ENABLED=1 on
   the server; a disabled or failed call falls back to the same refusal as before, so this is additive, not a behavior
   change when the endpoint is off). Nothing here invents a number: every figure is read from results.json, derived from
   it by arithmetic shown in the code, or (for a live answer) verified server-side against the same dataset before it
   reaches this file. See docs/ask-endpoint.md and docs/ai-generation-overview.md. */
(function () {
  'use strict';
  const SQ = window.SQ;
  const A = (SQ.ask = { draft: '', search: '', curId: null, menu: false, expanded: {}, copied: '', off: { sum: true, app: true }, fmt: 'pdf', notes: true, appendix: false, from: '', fromRoute: '' });
  const LIVE = Object.create(null);   // id -> synthetic ask[]-shaped entry for an answer that came back from a live /api/ask call

  const REFUSAL_HEAD = "I can't answer that from this data";
  const REFUSAL_TEXT = "Squint answers only from the saved results of this sample dataset: findings, rage-tap spots, data health and a few journeys. I won't guess. Try one of these instead.";
  const STOP = new Set(['the', 'a', 'an', 'is', 'are', 'of', 'to', 'do', 'does', 'we', 'why', 'what', 'which', 'who', 'in', 'on', 'at', 'and', 'for', 'with', 'show', 'me', 'tell', 'about', 'how', 'did', 'was', 'were', 'it', 'this', 'that', 'my', 'our', 'can', 'you', 'i']);
  const HIDDEN = /fraud|shared-device/i;   // same scrub as the old app: these personas are not featured
  const RED = '#D93025', GREY = '#BDC1C6', BLUE = '#1A73E8', AMBER = '#F9AB00';
  const WHO = { individual_trader: 'individual traders', large_business: 'large businesses', sari_sari: 'retail buyers', unregistered: 'unregistered users', individual: 'individuals' };
  const MINUS = '\u2212';

  /* ---------- small helpers ---------- */
  const cap1 = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
  const firstSentence = (t) => { t = String(t || '').trim(); const m = t.match(/^.*?[.!?](?=\s|$)/); return m ? m[0] : t; };
  const pctText = (frac) => (frac == null ? 'n/a' : (frac * 100 < 10 ? (frac * 100).toFixed(1).replace(/\.0$/, '') : String(Math.round(frac * 100))) + '%');
  const signed = (n, f) => (n > 0 ? '+' : n < 0 ? MINUS : '') + f(Math.abs(n));
  const focusColor = (sev) => (sev === 'critical' ? RED : sev === 'warning' ? AMBER : BLUE);
  const entries = () => (SQ.data.ask || []).filter((x) => !HIDDEN.test(JSON.stringify(x)));
  A.entries = entries;
  A.entry = (id) => entries().find((e) => e.id === id) || LIVE[id] || null;
  A.entryForInsight = (iid) => entries().find((e) => (e.refs || []).some((r) => r.type === 'insight' && r.id === iid)) || null;
  A.refusal = { head: REFUSAL_HEAD, text: REFUSAL_TEXT };
  const reduced = () => { try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (_) { return false; } };

  /* ---------- matching (the old app's matcher) ---------- */
  const tokens = (t) => String(t).toLowerCase().split(/[^a-z0-9]+/).filter((w) => w && !STOP.has(w)).map((w) => (w.length > 3 && w.endsWith('s') ? w.slice(0, -1) : w));
  A.match = (q) => {
    const user = [...new Set(tokens(q))];
    if (!user.length) return null;
    let best = null;
    for (const a of entries()) {
      const pool = new Set([...tokens(a.question), ...(a.keywords || []).flatMap(tokens)]);
      const hit = user.filter((w) => pool.has(w)).length;
      const ratio = hit / user.length;
      const ok = (hit >= 2 && ratio >= 0.5) || (hit >= 1 && user.length === 1);
      if (ok && (!best || hit > best.hit || (hit === best.hit && ratio > best.ratio))) best = { a, hit, ratio };
    }
    return best ? best.a : null;
  };

  /* ---------- per-visitor history: memory + sessionStorage in try/catch, seeded with nothing ---------- */
  const STORE = 'sq.ask.threads';
  let threads = [];
  try {
    const t = JSON.parse(sessionStorage.getItem(STORE) || '[]');
    if (Array.isArray(t)) threads = t.filter((x) => x && Array.isArray(x.turns)).map((x) => { x.turns.forEach((u) => { u.pending = false; }); return x; });
  } catch (_) { /* private mode: memory only */ }
  const save = () => { try { sessionStorage.setItem(STORE, JSON.stringify(threads)); } catch (_) { /* ignore */ } };
  const live = (u) => !u.stopped;
  A.threads = () => threads.slice().sort((a, b) => b.at - a.at);
  A.cur = () => threads.find((t) => t.id === A.curId) || null;

  /* where the question started: the page the visitor was on before Ask */
  A.fromRoute = (location.hash || '').replace(/^#/, '');
  window.addEventListener('hashchange', () => {
    const next = decodeURIComponent((location.hash || '').replace(/^#/, ''));
    if (!/^(Ask|AskFlow\d)$/.test(next) && next) A.fromRoute = next;
  });
  A.fromLabel = () => {
    if (SQ.state.askContext) return String(SQ.state.askContext);
    const r = A.fromRoute;
    if (!r || /^(Ask|AskFlow\d)$/.test(r)) return '';
    return SQ.titles[r] || '';
  };
  A.fromHref = () => { const r = A.fromRoute; return r && SQ.titles[r] ? (r === 'FlowPrototype' ? 'Journeys.dc.html' : r + '.dc.html') : ''; };

  const STEPS = () => {
    const n = (SQ.data.meta || {}).counts || {};
    return ['Read ' + SQ.fmt(n.sessions_in_window) + ' sessions in the sample', 'Looked for a saved answer to your question', 'Checked the numbers against the evidence', 'Drawing the chart'];
  };
  A.steps = STEPS;

  /* A question with no prepared match tries the live endpoint while the usual step animation plays, so a slow network
     is not a longer-feeling wait than today's fixed ~1.1s. Whichever finishes last ends the turn: the animation never
     ends the turn alone (so it cannot show a false refusal while the call is still in flight), and the call never ends
     it before step 4 (so a very fast cache hit does not skip the steps). Stop aborts the fetch, same as before otherwise. */
  const settle = (turn) => {
    if (!live(turn) || !turn.pending || turn.step < 4 || !turn.liveSettled) return;
    turn.pending = false; save(); SQ.redraw(); A.focus('ask-follow');
  };
  function askLive(turn) {
    const ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    turn.abort = ctrl;
    fetch('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: turn.q }), signal: ctrl ? ctrl.signal : undefined })
      .then((r) => r.json().then((body) => ({ ok: r.ok, body })).catch(() => ({ ok: false, body: null })))
      .then(({ ok, body }) => {
        if (!live(turn)) return;
        if (ok && body && typeof body.answer === 'string' && body.answer.trim() && !body.refused) {
          const id = 'live:' + turn.at.toString(36) + Math.random().toString(36).slice(2, 6);
          LIVE[id] = { id, question: turn.q, answer: body.answer, refs: (body.refs || []).filter((r) => r && r.id && r.label)
            .map((r) => ({ type: r.type === 'fault' ? 'fault' : 'insight', id: r.id, label: r.label })) };
          turn.eid = id;
        }
        turn.liveSettled = true;
        settle(turn);
      })
      .catch(() => { if (live(turn)) { turn.liveSettled = true; settle(turn); } });
  }
  A.submit = (q, opts = {}) => {
    q = String(q || '').trim().slice(0, 200);
    if (!q) return;
    const entry = A.match(q);
    const turn = { q, eid: entry ? entry.id : null, at: Date.now(), pending: true, step: 0, from: opts.from || '', liveSettled: !!entry };
    let th = opts.fresh ? null : A.cur();
    if (!th) {
      th = { id: 't' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5), title: entry ? entry.question : cap1(q), at: Date.now(), pinned: false, turns: [], from: opts.from || A.fromLabel() };
      threads.push(th);
      A.curId = th.id;
      turn.from = th.from || '';
      turn.first = true;
    }
    th.turns.push(turn);
    th.at = Date.now();
    A.draft = ''; A.menu = false;
    save();
    if (!entry) askLive(turn);
    const tick = () => {
      if (!live(turn) || !turn.pending) return;
      if (turn.step < 4) {
        turn.step += 1; SQ.redraw();
        if (turn.step < 4) { turn.timer = setTimeout(tick, 280); return; }
      }
      settle(turn);
      if (!turn.pending) A.focus('ask-follow');
      // else: step 4 reached before the live call settled; askLive() redraws and focuses when it resolves, no further ticks needed
    };
    if (reduced()) { turn.step = 4; SQ.redraw(); settle(turn); if (!turn.pending) A.focus('ask-follow'); }
    else { SQ.redraw(); turn.timer = setTimeout(tick, 280); }
  };
  A.stop = (th, turn) => {
    turn.stopped = true; turn.pending = false; clearTimeout(turn.timer);
    if (turn.abort) { try { turn.abort.abort(); } catch (_) { /* already settled */ } }
    th.turns = th.turns.filter((u) => u !== turn);
    A.draft = turn.q;
    if (!th.turns.length) { threads = threads.filter((x) => x !== th); A.curId = null; }
    save(); SQ.redraw(); A.focus('ask-follow');
  };
  A.newThread = () => { A.curId = null; A.menu = false; A.draft = ''; SQ.redraw(); A.focus('ask-follow'); };
  A.open = (id) => { A.curId = id; A.menu = false; SQ.redraw(); };
  A.togglePin = (th) => { th.pinned = !th.pinned; A.menu = false; save(); SQ.redraw(); };
  A.remove = (th) => { threads = threads.filter((x) => x !== th); if (A.curId === th.id) A.curId = null; A.menu = false; save(); SQ.redraw(); };
  A.clearAll = () => { threads = []; A.curId = null; A.menu = false; A.historyMenu = false; save(); SQ.redraw(); };
  A.focus = (id, end) => setTimeout(() => { const el = document.getElementById(id); if (el) { el.focus(); if (end && el.setSelectionRange) { const n = el.value.length; el.setSelectionRange(n, n); } } }, 30);

  /* The top-bar question. The top bar keeps its draft text in SQ.state.askQuestion on every keystroke, so a draft must not be taken as a
     question: only a submit of the top-bar search form (seen here in the capture phase, before the top bar's own handler) counts. */
  A.topSubmit = false;
  document.addEventListener('submit', (e) => { if (e.target && e.target.getAttribute && e.target.getAttribute('role') === 'search') A.topSubmit = true; }, true);
  A.consume = () => {
    if (!A.topSubmit) return;
    const v = SQ.state.askQuestion;
    if (v == null) return;
    A.topSubmit = false;
    SQ.state.askQuestion = null;
    const q = typeof v === 'string' ? v : (v.q || v.text || v.question || '');
    if (typeof v === 'object' && v.context) SQ.state.askContext = v.context;
    if (q) A.submit(q, { fresh: true, from: A.fromLabel() });
  };
  /* for other pages: A.ask('question') opens Ask and answers it */
  A.ask = (q) => { SQ.state.askQuestion = String(q || '').trim(); A.topSubmit = true; if (/^#Ask$/.test(location.hash)) SQ.redraw(); else SQ.go('Ask'); };

  A.copy = (text, key) => {
    const done = () => { A.copied = key; SQ.redraw(); setTimeout(() => { if (A.copied === key) { A.copied = ''; SQ.redraw(); } }, 1800); };
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(text).then(done, () => legacyCopy(text, done)); return; }
    } catch (_) { /* fall through */ }
    legacyCopy(text, done);
  };
  function legacyCopy(text, done) {
    try { const ta = document.createElement('textarea'); ta.value = text; ta.setAttribute('readonly', ''); ta.style.cssText = 'position:fixed;left:-9999px'; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); done(); } catch (_) { /* nothing more to try */ }
  }

  /* ---------- headline grammar: [Action] [Item] for [Who] · [context] ---------- */
  A.headline = (ins) => {
    const seg = ins.segment || {}, products = (SQ.data.scope.products || []);
    const prod = seg.product ? ((products.find((p) => p.id === seg.product) || {}).label || '') : '';
    const persona = seg.persona || (ins.persona_ids || [])[0];
    const who = persona ? (WHO[persona] || SQ.personaLabel(persona).toLowerCase()) : 'all users';
    const screen = ins.screen_label || '';
    let a = 'Investigate', b = screen, tail = '';
    if (ins.class === 'ux_friction') { a = 'Rewrite'; b = screen + ' labels'; }
    else if (ins.class === 'behavior_pattern' || ins.class === 'natural_exit') { a = 'Keep'; tail = ' screen as is'; }
    else if (ins.scope === 'segment') { a = 'Fix'; if (prod && /^checkout/i.test(screen)) b = prod + ' checkout'; }
    let ctx = '';
    if (ins.scope === 'burst') {
      const m = String(ins.segment_text || '').match(/([A-Z][a-z]{2} \d+) (\d\d:\d\d) to (\d\d:\d\d) UTC/);
      ctx = m ? m[1] + ', ' + m[2] + '\u2013' + m[3] + ' UTC' : '';
    }
    return { a, b, c: tail + ' for ' + who, ctx, text: a + ' ' + b + tail + ' for ' + who + (ctx ? ' \u00b7 ' + ctx : ''), who };
  };

  A.trust = () => {
    const g = (SQ.data.agents || []).find((x) => String(x.tier) === '0');
    return g ? { text: 'Data: ' + g.sub, color: g.status === 'warn' || g.status === 'fail' ? '#F9AB00' : '#1E8E3E' } : { text: '', color: '#1E8E3E' };
  };

  /* ---------- one answer, ready for the takeaway-card template ---------- */
  A.model = (entry) => {
    if (!entry) return null;
    SQ.problems();   // stamps the stable P1, P2 ... labels
    const D = SQ.data;
    const refs = entry.refs || [];
    const ins = refs.filter((r) => r.type === 'insight').map((r) => SQ.insight(r.id)).filter(Boolean)[0] || null;
    const sev = ins ? ins.severity : 'plain';
    const focus = focusColor(sev);
    const m = { id: entry.id, q: entry.question, text: entry.answer, ins, sev, focus, isIns: !!ins, isPlain: !ins, refs: refs.map((r) => r.label).filter(Boolean) };
    m.persona = 'All users';
    m.win = entry.viz ? 'Last 7 days' : 'Last 30 days';
    m.problem = ins && ins.severity !== 'healthy' ? (ins.__p || '') : '';
    m.hasProblem = !!m.problem;
    m.sevLabel = ins ? ({ critical: 'Critical', warning: 'Warning', healthy: 'Healthy' }[ins.severity] || '') : '';
    m.sevBg = sev === 'critical' ? '#FCE8E6' : sev === 'warning' ? '#FEF7E0' : '#E6F4EA';
    m.sevFg = sev === 'critical' ? '#C5221F' : sev === 'warning' ? '#B06000' : '#137333';
    m.money = ins && ins.impact && ins.impact.per_week_value > 0 ? SQ.money(ins.impact.per_week_value) : '';
    m.hasMoney = !!m.money;
    m.tags = ins ? ['AI', 'Calculated'] : ['Calculated'];
    m.hasAI = !!ins;
    m.when = 'Data up to ' + SQ.asOf();
    m.sessions = ins ? SQ.fmt(ins.n_sessions) : '';
    m.hasSessions = !!ins && ins.n_sessions != null;
    const conf = ins && ins.confidence != null ? (ins.confidence >= 0.75 ? 3 : ins.confidence >= 0.5 ? 2 : 1) : 0;
    m.confBars = [1, 2, 3].map((i, k) => ({ h: 7 + k * 4, c: i <= conf ? BLUE : '#DADCE0' }));
    m.hasConf = conf > 0;
    m.confLabel = ['', 'Low confidence', 'Medium confidence', 'High confidence'][conf];
    m.head = { a: '', b: '', c: '', ctx: '' };
    m.drivers = []; m.bars = []; m.stats = []; m.para = ''; m.hasWhy = false; m.hasBig = false; m.chartTitle = ''; m.chartNote = ''; m.legendA = ''; m.legendB = '';
    m.hypothesis = '';
    if (ins) {
      const h = A.headline(ins);
      m.head = h; m.headText = h.text; m.persona = cap1(h.who);
      m.para = entry.answer;
      const diag = ins.diagnosis || {};
      const sum = firstSentence(diag.summary || ins.summary || '');
      m.hasWhy = !!sum;
      m.why = sum;
      m.whySub = ((ins.causes || [])[0] || {}).why || '';
      m.hasWhySub = !!m.whySub;
      m.whyTag = diag.source === 'gemini' || diag.source === 'cached' ? 'AI' : 'Calculated';
      m.whyIsAI = m.whyTag === 'AI';
      const sig = (ins.signals || [])[0], fact = (ins.facts || [])[0] || '';
      const pm = fact.match(/(\d+(?:\.\d+)?)%/);
      if (sig) {
        m.hasBig = true; m.big = pctText(sig.value); m.barW = (sig.value * 100).toFixed(1) + '%';
        m.hasTick = sig.reference != null; m.tickL = ((sig.reference || 0) * 100).toFixed(1) + '%';
        m.evText = fact ? fact.replace(/^\d+(?:\.\d+)?%\s*/, '').replace(/versus/, 'vs') : '';
        m.drivers = (ins.signals || []).map((s) => ({ label: ({ drop_off: 'Leave at this step', rage: 'Repeated taps', error: 'Errors' })[s.metric] || cap1(String(s.metric).replace(/_/g, ' ')), a: (s.value * 100).toFixed(1) + '%', b: ((s.reference || 0) * 100).toFixed(1) + '%', ratio: (s.ratio >= 10 ? Math.round(s.ratio) : Number(s.ratio).toFixed(1)) + '\u00d7', vals: pctText(s.value) + ' vs ' + pctText(s.reference), value: s.value, ref: s.reference }));
        m.legendA = cap1(h.who); m.legendB = cap1(ins.compared_with || 'everyone else');
        m.chartTitle = 'What drives it';
      } else if (pm) {
        m.hasBig = true; m.big = pm[1] + '%'; m.barW = Math.min(100, Number(pm[1])) + '%'; m.hasTick = false; m.tickL = '0%';
        m.evText = fact.replace(pm[0], '').replace(/^\s+/, '');
      } else if (fact) { m.evText = fact; }
      m.hasEv = m.hasBig || !!m.evText;
    } else {
      const sentence = firstSentence(entry.answer);
      let headline = sentence, rest = entry.answer.slice(sentence.length).trim();
      if (headline.length > 70) { const k = headline.search(/[;:]/); if (k > 20) { rest = (headline.slice(k + 1).trim() + ' ' + rest).trim(); headline = headline.slice(0, k); } }
      m.head = { a: '', b: '', c: headline.replace(/\.$/, ''), ctx: '' };
      m.headText = m.head.c;
      m.para = rest;
      const ref0 = refs[0] || {};
      if (entry.viz && entry.viz.type === 'sankey') {
        const v = entry.viz, src = v.source || {}, total = src.value || (v.branches || []).reduce((s, b) => s + b.value, 0) || 1;
        const tone = (t) => (t === 'negative' ? RED : t === 'positive' ? BLUE : GREY);
        m.bars = (v.branches || []).map((b, i) => ({ name: b.label, v: Math.round(b.value / total * 100) + '%', w: (b.value / total * 100).toFixed(1) + '%', c: tone(b.tone), ls: b.tone === 'negative' ? 'font-weight: 500; color: #202124' : 'color: #3C4043', n: SQ.fmt(b.value) + ' ' + (v.unit || 'sessions'), note: b.call + (b.note ? ': ' + b.note : '') }));
        m.chartTitle = 'Where the ' + SQ.fmt(total) + ' ' + (v.unit || 'sessions') + ' went';
        m.chartNote = v.subtitle || '';
        m.persona = ((v.ticket || {}).persona && !/eligible/i.test(v.ticket.persona)) ? v.ticket.persona : 'All users';
        m.hypothesis = ((v.ticket || {}).hypothesis) || '';
        m.focus = BLUE;
        m.hasSessions = true; m.sessions = SQ.fmt(total);
      } else if (ref0.id === 'hotspot' && D.hotspot) {
        const sp = D.hotspot.spots.slice().sort((a, b) => b[3] - a[3]), mx = sp[0][3] || 1;
        const dup = {}; sp.forEach((s) => { dup[s[4]] = (dup[s[4]] || 0) + 1; });
        m.bars = sp.map((s, i) => ({ name: s[4] + (dup[s[4]] > 1 ? (s[1] < 50 ? ' (upper)' : ' (lower)') : ''), v: SQ.fmt(s[3]), w: (s[3] / mx * 100).toFixed(1) + '%', c: i === 0 ? RED : GREY, ls: i === 0 ? 'font-weight: 500; color: #202124' : 'color: #3C4043', n: '' }));
        m.chartTitle = 'Where people tap repeatedly on ' + D.hotspot.screen;
        m.chartNote = D.hotspot.note || '';
        m.focus = RED;
      } else if (ref0.id === 'health') {
        const tiles = ((SQ.view().health || {}).tiles || []);
        m.stats = tiles.map((t) => ({ v: t.value, label: t.label, note: t.sub, c: t.status === 'critical' ? RED : '#202124' }));
        m.chartTitle = 'Data health';
      } else {
        const c = D.meta.counts || {};
        m.stats = [{ v: SQ.fmt(c.events), label: 'events', note: '', c: '#202124' }, { v: SQ.fmt(c.sessions), label: 'sessions', note: '', c: '#202124' }, { v: SQ.fmt(c.users), label: 'users', note: '', c: '#202124' }];
        m.chartTitle = 'The sample';
      }
    }
    const goData = !ins && (!entry.viz && (refs[0] || {}).id !== 'hotspot');
    m.linkHref = goData ? 'DataSources.dc.html' : 'Journeys.dc.html'; m.linkLabel = goData ? 'Open Data sources' : 'Open in Journeys';
    m.hasPara = !!m.para; m.hasDrivers = m.drivers.length > 0; m.hasBars = m.bars.length > 0; m.hasStats = m.stats.length > 0; m.hasHyp = !!m.hypothesis;
    m.hasChartNote = !!m.chartNote; m.hasCtx = !!m.head.ctx; m.hasRefs = m.refs.length > 0 && m.isPlain;
    m.scope = m.persona + ' \u00b7 ' + m.win;
    const tr = A.trust(); m.trust = tr.text; m.trustColor = tr.color; m.hasTrust = !!tr.text;
    return m;
  };

  A.textOf = (m) => [m.headText, m.text, m.isIns && m.big ? 'Evidence: ' + m.big + ' ' + m.evText : '', ...m.drivers.map((d) => d.label + ': ' + d.vals), ...m.bars.map((b) => b.name + ': ' + b.v + (b.n ? ' (' + b.n + ')' : '')), ...m.stats.map((s) => s.label + ': ' + s.v), '', 'Sample data (synthetic), data up to ' + SQ.asOf() + '.'].filter((x) => x !== '' || true).join('\n').replace(/\n{3,}/g, '\n\n');
  A.threadText = (th) => [th.title, ''].concat(...th.turns.filter((u) => !u.pending).map((u) => { const e = u.eid && A.entry(u.eid); return ['Q: ' + u.q, e ? A.textOf(A.model(e)) : REFUSAL_HEAD + '. ' + REFUSAL_TEXT, '']; })).join('\n');

  /* ---------- the conversation, for the page ---------- */
  A.suggestions = (th) => {
    const asked = new Set(((th && th.turns) || []).map((u) => u.eid));
    const rest = entries().filter((e) => !asked.has(e.id));
    return rest.sort((a, b) => (b.chip ? 1 : 0) - (a.chip ? 1 : 0)).map((e) => e.question);
  };
  const dayStart = (t) => { const d = new Date(t); d.setHours(0, 0, 0, 0); return d.getTime(); };
  A.groups = () => {
    const q = A.search.trim().toLowerCase();
    const list = A.threads().filter((t) => !q || t.title.toLowerCase().includes(q) || t.turns.some((u) => u.q.toLowerCase().includes(q)));
    const today = dayStart(Date.now());
    const label = (t) => { const d = Math.round((today - dayStart(t.at)) / 864e5); return d <= 0 ? 'Today' : d === 1 ? 'Yesterday' : d <= 7 ? 'Last 7 days' : 'Earlier'; };
    const order = ['Pinned', 'Today', 'Yesterday', 'Last 7 days', 'Earlier'], map = {};
    list.forEach((t) => { const k = t.pinned ? 'Pinned' : label(t); (map[k] = map[k] || []).push(t); });
    return order.filter((k) => map[k]).map((k) => ({ label: k, items: map[k] }));
  };
  A.threadChip = (th) => {
    const first = th.turns.map((u) => u.eid && A.entry(u.eid)).filter(Boolean)[0];
    const m = first ? A.model(first) : null;
    return { scope: m ? m.persona + ' \u00b7 ' + (first.viz ? '7d' : '30d') : 'No answer', problem: m ? m.problem : '' };
  };

  /* ---------- export as slides ---------- */
  A.answersForDeck = () => {
    const cands = [A.cur()].concat(A.threads()).filter(Boolean);
    for (const th of cands) {
      const ids = []; th.turns.forEach((u) => { if (u.eid && !u.pending && !ids.includes(u.eid)) ids.push(u.eid); });
      if (ids.length) return { th, title: th.title, models: ids.map((id) => A.model(A.entry(id))), note: '' };
    }
    const top = SQ.problems()[0], e = (top && A.entryForInsight(top.id)) || entries()[0];
    return e ? { th: null, title: e.question, models: [A.model(e)], note: 'No question asked yet. These slides show the top problem for the current scope.' } : { th: null, title: 'Squint', models: [], note: 'No answers to export.' };
  };
  A.deck = () => {
    const src = A.answersForDeck(), D = SQ.data, c = D.meta.counts || {};
    const first = src.models[0];
    const bars = (rows, max, cols) => rows.map((r, i) => ({ name: r[0], v: r[1], w: (r[2] / max * 100).toFixed(1) + '%', c: i === 0 ? cols : GREY, ls: i === 0 ? 'font-weight: 500; color: #202124' : 'color: #3C4043' }));
    const slides = [];
    const stats = (m) => {
      const out = [];
      if (m.isIns && m.hasBig) {
        out.push({ v: m.big, label: m.evText.replace(/\.$/, ''), c: m.sev === 'critical' ? RED : '#202124' });
        m.drivers.slice(1, 3).forEach((d) => out.push({ v: pctText(d.value), label: d.label.toLowerCase() + ', vs ' + pctText(d.ref) + ' for ' + (m.legendB || 'everyone else').toLowerCase(), c: '#202124' }));
        if (out.length < 3 && m.hasSessions) out.push({ v: m.sessions, label: 'sessions in the finding', c: '#202124' });
      } else if (m.bars.length) {
        m.bars.slice(0, 3).forEach((b) => out.push({ v: b.n ? b.n.split(' ')[0] : b.v, label: b.name.toLowerCase(), c: '#202124' }));
      } else m.stats.slice(0, 3).forEach((s) => out.push({ v: s.v, label: s.label + (s.note ? ' \u00b7 ' + s.note : ''), c: s.c }));
      if (out.length < 3 && !out.some((s) => s.c === RED) && m.isIns && m.sev === 'critical') out[0].c = RED;
      return out.slice(0, 3);
    };
    const scopeLine = (m) => m.scope + ' \u00b7 data up to ' + SQ.asOf() + ' \u00b7 sample data (synthetic)';
    const head = (m) => ({ headA: m.head.a, headB: m.head.b, headC: m.head.c, headSub: m.head.ctx });
    if (first) {
      const st = stats(first);
      slides.push({ key: 'sum', title: 'Summary', kind: 'Takeaway + ' + st.length + ' numbers', eyebrow: src.title + ' \u00b7 Summary', ...head(first), sub: first.head.ctx || first.scope, isSummary: true, isChart: false, stats: st, hasStats: st.length > 0,
        whyTag: first.hasWhy && first.whyIsAI ? 'Why \u00b7 AI' : 'Answer \u00b7 Calculated', summaryLine: first.hasWhy ? first.why : first.text, bars: bars(first.drivers.length ? first.drivers.map((d) => [d.label, d.vals.split(' ')[0], d.value * 100]) : first.bars.map((b) => [b.name, b.v, parseFloat(b.w)]), 100, first.focus), accent: '#202124', chart: first.focus, scopeLine: scopeLine(first) });
      src.models.forEach((m, i) => {
        const rows = m.drivers.length ? m.drivers.map((d) => [d.label, pctText(d.value), d.value * 100]) : m.bars.map((b) => [b.name, b.v, parseFloat(b.w)]);
        const mx = m.drivers.length ? Math.max(100, ...rows.map((r) => r[2])) : 100;
        slides.push({ key: 'a' + i, title: m.headText, kind: 'Answer ' + (i + 1) + (rows.length ? ' \u00b7 bar chart' : ''), eyebrow: src.title + ' \u00b7 Answer ' + (i + 1), ...head(m), sub: m.head.ctx || m.scope, isSummary: false, isChart: true, stats: [],
          whyTag: m.hasWhy && m.whyIsAI ? 'Why \u00b7 AI' : 'Answer \u00b7 Calculated', why: m.hasWhy ? m.why : firstSentence(m.text), whySub: m.hasWhy ? (m.whySub || m.text) : (m.para || ''),
          chartTitle: m.drivers.length ? 'What drives it, share of sessions' : (m.chartTitle || 'What the data says'), bars: bars(rows, mx, m.focus),
          chartNote: m.drivers.length ? 'Compared with ' + (m.legendB || 'everyone else').toLowerCase() + ': ' + m.drivers.map((d) => pctText(d.ref)).join(', ') + '.' : (m.chartNote || (rows.length ? '' : m.text)), accent: '#202124', chart: m.focus, scopeLine: scopeLine(m) });
      });
    }
    const read = c.sessions_in_window || 0, held = c.sessions_quarantined || 0;
    slides.push({ key: 'app', title: 'Evidence and data notes', kind: 'Appendix', eyebrow: src.title + ' \u00b7 Appendix', headA: 'How', headB: 'these numbers', headC: 'were made', headSub: '', sub: SQ.fmt(read) + ' sessions in the window \u00b7 data up to ' + SQ.asOf(), isSummary: false, isChart: true, stats: [],
      whyTag: 'Method \u00b7 Calculated', why: 'Numbers are counted from the sample\u2019s events.', whySub: (D.meta.value_assumption || '') + ' The Why lines are an AI reading of the same numbers: check the evidence.',
      chartTitle: 'Sessions read and set aside', bars: [{ name: 'Sessions read', v: SQ.fmt(read), w: '100%', c: GREY, ls: 'color: #3C4043' }, { name: 'Sessions set aside', v: SQ.fmt(held), w: (read ? held / read * 100 : 0).toFixed(1) + '%', c: '#9AA0A6', ls: 'color: #3C4043' }],
      chartNote: (A.trust().text || '') + '. ' + (D.meta.dataset_label || 'Sample dataset (synthetic)') + '.', accent: '#9AA0A6', chart: '#9AA0A6', scopeLine: 'All users \u00b7 ' + (D.meta.window ? D.meta.window.start + ' to ' + D.meta.window.end : '') + ' \u00b7 sample data (synthetic)' });
    slides.forEach((s, i) => { s.n = i + 1; s.on = !A.off[s.key]; s.scopeShort = s.scopeLine.split(' · ').slice(0, 2).join(' · ') + ' · synthetic'; });
    const inc = slides.filter((s) => s.on);
    slides.forEach((s) => { s.pos = s.on ? inc.indexOf(s) + 1 : s.n; s.count = inc.length || slides.length; });
    return { slides, title: src.title, note: src.note, models: src.models };
  };
  A.deckText = (deck, include) => {
    const L = ['# ' + deck.title, '_Squint \u00b7 sample data (synthetic) \u00b7 data up to ' + SQ.asOf() + '_', ''];
    const list = include.filter((s) => A.appendix || s.key !== 'app');
    list.forEach((s, i) => {
      L.push('## Slide ' + (i + 1) + ': ' + (s.headA + ' ' + s.headB + ' ' + s.headC).replace(/\s+/g, ' ').trim(), '_' + s.eyebrow + '_');
      if (s.sub) L.push(s.sub);
      (s.stats || []).forEach((t) => L.push('- ' + t.v + ' ' + t.label));
      if (s.isChart || s.isSummary) { if (s.why) L.push(s.whyTag + ': ' + s.why); if (s.summaryLine) L.push(s.whyTag + ': ' + s.summaryLine); if (s.whySub) L.push(s.whySub); }
      if (s.isChart) { if (s.chartTitle) L.push(s.chartTitle + ':'); s.bars.forEach((b) => L.push('- ' + b.name + ': ' + b.v)); if (s.chartNote) L.push(s.chartNote); }
      if (A.notes && deck.models.length && s.key !== 'app') { const m = deck.models[s.key === 'sum' ? 0 : Number(s.key.slice(1))]; if (m) L.push('Speaker notes: ' + m.text); }
      L.push(s.scopeLine, '');
    });
    return L.join('\n');
  };
  A.download = (name, text, type) => {
    try {
      const url = URL.createObjectURL(new Blob([text], { type: type || 'text/markdown' }));
      const a = document.createElement('a'); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1500);
    } catch (_) { A.copy(text, 'export'); }
  };

  /* ---------- Weekly brief: optional "Rewrite with Gemini" wording, off unless the server has BRIEF_AI_ENABLED=1.
     The three number tiles, finding titles and owners always stay the ones code computed; only the headline, the lead
     sentence and the per-finding "why" line are swapped for the server's verified rewrite. See docs/brief-ai-endpoint.md. */
  A.briefAi = { statusChecked: false, status: false, loading: false, error: '', result: null, key: '' };
  const briefKey = () => SQ.scope.range + '|' + SQ.scope.platform + '|' + SQ.scope.persona;
  A.ensureBriefAiStatus = () => {
    if (A.briefAi.statusChecked) return;
    A.briefAi.statusChecked = true;
    fetch('/api/brief-ai/status').then((r) => r.json()).then((b) => { A.briefAi.status = !!(b && b.enabled); SQ.redraw(); })
      .catch(() => { /* leave status false: the button simply does not show */ });
  };
  A.rewriteBrief = (ids, again) => {
    if (A.briefAi.loading || !ids.length) return;
    const key = briefKey();
    A.briefAi.loading = true; A.briefAi.error = ''; SQ.redraw();
    fetch('/api/brief-ai', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ range: SQ.scope.range, platform: SQ.scope.platform, persona: SQ.scope.persona, ids: ids.slice(0, 3), again: !!again }) })
      .then((r) => r.json().then((body) => ({ ok: r.ok, body })).catch(() => ({ ok: false, body: null })))
      .then(({ ok, body }) => {
        A.briefAi.loading = false;
        if (ok && body && body.source === 'gemini') { A.briefAi.result = body; A.briefAi.key = key; A.briefAi.error = ''; }
        else { A.briefAi.result = null; A.briefAi.error = (body && body.reason) || 'The AI did not answer. The standard wording stays.'; }
        SQ.redraw();
      })
      .catch(() => { A.briefAi.loading = false; A.briefAi.result = null; A.briefAi.error = 'The AI did not answer. The standard wording stays.'; SQ.redraw(); });
  };
  A.useStandardBrief = () => { A.briefAi.result = null; A.briefAi.error = ''; SQ.redraw(); };

  A.brief = () => {
    const D = SQ.data, v = SQ.view(), P = SQ.problems(), top = P[0] || null;
    const kpi = (id) => (v.kpis || []).find((k) => k.id === id) || null;
    const crit = P.filter((i) => i.severity === 'critical').length, warn = P.filter((i) => i.severity === 'warning').length;
    const year = new Date(D.meta.as_of + 'T00:00:00Z').getUTCFullYear();
    const conv = kpi('conversion'), risk = kpi('value_at_risk');
    const delta = (k, fmt, unit, goodUp) => { if (!k || k.prev == null || k.value == null) return { t: '', c: '#5F6368' }; const d = k.value - k.prev; if (Math.abs(d) < 1e-9) return { t: 'no change', c: '#5F6368' }; return { t: signed(d, fmt) + unit, c: (d > 0) === goodUp ? '#137333' : '#C5221F' }; };
    const cd = delta(conv, (x) => x.toFixed(1), ' pts', true), rd = delta(risk, (x) => SQ.money(x), '', false);
    const nums = [
      { label: 'Sign-up completion', value: conv ? SQ.pct1(conv.value) : 'n/a', note: cd.t, nc: cd.c },
      { label: 'Value at risk', value: risk ? SQ.money(risk.value) + '/wk' : 'n/a', note: rd.t, nc: rd.c },
      { label: 'Open problems', value: String(P.length), note: crit + ' critical \u00b7 ' + warn + ' warning', nc: '#5F6368' }
    ].map((n, i) => ({ ...n, style: i < 2 ? 'padding: 16px 20px; border-right: 1px solid #E8EAED' : 'padding: 16px 20px', noteStyle: 'font-size: 12px; color: ' + n.nc }));
    const owner = (i) => (i.class === 'ux_friction' ? 'Design' : /technical/.test(i.class) ? 'Engineering' : 'Product');
    const item = (i, n) => {
      const h = A.headline(i), money = i.impact && i.impact.per_week_value > 0 ? ' About ' + SQ.money(i.impact.per_week_value) + ' a week.' : '';
      return { id: i.id, n, headA: h.a, headB: h.b, headC: h.c, ctx: h.ctx, hasCtx: !!h.ctx, owner: owner(i), why: ((i.facts || [])[0] || firstSentence((i.diagnosis || {}).summary)) + money, text: h.text };
    };
    const todo = P.slice(0, 3).map((i, k) => item(i, k + 1));
    const keep = (v.insight_ids || []).map((id) => SQ.insight(id)).filter((i) => i && i.severity === 'healthy').slice(0, 2).map((i, k) => item(i, k + 1));
    const notes = D.meta.dataset_label || 'Sample dataset (synthetic)';
    const comboN = SQ.scope.persona === 'all' || SQ.scope.persona === 'unregistered' ? 1 : (SQ.scope.persona.split('+').length);
    const isCombo = comboN > 1;
    const topWho = top ? SQ.whoOf(top) : '';
    const topPersonaId = top && top.segment ? top.segment.persona : null;
    const lead = top ? firstSentence((top.diagnosis || {}).summary || top.summary || '') : 'Nothing is flagged for this scope.';
    const th = top ? A.headline(top) : null;
    const out = {
      kicker: 'Squint \u00b7 Recommendations \u00b7 ' + SQ.personaLabel(SQ.scope.persona) + ' \u00b7 ' + SQ.rangeDates() + ', ' + year,
      has: !!top, hA: th ? th.a : 'Nothing', hB: th ? th.b : 'needs attention', hC: th ? th.c : 'this week', lead, leadAI: !!top && (((top.diagnosis || {}).source) === 'gemini' || ((top.diagnosis || {}).source) === 'cached'),
      nums, todo, hasTodo: todo.length > 0, keep, hasKeep: keep.length > 0, notes,
      isCombo, comboN, topWho, topPersonaId, showCombo: isCombo && !!topWho && !!topPersonaId
    };
    out.text = ['# Recommendations', out.kicker, '', th ? th.text : 'Nothing needs attention this week.', lead, '', ...nums.map((n) => n.label + ': ' + n.value + (n.note ? ' (' + n.note + ')' : '')), '', 'What to do this week, and why', ...(todo.length ? todo.map((t) => t.n + '. ' + t.text + ' [' + t.owner + ']\n   ' + t.why) : ['Nothing urgent.']), '', 'What to leave alone', ...(keep.length ? keep.map((t) => '- ' + t.text + '. ' + t.why) : ['- Nothing listed for this scope.']), '', 'Data notes: ' + notes].join('\n');

    /* AI-rewrite overlay: only applied when a verified result exists for this exact view and these exact finding ids
       (an older result for a different scope or combo selection is never shown). Owners and number tiles are untouched. */
    const rw = A.briefAi.result;
    out.rewriteIds = todo.map((t) => t.id);
    const rwMatch = !!rw && A.briefAi.key === briefKey() && JSON.stringify(rw.ids) === JSON.stringify(out.rewriteIds);
    if (!rwMatch && rw) { A.briefAi.result = null; }        // scope moved on since the rewrite: drop it rather than show a stale one
    out.aiRewritten = rwMatch;
    if (rwMatch) {
      out.hA = ''; out.hB = rw.headline; out.hC = '';
      out.lead = rw.sub; out.leadAI = true;
      out.todo = todo.map((t, i) => (rw.drivers[i] ? { ...t, why: rw.drivers[i] } : t));
      out.aiNotice = rw.notice;
    }
    out.showRewrite = A.briefAi.status && !out.isCombo && out.hasTodo;
    out.rewriting = A.briefAi.loading;
    out.hasAiError = !rwMatch && !!A.briefAi.error;
    out.aiError = A.briefAi.error;
    return out;
  };
  window.addEventListener('resize', () => { if (/^#DeckSlide/.test(location.hash)) SQ.redraw(); });
})();
