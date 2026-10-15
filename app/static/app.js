(function () {
  'use strict';
  // Plain DOM building only: no innerHTML anywhere, so data can never become markup.
  const NAME = window.PRODUCT_NAME || 'Dashboard';
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const $ = (id) => document.getElementById(id);
  const VIEWS = [['settings', 'Onboarding'], ['overview', 'Overview'], ['journeys', 'Journeys'], ['friction', 'Friction'], ['cohorts', 'Cohorts'], ['ask', 'Ask'], ['brief', 'Brief']];
  const NAV_ICON = {
    overview: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z', brief: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h6', journeys: 'M3 12h4l3-8 4 16 3-8h4',
    friction: 'M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
    cohorts: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8',
    ask: 'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z',
    settings: 'M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6',
  };
  const SPARKLE = 'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z';
  const GEAR ='M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z';
  const RANGE = { '24h': { label: '24H', name: 'Last 24 hours', days: 1, hours: 24 }, '7d': { label: '7 Days', name: 'Last 7 days', days: 7, hours: 168 }, '30d': { label: '30 Days', name: 'Last 30 days', days: 30, hours: 100000 } };
  const EXIT = { ux: ['UX / UI friction', 'warn'], language: ['Language overload', 'pos'], technical: ['Technical bug', 'crit'], natural: ['Natural exit', 'muted'] };
  const SEVLABEL = { critical: 'Critical', warning: 'Warning', healthy: 'Healthy' };
  const CLASSLABEL = { technical_bug: 'Technical bug', ux_friction: 'UX / UI friction', language_cognitive_overload: 'Confusing wording', natural_exit: 'Natural exit', behavior_pattern: 'Expected behavior pattern', unclassified_needs_review: 'Needs review' };
  // a raw fraction such as 0.0464 in any text the data supplies is shown as a percentage (4.6%)
  const pctText = (t) => (t == null ? t : String(t).replace(/(?<![\d.$])0\.(\d{3,4})(?!\d|\.\d)/g, (m) => (parseFloat(m) * 100).toFixed(1).replace(/\.0$/, '') + '%'));
  const classLabel = (k) => (Object.hasOwn(CLASSLABEL, k) ? CLASSLABEL[k] : String(k).replace(/_/g, ' '));
  // how an insight's diagnosis is described: one place so the card, the drawer and the ticket agree
  function diagState(i) {
    const dg = i.diagnosis || {};
    const status = dg.status || 'pending', src = dg.source || null;
    if (status === 'failed' || src === 'unclassified') return 'failed';
    if (status !== 'done' && status !== 'cached') return 'pending';
    if (src === 'rules') return 'rules';
    return status === 'cached' || src === 'cached' ? 'cached' : 'ai';
  }
  const HINT = { unclassified_needs_review: 'needs review', technical_fault: 'technical fault', technical_bug_or_ux_friction: 'technical bug or UX friction', ux_friction: 'UX friction', language_cognitive_overload: 'confusing wording', behavior_pattern: 'behavior pattern', natural_exit: 'natural exit' };
  const TONE = { critical: 'crit', warning: 'warn', healthy: 'ok', positive: 'pos' };
  const TONENAME = { critical: 'Critical', warning: 'Warning', healthy: 'Seamless', positive: 'Positive friction' };
  const COHORT_COLOR = { accent: 'var(--accent)', info: 'var(--pos-dot)', warn: 'var(--warn-dot)', crit: 'var(--crit-dot)', muted: 'var(--natural)' };
  const OWNERS = ['Unassigned', 'Product', 'Engineering', 'Design'];
  const STOP = new Set(['the', 'a', 'an', 'is', 'are', 'of', 'to', 'do', 'does', 'we', 'why', 'what', 'which', 'who', 'in', 'on', 'at', 'and', 'for', 'with', 'show', 'me', 'tell', 'about', 'how', 'did', 'was', 'were', 'it', 'this', 'that', 'my', 'our', 'can', 'you', 'i']);

  const NAME_KEY = 'squint-user-name';
  const readName = () => {
    let n = null;
    try { n = localStorage.getItem(NAME_KEY); } catch (e) { /* storage blocked: fall through */ }
    if (n && n.trim()) return n.trim().slice(0, 24);
    n = Math.random() < 0.5 ? 'Jane' : 'John';
    try { localStorage.setItem(NAME_KEY, n); } catch (e) { /* fine without storage */ }
    return n;
  };
  /* Everything that belongs to one loaded dataset lives in perDataset(): switching datasets overwrites all of it in one go, so no filter,
     selection, answer, drafted finding, brief or currency choice from one dataset can show up in the other. The few fields below the
     spread belong to the page, not to a dataset (the visitor's name, the server's feature switches, the registry of samples). */
  const perDataset = () => ({ bq: false, fc: {}, personas: [], platform: 'all', range: '7d', persona: 'all', compare: false, usd: false, briefOpen: false, briefRw: {}, briefRwBusy: false, briefRwMsg: '', briefRwUntil: 0, journey: null, skMode: 'friction', skView: 'chart', skProduct: 'all', mapJourney: null, mapTouched: false, frSig: 0, feedAll: false, flowPick: null,
    set: { flow: false, flowLoading: false, flowResult: null, verified: false, opened: false }, status: {}, owners: {}, drafted: {}, copied: {}, askAssign: {}, ask: null, askText: '', drawer: null, opener: null, dirty: false });
  const state = { userName: readName(), data: null, ui: {}, registry: [], flows: {}, flowIds: [], srcEvents: {}, bqMeta: null, dsId: 'wallet', dsBusy: null, dsMsg: '', gen: 0, view: 'overview', briefAI: null, askSeq: 0, askAIStatus: null, askAIStatusPending: null, ...perDataset() };

  /* ---------- helpers ---------- */
  /* Plain-language layer: one place that turns internal wording into everyday business wording, for text on screen and in copied
     text. It runs on every text node built by h() and on aria-label, title and placeholder. Agent names (Watchdog, Diagnostic Agent,
     Semantic Agent, Telemetry Guardian) are deliberately left alone. Add or remove pairs here, nowhere else. */
  const cap = (s, offset) => (offset === 0 ? s.charAt(0).toUpperCase() + s.slice(1) : s);
  const PLAIN = [
    [/(\d) s\b/g, '$1s'],
    [/\bAssumed\b/g, 'Estimated'], [/\bassumed\b/g, 'estimated'],
    [/natural behavioral pattern for this group\./g, 'natural behavioral pattern.'],
    [/This distinct behavior is not accompanied by any signs of technical issues or user friction, indicating a natural behavioral pattern\./g, 'Error rates are low: expected behavior, not a technical issue.'],
    [/([^“”":.;]+?): ([^,:“”]+?), ([^,:“”]+?) drop off far more often than everyone else/g, (m, a, b, c, o) => cap(`${b} users buying ${c} leave at ${a} far more often than other users`, o)],
    [/([^“”":.;]+?): ([^,:“”]+?) drop off far more often than everyone else/g, (m, a, b, o) => cap(`${b} users leave at ${a} far more often than other users`, o)],
    [/([^“”":.;]+?): exits jump from (\d+%) to (\d+%) between (\d\d:\d\d) and (\d\d:\d\d) UTC on ([A-Z][a-z]{2} \d{1,2})/g, (m, a, p, q, f, to, d, o) => cap(`people leaving at ${a} jumped from ${p} to ${q} on ${d} (${f} to ${to} UTC)`, o)],
    [/([^“”":.;]+?): a steady drop-off, the same for every (?:persona|user group)/g, (m, a, o) => cap(`a steady share of people leave at ${a}, whatever their user group`, o)],
    [/Critical blind spots/g, 'Serious problems'], [/Event mapping coverage/g, 'Tracking coverage'], [/Schema match/g, 'Events we could read'],
    [/of events fully mapped/g, 'of events fully understood'], [/Trackers firing/g, 'Trackers working'], [/Sessions held out/g, 'Sessions set aside'],
    [/inside a telemetry fault window/g, 'during a tracking problem'], [/\btelemetry\b/g, 'tracking'], [/Blind spot/g, 'Hidden problem'], [/Time window/g, 'Sudden spike'],
    [/Behavioral friction/g, 'People struggling'], [/Technical fault/g, 'Tracking or system fault'], [/technical fault/g, 'tracking or system fault'], [/\bDead taps\b/g, 'Taps that did nothing'], [/\bRage burst\b/g, 'Burst of repeated taps'], [/loop, rage and get stuck/g, 'loop, tap repeatedly and get stuck'], [/held out/g, 'set aside'], [/Probable causes/g, 'Likely reasons'], [/Probable cause/g, 'Likely reason'],
    [/Data confidence: /g, 'How sure we are: '], [/Release change/g, 'App update'], [/Technical bug/g, 'App problem'], [/UX \/ UI friction/g, 'Hard to use'],
    [/Language overload/g, 'Confusing wording'], [/\bRage-click\b/g, 'Repeated-click'], [/\brage[- ]?(click|tap)s\b/gi, 'repeated $1s'], [/\brage[- ]?(click|tap)\b/gi, 'repeated $1'],
    [/\bdead taps\b/g, 'taps that did nothing'], [/\bdead tap\b/g, 'tap that did nothing'], [/\bPersonas\b/g, 'User groups'], [/\bpersonas\b/g, 'user groups'],
    [/\bPersona\b/g, 'User group'], [/\bpersona\b/g, 'user group'], [/Findings are computed over the whole period, so there is no daily series/g, 'Based on the whole period, so there is no daily trend'],
  ];
  /* Money display. Amounts are stored in PHP; the USD view divides by one fixed reference rate (not live) so it is a reading aid, not a quote. */
  const PHP_PER_USD = 58;
  const usdText = (php) => { const u = php / PHP_PER_USD; return '$' + (u >= 10 ? fmt(Math.round(u)) : u.toFixed(2)); };
  const PHP_AMOUNT = /(?:PHP ?|₱ ?)(\d[\d,]*(?:\.\d+)?)/g;
  const plain = (x) => { let o = String(x); for (const [re, to] of PLAIN) o = o.replace(re, to); for (const [re, to] of state.extraPlain || []) o = o.replace(re, to); if (state.usd) o = o.replace(PHP_AMOUNT, (m, n) => usdText(parseFloat(n.replace(/,/g, '')))); return o; };
  const PLAIN_ATTRS = new Set(['aria-label', 'title', 'placeholder']);
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'style') el.style.cssText = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : (PLAIN_ATTRS.has(k) && typeof v === 'string' ? plain(v) : v));
    }
    for (const kid of kids.flat(2)) {
      if (kid == null || kid === false) continue;
      el.append(kid.nodeType ? kid : document.createTextNode(plain(kid)));
    }
    return el;
  }
  function s(tag, attrs, ...kids) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) { if (v != null && v !== false) el.setAttribute(k, v); }
    for (const kid of kids.flat(2)) { if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid))); }
    return el;
  }
  const icon = (d, size = 16, sw = 2) => s('svg', { viewBox: '0 0 24 24', width: size, height: size, fill: 'none', stroke: 'currentColor', 'stroke-width': sw, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' }, s('path', { d }));
  const fmt = (n) => Number(n).toLocaleString('en-US');
  const dot = (c) => h('span', { class: 'dot d-' + c, 'aria-hidden': 'true' });
  const slug = (t) => String(t).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const announce = (t) => { $('announce').textContent = ''; setTimeout(() => { $('announce').textContent = t; }, 30); };
  const D = () => state.data;
  const UI = () => state.ui || {};   // the loaded dataset's vocabulary and icons (datasets.json)
  const currency = () => ({ PHP: '₱', USD: '$' }[D().meta.currency] || (D().meta.currency + ' '));
  const money = (n) => (state.usd ? '$' + fmt(Math.round(n / PHP_PER_USD)) : currency() + fmt(Math.round(n)));
  const persLabel = (id) => (D().scope.personas.find((p) => p.id === id) || { label: id }).label;
  const visiblePersonas = () => D().scope.personas.filter((p) => p.id !== 'unknown' && p.id !== 'fraudster');
  const jDef = (id) => D().scope.journeys.find((j) => j.id === id);
  const jName = (id) => (jDef(id) ? jDef(id).name : id);
  const stepDef = (j, sid) => ((jDef(j) || { steps: [] }).steps.find((x) => x.id === sid));
  const stepName = (j, sid) => (stepDef(j, sid) ? stepDef(j, sid).name : sid);
  const insightById = (id) => D().insights.find((i) => i.id === id);
  const where = (i) => jName(i.journey) + ' · ' + stepName(i.journey, i.step);
  const age = (hrs) => (hrs < 1 ? 'less than an hour ago' : hrs < 24 ? hrs + ' h ago' : Math.round(hrs / 24) === 1 ? '1 day ago' : Math.round(hrs / 24) + ' days ago');
  const dateFmt = (iso, o) => new Date(iso + 'T00:00:00Z').toLocaleDateString('en-US', Object.assign({ timeZone: 'UTC' }, o));
  function rangeLabel() {
    const end = D().meta.as_of;
    const days = RANGE[state.range].days;
    if (days === 1) return dateFmt(end, { month: 'short', day: 'numeric', year: 'numeric' });
    const start = new Date(new Date(end + 'T00:00:00Z').getTime() - (days - 1) * 86400000).toISOString().slice(0, 10);
    const sameMonth = start.slice(0, 7) === end.slice(0, 7);
    return dateFmt(start, { month: 'short', day: 'numeric' }) + ' – ' + (sameMonth ? new Date(end + 'T00:00:00Z').getUTCDate() : dateFmt(end, { month: 'short', day: 'numeric' })) + ', ' + end.slice(0, 4);
  }
  const timeframeText = () => `${RANGE[state.range].name}, ${rangeLabel()}`;
  function view() {
    const v = D().views;
    if (state.personas.length > 1) return mergedView(state.personas);
    return v[`${state.range}|${state.platform}|${state.persona}`] || null;
  }
  /* Several user groups at once: there is no precomputed view for every combination, so one is built from each group's own view.
     Sessions and exits add up; rates are weighted by sessions; findings are the union of the groups' findings; money is summed over
     the distinct findings (not per group, which would count a shared finding twice). Comparisons with the previous period are not
     shown for combined groups. */
  const mergeCache = new Map();
  function mergedView(ids) {
    const key = `${state.range}|${state.platform}|${[...ids].sort().join('+')}`;
    if (!mergeCache.has(key)) {
      const parts = ids.map((id) => D().views[`${state.range}|${state.platform}|${id}`]).filter(Boolean);
      mergeCache.set(key, parts.length > 1 ? combineViews(parts) : (parts[0] || null));
    }
    return mergeCache.get(key);
  }
  function combineViews(parts) {
    const w = parts.map((p) => p.sessions || 0), W = w.reduce((a, b) => a + b, 0) || 1, sum = (a) => a.reduce((x, y) => x + y, 0);
    const wavg = (get) => sum(parts.map((p, i) => (Number(get(p)) || 0) * w[i])) / W;
    const insIds = [...new Set(parts.flatMap((p) => p.insight_ids))], ins = insIds.map(insightById).filter(Boolean);
    const open = ins.filter((i) => i.severity !== 'healthy');
    const crit = open.filter((i) => i.severity === 'critical').length, risk = sum(open.map((i) => (i.impact || {}).per_week_value || 0));
    const stepOf = (p, jid, sid) => (((p.journeys.find((x) => x.id === jid) || { steps: [] }).steps.find((x) => x.id === sid)) || null);
    const kpis = parts[0].kpis.map((k) => {
      const at = (p) => p.kpis.find((x) => x.id === k.id) || k, flat = (v) => (k.series || []).map(() => v);
      if (k.id === 'conversion') return { ...k, value: wavg((p) => at(p).value), prev: wavg((p) => at(p).prev), series: (k.series || []).map((_, d) => wavg((p) => (at(p).series || [])[d])), prev_series: (k.prev_series || []).map((_, d) => wavg((p) => (at(p).prev_series || [])[d])), sub: 'Weighted across the selected groups' };
      if (k.id === 'blind_spots') return { ...k, value: crit, prev: crit, series: flat(crit), prev_series: flat(crit), no_compare: true, sub: 'Distinct findings across the selected groups' };
      if (k.id === 'value_at_risk') return { ...k, value: risk, prev: risk, series: flat(risk), prev_series: flat(risk), no_compare: true, sub: 'Estimated value, counted once per finding' };
      return { ...k };
    });
    const journeys = parts[0].journeys.map((j) => ({ id: j.id, steps: j.steps.map((st) => {
      const ms = parts.map((p) => stepOf(p, j.id, st.id)).filter(Boolean), sessions = sum(ms.map((x) => x.sessions)), exits = sum(ms.map((x) => x.exits));
      const dom = ms.slice().sort((a, b) => b.exits - a.exits)[0] || st;
      return { ...dom, id: st.id, sessions, exits, low_sample: sessions < 20, tag: dom.tag && /exit/.test(dom.tag) ? `${Math.round(100 * exits / Math.max(1, sessions))}% exit` : dom.tag };
    }) }));
    const signals = {};
    Object.keys(parts[0].signals || {}).forEach((jid) => {
      signals[jid] = {};
      Object.keys(parts[0].signals[jid]).forEach((sid) => {
        const ws = parts.map((p) => (stepOf(p, jid, sid) || { sessions: 0 }).sessions), tot = sum(ws) || 1;
        signals[jid][sid] = (parts[0].signals[jid][sid] || []).map((_, k) => +(sum(parts.map((p, n) => (((p.signals[jid] || {})[sid] || [])[k] || 0) * ws[n])) / tot).toFixed(1));
      });
    });
    const loops = {};
    parts.forEach((p) => Object.entries(p.loops || {}).forEach(([jid, list]) => { loops[jid] = loops[jid] || []; (list || []).forEach((l) => { const m = loops[jid].find((x) => x.from === l.from && x.to === l.to); if (m) m.count += l.count; else loops[jid].push({ ...l }); }); }));
    const exits = {}; parts.forEach((p) => Object.entries(p.exits || {}).forEach(([k, n]) => { exits[k] = (exits[k] || 0) + n; }));
    const R0 = parts[0].rhythm, rhythm = { ...R0, natural: R0.natural.map((_, d) => sum(parts.map((p) => p.rhythm.natural[d] || 0))), frustrated: R0.frustrated.map((_, d) => sum(parts.map((p) => p.rhythm.frustrated[d] || 0))), note: '' };
    const names = [...new Set(parts.flatMap((p) => (p.cohorts.items || []).map((c) => c.name)))];
    const cohorts = { items: names.map((nm) => { const its = parts.map((p) => (p.cohorts.items || []).find((c) => c.name === nm)); const first = its.find(Boolean);
      return { ...first, share: Math.round(sum(its.map((c, i) => (c ? c.share : 0) * w[i])) / W), is_new: its.some((c) => c && c.is_new) }; }), note: 'Weighted across the selected groups.' };
    return { ...parts[0], sessions: W, insight_ids: insIds, kpis, journeys, signals, loops, exits, rhythm, cohorts, blind: null };
  }
  const selectedLabels = () => (state.personas.length ? state.personas.map(persLabel).join(' + ') : 'All users');
  function setPersonas(ids) {
    if (ids.length > 1 && state.personas.length < 2 && state.skMode !== 'group') state.skMode = 'group';   // comparing: open the Sankey by user group
    state.personas = ids; state.persona = ids.length === 1 ? ids[0] : 'all';
    buildPersonaSeg(); renderView(); renderNav();
    announce('Showing ' + selectedLabels());
  }
  // User group filter: pick one, several, or none (none = everyone). "All Users" clears the choice.
  function buildPersonaSeg() {
    const box = $('persona'), opts = [['all', 'All Users'], ...visiblePersonas().map((p) => [p.id, p.label])];
    box.replaceChildren(...opts.map(([id, label]) => {
      const on = id === 'all' ? state.personas.length === 0 : state.personas.includes(id);
      return h('button', { type: 'button', 'data-v': id, 'aria-pressed': String(on), style: `--pc:${LENS_COLOR[id] || LENS_COLOR.all}`, onclick: () => {
        if (id === 'all') return setPersonas([]);
        // Unregistered is a choice on its own (a different journey); the registered groups can be combined.
        const regs = state.personas.filter((x) => x !== 'unregistered');
        const cur = id === 'unregistered' ? (state.personas.includes(id) ? [] : [id]) : (regs.includes(id) ? regs.filter((x) => x !== id) : [...regs, id]);
        setPersonas(cur);
        const again = box.querySelector(`[data-v="${id}"]`); if (again) again.focus();
      } }, label);
    }));
  }
  const statusOf = (id) => state.status[id] || 'open';
  function activeFaults() { return (D().guardian.faults || []).filter((f) => f.hours_ago <= RANGE[state.range].hours); }
  const scroller = (label, child) => h('div', { class: 'scroller', tabindex: '0', role: 'region', 'aria-label': label }, child);

  /* ---------- focus restore (re-rendering a view must not drop the keyboard user) ---------- */
  let pendingFocus = null;
  const fk = (key) => ({ 'data-fk': key });
  function rerender(focusKey) { pendingFocus = focusKey || null; renderView(); }
  function applyFocus() {
    if (!pendingFocus) return;
    const el = document.querySelector(`[data-fk="${pendingFocus}"]`);
    pendingFocus = null;
    if (el) el.focus();
  }

  /* ---------- theme ---------- */
  function applyTheme(t) {
    document.documentElement.dataset.theme = t;
    const SUN = 'M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 1v3M12 20v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M1 12h3M20 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1';
    const MOON = 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z';
    const b = $('theme');
    b.replaceChildren(icon(t === 'dark' ? SUN : MOON, 20, 1.8));
    const label = t === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
    b.setAttribute('aria-label', label); b.title = label;
    try { localStorage.setItem('theme', t); } catch (e) { /* storage blocked: the theme still applies for this visit */ }
  }
  function initTheme() {
    let t = null;
    try { t = localStorage.getItem('theme'); } catch (e) { /* ignore */ }
    applyTheme(t === 'dark' ? 'dark' : 'light');
    $('theme').addEventListener('click', () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
  }

  /* ---------- chrome: header, filters, nav, footer ---------- */
  function buildSeg(box, opts, key, label) {
    box.replaceChildren(...opts.map(([v, text, aria]) => h('button', {
      type: 'button', role: 'radio', 'data-v': v, 'aria-checked': String(state[key] === v), 'aria-label': aria || null, tabindex: state[key] === v ? '0' : '-1',
      onclick: () => setFilter(key, v),
      onkeydown: (e) => {
        if (!['ArrowRight', 'ArrowLeft', 'ArrowDown', 'ArrowUp'].includes(e.key)) return;
        e.preventDefault();
        const i = opts.findIndex((o) => o[0] === state[key]);
        const step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : opts.length - 1;
        const next = opts[(i + step) % opts.length][0];
        setFilter(key, next);
        box.querySelector(`[data-v="${next}"]`).focus();
      },
    }, text)));
  }
  function syncSeg(box, key) {
    box.querySelectorAll('button').forEach((b) => { const on = b.dataset.v === state[key]; b.setAttribute('aria-checked', String(on)); b.tabIndex = on ? 0 : -1; });
  }
  function buildFilters() {
    const m = D().meta;
    const multi = m.platforms.length > 1;
    $('g-platform').hidden = !multi;
    if (multi) buildSeg($('platform'), [['all', 'All platforms'], ...m.platforms.map((p) => [p, p === 'app' ? 'App' : p === 'web' ? 'Web' : p])], 'platform');
    buildSeg($('range'), Object.keys(RANGE).filter((r) => D().scope.ranges.includes(r)).map((r) => [r, RANGE[r].label, RANGE[r].name]), 'range');
    buildPersonaSeg();
  }
  function setFilter(key, v) {
    if (state[key] === v) return;
    state[key] = v;
    syncSeg($(key), key);
    renderView(); renderNav();
    announce(`Showing ${key === 'range' ? RANGE[v].name : key === 'persona' ? (v === 'all' ? 'all users' : persLabel(v)) : v}`);
  }
  function renderNav() {
    const v = view();
    const open = v ? v.insight_ids.map(insightById).filter((i) => i && i.severity === 'critical' && statusOf(i.id) === 'open').length : 0;
    const items = VIEWS.map(([id, label]) => {
      const on = state.view === id;
      return h('a', { class: 'navi', href: '#' + (SLUG[id] || id), 'aria-current': on ? 'page' : null, 'data-view': id },
        h('span', { class: 'ico' }, icon(NAV_ICON[id], 16)), h('span', { class: 'lbl' }, label),
        id === 'overview' && open > 0 ? h('span', { class: 'badge', 'aria-label': open + ' serious open findings' }, String(open)) : null);
    });
    items.splice(1, 0, h('div', { class: 'navsep', 'aria-hidden': 'true' }));
    $('navlist').replaceChildren(...items);
  }
  function renderChrome() {
    const m = D().meta;
    $('src').replaceChildren();   // owner's call: no data label under the nav (the Overview greeting, the Brief source line and Onboarding still say it is synthetic)
    $('foot').textContent = `${NAME} · Built for AI Builder Cup 2026 · Gemini on Google Cloud`;
  }

  /* ---------- routing ---------- */
  const SLUG = { settings: 'onboarding' };   // the tab is called Onboarding, so its address is #onboarding; #settings (the internal id) still works
  function routeFromHash() {
    let id = location.hash.replace('#', '');
    if (id === 'onboarding') id = 'settings';
    return VIEWS.some((v) => v[0] === id) ? id : null;
  }
  function onHash() {
    const r = routeFromHash();
    if (!r || r === state.view) return;
    state.view = r;
    closeDrawer(true);
    renderNav(); renderView();
    window.scrollTo(0, 0);
    announce('Showing ' + VIEWS.find((v) => v[0] === r)[1]);
  }

  /* ---------- shared pieces ---------- */
  function currencySwitch() {
    const note = `Converted at a fixed reference rate of ${PHP_PER_USD} PHP = 1 USD. It is not a live exchange rate.`;
    return h('div', { class: 'switchrow cur-row', title: note }, h('span', { id: 'cur-label' }, 'Show money in'),
      h('div', { class: 'seg', role: 'group', 'aria-labelledby': 'cur-label' }, [[false, '₱ PHP'], [true, '$ USD']].map(([usd, label]) =>
        h('button', { type: 'button', ...fk('cur-' + (usd ? 'usd' : 'php')), 'aria-pressed': String(state.usd === usd), onclick: () => { if (state.usd === usd) return; state.usd = usd; rerender('cur-' + (usd ? 'usd' : 'php')); announce(usd ? 'Showing money in US dollars at a reference rate' : 'Showing money in Philippine pesos'); } }, label))),
      state.usd ? h('span', { class: 'cur-note' }, `${PHP_PER_USD} PHP = 1 USD (reference rate)`) : null);
  }
  function pageHead(title, withCompare, withRange = false, withCurrency = false) {
    return h('div', { class: 'page-head' },
      h('div', {}, withRange ? h('span', { class: 'eyebrow' }, rangeLabel()) : null, h('h1', { class: 'title', id: 'page-title' }, title)),
      withCurrency ? currencySwitch() : null,
      withCompare ? h('div', { class: 'switchrow' }, h('span', { id: 'cmp-label' }, 'Compare to previous period'),
        h('button', { type: 'button', class: 'switch', role: 'switch', 'aria-checked': String(state.compare), 'aria-labelledby': 'cmp-label', ...fk('compare'),
          onclick: () => { state.compare = !state.compare; rerender('compare'); } })) : null);
  }
  /* Small "i" circle: the explanation shows on hover and keyboard focus instead of sitting under the heading. */
  let tipN = 0;
  // icons in the right half open their explanation to the left, so it never runs off the page
  const flipTip = (btn) => { const pop = btn.nextElementSibling; if (pop) pop.classList.toggle('flip', btn.getBoundingClientRect().left > window.innerWidth * 0.5); };
  function infoTip(text) {
    const id = 'itip-' + (++tipN);
    return h('span', { class: 'itip' },
      h('button', { type: 'button', class: 'itip-b', 'aria-label': 'More info', 'aria-describedby': id,
        onkeydown: (e) => { if (e.key === 'Escape') e.currentTarget.blur(); },
        onmouseenter: (e) => flipTip(e.currentTarget), onfocus: (e) => flipTip(e.currentTarget) }, 'i'),
      h('span', { class: 'itip-pop', role: 'tooltip', id }, text));
  }
  // card() sees this marker: the "i" goes beside the heading, the short text (if any) stays under it.
  function subTip(short, tip) { return { tipSub: true, short, tip }; }
  /* Quoted words inside AI-written text ('payment_timeout', 'Checkout step', “Phone number”) are shown as code-style chips, so the
     names of things stand out from the sentence around them. */
  function rt(text) {
    const s = String(text == null ? '' : text), out = [], re = /(^|[\s(])(?:'([^'\n]{1,48})'|“([^”\n]{1,60})”|"([^"\n]{1,48})")(?=[\s.,;:!?)]|$)/g;
    let last = 0, m;
    while ((m = re.exec(s))) {
      const start = m.index + m[1].length;
      out.push(s.slice(last, start), h('code', { class: 'q' }, m[2] || m[3] || m[4]));
      last = start + (m[0].length - m[1].length);
    }
    out.push(s.slice(last));
    return out;
  }
  function card(label, title, sub, right, ...body) {
    const ts = sub && sub.tipSub ? sub : null;
    return h('section', { class: 'card', 'aria-label': label },
      h('div', { class: 'card-h' }, h('div', {}, ts ? h('div', { class: 'ttl' }, h('h2', {}, title), infoTip(ts.tip)) : h('h2', {}, title),
        ts ? (ts.short ? h('span', { class: 'sub' }, ts.short) : null) : (sub ? h('span', { class: 'sub' }, sub) : null)), right || null), ...body);
  }
  /* A card whose body is folded away until asked for (Onboarding page: dataset contents, agent pipeline, intent translation). */
  const foldOpen = {};   // remembers which keyed fold cards the visitor opened or closed, so a re-render does not reset them
  function foldCard(label, title, sub, ...body) { return foldCardKeyed(null, label, title, sub, ...body); }
  function foldCardKeyed(o, label, title, sub, ...body) {
    return h('section', { class: 'card fold', 'aria-label': label },
      h('details', o ? { open: foldOpen[o.key] != null ? foldOpen[o.key] : o.open, ontoggle: (e) => { foldOpen[o.key] = e.target.open; } } : {}, h('summary', {}, h('span', { class: 'fold-l' }, o && o.icon ? h('span', { class: 'fold-i', 'aria-hidden': 'true' }, icon(o.icon, 20, 1.7)) : null, h('span', { class: 'fold-t' }, h('h2', {}, title), sub ? h('span', { class: 'sub' }, sub) : null)), h('span', { class: 'fold-c', 'aria-hidden': 'true' }, icon('M6 9l6 6 6-6', 18))),
        h('div', { class: 'fold-b' }, ...body)));
  }
  function noData() {
    return h('div', { class: 'card' }, h('h2', {}, 'No data for this combination'), h('p', { class: 'sub' }, 'The results file has no view for this timeframe and persona. Pick another filter.'));
  }
  function journeyTabs(v) {
    const js = v.journeys.filter((j) => jDef(j.id));
    if (!js.length) return { cur: null, tabs: null };
    if (!js.some((j) => j.id === state.journey)) state.journey = js[0].id;
    const tabs = js.length > 1 ? h('div', { class: 'jtabs', role: 'group', 'aria-label': 'Journey' }, js.map((j) =>
      h('button', { type: 'button', class: 'jtab', 'data-j': j.id, 'aria-pressed': String(j.id === state.journey), ...fk('jt-' + j.id), onclick: () => { state.journey = j.id; rerender('jt-' + j.id); } }, jName(j.id)))) : null;
    return { cur: js.find((j) => j.id === state.journey), tabs };
  }
  const CAUSE_CLS = (c) => (c.type === 'technical' ? 'tech' : c.type === 'release' ? 'pos' : 'warn');
  const CAUSE_LABEL = { behavior: 'Behavioral friction', technical: 'Technical fault', release: 'Release change' };
  const legendDot = (c, t) => h('span', {}, dot(c), t);

  /* ---------- Ask ---------- */
  const tokens = (t) => t.toLowerCase().split(/[^a-z0-9]+/).filter((w) => w && !STOP.has(w)).map((w) => (w.length > 3 && w.endsWith('s') ? w.slice(0, -1) : w));
  function matchAsk(q) {
    const user = [...new Set(tokens(q))];
    if (!user.length) return null;
    let best = null;
    for (const a of D().ask || []) {
      const pool = new Set([...tokens(a.question), ...(a.keywords || []).flatMap(tokens)]);
      const hit = user.filter((w) => pool.has(w)).length;
      const ratio = hit / user.length;
      const ok = (hit >= 2 && ratio >= 0.5) || (hit >= 1 && user.length === 1);
      if (ok && (!best || hit > best.hit || (hit === best.hit && ratio > best.ratio))) best = { a, hit, ratio };
    }
    return best ? best.a : null;
  }
  const delay = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));
  async function unmatchedAsk(q, seq) {
    const refusal = "I can only answer questions about this dataset's findings.";
    const update = (answer, extra = {}) => { if (seq !== state.askSeq) return; state.ask = { q, ai: true, answer, loading: false, ...extra }; rerender('ask-input'); announce(answer); };
    try {
      if (state.askAIStatus == null) {
        if (!state.askAIStatusPending) state.askAIStatusPending = fetch('/api/ask/status', { method: 'GET', headers: { Accept: 'application/json' }, credentials: 'same-origin' })
          .then(async (status) => status.ok ? (await status.json()).enabled === true : false).catch(() => false);
        state.askAIStatus = await state.askAIStatusPending; state.askAIStatusPending = null;
      }
      if (!state.askAIStatus) return update(refusal, { none: true });
      if (seq === state.askSeq) { state.ask = { q, ai: true, loading: true }; rerender('ask-input'); announce('Checking this dataset'); }
      const response = await fetch('/api/ask', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ question: q, dataset: state.dsId }) });
      if (!response.ok) return update(refusal, { none: true });
      const data = await response.json();
      if (typeof data.answer !== 'string' || data.grounded !== true || (data.source !== 'gemini' && data.source !== 'cache')) return update(refusal, { none: true });   // 'cache' is a saved earlier Gemini answer, verified the same way
      update(data.answer, { refs: Array.isArray(data.refs) ? data.refs : [] });
    } catch (_) { state.askAIStatus = false; update(refusal, { none: true }); }
  }
  async function doAsk(q) {
    q = q.trim(); const seq = ++state.askSeq;
    state.askText = '';
    if (!q) { state.ask = { q: '', none: true, empty: true }; rerender('ask-input'); return; }
    state.ask = { q, loading: true }; rerender('ask-input');
    for (let i = 1; i <= q.length; i++) {
      if (seq !== state.askSeq) return;
      state.askText = q.slice(0, i); const field = $('ask'); if (field) field.value = state.askText;
      if (i < q.length) await delay(600 / q.length);
    }
    if (seq !== state.askSeq) return;
    const a = matchAsk(q);
    if (a) { state.ask = { q, a }; rerender('ask-input'); announce(a.answer); }
    else { state.ask = { q, none: true }; rerender('ask-input'); await unmatchedAsk(q, seq); }
  }
  function flowRibbon(x1, t1, b1, x2, t2, b2) { const xm = (x1 + x2) / 2; return `M${fin(x1)} ${fin(t1)} C${fin(xm)} ${fin(t1)} ${fin(xm)} ${fin(t2)} ${fin(x2)} ${fin(t2)} L${fin(x2)} ${fin(b2)} C${fin(xm)} ${fin(b2)} ${fin(xm)} ${fin(b1)} ${fin(x1)} ${fin(b1)} Z`; }
  let gradN = 0;
  function renderFlowSankey(nodes, links, options = {}) {
    const source = nodes.find((n) => n.side === 'source') || nodes[0];
    const branches = nodes.filter((n) => n !== source);
    const W = 940, nodeW = 18, leftX = 24, rightX = 430, topPad = 74, rowMin = 84, gapY = 14, bottomPad = 16;
    const total = Math.max(1, source.value), scale = Math.min(230, Math.max(120, branches.length * 80)) / total;
    // each branch gets a row tall enough for its label; its bar is as tall as its share
    const heights = branches.map((n) => Math.max(10, n.value * scale));
    const rows = heights.map((hh) => Math.max(rowMin, hh + 12));
    const H = topPad + rows.reduce((a, b) => a + b, 0) + gapY * Math.max(0, branches.length - 1) + bottomPad;
    const positions = new Map(); let y = topPad;
    branches.forEach((n, k) => { positions.set(n.id, { y: y + (rows[k] - heights[k]) / 2, h: heights[k], rowY: y, rowH: rows[k] }); y += rows[k] + gapY; });
    const sourceH = Math.min(heights.reduce((a, b) => a + b, 0), Math.max(24, total * scale)), mid = topPad + (H - topPad - bottomPad) / 2, sourceY = mid - sourceH / 2;
    positions.set(source.id, { y: sourceY, h: sourceH });
    const toneColor = { positive: '#0A8F5B', negative: '#E5483B', neutral: '#8E8E93' };
    const uid = 'ask-g' + (++gradN), defs = s('defs', {});
    defs.append(s('linearGradient', { id: 'ask-src', x1: 0, y1: 0, x2: 0, y2: 1 }, s('stop', { offset: '0%', 'stop-color': '#3B9BFF' }), s('stop', { offset: '100%', 'stop-color': '#0071E3' })));
    const paths = []; let sourceOffset = sourceY;
    links.forEach((link, k) => {
      const a = positions.get(link.from), b = positions.get(link.to), node = branches.find((n) => n.id === link.to);
      if (!a || !b || !node) return;
      const hh = Math.max(3, node.value * scale * (sourceH / Math.max(1, heights.reduce((x, y2) => x + y2, 0))));
      const col = toneColor[node.tone] || toneColor.neutral, gid = `${uid}-${k}`;
      const grad = s('linearGradient', { id: gid, gradientUnits: 'userSpaceOnUse', x1: leftX + nodeW, x2: rightX, y1: 0, y2: 0 });
      grad.append(s('stop', { offset: '0%', 'stop-color': '#0071E3', 'stop-opacity': '.55' }), s('stop', { offset: '100%', 'stop-color': col, 'stop-opacity': '.62' }));
      defs.append(grad);
      paths.push(s('path', { d: flowRibbon(leftX + nodeW, sourceOffset, sourceOffset + hh, rightX, b.y, b.y + Math.min(b.h, Math.max(hh, 3))), class: 'ask-link sk-el', style: `fill:url(#${gid})`, 'data-branch': node.id, 'aria-hidden': 'true' }));
      sourceOffset += hh;
    });
    const chip = (x, yy, text, color) => { const w = text.length * 7.4 + 18; return [s('rect', { x, y: yy - 14, width: w, height: 22, rx: 11, fill: color, 'fill-opacity': .14 }), s('text', { x: x + 9, y: yy + 1, class: 'ask-node-value', style: `fill:${color}` }, text)]; };
    const svg = s('svg', { class: 'ask-sankey-svg', viewBox: `0 0 ${W} ${H}`, role: 'group', 'aria-label': options.label || 'Measured Sankey flow from the dataset' }, defs,
      s('g', {}, ...paths),
      s('rect', { x: leftX, y: sourceY, width: nodeW, height: sourceH, rx: 9, class: 'ask-source-node' }),
      s('text', { x: leftX, y: 22, class: 'ask-node-title big' }, source.label),
      s('text', { x: leftX, y: 46, class: 'ask-node-value big' }, `${fmt(source.value)} ${source.unit || 'sessions'}`),
      s('text', { x: leftX, y: 64, class: 'ask-node-sub' }, source.share_of_active != null ? `${(source.share_of_active * 100).toFixed(1)}% of active sessions` : ''),
      ...branches.map((n) => {
        const p = positions.get(n.id), share = source.value ? n.value / source.value * 100 : 0, col = toneColor[n.tone] || toneColor.neutral, tx = rightX + nodeW + 16, cy = p.rowY + p.rowH / 2;
        const desc = wrapName(plain(n.note || n.call || ''), 58), top = cy - (24 + 14 * desc.length) / 2;
        const g = s('g', { class: 'ask-branch', tabindex: '0', role: 'group', 'aria-label': `${n.label}: ${fmt(n.value)} sessions, ${share.toFixed(1)}% of this cohort. ${plain(n.note || n.call || '')}` });
        g.append(s('rect', { x: rightX, y: p.y, width: nodeW, height: p.h, rx: 6, class: 'ask-branch-node tone-' + n.tone, 'data-branch': n.id }));
        g.append(s('text', { x: tx, y: top + 14, class: 'ask-node-title big' }, n.label));
        g.append(...chip(tx, top + 36, `${fmt(n.value)} sessions · ${share.toFixed(1)}%`, col));
        desc.forEach((ln, k) => g.append(s('text', { x: tx, y: top + 58 + 14 * k, class: 'ask-node-sub' }, ln)));
        const highlight = (active) => paths.forEach((path) => { path.classList.toggle('dim', !!active && path.getAttribute('data-branch') !== n.id); path.classList.toggle('active', !!active && path.getAttribute('data-branch') === n.id); });
        g.addEventListener('pointerenter', () => highlight(true)); g.addEventListener('pointerleave', () => highlight(false));
        g.addEventListener('focus', () => highlight(true)); g.addEventListener('blur', () => highlight(false));
        return g;
      }));
    return svg;
  }
  function askSankey(viz) {
    const nodes = [{ ...viz.source, id: 'source', side: 'source' }, ...viz.branches.map((b) => ({ ...b, side: 'branch' }))];
    const links = viz.branches.map((b) => ({ from: 'source', to: b.id, value: b.value }));
    const chart = renderFlowSankey(nodes, links, { label: `${viz.title}. ${fmt(viz.source.value)} ${viz.unit}; ${viz.subtitle}` });
    const chartWrap = h('div', { class: 'ask-flow-chart' }, chart);   // hovering only highlights the ribbon: the labels already say everything
    return h('section', { class: 'answer ask-flow', id: 'ask-flow', 'aria-label': 'Measured journey Sankey' }, h('h3', {}, viz.title), h('p', { class: 'sub' }, viz.subtitle), chartWrap);
  }
  // the hint in the empty Ask box: the file's own, else the dataset's wording, else its first prepared question
  const askPlaceholder = () => D().ask_placeholder || UI().ask_placeholder || ('Ask about this dataset' + (((D().ask || [])[0] || {}).question ? ', for example: ' + D().ask[0].question : ''));
  function askBlock() {
    const chips = (D().ask || []).filter((a) => a.chip);
    const chipLabels = UI().chip_labels || {};
    const input = h('input', { id: 'ask', ...fk('ask-input'), type: 'text', autocomplete: 'off', placeholder: askPlaceholder(), value: state.askText, oninput: (e) => { state.askText = e.target.value; },
      onkeydown: (e) => { if (e.key === 'Enter') doAsk(input.value); } });
    const out = [h('div', { class: 'askbar' }, icon(SPARKLE, 20, 1.8),
      h('label', { for: 'ask', class: 'sr' }, 'Ask about this dataset'), input, h('button', { type: 'button', class: 'btn', ...fk('ask-btn'), onclick: () => doAsk(input.value) }, 'Ask')),
    h('div', { class: 'chips', role: 'group', 'aria-label': 'Suggested questions' }, chips.map((c) => h('button', { type: 'button', class: 'chip', ...fk('chip-' + c.id), onclick: () => doAsk(c.question) }, h('span', { class: 'chip-sp' }, icon(SPARKLE, 14, 1.8)), chipLabels[c.id] || c.question)))];
    if (state.ask) {
      const k = state.ask;
      if (k.loading) {
        out.push(h('div', { class: 'answer', id: 'ask-answer', 'aria-busy': 'true' }, h('span', { class: 'q' }, 'You asked: ' + k.q), h('p', { class: 'a' }, 'Searching this dataset…')));
      } else if (k.ai && !k.none) {
        out.push(h('div', { class: 'answer', id: 'ask-answer' }, h('span', { class: 'q' }, 'You asked: ' + k.q), h('p', { class: 'a' }, k.answer), h('span', { class: 'sub' }, 'AI answer, based only on this dataset\'s results'), h('div', { class: 'refs' }, (k.refs || []).map((r) => h('button', { type: 'button', class: 'btn-line', onclick: (e) => openRef(r, e.currentTarget) }, r.label || r.id || 'View evidence')))));
      } else if (k.none) {
        out.push(h('div', { class: 'answer nomatch', id: 'ask-answer' },
          k.q ? h('span', { class: 'q' }, 'You asked: ' + k.q) : null,
          h('p', { class: 'a' }, k.empty ? "Type a question first. I can only answer questions about this dataset's findings." : "I can only answer questions about this dataset's findings."),
          h('div', { class: 'refs' }, h('span', { class: 'sub' }, 'Try:'), (D().ask || []).slice(0, 4).map((c) => h('button', { type: 'button', class: 'btn-line', ...fk('try-' + c.id), onclick: () => doAsk(c.question) }, c.question)))));
      } else {
        out.push(h('div', { class: 'answer', id: 'ask-answer' },
          h('span', { class: 'q' }, 'You asked: ' + k.q),
          h('p', { class: 'a' }, k.a.answer),
          h('span', { class: 'sub' }, 'Answered from this dataset\'s precomputed findings. Nothing is sent to a model.'),
          h('div', { class: 'refs' }, (k.a.refs || []).map((r) => h('button', { type: 'button', class: 'btn-line', onclick: (e) => openRef(r, e.currentTarget) }, r.label)))));
        if (k.a.viz && k.a.viz.type === 'sankey') out.push(askSankey(k.a.viz));
        if (k.a.viz && k.a.viz.ticket && !k.hideSnack) out.push(h('div', { class: 'ask-snack', role: 'status', 'aria-live': 'polite' }, h('span', {}, 'Ticket drafted - hypothesis, persona and evidence attached'), h('button', { type: 'button', class: 'btn-line', ...fk('ask-ticket-open'), onclick: (e) => openDrawer({ type: 'ask-ticket', ticket: k.a.viz.ticket }, e.currentTarget) }, 'Open'), h('button', { type: 'button', class: 'snack-close', 'aria-label': 'Dismiss ticket notice', onclick: () => { state.ask = { ...state.ask, hideSnack: true }; rerender('ask-input'); } }, '×')));
      }
    }
    return out;
  }
  function openRef(r, opener) {
    if (r.type === 'insight' && insightById(r.id)) openDrawer({ type: 'insight', id: r.id }, opener);
    else if (r.type === 'view') location.hash = '#' + r.id;
    else if (r.type === 'fault') location.hash = '#overview';   // Guardian faults are listed on Overview (the "active faults" pill)
  }

  /* ---------- Overview ---------- */
  const fmtKpi = (k, x) => (k.format === 'pct1' ? x.toFixed(1) + '%' : k.format === 'php_week' ? money(x) : fmt(x));
  function deltaText(k) {
    if (k.no_compare) return 'Not compared for combined groups';
    const d = k.value - k.prev;
    if (Math.abs(d) < (k.format === 'pct1' ? 0.05 : 0.5)) return 'No change vs. previous period';
    const sign = d > 0 ? '+' : '−';
    const a = Math.abs(d);
    return sign + (k.format === 'pct1' ? a.toFixed(1) + ' points' : k.format === 'php_week' ? money(a) : fmt(a)) + ' vs. previous period';
  }
  function spark(k, showPrev, color) {
    const all = k.series.concat(k.prev_series || []);
    const mn = Math.min(...all), mx = Math.max(...all), rng = (mx - mn) || 1;
    const pts = (arr) => arr.map((v, i) => (i * 140 / (arr.length - 1)).toFixed(1) + ',' + (40 - ((v - mn) / rng) * 34).toFixed(1)).join(' ');
    return s('svg', { class: 'spark', viewBox: '0 0 140 44', preserveAspectRatio: 'none', role: 'img', 'aria-label': `${k.label}, trend for ${RANGE[state.range].name.toLowerCase()}${showPrev ? ' with the previous period' : ''}` },
      showPrev && k.prev_series.length > 1 ? s('polyline', { points: pts(k.prev_series), fill: 'none', style: 'stroke:var(--ink-3)', 'stroke-width': 1.5, 'stroke-dasharray': '3 3', 'vector-effect': 'non-scaling-stroke' }) : null,
      s('polyline', { points: pts(k.series), fill: 'none', style: 'stroke:' + color, 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'vector-effect': 'non-scaling-stroke' }));
  }
  function kpiCards(v) {
    return h('section', { class: 'kpis', 'aria-label': 'Key metrics' }, v.kpis.map((k) => {
      const d = k.value - k.prev;
      const good = k.higher_is_better ? d >= 0 : d <= 0;
      const flat = Math.abs(d) < (k.format === 'pct1' ? 0.05 : 0.5);
      const unit = k.format === 'php_week' ? h('small', {}, ' /wk') : null;
      const crit = k.id === 'blind_spots' && k.value > 0;
      return h('div', { class: 'kpi' }, h('span', { class: 'k-label' }, k.label),
        h('span', { class: 'k-val ' + (crit ? 't-crit' : '') }, fmtKpi(k, k.value), unit),
        h('span', { class: 'k-delta ' + (flat ? '' : good ? 't-ok' : 't-crit') }, deltaText(k)),
        new Set(k.series).size <= 1 ? h('span', { class: 'k-flat' }, 'Whole-period figure, no daily trend') : spark(k, state.compare, k.higher_is_better ? 'var(--accent)' : k.id === 'blind_spots' ? 'var(--crit-dot)' : 'var(--warn-dot)'),
        h('span', { class: 'k-sub' }, state.compare ? `Previous: ${fmtKpi(k, k.prev)}${k.prev_label ? ' (' + k.prev_label + ')' : ''}${new Set(k.series).size <= 1 ? '' : ', dashed'}` : k.sub));
    }));
  }
  function confOf(causes) {
    if (causes.some((c) => c.quarantine && !c.resolved)) return ['Low', 'low'];
    if (causes.some((c) => c.type === 'technical' && c.fault_id && !c.resolved)) return ['Medium', 'med'];
    return ['High', 'high'];
  }
  function causeRows(v) {
    const rows = [];
    for (const id of v.insight_ids) {
      const i = insightById(id);
      if (!i || i.severity === 'healthy' || !i.causes || !i.causes.length) continue;
      const st = ((v.journeys.find((j) => j.id === i.journey) || { steps: [] }).steps.find((x) => x.id === i.step));
      rows.push({ key: i.id, title: stepName(i.journey, i.step), sub: jName(i.journey) + (i.segment_text ? ' · ' + i.segment_text : ''), tone: i.tone, insight: i, causes: i.causes,
        value: st ? `−${fmt(st.exits)} exits · ${(100 * st.exits / Math.max(1, st.sessions)).toFixed(1)}% of step` : i.segment_text, exits: st ? st.exits : 0 });
    }
    for (const f of activeFaults()) {
      if (f.metric && f.sev !== 'resolved') {
        rows.push({ key: f.id, title: f.metric.title, sub: f.metric.sub, tone: f.sev === 'critical' ? 'critical' : 'warning', insight: null, value: f.metric.value, exits: -1,
          causes: [{ type: f.metric.behType, share: 1 - f.share, title: f.metric.beh, why: f.metric.behWhy, resolved: false },
            { type: 'technical', share: f.share, title: f.cause, why: f.why, fault_id: f.id, resolved: false, quarantine: f.quarantine }] });
      }
    }
    const tech = (r) => r.causes.some((c) => c.type === 'technical' && c.fault_id && !c.resolved);
    const severityOrder = (r) => r.tone === 'critical' ? 0 : r.tone === 'warning' ? 1 : 2;
    rows.sort((a, b) => (severityOrder(a) - severityOrder(b)) || (tech(b) - tech(a)) || (b.exits - a.exits));
    return rows.slice(0, 6);
  }
  function copyNote(f, btn) {
    const text = `${f.title}: ${f.desc} Impact: ${f.impact}`;
    const done = () => { state.copied[f.id] = true; rerender(btn); announce('Note copied'); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, done); else done();
  }
  function whySection(v) {
    const faults = activeFaults();
    const act = faults.filter((f) => f.sev !== 'resolved');
    const rows = causeRows(v);
    const pill = act.length ? h('span', { class: 'pill', style: 'background:var(--crit-bg);color:var(--crit);box-shadow:none' }, dot('crit'), `${act.length} active ${act.length > 1 ? 'faults' : 'fault'}`)
      : h('span', { class: 'pill', style: 'background:var(--ok-bg);color:var(--ok);box-shadow:none' }, dot('ok'), 'All systems normal');
    const tiles = v.health.tiles.map((t) => h('div', { class: 'tile' }, h('span', { class: 't-l' }, dot({ ok: 'ok', warning: 'warn', critical: 'crit' }[t.status] || 'muted'), t.label), h('span', { class: 't-v' }, t.value), h('span', { class: 't-s' }, t.sub)));
    const rowEls = rows.map((r) => {
      const [confText, confCls] = confOf(r.causes);
      // A cause that rounds to 0% and is not a fixed fault is noise here; it stays in the drawer. Keep all if that would leave nothing.
      const shown = r.causes.filter((c) => c.resolved || Math.round(c.share * 100) >= 1);
      const sorted = (shown.length ? shown : r.causes).slice().sort((a, b) => b.share - a.share);
      const faultById = (id) => (D().guardian.faults || []).find((f) => f.id === id);
      return h('article', { class: 'cause-row' },
        h('div', { class: 'cause-l' }, h('span', { class: 'c-kind' }, dot(TONE[r.tone] || 'warn'), r.sub), h('span', { class: 'c-title' }, r.title),
          h('span', { class: 'c-val ' + 't-' + (TONE[r.tone] || 'warn') }, r.value), h('span', { class: 'conf ' + confCls }, 'Data confidence: ' + confText),
          h('div', { class: 'sharebar', 'aria-hidden': 'true' }, sorted.filter((c) => c.share > 0).map((c) => h('div', { style: `width:${(c.share * 100).toFixed(1)}%;background:${c.type === 'technical' ? 'var(--tech-dot)' : c.type === 'release' ? 'var(--pos-dot)' : 'var(--warn-dot)'}` })))),
        h('div', { class: 'cause-r' }, sorted.map((c) => {
          const f = c.fault_id ? faultById(c.fault_id) : null;
          const fkey = 'note-' + r.key + '-' + (c.fault_id || 'x');
          return h('div', { class: 'cause' + (c.resolved || c.share < 0.005 ? ' ruled' : '') },
            h('span', { class: 'pct t-' + CAUSE_CLS(c) + (c.resolved || c.share < 0.005 ? ' pct-ruled' : '') }, c.resolved || c.share < 0.005 ? 'Not the cause' : Math.round(c.share * 100) + '%'),
            h('div', { class: 'body' }, h('span', { class: 'head' }, h('span', { class: 'typechip ' + c.type }, CAUSE_LABEL[c.type] || c.type), h('b', {}, c.title)), h('span', { class: 'why', title: c.why }, c.why)),
            c.resolved ? h('span', { class: 'sub t-ok', style: 'font-weight:600' }, 'Ruled out · fixed')
              : f ? h('button', { type: 'button', class: state.copied[f.id] ? 'btn-dark btn-ok' : 'btn-dark', ...fk(fkey), onclick: () => copyNote(f, fkey) }, state.copied[f.id] ? 'Note copied' : 'Copy note for engineering')
                : r.insight ? h('button', { type: 'button', class: 'btn-line', onclick: (e) => openDrawer({ type: 'insight', id: r.insight.id }, e.currentTarget) }, 'View diagnosis') : null);
        })));
    });
    return card('Data health and technical faults', 'Why users drop off: behavior or technical fault?', subTip('', 'The badge counts Guardian faults in this time range; rows show separate drop-off findings and their likely causes.'), pill,
      h('div', { class: 'tiles' }, tiles),
      h('div', { class: 'legend' }, legendDot('warn', 'Behavioral friction (real users struggling)'), legendDot('tech', 'Technical fault (tracker, database, integration)'), legendDot('pos', 'Release change')),
      rows.length ? h('div', { class: 'cause-list' }, h('h3', { class: 'cause-list-label' }, 'Probable causes'), ...rowEls) : h('div', { class: 'empty' }, 'No unexplained drop-offs or technical faults for these filters.'));
  }
  const firstSentence = (s) => { const m = /^(.+?[.!?])(\s|$)/.exec(String(s || '').trim()); return m ? m[1] : String(s || '').trim(); };
  /* The finding template (see docs/ai-copy-template.md). Each row says who wrote it: the model from the numbers (AI), plain rules (Rules),
     or straight arithmetic on the data (Calculated). Nothing here calls Gemini: it reads the saved diagnosis. */
  function findingRows(i) {
    const ds = diagState(i), ai = ds === 'ai' || ds === 'cached', dg = i.diagnosis || {}, imp = i.impact || {};
    const reason = ai && dg.summary ? firstSentence(dg.summary)
      : ds === 'pending' ? 'Not looked at by the analyst yet.' : ds === 'failed' ? 'We could not tell. A person should look.'
      : ds === 'rules' ? (((i.causes || [])[0] || {}).title || 'Rule-based guess only.') : (((i.causes || [])[0] || {}).title || 'We cannot tell yet.');
    const step = ai && (dg.next_steps || [])[0] ? dg.next_steps[0].text : null;
    return [
      ['What we see', (i.facts || [])[0] || `${fmt(i.n_sessions)} sessions are affected.`, 'calc'],
      ['Likely reason', reason, ai ? 'ai' : 'rules'],
      step ? ['Next step', step, 'ai'] : null,
      imp.per_week_value > 0 ? ['Effect', `About ${money(imp.per_week_value)} a week (estimated value).`, 'calc'] : null,
    ].filter(Boolean);
  }
  const TAGS = { ai: ['AI', 'Written by the model from the numbers. Saved result, not a live call.'], calc: ['Calculated', 'Worked out directly from the data, no AI involved.'], rules: ['Rules', 'A simple rule picked this, not the AI.'] };
  function findingTicket(i, owner) {
    const dg = i.diagnosis || {}, rows = findingRows(i), imp = i.impact || {};
    const steps = (dg.next_steps || []).map((x) => typeof x === 'string' ? x : x.text).filter(Boolean);
    const lines = [`Title: ${i.title}`, `Owner: ${owner}`, `Priority: ${i.label}`, `Affected: ${i.segment_text || 'All users'} · ${fmt(i.n_sessions)} sessions`,
      `Impact: ${imp.per_week_value > 0 ? money(imp.per_week_value) + '/week (estimated value)' : 'Not estimated'}`, '', 'Summary:', dg.summary || i.hypothesis || rows[0]?.[1] || 'Review the attached evidence.', '', 'Evidence:',
      ...rows.map(([label, text]) => `- ${label}: ${text}`), ...(steps.length ? ['', 'Suggested next step:', `- ${steps[0]}`] : [])];
    return { owner, text: lines.join('\n') };
  }
  /* One words-only confidence label for a finding (shared by the feed cards and the "Biggest issue" block). */
  function confLabel(i) {
    const ds = diagState(i), cf = (ds === 'ai' || ds === 'cached') ? ((i.diagnosis && i.diagnosis.confidence != null) ? i.diagnosis.confidence : i.confidence) : null;
    return ds === 'pending' ? 'Not looked at yet' : ds === 'failed' ? 'Needs a person' : ds === 'rules' ? 'Rule-based, not AI' : typeof cf !== 'number' ? 'No score' : (cf >= 0.75 ? 'High' : cf >= 0.5 ? 'Medium' : 'Low') + ' confidence';
  }
  function feedSection(v) {
    const all = v.insight_ids.map(insightById).filter((i) => i && i.severity !== 'healthy');
    const open = all.filter((i) => statusOf(i.id) === 'open').sort((a, b) => ((b.impact || {}).score || 0) - ((a.impact || {}).score || 0));
    const snoozed = all.filter((i) => statusOf(i.id) === 'snoozed').length, fixed = all.filter((i) => statusOf(i.id) === 'fixed').length;
    const shown = state.feedAll ? open : open.slice(0, 3);
    const cards = shown.map((i) => {
      const t = TONE[i.tone] || 'warn';
      const techCause = (i.causes || []).find((c) => c.type === 'technical' && c.fault_id && !c.resolved);
      const owner = state.owners[i.id] || 'Unassigned';
      const ds = diagState(i), conf = confLabel(i);
      const rows = findingRows(i);
      return h('article', { class: 'ins tone-' + t, 'aria-label': i.title },
        h('div', { class: 'i-top' }, h('span', { class: 'i-lab t-' + t }, dot(t), i.label), h('span', {}, i.is_new ? h('span', { class: 'newtag' }, 'NEW') : null, ((i.impact || {}).score > 0 ? h('span', { class: 'i-imp prio', title: 'Priority: how serious, how many people, what they are worth' }, h('i', { class: 'pdot', 'aria-hidden': 'true' }), 'Priority') : null))),
        h('p', { class: 'i-body' }, i.title),
        h('div', { class: 'frows' }, rows.map(([l, txt, kind]) => h('div', { class: 'frow' },
          h('div', { class: 'fr-h' }, h('span', { class: 'fr-l' }, l), h('span', { class: 'fr-tag tag-' + kind, title: TAGS[kind][1] }, kind === 'ai' ? icon(SPARKLE, 11, 2) : null, TAGS[kind][0])),
          h('span', { class: 'fr-t' }, rt(txt))))),
        h('div', { class: 'i-bottom' },
        h('div', { class: 'facts' }, h('span', { class: 'fact' }, fmt(i.n_sessions) + ' sessions'), h('span', { class: 'fact' }, conf), h('span', { class: 'fact' }, where(i))),
        techCause && techCause.share > 0 ? h('div', { class: 'technote' }, dot('tech'), h('span', {}, h('strong', {}, 'It could also be a tracking or system fault: '), `${techCause.title} (${Math.round(techCause.share * 100)}% likely)`)) : null,
        h('span', { class: 'i-age' }, `Spotted ${age(i.detected_hours_ago)}`),
        h('div', { class: 'acts' },
          h('button', { type: 'button', class: 'btn-dark', ...fk('diag-' + i.id), onclick: (e) => openDrawer({ type: 'insight', id: i.id }, e.currentTarget) }, 'See why'),
          i.replays > 0 ? h('button', { type: 'button', class: 'btn-line', onclick: () => { state.journey = i.journey; location.hash = '#friction'; } }, icon('M6 4l14 8-14 8z', 14), `Watch ${i.replays} sessions`) : null)),
        h('div', { class: 'foot-r' },
          h('span', {}, h('label', { for: 'own-' + slug(i.id) }, 'Owner'), h('select', { id: 'own-' + slug(i.id), onchange: (e) => { state.owners[i.id] = e.target.value; announce('Owner set to ' + e.target.value); rerender('own-' + slug(i.id)); } }, OWNERS.map((o) => h('option', { value: o, selected: o === owner }, o)))),
          h('span', {}, owner !== 'Unassigned' ? h('button', { type: 'button', class: 'btn-text link', onclick: (e) => openDrawer({ type: 'insight', id: i.id, ticket: findingTicket(i, owner) }, e.currentTarget) }, state.drafted[i.id] ? 'Open ticket draft' : 'Draft ticket') : null,
            h('button', { type: 'button', class: 'btn-text snooze', onclick: () => setStatus(i, 'snoozed') }, 'Snooze a week'), h('button', { type: 'button', class: 'btn-text ok', onclick: () => setStatus(i, 'fixed') }, 'Mark fixed'))));
    });
    const healthy = v.insight_ids.map(insightById).find((i) => i && i.severity === 'healthy');
    const c = card('Agentic insight feed', 'Insight Feed', subTip((open.length > shown.length ? `Top ${shown.length} of ${open.length} open insights` : `${open.length} open ${open.length === 1 ? 'insight' : 'insights'}`), 'Ranked by priority: how serious the problem is, how many people it affects, and what each of them is worth. Rows tagged AI were written by the model from the numbers (saved results, not live). Rows tagged Calculated come straight from the data. Money values are estimates, not measured.'),
      snoozed + fixed > 0 ? h('div', { class: 'feedstatus' }, h('span', {}, `${snoozed} snoozed · ${fixed} marked fixed`), h('button', { type: 'button', class: 'btn-text link', onclick: () => { state.status = {}; rerender('feed-h'); } }, 'Restore')) : null,
      open.length ? h('div', { class: 'feed' }, cards) : h('div', { class: 'empty' }, 'All clear: no open insights. Snoozed and fixed items stay tracked by the Watchdog.'),
      open.length > 3 ? h('button', { type: 'button', class: 'btn-line', style: 'align-self:flex-start', ...fk('feed-more'), onclick: () => { state.feedAll = !state.feedAll; rerender('feed-more'); } }, state.feedAll ? 'Show only the top 3' : `Show the other ${open.length - 3} ${open.length - 3 === 1 ? 'finding' : 'findings'}`) : null,
      healthy ? h('div', { class: 'healthy-line' }, dot('ok'), h('p', {}, h('strong', {}, 'Healthy. '), healthy.title + '. ' + (healthy.summary || ''))) : null);
    const hd = c.querySelector('h2'); hd.id = 'feed-h'; hd.tabIndex = -1; hd.dataset.fk = 'feed-h';
    return c;
  }
  function setStatus(i, st) {
    state.status[i.id] = st;
    rerender('feed-h');
    renderNav();
    announce(`${i.title}: ${st === 'fixed' ? 'marked fixed' : 'snoozed for 7 days'}`);
  }
  function donutCard(v) {
    const ex = v.exits;
    const order = Object.keys(EXIT).sort((a, b) => ex[b] - ex[a]);
    const total = order.reduce((t, k) => t + ex[k], 0) || 1;
    const R = 83, C = 2 * Math.PI * R;
    let acc = 0;
    const colors = { ux: 'var(--warn-dot)', language: 'var(--pos-dot)', technical: 'var(--crit)', natural: 'var(--natural)' };
    const segs = order.filter((k) => ex[k] > 0).map((k) => {
      const len = C * ex[k] / total, mid = ((acc + len / 2) / C) * 2 * Math.PI;
      const el = s('circle', { cx: 100, cy: 100, r: R, fill: 'none', 'data-k': k, 'stroke-width': 34, style: `stroke:${colors[k]};--dx:${(Math.cos(mid) * 7).toFixed(1)}px;--dy:${(Math.sin(mid) * 7).toFixed(1)}px`, 'stroke-dasharray': `${Math.max(0, len - 2)} ${C - Math.max(0, len - 2)}`, 'stroke-dashoffset': -acc });
      el.append(s('title', {}, `${EXIT[k][0]}: ${Math.round(100 * ex[k] / total)}% (${fmt(ex[k])})`)); acc += len; return el;
    });
    const fixable = Math.round(100 * (total - ex.natural) / total);
    const rows = order.map((k) => h('div', { class: 'drow', 'data-k': k, tabindex: '0' }, h('span', { class: 'sw', style: 'background:' + colors[k] }), h('span', { class: 'l' }, EXIT[k][0]), h('b', {}, Math.round(100 * ex[k] / total) + '%'), h('span', { class: 'c' }, fmt(ex[k]))));
    const INFO = { natural: 'They finished, browsed or changed their mind. Nothing to fix, and we never try to pull them back.', technical: 'Something broke for them: an error, or taps that did nothing. Worth fixing first.',
      language: 'They sat on one screen for a long time with no error, often because the wording or the steps are confusing.', ux: 'They went back a step or hesitated, which points to a screen that is hard to use.' };
    const pop = h('div', { class: 'donut-pop', 'aria-live': 'polite' });
    const showPop = (k) => {
      if (!k || !(k in ex)) { pop.replaceChildren(h('span', { class: 'dp-hint' }, 'Hover a slice, or a row below, to see what it means.')); return; }
      pop.replaceChildren(h('span', { class: 'dp-k' }, h('i', { style: 'background:' + colors[k] }), EXIT[k][0]), h('b', { class: 'dp-n' }, Math.round(100 * ex[k] / total) + '%'),
        h('span', { class: 'dp-c' }, `${fmt(ex[k])} of ${fmt(total)} people who left`), h('p', { class: 'dp-t' }, INFO[k] || ''));
    };
    showPop(null);
    const wrap = h('div', { class: 'donutwrap' }, h('div', { class: 'donutbox', role: 'img', 'aria-label': 'Donut chart: ' + order.map((k) => EXIT[k][0] + ' ' + Math.round(100 * ex[k] / total) + '%').join(', ') },
      s('svg', { viewBox: '0 0 200 200', 'aria-hidden': 'true' }, ...segs), h('div', { class: 'mid' }, h('b', {}, fmt(total)), h('span', {}, 'exits classified'))), pop);
    const hit = (e) => { const el = e.target.closest && e.target.closest('[data-k]'); return el ? el.dataset.k : null; };
    wrap.addEventListener('mouseover', (e) => showPop(hit(e)));
    wrap.addEventListener('mouseleave', () => showPop(null));
    const drows = h('div', { class: 'drows' }, rows, h('details', { class: 'more-note' }, h('summary', {}, 'More detail'),
      h('p', { class: 'sub' }, `About ${fixable}% of the people who left ran into something we could fix. The other ${100 - fixable}% left calmly, so we leave them alone and never push them to come back.`)));
    drows.addEventListener('mouseover', (e) => showPop(hit(e))); drows.addEventListener('mouseleave', () => showPop(null));
    drows.addEventListener('focusin', (e) => showPop(hit(e))); drows.addEventListener('focusout', () => showPop(null));
    return card('Drop-off root cause', 'Why users leave', subTip('', 'Every person who left is sorted into a reason: struggling, a tracking fault, or a normal exit.'), null, wrap, drows);
  }
  function rhythmCard(v) {
    const R = v.rhythm;
    const maxT = Math.max(1, ...R.frustrated.map((f, i) => f + R.natural[i]));
    const sc = 140 / maxT;
    const mks = (i) => (R.markers || []).map((m, n) => [m, n + 1]).filter((x) => x[0].index === i);
    const faultNotes = activeFaults().filter((f) => f.metric && f.sev !== 'resolved').map((f) => f.metric.rhythmNote);
    return card('Exit rhythm', 'Natural vs. frustrated exits', subTip('', 'Each bar is one day. Natural exits are people who left calmly. Frustrated exits show trouble, such as repeated taps or errors.'),
      h('div', { class: 'legend', style: 'align-self:flex-start' }, h('span', {}, h('i', { class: 'sw', style: 'background:var(--natural)' }), 'Natural'), h('span', {}, h('i', { class: 'sw', style: 'background:var(--warn-dot)' }), 'Frustrated'), h('span', {}, h('i', { style: 'width:0;height:12px;border-left:1.5px dashed var(--tech-dot);display:inline-block' }), 'Event')),
      h('div', { class: 'rhy', role: 'img', 'aria-label': `Stacked bar chart: frustrated exits ${R.frustrated.join(', ')}; natural exits ${R.natural.join(', ')}` },
        R.frustrated.map((f, i) => h('div', { class: 'd' }, mks(i).length ? h('span', { class: 'ms', 'aria-hidden': 'true' }, mks(i).map((x) => h('span', { class: 'm' }, String(x[1]))), h('i')) : null, h('span', { class: 'v' }, String(f)), h('div', { class: 'f', style: `height:${Math.round(f * sc)}px` }), h('div', { class: 'n', style: `height:${Math.round(R.natural[i] * sc)}px` })))),
      h('div', { class: 'rlab' }, R.labels.map((l, i) => h('span', { style: i === R.labels.length - 1 ? 'color:var(--ink);font-weight:600' : '' }, l))),
      (R.markers || []).length ? h('ol', { class: 'mklist', 'aria-label': 'Chart events' }, R.markers.map((m, n) => h('li', {}, h('b', {}, String(n + 1)), ' ' + (R.labels[m.index] || '') + ': ' + m.label))) : null,
      rhythmNote(R, faultNotes));
  }
  /* Plain-language summary of the exit rhythm: one sentence always visible, the rest folded behind "More detail". */
  function rhythmNote(R, faults) {
    const tf = R.frustrated.reduce((a, b) => a + b, 0), tn = R.natural.reduce((a, b) => a + b, 0);
    if (!(tf + tn > 0) || R.frustrated.length < 2) return h('p', { class: 'sub' }, R.note);
    const peak = R.frustrated.indexOf(Math.max(...R.frustrated));
    const near = (R.markers || []).filter((m) => m.index === peak).map((m) => m.label)[0];
    const lines = [`Most of the frustrated exits started around ${R.labels[peak]}${near ? `, at the same time as “${near}”` : ''}.`, `${fmt(tn)} other people left normally.`];
    faults.forEach((n) => {
      const m = /^(\d{4}-\d{2}-\d{2}) is also missing ([\d.]+%) of its rows/.exec(n);
      lines.push(m ? `Heads-up: about ${m[2]} of the data for ${dateFmt(m[1], { month: 'short', day: 'numeric' })} is missing because of a tracking problem, so the real number may be a little higher.` : n);
    });
    return h('div', { class: 'rhy-note' },
      h('details', { class: 'more-note' }, h('summary', {}, 'More detail'), h('ul', {}, lines.map((x) => h('li', { class: 'sub' }, x)))));
  }
  /* "How the groups compare": shown when two or more registered user groups are selected (All Users and Unregistered do not count,
     unregistered people have a different journey). Each column is one group's own view of results.json. */
  function compareCard() {
    const ids = state.personas.filter((id) => id !== 'unregistered');
    if (ids.length < 2) return null;
    const cols = ids.map((id) => {
      const vv = D().views[`${state.range}|${state.platform}|${id}`]; if (!vv) return null;
      const conv = (vv.kpis.find((k) => k.id === 'conversion') || {}).value;
      const ex = vv.exits || {}, tot = Object.values(ex).reduce((a, b) => a + b, 0) || 1;
      let worst = null;
      vv.journeys.forEach((j) => j.steps.forEach((st) => { const r = st.sessions >= 30 ? st.exits / st.sessions : 0; if (!worst || r > worst.r) worst = { r, name: stepName(j.id, st.id) }; }));
      const top = vv.insight_ids.map(insightById).filter((i) => i && i.severity !== 'healthy').sort((a, b) => ((b.impact || {}).score || 0) - ((a.impact || {}).score || 0))[0];
      return { id, label: persLabel(id), color: GROUP_COLOR[id] || '#8E8E93', sessions: vv.sessions, conv, ex, tot, worst, top };
    }).filter(Boolean);
    if (cols.length < 2) return null;
    const best = cols.reduce((a, b) => (b.conv > a.conv ? b : a)), low = cols.reduce((a, b) => (b.conv < a.conv ? b : a));
    const MIX = [['natural', 'Left calmly', 'var(--natural)'], ['technical', 'App problem', 'var(--crit-dot)'], ['language', 'Confusing wording', 'var(--pos-dot)'], ['ux', 'Hard to use', 'var(--warn-dot)']];
    const row = (label, cell) => [h('div', { class: 'cmp-l' }, label), ...cols.map(cell)];
    const grid = h('div', { class: 'cmp', style: `--n:${cols.length}` },
      h('div', { class: 'cmp-0' }), ...cols.map((c) => h('div', { class: 'cmp-h' }, h('i', { style: `background:${c.color}` }), c.label)),
      ...row('Finish rate', (c) => h('div', { class: 'cmp-c' }, h('b', {}, Math.round(c.conv) + '%'), evBar(c.conv / 100, c === low ? 'now' : 'usual'), c === best ? h('span', { class: 'cmp-tag ok' }, 'Highest') : c === low ? h('span', { class: 'cmp-tag bad' }, 'Lowest') : null)),
      ...row('Sessions', (c) => h('div', { class: 'cmp-c' }, h('b', {}, fmt(c.sessions)))),
      ...row('Why they leave', (c) => h('div', { class: 'cmp-c' }, h('span', { class: 'cmp-mix', role: 'img', 'aria-label': MIX.map(([k, l]) => `${l} ${Math.round(100 * (c.ex[k] || 0) / c.tot)}%`).join(', ') },
        MIX.map(([k, l, col]) => h('i', { style: `flex:${c.ex[k] || 0};background:${col}`, title: `${l}: ${Math.round(100 * (c.ex[k] || 0) / c.tot)}%` }))), h('span', { class: 'sub' }, `${Math.round(100 * (c.ex.natural || 0) / c.tot)}% left calmly`))),
      ...row('Most leave at', (c) => h('div', { class: 'cmp-c' }, c.worst && c.worst.r > 0 ? [h('b', {}, c.worst.name), h('span', { class: 'sub' }, `${(100 * c.worst.r).toFixed(1)}% of people there`)] : h('span', { class: 'sub' }, 'Nowhere stands out'))),
      ...row('Biggest problem', (c) => h('div', { class: 'cmp-c' }, c.top ? h('span', { class: 'cmp-p' }, c.top.title) : h('span', { class: 'sub' }, 'Nothing serious')))
    );
    const key = h('div', { class: 'legend' }, MIX.map(([k, l, col]) => h('span', {}, h('i', { class: 'sw', style: `background:${col}` }), l)));
    return card('Group comparison', 'How the groups compare', subTip(`${best.label} finishes most often (${Math.round(best.conv)}%); ${low.label} least (${Math.round(low.conv)}%).`,
      `Shown because you picked two or more registered groups, so this page compares them. Each column is that group on its own, for the same timeframe and platform. ${UI().unregistered_people || 'Unregistered people'} are a separate choice because their journey is different.`),
    null, key, scroller('Group comparison table, scroll sideways', grid));
  }
  function renderOverview(v) {
    const meta = D().meta;
    const dateRange = `${dateFmt(meta.window.start, { month: 'short', day: 'numeric' })} – ${dateFmt(meta.window.end, { month: 'short', day: 'numeric', year: 'numeric' })}`;
    const banner = h('div', { class: 'banner greet-card', role: 'note' },
      h('div', { class: 'bn-txt' }, h('span', { class: 'bn-t' }, `Hi ${state.userName} 👋`),
        h('span', { class: 'src-ds' }, dot('ok'), `Working on sample data demo · ${meta.dataset || 'sample'}`)));
    // Two or more groups picked: the page becomes the comparison and the Ask bar, nothing else.
    if (state.personas.length > 1) { const cmp = compareCard(); if (cmp) return [banner, pageHead('Overview', false, false), cmp]; }
    return [banner, pageHead('Overview', true, false, true), kpiCards(v), whySection(v), feedSection(v), h('div', { class: 'grid2s' }, donutCard(v), rhythmCard(v))];
  }

  /* ---------- Journeys ---------- */
  function stepFaultActive(j, sid) { return activeFaults().some((f) => f.sev !== 'resolved' && f.link && f.link.journey === j && f.link.step === sid); }
  function flowCard(v, jt) {
    const { cur } = jt || journeyTabs(v);
    if (!cur) return h('div', { class: 'card' }, h('h2', {}, 'Journey Flow'), h('p', { class: 'sub' }, 'This persona has no sessions in a mapped journey for this timeframe.'));
    const max = Math.max(1, ...cur.steps.map((x) => x.sessions)), last = cur.steps[cur.steps.length - 1];
    const stages = cur.steps.map((st, i) => {
      const t = TONE[st.tone] || 'ok';
      const bandH = Math.min(56, Math.max(10, Math.round(56 * st.sessions / max)));
      const isLast = i === cur.steps.length - 1;
      const ex = EXIT[st.exit_class] || EXIT.natural;
      return h('div', { class: 'fstep' }, i > 0 ? h('div', { class: 'band', style: `height:${bandH}px;margin-top:${Math.round((112 - bandH) / 2)}px`, 'aria-hidden': 'true' }) : null,
        h('div', { class: 'fcol' },
          h('button', { type: 'button', class: 'stage tone-' + t, ...fk(`st-${cur.id}-${st.id}`), onclick: (e) => openDrawer({ type: 'step', journey: cur.id, step: st.id }, e.currentTarget) },
            h('span', { class: 's-tag t-' + t }, dot(t), st.tag), h('span', { class: 's-name' }, stepName(cur.id, st.id)), h('span', { class: 's-cnt' }, fmt(st.sessions))),
          h('div', { class: 'fexit' }, h('span', { class: 'e-n', style: isLast ? 'color:var(--ok)' : '' }, isLast ? 'Completed' : (st.exits ? fmt(st.exits) + ' left' : '—')),
            h('span', { class: 'e-l t-' + (ex[1] === 'muted' ? '' : ex[1]), style: ex[1] === 'muted' ? 'color:var(--ink-3)' : '' }, isLast ? '' : (st.exits ? ex[0] : 'No exits')),
            stepFaultActive(cur.id, st.id) ? h('span', { class: 'gaptag' }, 'Possible data gap') : null)));
    });
    return card('Dynamic journey flow', 'Journey Flow', subTip('Select a step to diagnose.', 'Wider paths mean more sessions. Colour shows how much friction people hit at each step.'),
      h('div', { class: 'legend' }, legendDot('ok', 'Seamless'), legendDot('pos', 'Positive loop'), legendDot('warn', 'Watch'), legendDot('crit', 'High friction')),
      h('div', { class: 'jstats' }, h('span', {}, h('strong', {}, fmt(max)), ' at the busiest step'), h('span', {}, h('strong', {}, fmt(last.sessions)), ' completed'), h('span', {}, h('strong', {}, (100 * last.sessions / max).toFixed(1) + '%'), ' completion')),
      scroller('Journey steps, scroll sideways', h('div', { class: 'flow', style: `--n:${cur.steps.length}` }, stages)));
  }
  function blindCard(v) {
    const B = v.blind;
    if (!B) return null;
    const vals = B.bars.map((b) => b.value);
    const top = Math.max(20, Math.ceil(Math.max(...vals, B.baseline) / 20) * 20);
    const ticks = [top, Math.round(top * 2 / 3), Math.round(top / 3), 0];
    return card('Blind spot by segment', B.title, B.sub, h('span', { class: 'pill', style: 'background:var(--crit-bg);color:var(--crit);box-shadow:none;align-self:flex-start' }, B.badge),
      h('div', { class: 'barchart', role: 'img', 'aria-label': 'Bar chart: ' + B.bars.map((b) => `${b.l1} ${b.l2} ${b.value}%`).join(', ') + `. Baseline ${B.baseline}%` },
        h('div', { class: 'yax', 'aria-hidden': 'true' }, ticks.map((t) => h('span', {}, t + '%'))),
        h('div', { class: 'plot' },
          h('div', { class: 'cols', style: `grid-template-columns:repeat(${B.bars.length},minmax(0,1fr))` }, B.bars.map((b) => h('div', { class: 'col' + (b.hot ? ' hot' : ''), style: `height:${(100 * b.value / top).toFixed(1)}%` }, h('span', {}, b.value + '%'))),
            h('div', { class: 'baseline', style: `bottom:${(100 * B.baseline / top).toFixed(1)}%` })),
          h('div', { class: 'xlab', style: `grid-template-columns:repeat(${B.bars.length},minmax(0,1fr))`, 'aria-hidden': 'true' }, B.bars.map((b) => h('span', { class: b.hot ? 'hot' : '' }, h('span', {}, b.l1), h('span', {}, b.l2)))),
          h('span', { class: 'sub', style: 'display:inline-flex;align-items:center;gap:6px' }, h('span', { style: 'width:14px;border-top:1.5px dashed var(--ink);display:inline-block' }), B.baseline_label))));
  }
  // Icons come from the loaded dataset's ui block (datasets.json), keyed by the shared product and step ids.
  const DEFAULT_ICON = 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z';
  const productIcon = (id) => (UI().product_icon || {})[id] || DEFAULT_ICON;
  const stepIcon = (id) => (UI().step_icon || {})[id] || (UI().step_icon || {}).done || DEFAULT_ICON;

  const PF_REASON = { technical: 'usually after an error or a tap that did nothing', ux: 'usually after going back a step', language: 'usually after getting stuck on the wording', natural: 'mostly people just browsing' };
  function productCard() {
    const P = D().product_funnels;
    if (!P || !Object.keys(P).length) return null;
    const rows = Object.entries(P).filter(([, f]) => f && f.completion != null).map(([id, f]) => {
      const worst = (f.steps || []).filter((x) => x.exit_rate > 0).sort((a, b) => b.exit_rate - a.exit_rate)[0];
      return { id, f, worst };
    }).sort((a, b) => a.f.completion - b.f.completion);
    const avg = rows.reduce((t, r) => t + r.f.completion, 0) / Math.max(1, rows.length);
    const pcard = UI().product_card || {}, noun = UI().product_noun || 'product';
    return card(pcard.label || 'Buy, by product', pcard.title || 'Buying, by product', subTip('', `Share of sessions that reach ${stepName(PRODUCT_JOURNEY, 'done')}, by ${noun}. Whole window, all personas.`), null,
      h('div', { style: 'display:flex;flex-direction:column;gap:14px' }, rows.map((r) => {
        const low = r.f.completion < avg - 0.1;
        return h('div', { class: 'cohrow' }, h('span', { class: 'n' }, h('span', { class: 'pi', 'aria-hidden': 'true' }, icon(productIcon(r.id), 18, 1.7)), h('span', { class: 'pn' }, r.f.label, h('span', { class: 'sub' }, fmt(r.f.sessions) + ' sessions'))),
          h('div', { class: 'bar', 'aria-hidden': 'true' }, h('i', { style: `width:${(100 * r.f.completion).toFixed(1)}%;background:${low ? 'var(--crit-dot)' : 'var(--accent)'}` })),
          h('span', { class: 's' }, Math.round(100 * r.f.completion) + '%'),
          r.worst ? h('span', { class: 'sub pf-w' }, `Most people leave at ${r.worst.name} (${(100 * r.worst.exit_rate).toFixed(1)}%)${PF_REASON[r.worst.exit_class] ? ', ' + PF_REASON[r.worst.exit_class] : ''}`) : null);
      })),
      h('p', { class: 'sub' }, `Average completion ${Math.round(100 * avg)}%. A ${noun} more than 10 points below it is marked red.`));
  }
  /* ---------- Sankey: where sessions go ---------- */
  const PRODUCT_JOURNEY = 'transaction';   // product_funnels is this journey split by product
  const fin = (x) => (Number.isFinite(x) ? Math.round(x * 100) / 100 : 0);
  const rate1 = (a, b) => (b > 0 ? (100 * a / b).toFixed(1).replace(/\.0$/, '') + '%' : '0%');
  function wrapName(t, max) {
    const out = []; let cur = '';
    for (const w of String(t).split(/\s+/)) {
      if (cur && (cur + ' ' + w).length > max) { out.push(cur); cur = w; } else cur = cur ? cur + ' ' + w : w;
    }
    if (cur) out.push(cur);
    return out.slice(0, 3);
  }
  function skSource(cur) {
    const P = D().product_funnels;
    if (cur.id === PRODUCT_JOURNEY && state.skProduct !== 'all' && P && P[state.skProduct]) {
      const f = P[state.skProduct];
      return { product: f.label, steps: (f.steps || []).map((x) => { const r = x.exit_rate || 0; return { id: x.id, name: x.name, sessions: x.sessions || 0, exits: x.exits || 0, tone: r >= 0.2 ? 'critical' : r >= 0.1 ? 'warning' : 'healthy', tag: Math.round(100 * r) + '% exit', low_sample: (x.sessions || 0) < 20 }; }) };
    }
    return { product: null, steps: cur.steps.map((x) => ({ ...x, name: stepName(cur.id, x.id), sessions: x.sessions || 0, exits: x.exits || 0 })) };
  }
  const skIns = (v, journey, step) => v.insight_ids.map(insightById).filter((i) => i && i.journey === journey && i.step === step).sort((a, b) => ((b.impact || {}).score || 0) - ((a.impact || {}).score || 0))[0] || null;
  /* "By user group" Sankey: each step is a stack of user-group bands, so the flow branches by who is travelling instead of
     being one grey band with a red stub. Numbers come from each group's own view of results.json (same timeframe and platform). */
  const GROUP_COLOR = { unregistered: '#7C5CFF', large_business: '#A0693B', sari_sari: '#E07B00', individual_trader: '#D63384', individual: '#0F7B9A' };
  function groupSankey(cur, stepIds) {
    const groups = visiblePersonas().filter((g) => !state.personas.length || state.personas.includes(g.id)).map((g) => {
      const vv = D().views[`${state.range}|${state.platform}|${g.id}`], j = vv && vv.journeys.find((x) => x.id === cur.id), map = {};
      ((j && j.steps) || []).forEach((st) => { map[st.id] = st; });
      return { g, map, color: GROUP_COLOR[g.id] || '#8E8E93' };
    }).filter((x) => Object.keys(x.map).length);
    const n = stepIds.length;
    if (!groups.length || n < 2) return { legend: null, body: h('div', { class: 'empty' }, 'No user-group data for this view.') };
    const W = 900, H = 420, top = 52, bottom = 96, nodeW = 14, GAP = 1.5, leftX = 50, rightX = W - 12 - nodeW - 44;
    const colX = (i) => leftX + (i * (rightX - leftX)) / (n - 1);
    const val = (gr, sid, k) => (gr.map[sid] ? Number(gr.map[sid][k]) || 0 : 0);
    const totals = stepIds.map((sid) => groups.reduce((a, gr) => a + val(gr, sid, 'sessions'), 0));
    const scale = (H - top - bottom - GAP * groups.length) / Math.max(1, ...totals);
    const yTop = stepIds.map((sid) => { let y = top; return groups.map((gr) => { const y0 = y; y += val(gr, sid, 'sessions') * scale + GAP; return y0; }); });
    const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, class: 'gsk', role: 'group', style: 'width:100%;min-width:640px;max-width:960px;display:block;margin:0 auto;height:auto',
      'aria-label': `Sessions by step and user group for ${jName(cur.id)}. The Table view lists the same numbers.` });
    const linksG = s('g'), nodesG = s('g'), exitsG = s('g'), labelsG = s('g');
    const exitCursor = stepIds.map(() => H - bottom + 16);
    // the numbers behind the hover preview and the pinned strip: one entry per step, one row per user group that has sessions there
    const stepInfo = stepIds.map((sid, i) => {
      const rows = groups.map((gr) => ({ gr, sess: val(gr, sid, 'sessions'), ex: i < n - 1 ? val(gr, sid, 'exits') : 0 })).filter((r) => r.sess > 0), exits = rows.reduce((a, r) => a + r.ex, 0);
      return { i, name: stepName(cur.id, sid), sessions: totals[i], exits, cont: i < n - 1 ? Math.max(0, totals[i] - exits) : 0, last: i === n - 1, rows };
    });
    stepIds.forEach((sid, i) => {
      const x = colX(i), name = stepName(cur.id, sid);
      let exitSum = 0;
      groups.forEach((gr, gi) => {
        const sess = val(gr, sid, 'sessions'), ex = i < n - 1 ? val(gr, sid, 'exits') : 0, cont = i < n - 1 ? Math.max(0, sess - ex) : 0, y0 = yTop[i][gi];
        nodesG.append(s('rect', { x: fin(x), y: fin(y0), width: nodeW, height: fin(Math.max(1, sess * scale)), rx: 2, fill: gr.color, class: 'g-node', 'data-g': gr.g.id, 'data-i': i }));
        if (i < n - 1 && cont > 0) {
          const y1 = yTop[i + 1][gi], hc = cont * scale, hn = Math.max(1, Math.min(hc, val(gr, stepIds[i + 1], 'sessions') * scale || hc));
          linksG.append(s('path', { d: flowRibbon(x + nodeW, y0, y0 + hc, colX(i + 1), y1, y1 + hn), fill: gr.color, 'fill-opacity': 0.4, class: 'g-link', 'data-g': gr.g.id, 'data-i': i }));
        }
        if (ex > 0) {
          const eh = Math.max(1.6, ex * scale), yS = y0 + cont * scale, yE = exitCursor[i], xe = x + nodeW + 40;
          exitCursor[i] += eh + 2.5; exitSum += ex;
          exitsG.append(s('path', { d: flowRibbon(x + nodeW, yS, yS + Math.max(eh, ex * scale), xe, yE, yE + eh), fill: gr.color, 'fill-opacity': 0.62, class: 'g-exit', 'data-g': gr.g.id, 'data-i': i }),
            s('rect', { x: fin(xe), y: fin(yE), width: 5, height: fin(eh), rx: 1.5, fill: gr.color, class: 'g-exit', 'data-g': gr.g.id, 'data-i': i }));
        }
      });
      const cx = x + nodeW / 2, lines = wrapName(name, 13);
      lines.forEach((ln, k) => labelsG.append(s('text', { x: fin(cx), y: fin(top - 20 - 12 * (lines.length - 1 - k)), 'text-anchor': 'middle', class: 'sk-name' }, ln)));
      labelsG.append(s('text', { x: fin(cx), y: fin(top - 7), 'text-anchor': 'middle', class: 'sk-count' }, fmt(totals[i])));
      if (exitSum > 0) labelsG.append(s('text', { x: fin(x + nodeW + 43), y: fin(exitCursor[i] + 10), 'text-anchor': 'middle', class: 'sk-exit-lab' }, `${fmt(exitSum)} left`));
    });
    // one focusable, invisible hit area per step, under the bands: it carries the keyboard and the accessible numbers
    const hitG = s('g');
    const hits = stepInfo.map((d) => {
      const r = s('rect', { x: fin(colX(d.i) - 8), y: fin(top - 4), width: nodeW + 16, height: fin(H - bottom - top + 8), fill: 'transparent', class: 'g-hit', tabindex: '0', role: 'button', 'data-i': d.i,
        'aria-label': `${d.name}: ${fmt(d.sessions)} sessions` + (d.last ? ', journey completed' : `, ${fmt(d.cont)} continue, ${fmt(d.exits)} leave (${rate1(d.exits, d.sessions)})`) + '. Press Enter to pin the numbers.' });
      hitG.append(r); return r;
    });
    svg.append(hitG, linksG, exitsG, nodesG, labelsG);
    const inner = h('div', { class: 'sk-inner' });
    const tip = h('div', { class: 'sk-tip', role: 'tooltip', hidden: true });
    const dock = h('div', { class: 'sk-dock', hidden: true, 'aria-live': 'polite' });
    const fillCard = (d, target, hot) => {
      const stat = (l, v, sub) => h('div', { class: 'tp-s' }, h('span', { class: 'tp-l' }, l), h('b', {}, v), sub ? h('span', { class: 'tp-sub' }, sub) : null);
      target.replaceChildren(
        h('div', { class: 'tp-head' }, h('b', {}, d.name)),
        h('div', { class: 'tp-stats' }, stat('Reached', fmt(d.sessions)), d.last ? stat('Finished', fmt(d.sessions)) : stat('Went on', fmt(d.cont)), d.last ? null : stat('Left', fmt(d.exits), rate1(d.exits, d.sessions))),
        h('div', { class: 'tp-groups' }, d.rows.map((r) => h('div', { class: 'tp-g' + (hot === r.gr.g.id ? ' hot' : '') }, h('i', { style: `background:${r.gr.color}` }), h('span', { class: 'tp-gn' }, r.gr.g.label),
          h('span', { class: 'tp-gv' }, d.last ? `${fmt(r.sess)} finished` : `${fmt(r.sess)} reached · ${fmt(r.ex)} left (${rate1(r.ex, r.sess)})`)))),
        h('span', { class: 'sk-hint' }, target === dock ? 'Click the step again, or press Esc, to release it' : 'Click to pin this step, click again to release'));
    };
    const place = (el) => {
      const r = el.getBoundingClientRect(), b = inner.getBoundingClientRect();
      tip.hidden = false;
      const tw = tip.offsetWidth, th = tip.offsetHeight;
      let left = r.left - b.left + r.width / 2 - tw / 2;
      left = Math.max(4, Math.min(left, b.width - tw - 4));
      let topPx = r.bottom - b.top + 8;
      if (topPx + th > b.height - 2) topPx = Math.max(2, r.top - b.top - th - 8);
      tip.style.left = Math.round(left) + 'px'; tip.style.top = Math.round(topPx) + 'px';
    };
    let locked = null, pinned = null;
    const focus = (id) => svg.querySelectorAll('[data-g]').forEach((e) => e.classList.toggle('dim', !!id && e.dataset.g !== id));
    const hideTip = () => { tip.hidden = true; };
    const showTip = (i, el, hot) => { if (pinned !== null) return; fillCard(stepInfo[i], tip, hot); place(el); };
    const pin = (i) => {
      pinned = pinned === i ? null : i;
      hits.forEach((r, k) => r.classList.toggle('pinned', k === pinned));
      if (pinned === null) { dock.hidden = true; return; }
      fillCard(stepInfo[pinned], dock, null); dock.hidden = false; hideTip(); announce(`${stepInfo[pinned].name} pinned`);
    };
    const stepOf = (e) => { const el = e.target.closest && e.target.closest('[data-i]'); return el ? { i: Number(el.dataset.i), g: el.dataset.g || null, el } : null; };
    svg.addEventListener('mouseover', (e) => {
      const el = e.target.closest && e.target.closest('[data-g]'); if (el && !locked) focus(el.dataset.g);
      const st = stepOf(e); if (st) showTip(st.i, st.el, st.g);
    });
    svg.addEventListener('mouseleave', () => { if (!locked) focus(null); hideTip(); });
    svg.addEventListener('click', (e) => { const st = stepOf(e); if (st) pin(st.i); });
    hits.forEach((r) => {
      r.addEventListener('focus', () => showTip(Number(r.dataset.i), r)); r.addEventListener('blur', hideTip);
      r.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pin(Number(r.dataset.i)); }
        else if (e.key === 'Escape') { if (pinned !== null) pin(pinned); hideTip(); }
        else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { const to = hits[Number(r.dataset.i) + (e.key === 'ArrowRight' ? 1 : -1)]; if (to) { e.preventDefault(); to.focus(); } }
      });
    });
    const keys = h('div', { class: 'gkeys', role: 'group', 'aria-label': 'User groups, press to follow one group' }, groups.map((gr) => {
      const b = h('button', { type: 'button', class: 'gkey', 'aria-pressed': 'false', onclick: () => {
        locked = locked === gr.g.id ? null : gr.g.id; focus(locked);
        b.parentElement.querySelectorAll('.gkey').forEach((x) => x.setAttribute('aria-pressed', String(!!locked && x === b)));
      }, onmouseenter: () => { if (!locked) focus(gr.g.id); }, onmouseleave: () => { if (!locked) focus(null); } },
      h('i', { style: `background:${gr.color}` }), gr.g.label);
      return b;
    }));
    inner.append(svg, tip);
    return { legend: keys, body: scroller('Sessions by step and user group chart, scroll sideways', inner), dock };
  }
  function sankeyCard(v, jt) {
    const title = 'Where sessions go';
    const cur = jt.cur;
    if (!cur) return card('Where sessions go', title, subTip('', 'Each step, how many sessions continue and how many leave.'), null, h('div', { class: 'empty' }, 'No sessions in a mapped journey for this timeframe and persona.'));
    const P = D().product_funnels, hasProducts = cur.id === PRODUCT_JOURNEY && P && Object.keys(P).length > 0;
    if (!hasProducts || (state.skProduct !== 'all' && !P[state.skProduct])) state.skProduct = 'all';
    const src = skSource(cur), steps = src.steps, n = steps.length;
    const maxS = Math.max(0, ...steps.map((s) => s.sessions));
    const controls = h('div', { class: 'sk-controls' },
      hasProducts ? h('span', { class: 'sk-sel' }, h('label', { for: 'sk-product' }, cap(UI().product_noun || 'product', 0)), h('select', { id: 'sk-product', ...fk('sk-product'), onchange: (e) => { state.skProduct = e.target.value; rerender('sk-product'); announce('Showing ' + (e.target.value === 'all' ? 'all ' + (UI().products_noun || 'products') : P[e.target.value].label)); } },
        h('option', { value: 'all', selected: state.skProduct === 'all' }, cap('all ' + (UI().products_noun || 'products'), 0)), Object.entries(P).map(([id, f]) => h('option', { value: id, selected: state.skProduct === id }, f.label)))) : null,
      h('div', { class: 'seg', role: 'group', 'aria-label': 'Color by' }, [['friction', 'Friction'], ['share', 'Drop-off share'], ['group', 'By user group']].map(([id, l]) => h('button', { type: 'button', 'aria-pressed': String(state.skMode === id), disabled: id === 'group' && !!src.product, ...fk('sk-mode-' + id), onclick: () => { state.skMode = id; rerender('sk-mode-' + id); } }, l))),
      h('div', { class: 'seg', role: 'group', 'aria-label': 'Chart or table' }, [['chart', 'Chart'], ['table', 'Table']].map(([id, l]) => h('button', { type: 'button', 'aria-pressed': String(state.skView === id), ...fk('sk-view-' + id), onclick: () => { state.skView = id; rerender('sk-view-' + id); } }, l))));
    const sub = 'Each column is a step, sized by sessions. Grey-blue bands are sessions that continue; red bands leave the journey.' + (src.product ? ` Showing ${src.product}: whole window, all personas.` : '');
    if (!n || maxS <= 0) return card('Where sessions go', title, subTip('', sub), controls, h('div', { class: 'empty' }, 'No sessions in this journey for these filters.'));

    if (state.skMode === 'group' && !src.product && state.skView !== 'table') {
      const gs = groupSankey(cur, steps.map((x) => x.id));
      const cg = card('Where sessions go', title, subTip('', 'Each coloured band is a user group. Wider means more sessions. A band that runs on to the next step continues; a band that peels off to the right left the journey. Hover a band to see the numbers and follow one group, click a step to pin it, or press a name in the key.'), controls, gs.legend, gs.body, gs.dock,
        h('p', { class: 'sub' }, 'Sessions per user group for this timeframe and platform. Groups with no sessions in this journey are left out.'));
      cg.id = 'sankey'; return cg;
    }

    // ----- numbers (all from the view; nothing invented)
    const loops = ((v.loops || {})[cur.id] || []);
    const totalExits = steps.reduce((t, s) => t + s.exits, 0);
    const info = steps.map((s, i) => {
      const cont = i < n - 1 ? Math.max(0, s.sessions - s.exits) : 0;
      const joined = cur.id === 'register_login' && i > 0 ? Math.max(0, s.sessions - Math.max(0, steps[i - 1].sessions - steps[i - 1].exits)) : 0;
      const back = src.product ? 0 : loops.filter((l) => l.from === s.id).reduce((t, l) => t + (l.count || 0), 0);
      const ins = src.product ? null : skIns(v, cur.id, s.id);
      const cause = ins && (ins.causes || []).filter((c) => c && c.title && !c.resolved).sort((a, b) => (Number(b.share) || 0) - (Number(a.share) || 0))[0];
      return { ...s, i, cont, joined, last: i === n - 1, back, ins, cause, exitRate: s.sessions > 0 ? s.exits / s.sessions : 0, share: totalExits > 0 ? s.exits / totalExits : 0, ofMax: rate1(s.sessions, maxS) };
    });
    const label = (d) => `${d.name}: ${fmt(d.sessions)} sessions (${d.ofMax} of the busiest step)` + (d.last ? ', journey completed' : `, ${fmt(d.cont)} continue, ${fmt(d.exits)} leave (${rate1(d.exits, d.sessions)})`) + (d.low_sample ? ', few sessions' : '') + (d.ins ? '. Press Enter for the diagnosis.' : '.');

    // ----- layout (SVG user units)
    const W = 800, nodeW = 16, mx = 30, y0 = 58, Hmain = 170, exitY = y0 + Hmain + 36;
    const sc = Hmain / maxS;
    const H = Math.ceil(exitY + Math.max(4, ...info.map((d) => d.exits * sc)) + 30);
    const gap = n > 1 ? (W - 2 * mx - n * nodeW) / (n - 1) : 0;
    const X = (i) => (n > 1 ? mx + i * (nodeW + gap) : W / 2 - nodeW / 2);
    const nh = (s) => Math.max(3, s * sc);
    const toneVar = { critical: 'crit', warning: 'warn', positive: 'pos', healthy: 'ok' };
    const heat = (sh) => (sh >= 0.4 ? 4 : sh >= 0.25 ? 3 : sh >= 0.15 ? 2 : sh > 0.05 ? 1 : 0);
    const nodeFill = (d) => (d.low_sample ? 'url(#sk-hatch)' : state.skMode === 'share' ? `var(--h${heat(d.share)})` : `var(--${toneVar[d.tone] || 'ok'}-dot)`);
    const linkFill = (d) => (d.low_sample ? 'var(--muted-dot)' : state.skMode === 'share' ? `var(--h${Math.max(1, heat(d.share))})` : `var(--${toneVar[d.tone] || 'ok'}-dot)`);
    const ribbon = flowRibbon;

    // ----- element registry for highlighting
    const reg = {};
    const add = (key, el) => { reg[key] = el; el.classList.add('sk-el'); return el; };
    let pinned = null, tipOn = null;
    const inner = h('div', { class: 'sk-inner' });
    const tip = h('div', { class: 'sk-tip', role: 'tooltip', id: 'sk-tip', hidden: true });
    const dock = h('div', { class: 'sk-dock', hidden: true, 'aria-live': 'polite' });
    const related = (key) => {
      const k = key[0], i = Number(key.slice(1));
      if (k === 'n') return ['n' + i, 'c' + i, 'c' + (i - 1), 'x' + i, 'e' + i];
      if (k === 'c') return ['c' + i, 'n' + i, 'n' + (i + 1)];
      return ['x' + i, 'e' + i, 'n' + i];
    };
    const highlight = (keys) => { const set = keys ? new Set(keys) : null; for (const [k, el] of Object.entries(reg)) el.classList.toggle('dim', !!set && !set.has(k)); };
    // Clicking (pinning) a path makes its bands flow: marching dashes along the ribbons, see .sk-el.flow in app.css.
    const flowing = (keys) => {
      const set = keys ? new Set(keys) : null;
      for (const [k, el] of Object.entries(reg)) el.classList.toggle('flow', !!set && set.has(k) && el.classList.contains('sk-link'));
      const root = inner.querySelector('svg.sk-svg'); if (!root) return;
      root.querySelectorAll('.sk-dots').forEach((n) => n.remove());
      if (!set || (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
      const g = s('g', { class: 'sk-dots', 'aria-hidden': 'true', 'pointer-events': 'none' });
      for (const [k, el] of Object.entries(reg)) {
        if (!set.has(k) || !el.classList.contains('sk-link')) continue;
        const n = (el.getAttribute('d').match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
        if (n.length < 16) continue;
        const ya = (n[1] + n[15]) / 2, yb = (n[5] + n[9]) / 2;
        const cl = `M${n[0]} ${ya} C${n[2]} ${ya} ${n[2]} ${yb} ${n[6]} ${yb}`;
        const len = Math.max(1, n[6] - n[0]);
        for (let p = 0; p < 3; p++) {
          const dot = s('circle', { r: 3.4, class: 'sk-dot' });
          dot.append(s('animateMotion', { dur: Math.max(1.6, Math.min(3.4, len / 90)).toFixed(1) + 's', repeatCount: 'indefinite', begin: (-p * 0.9).toFixed(1) + 's', path: cl }));
          g.append(dot);
        }
      }
      root.append(g);
    };
    const TIPTONE = { critical: ['crit', 'Needs attention'], warning: ['warn', 'Keep an eye on it'], positive: ['pos', 'Healthy loop'], healthy: ['ok', 'Healthy'] };
    const fillTip = (d, target = tip) => {
      const [tc, tl] = TIPTONE[d.tone] || TIPTONE.healthy;
      const stat = (l, v, sub) => h('div', { class: 'tp-s' }, h('span', { class: 'tp-l' }, l), h('b', {}, v), sub ? h('span', { class: 'tp-sub' }, sub) : null);
      const plainLine = d.low_sample ? 'Too few sessions here to judge.' : d.last ? 'People who get here have finished the journey.'
        : `${rate1(d.exits, d.sessions)} of people leave here, which is ${rate1(d.exits, totalExits)} of everyone who leaves this journey.`;
      const extras = [!src.product && d.back > 0 ? `${fmt(d.back)} went back a step` : null, d.joined > 0 ? `${fmt(d.joined)} joined from elsewhere` : null].filter(Boolean).join(' · ');
      target.replaceChildren(...[
        h('div', { class: 'tp-head' }, h('b', {}, d.name), h('span', { class: 'tp-tone t-' + tc }, dot(tc), tl)),
        h('div', { class: 'tp-stats' }, stat('Reached', fmt(d.sessions), d.ofMax + ' of busiest'), d.last ? stat('Finished', fmt(d.sessions)) : stat('Went on', fmt(d.cont)), d.last ? null : stat('Left', fmt(d.exits), rate1(d.exits, d.sessions))),
        h('p', { class: 'tp-line' }, plainLine),
        d.cause && !d.low_sample ? h('p', { class: 'tp-line' }, h('b', {}, 'Most likely: '), `${d.cause.title} (${Math.round((Number(d.cause.share) || 0) * 100)}%)`) : null,
        extras ? h('p', { class: 'tp-meta' }, extras) : null,
        h('span', { class: 'sk-hint' }, d.ins ? 'Click to follow this path, click again to see why' : 'Click to follow this path')].filter(Boolean));
    };
    const place = (el) => {
      const r = el.getBoundingClientRect(), b = inner.getBoundingClientRect();
      tip.hidden = false;
      const tw = tip.offsetWidth, th = tip.offsetHeight;
      let left = r.left - b.left + r.width / 2 - tw / 2;
      left = Math.max(4, Math.min(left, b.width - tw - 4));
      let top = r.bottom - b.top + 8;
      if (top + th > b.height - 2) top = Math.max(2, r.top - b.top - th - 8);
      tip.style.left = Math.round(left) + 'px'; tip.style.top = Math.round(top) + 'px';
    };
    const show = (key, el) => { if (pinned) return; const i = Number(key.slice(1)); fillTip(info[i]); highlight(related(key)); place(el); tipOn = key; };
    const rest = () => { flowing(pinned ? related(pinned.key) : null); if (pinned) { highlight(related(pinned.key)); fillTip(info[Number(pinned.key.slice(1))], dock); dock.hidden = false; tip.hidden = true; tipOn = pinned.key; } else { dock.hidden = true; highlight(null); tip.hidden = true; tipOn = null; } };
    const activate = (key, el) => {
      const d = info[Number(key.slice(1))];
      if (d.ins && pinned && pinned.key === key) { openDrawer({ type: 'insight', id: d.ins.id }, el); return; }
      pinned = pinned && pinned.key === key ? null : { key, el };
      rest(); if (pinned) announce(`${d.name} pinned`);
    };
    const svg = s('svg', { class: 'sk-svg', viewBox: `0 0 ${W} ${H}`, role: 'group', 'aria-label': `Sessions by step for ${jName(cur.id)}${src.product ? ', ' + src.product : ''}. Arrow keys move between steps, Enter opens details, Escape clears.`, style: `width:100%;min-width:640px;max-width:960px;display:block;margin:0 auto;height:auto` },
      s('defs', {}, s('pattern', { id: 'sk-hatch', width: 6, height: 6, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' }, s('rect', { width: 6, height: 6, style: 'fill:var(--soft)' }), s('line', { x1: 0, y1: 0, x2: 0, y2: 6, 'stroke-width': 3, style: 'stroke:var(--muted-dot)' }))));
    const nodesG = s('g', {}), linksG = s('g', {}), labelsG = s('g', {});
    const stepNodes = [];
    info.forEach((d) => {
      const x = X(d.i), hh = nh(d.sessions);
      if (d.joined > 0) {
        const jh = Math.max(3, d.joined * sc), jy = y0 + Math.max(0, (hh - jh) / 2);
        const join = add('j' + d.i, s('path', { d: ribbon(0, y0, y0 + jh, x, jy, jy + jh), style: 'fill:var(--muted-dot)', 'fill-opacity': '.38', class: 'sk-link sk-joinlink', 'aria-label': `${fmt(d.joined)} sessions join here from login or another entry point` }));
        linksG.append(join);
      }
      // continue link
      if (!d.last && d.cont > 0 && n > 1) {
        const lh = Math.max(2, d.cont * sc);
        const lk = add('c' + d.i, s('path', { d: ribbon(x + nodeW, y0, y0 + lh, X(d.i + 1), y0, y0 + lh), style: `fill:${linkFill(d)}`, 'fill-opacity': d.low_sample ? 0.18 : 0.3, class: 'sk-link', 'aria-hidden': 'true' }));
        lk.addEventListener('mouseenter', () => show('c' + d.i, lk)); lk.addEventListener('mouseleave', rest);
        linksG.append(lk);
      }
      // exit link and node
      if (!d.last && d.exits > 0) {
        const eh = Math.max(4, d.exits * sc), lt = y0 + Math.min(hh, d.cont * sc + (d.cont > 0 ? 0 : 0)), exX = x + nodeW + gap * 0.58;
        const top1 = y0 + (d.cont > 0 ? Math.max(2, d.cont * sc) : 0), bot1 = Math.min(y0 + hh, top1 + eh);
        const xl = add('x' + d.i, s('path', { d: ribbon(x + nodeW, top1, Math.max(bot1, top1 + 2), exX, exitY, exitY + eh), style: 'fill:var(--crit-dot)', 'fill-opacity': 0.3, class: 'sk-link sk-exitlink', 'aria-hidden': 'true' }));
        xl.addEventListener('mouseenter', () => show('x' + d.i, xl)); xl.addEventListener('mouseleave', rest);
        linksG.append(xl);
        const eg = add('e' + d.i, s('g', { class: 'sk-g', tabindex: '-1', role: 'button', 'aria-label': `${d.name}: ${fmt(d.exits)} sessions leave here (${rate1(d.exits, d.sessions)} of the step)` + (d.ins ? '. Press Enter for the diagnosis.' : ''), 'data-fk': 'skx-' + d.i, 'data-k': 'e' + d.i },
          s('rect', { x: fin(exX), y: fin(exitY), width: 12, height: fin(eh), rx: 2, class: 'sk-node', style: 'fill:var(--crit-dot)' })));
        stepNodes.push(eg); nodesG.append(eg);
        labelsG.append(s('text', { x: fin(exX + 6), y: fin(exitY + eh + 14), 'text-anchor': 'middle', class: 'sk-exit-lab' }, `${fmt(d.exits)} exit`));
        eg.addEventListener('mouseenter', () => show('e' + d.i, eg)); eg.addEventListener('mouseleave', rest);
        eg.addEventListener('focus', () => show('e' + d.i, eg)); eg.addEventListener('blur', rest);
        eg.addEventListener('click', () => activate('e' + d.i, eg));
      }
      // step node
      const g = add('n' + d.i, s('g', { class: 'sk-g', tabindex: d.i === 0 ? '0' : '-1', role: 'button', 'aria-label': label(d) + (d.joined ? ` ${fmt(d.joined)} sessions join here from login or another entry point.` : ''), 'data-fk': 'skn-' + d.i, 'data-k': 'n' + d.i },
        s('rect', { x: fin(x), y: y0, width: nodeW, height: fin(hh), rx: 3, class: 'sk-node', style: `fill:${nodeFill(d)}` })));
      nodesG.append(g); stepNodes.push(g);
      g.addEventListener('mouseenter', () => show('n' + d.i, g)); g.addEventListener('mouseleave', rest);
      g.addEventListener('focus', () => show('n' + d.i, g)); g.addEventListener('blur', rest);
      g.addEventListener('click', () => activate('n' + d.i, g));
      const lines = wrapName(d.name, 13), cx = x + nodeW / 2;
      lines.forEach((ln, k) => labelsG.append(s('text', { x: fin(cx), y: fin(y0 - 20 - 12 * (lines.length - 1 - k)), 'text-anchor': 'middle', class: 'sk-name' }, ln)));
      labelsG.append(s('text', { x: fin(cx), y: fin(y0 - 7), 'text-anchor': 'middle', class: 'sk-count' }, fmt(d.sessions)));
      if (d.last) labelsG.append(s('text', { x: fin(cx), y: fin(y0 + hh + 14), 'text-anchor': 'middle', class: 'sk-done-lab' }, 'completed'));
      if (d.low_sample) labelsG.append(s('text', { x: fin(cx), y: fin(y0 + hh + 14), 'text-anchor': 'middle', class: 'sk-few-lab' }, 'few sessions'));
    });
    svg.append(linksG, nodesG, labelsG);
    // keyboard: arrows between steps, up and down between a step and its exit, Escape clears
    svg.addEventListener('keydown', (e) => {
      const g = e.target.closest ? e.target.closest('.sk-g') : null;
      if (e.key === 'Escape') { pinned = null; highlight(null); flowing(null); tip.hidden = true; dock.hidden = true; return; }
      if (!g) return;
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(g.dataset.k, g); return; }
      const k = g.dataset.k, i = Number(k.slice(1));
      let to = null;
      if (k[0] === 'n') {
        if (e.key === 'ArrowRight') to = reg['n' + (i + 1)]; else if (e.key === 'ArrowLeft') to = reg['n' + (i - 1)]; else if (e.key === 'ArrowDown') to = reg['e' + i];
        else if (e.key === 'Home') to = reg.n0; else if (e.key === 'End') to = reg['n' + (n - 1)];
      } else if (e.key === 'ArrowUp') to = reg['n' + i]; else if (e.key === 'ArrowRight') { for (let q = i + 1; q < n && !to; q++) to = reg['e' + q]; } else if (e.key === 'ArrowLeft') { for (let q = i - 1; q >= 0 && !to; q--) to = reg['e' + q]; }
      if (to) { e.preventDefault(); stepNodes.forEach((x) => x.setAttribute('tabindex', '-1')); to.setAttribute('tabindex', '0'); to.focus(); }
    });
    inner.append(svg, tip);
    const legend = state.skMode === 'share'
      ? h('div', { class: 'legend' }, [['≤ 5% of exits', 0], ['5–15%', 1], ['15–25%', 2], ['25–40%', 3], ['≥ 40%', 4]].map(([t, l]) => h('span', {}, h('i', { class: 'sw', style: `width:18px;height:12px;background:var(--h${l});box-shadow:inset 0 0 0 1px var(--line-2)` }), t)), h('span', {}, h('i', { class: 'sw', style: 'background:var(--crit-dot)' }), 'Exit'))
      : h('div', { class: 'legend' }, legendDot('ok', 'Seamless'), legendDot('pos', 'Positive loop'), legendDot('warn', 'Watch'), legendDot('crit', 'High friction or exit'), h('span', {}, h('i', { class: 'sw', style: 'background:repeating-linear-gradient(45deg,var(--muted-dot) 0 2px,var(--soft) 2px 5px)' }), 'Few sessions'));
    // table alternative: the same numbers as real rows
    const table = h('table', { class: 'sk-table' }, h('caption', {}, `${jName(cur.id)}${src.product ? ', ' + src.product : ''}: sessions at each step, how many continue and how many leave`),
      h('thead', {}, h('tr', {}, ['Step', 'Sessions', 'Of busiest step', 'Continue', 'Exits', 'Exit rate', 'Backward moves', 'Note'].map((c) => h('th', { scope: 'col' }, c)))),
      h('tbody', {}, info.map((d) => h('tr', {}, h('th', { scope: 'row' }, d.name), h('td', { class: 'num' }, fmt(d.sessions)), h('td', { class: 'num' }, d.ofMax), h('td', { class: 'num' }, d.last ? '—' : fmt(d.cont)),
        h('td', { class: 'num' }, d.last ? '—' : fmt(d.exits)), h('td', { class: 'num' }, d.last ? '—' : rate1(d.exits, d.sessions)), h('td', { class: 'num' }, src.product ? '—' : fmt(d.back)), h('td', {}, d.last ? 'Completed' : d.low_sample ? 'Few sessions' : (d.tag || ''))))));
    const view_ = state.skView === 'table'
      ? scroller('Sessions by step as a table, scroll sideways', table)
      : scroller('Sessions by step chart, scroll sideways', inner);
    const c = card('Where sessions go', title, subTip('', sub), controls, legend, view_, dock,
      h('p', { class: 'sub' }, 'Back-and-forth moves loop and do not fit a flow chart, so they are listed in each step\'s details and drawn on Friction. Shares are of the busiest step; small bands are widened to stay visible, so read the printed numbers.'));
    c.id = 'sankey';
    return c;
  }

  /* Comparisons for Journeys, Cohorts and Friction. Columns: two or more picked groups side by side; one picked group is set against
     All users; none picked puts every group side by side. Each column is that group's own view of results.json. */
  const compareIds = () => (state.personas.length > 1 ? state.personas : state.personas.length === 1 ? [state.personas[0], 'all'] : visiblePersonas().map((p) => p.id));
  function compareCols() {
    return compareIds().map((id) => {
      const vv = D().views[`${state.range}|${state.platform}|${id}`];
      return vv ? { id, vv, label: id === 'all' ? 'All users' : persLabel(id), color: id === 'all' ? '#8E8E93' : LENS_COLOR[id] || LENS_COLOR.all } : null;
    }).filter(Boolean);
  }
  function heatTable(o) {
    const cols = o.cols, vals = o.rows.flatMap((r) => r.vals).filter((x) => x != null), mx = Math.max(0.0001, ...vals);
    const base = o.tone === 'accent' ? 'var(--accent)' : 'var(--crit-dot)';
    const tint = (x) => (x == null ? 'transparent' : `color-mix(in srgb, ${base} ${Math.round(6 + 52 * x / mx)}%, transparent)`);
    const grid = h('div', { class: 'hcmp', style: `--n:${cols.length}` }, h('div', { class: 'cmp-0' }), ...cols.map((c) => h('div', { class: 'cmp-h' }, h('i', { style: `background:${c.color}` }), c.label)),
      ...o.rows.flatMap((r) => { const top = Math.max(-1, ...r.vals.filter((x) => x != null)); return [h('div', { class: 'cmp-l' }, r.label),
        ...r.vals.map((x) => h('div', { class: 'hc' + (x != null && x === top && top > 0 ? ' top' : ''), style: `background:${tint(x)}` }, x == null ? h('span', { class: 'sub' }, 'few sessions') : h('b', {}, o.fmt(x))))]; }));
    return card(o.label, o.title, subTip(o.sub || '', o.tip), o.right || null, scroller(o.label + ' table, scroll sideways', grid));
  }
  function journeyCompare(cur) {
    if (!cur) return null;
    const cols = compareCols().filter((c) => c.vv.journeys.some((j) => j.id === cur.id)); if (cols.length < 2) return null;
    const stepsOf = (c) => (c.vv.journeys.find((j) => j.id === cur.id) || { steps: [] }).steps;
    const ids = stepsOf(cols[0]).map((x) => x.id).slice(0, -1);
    const rows = ids.map((sid) => ({ label: stepName(cur.id, sid), vals: cols.map((c) => { const st = stepsOf(c).find((x) => x.id === sid); return st && st.sessions >= 20 ? st.exits / st.sessions : null; }) }));
    let gap = null; rows.forEach((r) => { const v = r.vals.filter((x) => x != null); if (v.length > 1) { const d = Math.max(...v) - Math.min(...v); if (!gap || d > gap.d) gap = { d, r, hi: cols[r.vals.indexOf(Math.max(...v))], lo: cols[r.vals.indexOf(Math.min(...v))], a: Math.max(...v), b: Math.min(...v) }; } });
    return heatTable({ label: 'Step by step comparison', title: 'Who leaves where', cols, rows, fmt: (x) => (100 * x).toFixed(1) + '%',
      sub: gap ? `Biggest gap: ${gap.r.label}, ${gap.hi.label} ${(100 * gap.a).toFixed(1)}% against ${gap.lo.label} ${(100 * gap.b).toFixed(1)}%.` : '',
      tip: 'Each cell is the share of people at that step who left, for that group. Darker means more people leave. The bold figure marks the group where most leave at that step.' });
  }
  // A cohort's colour and wording come from the dataset's ui block (keyed by cohort name); one it does not know falls back to its tone.
  const cohortHue = (name, tone) => ((UI().cohorts || {})[name] || {}).hue || COHORT_COLOR[tone] || 'var(--natural)';
  /* One bar per user group, split by behaviour: the shares add up to the whole group, so a stacked bar reads better than a heat grid
     (and no longer looks like the red "Where each group struggles" grid on Friction). */
  function cohortCompare() {
    const cols = compareCols(); if (cols.length < 2) return null;
    const names = []; cols.forEach((c) => (c.vv.cohorts.items || []).forEach((x) => { if (!names.includes(x.name)) names.push(x.name); }));
    const tones = {}; cols.forEach((c) => (c.vv.cohorts.items || []).forEach((x) => { tones[x.name] = x.tone; }));
    const hue = (nm) => cohortHue(nm, tones[nm]);
    const seg = (c) => names.map((nm) => { const it = (c.vv.cohorts.items || []).find((x) => x.name === nm); return it && it.share > 0 ? { nm, share: it.share } : null; }).filter(Boolean);
    const rows = cols.map((c) => { const sg = seg(c), top = sg.slice().sort((a, b) => b.share - a.share).slice(0, 2);
      return h('div', { class: 'cmix-row' }, h('div', { class: 'cmix-l' }, h('i', { style: `background:${c.color}` }), c.label),
        h('div', { class: 'cmp-mix', role: 'img', 'aria-label': `${c.label}: ` + sg.map((x) => `${x.nm} ${x.share}%`).join(', ') }, sg.map((x) => h('i', { style: `flex:${x.share} 1 0;background:${hue(x.nm)}`, title: `${x.nm}: ${x.share}%` }))),
        h('span', { class: 'cmix-t' }, top.map((x) => `${x.nm} ${x.share}%`).join(' \u00b7 '))); });
    const key = h('div', { class: 'cmix-key' }, names.filter((nm) => cols.some((c) => seg(c).some((x) => x.nm === nm))).map((nm) => h('span', {}, h('i', { style: `background:${hue(nm)}` }), nm)));
    return card('Cohort comparison', 'Which groups behave how', subTip('Each bar is one user group, split by what its people do.', 'Each bar is one user group. Its colored parts are the share of that group in each behaviour, and together they make up the whole group. The line under the bar names the two biggest.'), null, key, h('div', { class: 'cmix' }, rows));
  }
  const FR_SIG = ['Repeated clicks', 'Going back and forth', 'Taps that did nothing', 'Stuck over 30s'];
  function frictionCompare(cur) {
    if (!cur) return null;
    const cols = compareCols().filter((c) => (c.vv.signals || {})[cur.id]); if (cols.length < 2) return null;
    const idx = Math.min(3, Math.max(0, state.frSig || 0)), stepIds = Object.keys(cols[0].vv.signals[cur.id]).filter((sid) => sid !== 'done');
    const rows = stepIds.map((sid) => ({ label: stepName(cur.id, sid), vals: cols.map((c) => { const a = (c.vv.signals[cur.id] || {})[sid]; const st = ((c.vv.journeys.find((j) => j.id === cur.id) || { steps: [] }).steps.find((x) => x.id === sid)) || {}; return a && st.sessions >= 20 ? a[idx] : null; }) }));
    const right = h('div', { class: 'sk-controls' }, h('div', { class: 'seg', role: 'group', 'aria-label': 'Which friction signal' }, FR_SIG.map((l, k) => h('button', { type: 'button', 'aria-pressed': String(k === idx), ...fk('fr-sig-' + k), onclick: () => { state.frSig = k; rerender('fr-sig-' + k); } }, l))));
    return heatTable({ label: 'Friction comparison', title: 'Where each group struggles', cols, rows, right, fmt: (x) => x.toFixed(1) + '%',
      sub: `Share of sessions at each step with: ${FR_SIG[idx].toLowerCase()}.`, tip: 'Pick a signal. Each cell is the share of that group\u2019s sessions at that step that showed it. Darker means more. The bold figure marks the group with the most.' });
  }

  function renderJourneys(v) {
    const jt = journeyTabs(v);
    // Comparing groups: the step cards would just be the combined numbers again, and "Buying by product" is not split by group,
    // so it only shows when no group is picked (it would look like it followed the filter, and it does not).
    const multi = state.personas.length > 1;
    return [pageHead('Journeys', false), jt.tabs ? h('div', { class: 'page-tabs' }, jt.tabs) : null, sankeyCard(v, jt), journeyCompare(jt.cur), multi ? null : flowCard(v, jt), multi ? null : blindCard(v), state.personas.length ? null : productCard()];
  }

  /* ---------- Friction ---------- */

  function arcsCard(cur) {
    const steps = cur.steps, n = steps.length;
    const pos = (i) => ((i + 0.5) / n) * 100;
    const idx = (id) => steps.findIndex((x) => x.id === id);
    const L = ((view().loops || {})[cur.id] || []).filter((l) => idx(l.from) >= 0 && idx(l.to) >= 0);
    const maxL = Math.max(1, ...L.map((l) => l.count));
    let maxH = 0;
    const arcs = L.map((l) => {
      const a = idx(l.from), b = idx(l.to), hh = 26 + Math.abs(a - b) * 34;
      maxH = Math.max(maxH, hh);
      const crit = steps[a].tone === 'critical', pos2 = l.kind === 'pos';
      const col = pos2 ? 'var(--pos-dot)' : crit ? 'var(--crit-dot)' : 'var(--warn-dot)';
      const txt = pos2 ? 'var(--pos)' : crit ? 'var(--crit)' : 'var(--warn)';
      const lo = Math.min(pos(a), pos(b)), hi = Math.max(pos(a), pos(b));
      return [h('div', { class: 'loop-arc', style: `position:absolute;left:${lo.toFixed(2)}%;width:${(hi - lo).toFixed(2)}%;bottom:77px;height:${hh}px;border:${Math.max(2, Math.round(2 + 8 * l.count / maxL))}px solid ${col};border-bottom:0;border-radius:50% 50% 0 0 / 100% 100% 0 0;opacity:.85`, 'aria-hidden': 'true' },
          s('svg', { class: 'arc-motion', viewBox: `0 0 100 ${hh}`, preserveAspectRatio: 'none' },
            s('path', { class: 'loop-track', d: `M 100 ${hh} C 78 0, 22 0, 0 ${hh}`, stroke: col, 'stroke-width': 3, 'stroke-dasharray': '8 7', 'stroke-linecap': 'round', fill: 'none' }),
            s('circle', { r: 3, fill: col }, s('animateMotion', { dur: '1.6s', repeatCount: 'indefinite', path: `M 100 ${hh} C 78 0, 22 0, 0 ${hh}` })))),
        h('div', { style: `position:absolute;left:${((lo + hi) / 2).toFixed(2)}%;bottom:${77 + hh + 4}px;width:60px;margin-left:-30px;text-align:center;font-size:12px;font-weight:600;color:${txt}`, role: 'img', 'aria-label': `${fmt(l.count)} sessions went back from ${stepName(cur.id, l.from)} to ${stepName(cur.id, l.to)}`, title: `Back from ${stepName(cur.id, l.from)} to ${stepName(cur.id, l.to)}` }, fmt(l.count))];
    });
    const total = L.reduce((t, l) => t + l.count, 0);
    return card('Back-and-forth loops', 'Back-and-forth', subTip('', 'Each arc is users stepping backwards, with the number of sessions. Thicker arc = more sessions.'),
      h('div', { class: 'legend loop-legend' },
        h('div', { class: 'loop-legend-items' },
          h('span', { class: 'loop-legend-item' }, h('i', { class: 'loop-icon warn' }), 'Frustrated loop'),
          h('span', { class: 'loop-legend-item' }, h('i', { class: 'loop-icon crit' }), 'Loop out of a critical step'),
          h('span', { class: 'loop-legend-item' }, h('i', { class: 'loop-icon pos' }), 'Comparison loop')),
        h('span', { class: 'pillstat' }, fmt(total) + ' backward moves')),
      scroller('Back-and-forth arcs, scroll sideways', h('div', { class: 'arcs', style: `height:${77 + maxH + 32}px;position:relative` },
        h('div', { style: `position:absolute;left:${pos(0).toFixed(2)}%;width:${(pos(n - 1) - pos(0)).toFixed(2)}%;bottom:76px;height:2px;background:var(--line-2)` }),
        arcs, steps.map((st, i) => [h('div', { style: `position:absolute;left:${pos(i).toFixed(2)}%;bottom:71px;width:12px;height:12px;margin-left:-6px;border-radius:50%;background:var(--${{ critical: 'crit', warning: 'warn', positive: 'pos', healthy: 'ok' }[st.tone]}-dot);box-shadow:0 0 0 3px var(--panel)`, 'aria-hidden': 'true' }),
          h('div', { class: 'arc-lab', style: `position:absolute;left:${pos(i).toFixed(2)}%;bottom:8px;width:120px;margin-left:-60px` }, h('span', { class: 'arc-ico', 'aria-hidden': 'true' }, icon(stepIcon(st.id), 15, 1.7)), stepName(cur.id, st.id))]))));
  }
  const heatLevel = (x) => (x >= 10 ? 4 : x >= 6 ? 3 : x >= 3 ? 2 : x >= 1 ? 1 : 0);
  function heatCard(cur, v) {
    const sig = (v.signals || {})[cur.id] || {};
    const rows = cur.steps.map((st) => h('div', { class: 'hrow' },
      h('button', { type: 'button', class: 'hname', onclick: (e) => openDrawer({ type: 'step', journey: cur.id, step: st.id }, e.currentTarget) }, stepName(cur.id, st.id), stepFaultActive(cur.id, st.id) ? h('span', { title: 'Possible data gap', style: 'display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--tech-dot);margin-left:6px' }) : null),
      (sig[st.id] || [0, 0, 0, 0]).map((x) => h('div', { class: 'hcell h' + heatLevel(x) }, x.toFixed(1) + '%'))));
    return card('Friction signals by step', 'Friction signals by step', subTip('', '% of sessions at each step showing the signal. A purple dot means a technical fault may be distorting that row.'), null,
      scroller('Friction signals table, scroll sideways', h('div', { class: 'heat' }, h('div', { class: 'hrow head' }, h('span'), h('span', {}, 'Rage clicks'), h('span', {}, 'Back-and-forth'), h('span', {}, 'Dead taps'), h('span', {}, 'Stuck >30 s')), rows)),
      h('div', { class: 'legend' }, [['< 1%', 0], ['1–3%', 1], ['3–6%', 2], ['6–10%', 3], ['≥ 10%', 4]].map(([t, l]) => h('span', {}, h('i', { class: 'sw', style: `width:18px;height:12px;background:var(--h${l});box-shadow:inset 0 0 0 1px var(--line-2)` }), t))));
  }
  function hotCards(cur) {
    const list = D().hotspots && D().hotspots.length ? D().hotspots : (D().hotspot ? [D().hotspot] : []);
    return list.filter((H) => H.journey === cur.id).map((H) => hotCard(H));
  }
  function hotCard(H) {
    if (!H.spots || !H.spots.length) return null;
    const total = H.spots.reduce((t, x) => t + x[3], 0), maxS = Math.max(1, ...H.spots.map((x) => x[3]));
    return card('Rage-click hotspots', 'Rage-click hotspots · ' + H.screen, subTip('', 'A rage click is three or more taps on the same spot within two seconds. The screen is a simple sketch, not a screenshot.'), null,
      h('div', { class: 'hotwrap' },
        h('div', { class: 'phone', role: 'img', 'aria-label': `Hotspot map of the ${H.screen} screen: ` + H.spots.map((x) => `${x[4]} ${fmt(x[3])} rage taps`).join('; ') },
          H.elements.map((e) => h('div', { class: 'el ' + e[4], style: `top:${e[0]}%;left:${e[1]}%;width:${e[2]}%;height:${e[3]}%` }, e[5] || '')),
          H.spots.map((x, i) => [h('div', { class: 'spot', style: `top:${x[0]}%;left:${x[1]}%;width:${x[2]}px;height:${x[2]}px;margin:-${x[2] / 2}px 0 0 -${x[2] / 2}px` }), h('span', { class: 'spotn', style: `top:${x[0]}%;left:${x[1]}%;transform:translate(${i % 2 ? 12 : -12}px,${i % 2 ? 8 : -8}px)` }, String(i + 1))])),
        h('div', { class: 'hot-l' }, H.spots.map((x, i) => h('div', { class: 'hot-i' }, h('div', { class: 'r' }, h('span', { class: 'spotn' }, String(i + 1)), h('span', { class: 't' }, x[4]), h('b', {}, fmt(x[3]))), h('div', { class: 'track' }, h('i', { style: `width:${Math.round(100 * x[3] / maxS)}%` })))),
          h('p', { class: 'sub' }, H.note + ` ${fmt(total)} rage taps in all.`),
          h('button', { type: 'button', class: 'btn-dark', style: 'align-self:flex-start', onclick: (e) => openDrawer({ type: 'step', journey: H.journey, step: H.step }, e.currentTarget) }, 'View diagnosis'))));
  }
  const MK = { tap: [8, 26, '50%', '8px', -4, ''], rage: [16, 22, '4px', null, 0, ''], idle: [6, 27, '3px', null, 0, ''], back: [16, 22, '50%', '16px', -8, '←'], exit: [14, 23, '3px', '14px', -7, '×'], done: [14, 23, '50%', '14px', -7, ''] };
  function replayCard(cur) {
    const ss = (D().stuck_sessions || []).filter((x) => (!state.personas.length || state.personas.includes(x.persona)) && x.journey === cur.id);
    const pct = (t) => (100 * t / 120).toFixed(2);
    const rows = ss.map((x) => h('div', { class: 'rrow' }, h('div', { class: 'who' }, h('b', {}, x.who), h('span', { class: x.good ? 't-ok' : 't-crit' }, x.outcome)),
      h('div', { class: 'lane', role: 'img', 'aria-label': `${x.who}: ${x.outcome}. Screens: ` + x.bands.map((b) => b[2]).join(', ') },
        x.bands.map((b, i) => h('div', { class: 'bnd' + (i % 2 ? ' alt' : ''), style: `left:${pct(b[0])}%;width:${pct(b[1] - b[0])}%` }, b[2])),
        x.marks.map((m) => { const d = MK[m[0]]; const rng = m.length > 2; return h('div', { class: 'mk ' + m[0], style: `left:${pct(m[1])}%;top:${d[1]}px;height:${d[0]}px;width:${rng ? pct(m[2] - m[1]) + '%' : d[3]};margin-left:${rng ? 0 : d[4]}px` }, d[5]); }),
        h('div', { class: 'replay-playhead', 'aria-hidden': 'true' }))));
    const lg = (c, t) => h('span', { class: 'lg-i' }, c, t);
    return card('Stuck sessions', 'Stuck sessions, replayed', subTip('', 'Sessions picked by the AI. Each row is one session; shaded bands are screens, read left to right.'), null,
      h('div', { class: 'legend' }, lg(h('i', { class: 'sw', style: 'width:8px;height:8px;border-radius:50%;background:var(--muted-dot)' }), 'Tap'), lg(h('i', { class: 'sw', style: 'width:18px;height:10px;background:var(--crit-dot)' }), 'Rage burst'),
        lg(h('i', { class: 'sw', style: 'width:18px;height:6px;background:repeating-linear-gradient(90deg,var(--muted-dot) 0 4px,transparent 4px 7px)' }), 'Idle / stuck'), lg(h('i', { class: 'sw', style: 'width:14px;height:14px;border-radius:50%;background:var(--pos-dot)' }), 'Went back'),
        lg(h('i', { class: 'sw', style: 'width:12px;height:12px;background:var(--ink)' }), 'Exit'), lg(h('i', { class: 'sw', style: 'width:12px;height:12px;border-radius:50%;background:var(--ok-dot)' }), 'Completed')),
      ss.length ? scroller('Stuck session replays, scroll sideways', h('div', { class: 'rep' }, rows, h('div', { class: 'axis' }, h('span'), h('div', {}, ['0s', '30s', '60s', '90s', '120s'].map((t) => h('span', {}, t)))))) : h('div', { class: 'empty' }, 'No sampled sessions for this persona in this journey.'),
      h('p', { class: 'sub' }, 'Stuck = no forward progress for 30s or more, or 3+ taps on one target within 2 s.'));
  }
  function renderFriction(v) {
    const { cur, tabs } = journeyTabs(v);
    const head = h('div', { class: 'page-head' }, h('div', {}, h('h1', { class: 'title', id: 'page-title' }, 'Friction'), h('p', { class: 'sub' }, 'Where users loop, rage and get stuck')), tabs);
    if (!cur) return [head, h('div', { class: 'card' }, h('p', { class: 'sub' }, 'This persona has no sessions in a mapped journey for this timeframe.'))];
    const hots = hotCards(cur);
    return [head, arcsCard(cur), frictionCompare(cur), hots.length ? h('div', { class: 'grid2' }, heatCard(cur, v), hots[0]) : heatCard(cur, v), hots.slice(1), replayCard(cur)];
  }

  /* ---------- Brief: a one-page status report, built only from fields already in results.json ---------- */
  /* Numbers stand out inside a sentence (dates like 2026-10-11 are left alone). */
  function boldNums(text) {
    const s2 = String(text || ''), out = [], re = /(?<![\d-])\d[\d,]*(?:\.\d+)?%?(?![\d-])/g;
    let last = 0, m;
    while ((m = re.exec(s2))) { out.push(s2.slice(last, m.index), h('b', {}, m[0])); last = m.index + m[0].length; }
    out.push(s2.slice(last));
    return out;
  }
  function briefModel(v) {
    const kp = Object.fromEntries(v.kpis.map((k) => [k.id, k]));
    const all = v.insight_ids.map(insightById).filter(Boolean);
    const open = all.filter((i) => i.severity !== 'healthy' && statusOf(i.id) === 'open').sort((a, b) => ((b.impact || {}).score || 0) - ((a.impact || {}).score || 0));
    const fine = all.filter((i) => i.severity === 'healthy').slice(0, 3);
    const R = v.rhythm, sum = (a) => (a || []).reduce((x, y) => x + y, 0), tn = sum(R.natural), tf = sum(R.frustrated);
    const trackers = ((v.health || {}).tiles || []).find((x) => x.label === 'Trackers firing');
    const faults = activeFaults().filter((f) => f.sev !== 'resolved');
    const first = (s) => { const m = /^(.+?[.!?])(\s|$)/.exec(String(s || '').trim()); return m ? m[1] : String(s || '').trim(); };
    const items = open.slice(0, 3).map((i) => {
      const ds = diagState(i), ai = ds === 'ai' || ds === 'cached', dg = i.diagnosis || {};
      const cause = ai && dg.summary ? first(dg.summary) : ((i.causes || [])[0] || {}).title || 'Cause not diagnosed yet.';
      const step = ai && (dg.next_steps || [])[0] ? dg.next_steps[0].text : null;
      const w = (i.impact || {}).per_week_value;
      return { i, cause, step, who: [i.segment_text, `${fmt(i.n_sessions)} sessions`, w > 0 ? `about ${money(w)} a week (estimated value)` : null].filter(Boolean).join(' · ') };
    });
    const conv = kp.conversion, head = [
      conv ? `${conv.label} is ${fmtKpi(conv, conv.value)} (${deltaText(conv)}).` : '',
      open.length ? `${open.length} ${open.length === 1 ? 'finding needs' : 'findings need'} attention; the biggest is “${open[0].title}”.` : 'Nothing needs attention right now.'].filter(Boolean).join(' ');
    return { kp, open, items, fine, tn, tf, trackers, faults, head, conv };
  }
  /* One-page brief. The user-group filter changes the lens: its own accent, kicker, action title (one sentence with the takeaway),
     three numbers, and so on, all computed from that group's view of results.json. Built to print on one A4 page. */
  const LENS_COLOR = { all: '#0071E3', unregistered: '#7C5CFF', large_business: '#A0693B', sari_sari: '#E07B00', individual_trader: '#D63384', individual: '#0F7B9A' };   // the groups' ids are the same in every dataset; their wording is in ui.brief
  const DEFAULT_LENS = { lead: '{convLabel} is {c}, {dlt}', sub: '{sub}', tiles: ['completion', 'money', 'probs'] };

  const lowerFirst = (x) => (/^[A-Z]{2,}/.test(x) ? x : x.charAt(0).toLowerCase() + x.slice(1));
  const shorten = (x) => plain(x).replace(/\s*\([^)]*\)/g, '').replace(/\.$/, '');
  const ownerOf = (txt) => (/log|infrastructure|backend|service|error|timeout|tracker|tracking|fix/i.test(txt) ? 'Engineering' : /screen|content|wording|copy|layout|design/i.test(txt) ? 'Design' : 'Product');
  function briefPlan(v, B) {
    const BR = UI().brief || {}, specs = BR.personas || {};
    const pid = state.personas.length <= 1 && LENS_COLOR[state.persona] && specs[state.persona] ? state.persona : 'all', accent = LENS_COLOR[pid], kicker0 = (BR.kickers || {})[pid] || selectedLabels(), kicker = state.personas.length > 1 ? selectedLabels() + ' · combined' : kicker0;
    const coh = (name) => ((v.cohorts.items.find((c) => c.name === name) || {}).share) || 0;
    const conv = B.conv, c = conv ? Math.round(conv.value) + '%' : '', risk = B.kp.value_at_risk, bs = B.kp.blind_spots;
    const drv = B.items[0] ? lowerFirst(shorten(B.items[0].i.title)) : null;
    const num = (label, value, note, cls) => ({ label, value, note, cls });
    const completion = conv ? num(conv.label, fmtKpi(conv, conv.value), deltaText(conv)) : null;
    const money1 = risk ? num('Value at risk', fmtKpi(risk, risk.value) + ' /wk', 'Estimated value, not measured', 't-crit') : null;
    const probs = bs ? num('Serious problems', String(bs.value), `${bs.value - bs.prev >= 0 ? '+' : ''}${bs.value - bs.prev} vs. previous period`, bs.value > 0 ? 't-crit' : '') : null;
    const dd = conv ? conv.value - conv.prev : 0, dlt = conv && Math.abs(dd) >= 0.05 ? `${dd < 0 ? 'down' : 'up'} ${Math.abs(dd).toFixed(1)} points` : 'flat';
    // The headline is two parts: the claim (one line where it fits) and what drives it (a lighter second line).
    const tidy = (x) => String(x || '').replace(/^(.+?) users buying (.+?) leave at (.+?) far more often than other users$/i, '$2 buyers leave at $3 far more often').replace(/ than other users$/i, '');
    const sub0 = B.items[0] ? tidy(shorten(B.items[0].i.title)) : null, subCap = sub0 ? sub0.charAt(0).toUpperCase() + sub0.slice(1) : null;
    // The headline, its second line and the three number tiles come from the dataset's ui.brief block, one entry per user group.
    const spec = specs[pid] || DEFAULT_LENS, fill = (t) => String(t).replace(/\{(\w+)\}/g, (m, k) => ({ c, dlt, convLabel: conv ? conv.label : 'Completion', coh: coh(spec.sub_cohort), sub: subCap, subLower: sub0 ? lowerFirst(sub0) : '' })[k] ?? '');
    let sub = null;
    if (spec.sub_when && B.items.find((x) => new RegExp(spec.sub_when.title, 'i').test(x.i.title))) sub = spec.sub_when.text;
    else if (spec.sub) sub = /\{sub(Lower)?\}/.test(spec.sub) && !sub0 ? (spec.sub_fallback || null) : fill(spec.sub);
    const tileOf = (t) => {
      if (t === 'completion') return completion; if (t === 'money') return money1; if (t === 'probs') return probs;
      if (t === 'sessions') return num('Sessions', fmt(v.sessions), 'in this range');
      if (t && t.product) { const p = ((D().product_funnels || {})[t.product] || {}).completion; return p != null ? num(t.label, Math.round(100 * p) + '%', t.note) : (t.otherwise ? tileOf(t.otherwise) : null); }
      if (t && t.cohort) return num(t.label, coh(t.cohort) + '%', t.note, t.cls);
      return null;
    };
    const T = [fill(spec.lead), sub, (spec.tiles || DEFAULT_LENS.tiles).map(tileOf)];
    const steps = B.items.filter((x) => x.step).slice(0, 3).map((x) => ({ owner: ownerOf(x.step), text: x.step }));
    return { pid, kicker, accent, lead: T[0], sub: T[1], title: T[1] ? `${T[0]}. ${T[1]}` : T[0], nums: T[2].filter(Boolean), steps, drivers: B.items.slice(0, 2) };
  }
  function briefText(P, B) {
    return [`# ${plain(P.title)}`, `_${P.kicker}_`, `Timeframe: ${timeframeText()}`, '', ...P.nums.map((n) => `- ${n.label}: ${n.value} (${n.note})`), '', '## What is driving it',
      ...P.drivers.map((x) => `- ${x.i.title}. ${x.cause}`), '', '## What we would do this week', ...(P.steps.length ? P.steps.map((s, n) => `${n + 1}. ${s.owner}: ${s.text}`) : ['Nothing urgent.']), '',
      '## Working as expected', `- ${fmt(B.tn)} of ${fmt(B.tn + B.tf)} exits were people leaving normally.`, ...B.fine.map((i) => `- ${i.title}`), '',
      '## Read with care', ...(B.faults.length ? B.faults.map((f) => `- ${f.title}. ${f.impact}`) : ['- No tracking problems in this range.']), '', '_Synthetic sample data. Money figures are estimated values, not measured._'].map(plain).join('\n');
  }
  /* "Rewrite with Gemini" on the Brief (docs/brief-ai-endpoint.md). The server says whether it is switched on; it is OFF everywhere until the
     owner activates it, and then the button is simply not drawn. Gemini rewrites only the wording; the tiles, finding titles and charts stay
     computed by code, and the server throws the answer away if it quotes a number that is not in the data. */
  function briefAIStatus() {
    if (state.briefAI !== null) return;
    state.briefAI = false;    // until the server says otherwise (also covers a static host with no /api)
    fetch('/api/brief-ai/status').then((r) => (r.ok ? r.json() : null)).then((d) => { if (d && d.enabled === true) { state.briefAI = true; if (state.view === 'brief') renderView(); } }).catch(() => {});
  }
  const briefKey = (B, P) => `${state.range}|${state.platform}|${P.pid}|${B.items.map((x) => x.i.id).join(',')}`;
  /* The standard plan with Gemini's wording laid over it, when there is one for this view and these findings. */
  function withRewrite(P, rw) {
    if (!rw) return P;
    const drivers = P.drivers.map((x, n) => ({ ...x, cause: rw.drivers[n] || x.cause }));
    return { ...P, lead: rw.headline, sub: rw.sub, title: `${rw.headline}. ${rw.sub}`, drivers, steps: rw.steps.length ? rw.steps : P.steps };
  }
  async function runBriefRewrite(B, P, again) {
    if (state.briefRwBusy || Date.now() < state.briefRwUntil) return;
    const key = briefKey(B, P), gen = state.gen;
    state.briefRwBusy = true; state.briefRwMsg = ''; rerender('brief-ai'); announce('Asking Gemini to rewrite the brief');
    try {
      const res = await fetch('/api/brief-ai', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ range: state.range, platform: state.platform, persona: P.pid, ids: B.items.map((x) => x.i.id), again: !!again, dataset: state.dsId }) });
      const d = await res.json().catch(() => null);
      if (gen !== state.gen) return;
      if (!res.ok || !d) throw new Error('bad_response');
      state.briefRwUntil = Date.now() + (d.retry_in_s != null ? d.retry_in_s : 30) * 1000;
      if (d.source === 'gemini' && Array.isArray(d.drivers) && Array.isArray(d.steps)) { state.briefRw[key] = d; announce('Brief rewritten'); }
      else state.briefRwMsg = d.reason || 'The standard brief stays.';
    } catch (e) { if (gen !== state.gen) return; state.briefRwMsg = 'The rewrite could not be reached. The standard brief stays.'; }
    state.briefRwBusy = false;
    if (state.view === 'brief') rerender('brief-ai');
    const wait = state.briefRwUntil - Date.now();
    if (wait > 0) window.setTimeout(() => { if (state.view === 'brief') rerender(null); }, wait + 50);
  }
  /* The Brief starts folded and is generated on request: with a real data source the Brief would not exist until someone asks for it,
     so the demo behaves the same way. It is built by code from the numbers on the page, so generating it is instant. */
  function briefFolded(P) {
    const btn = h('button', { type: 'button', class: 'btn', ...fk('brief-gen'), onclick: () => { state.briefOpen = true; rerender('brief-title'); announce('Brief generated'); } }, icon(SPARKLE, 16, 1.8), 'Generate brief');
    return h('article', { class: 'card brief brief-folded', 'aria-label': 'Brief, not generated yet', 'data-persona': P.pid, style: `--b-accent:${P.accent}` },
      h('div', { class: 'b-kick' }, h('span', { class: 'b-dot' }), P.kicker, h('span', { class: 'b-when' }, timeframeText())),
      h('p', { class: 'b-fold-t' }, 'A one-page brief for this timeframe and user group: the headline, three numbers, what is driving it and what to do this week.'),
      h('div', { class: 'b-foot' }, btn, h('span', { class: 'sub' }, 'Built from the synthetic sample data on this view. Change the timeframe or user group above first if you want a different one.')));
  }
  function renderBrief(v) {
    briefAIStatus();
    const B = briefModel(v), P0 = briefPlan(v, B), key = briefKey(B, P0), rw = state.briefRw[key] || null, P = withRewrite(P0, rw);
    if (!state.briefOpen) return [pageHead('Brief', false, false, true), briefFolded(P0)];
    const copyBtn = h('button', { type: 'button', class: 'btn-line', onclick: () => {
      const done = () => { copyBtn.textContent = 'Copied'; announce('Brief copied'); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(briefText(P, B)).then(done, done); else done();
    } }, 'Copy as text');
    // Same local ticket draft as the finding cards, for the finding that drives the brief; the owner is the first step's owner.
    const top = B.items[0] && B.items[0].i, owner = (P.steps[0] && P.steps[0].owner) || 'Engineering';
    const ticketBtn = top ? h('button', { type: 'button', class: 'btn-line', ...fk('brief-ticket'), onclick: (e) => { state.owners[top.id] = state.owners[top.id] || owner; openDrawer({ type: 'insight', id: top.id, ticket: findingTicket(top, state.owners[top.id]) }, e.currentTarget); } }, 'Draft ticket') : null;
    const canAI = state.briefAI === true && state.personas.length <= 1 && B.items.length > 0, wait = Math.max(0, Math.ceil((state.briefRwUntil - Date.now()) / 1000));
    const aiBtns = canAI ? [h('button', { type: 'button', class: 'btn-line b-aibtn', ...fk('brief-ai'), disabled: state.briefRwBusy || wait > 0, 'aria-busy': String(state.briefRwBusy),
        onclick: () => runBriefRewrite(B, P0, !!rw) }, icon(SPARKLE, 14, 1.8), state.briefRwBusy ? 'Rewriting…' : rw ? (wait > 0 ? `Rewrite again in ${wait}s` : 'Rewrite again') : 'Rewrite with Gemini'),
      rw ? h('button', { type: 'button', class: 'btn-text link', onclick: () => { delete state.briefRw[key]; rerender('brief-ai'); announce('Standard wording restored'); } }, 'Standard wording') : null,
      state.briefRwMsg ? h('span', { class: 'sub', role: 'status' }, state.briefRwMsg) : null] : (state.personas.length <= 1 && B.items.length > 0 ? [
      // Switched off on the server: still drawn, greyed out, so the feature can be seen and nobody hunts for it. Nothing happens on click.
      h('button', { type: 'button', class: 'btn-line b-aibtn', disabled: true }, icon(SPARKLE, 14, 1.8), 'Rewrite with Gemini')] : null);
    return [pageHead('Brief', false, false, true), h('article', { class: 'card brief', 'aria-label': 'One-page brief', 'data-persona': P.pid, style: `--b-accent:${P.accent}` },
      h('div', { class: 'b-kick' }, h('span', { class: 'b-dot' }), P.kicker, rw ? h('span', { class: 'b-ai', title: rw.notice }, icon(SPARKLE, 12, 2), 'Wording by Gemini, numbers checked by code') : null, h('span', { class: 'b-when' }, timeframeText())),
      h('h2', { class: 'b-title', ...fk('brief-title'), tabindex: '-1' }, h('span', { class: 'b-t1' }, P.lead), P.sub ? h('span', { class: 'b-t2' }, P.sub) : null),
      h('div', { class: 'b-stats' }, P.nums.map((n) => h('div', { class: 'b-stat' }, h('span', { class: 'k-label' }, n.label), h('span', { class: 'k-val ' + (n.cls || '') }, n.value), h('span', { class: 'sub' }, n.note)))),
      h('div', { class: 'b-cols' },
        h('section', { class: 'b-sec', 'aria-labelledby': 'b-h1' }, h('h3', { id: 'b-h1' }, 'What is driving it'),
          P.drivers.length ? h('ul', { class: 'b-plain' }, P.drivers.map((x) => { const a = h('button', { type: 'button', class: 'b-link', onclick: () => openDrawer({ type: 'insight', id: x.i.id }, a) }, x.i.title); return h('li', { class: 'b-drv' }, h('span', { class: 'b-ico ' + (x.i.severity === 'critical' ? 'crit' : 'warn'), 'aria-hidden': 'true' }, icon(NAV_ICON.friction, 18, 1.9)), h('div', {}, a, h('span', { class: 'sub' }, ' ' + x.cause))); })) : h('p', { class: 'b-p' }, 'No single problem stands out.')),
        h('section', { class: 'b-sec', 'aria-labelledby': 'b-h2' }, h('h3', { id: 'b-h2' }, 'What we would do this week'),
          P.steps.length ? h('ol', { class: 'b-list' }, P.steps.map((s) => h('li', {}, h('span', { class: 'b-own' }, s.owner), ' ' + s.text))) : h('p', { class: 'b-p' }, 'Nothing urgent.'))),
      h('div', { class: 'b-strip' },
        h('p', {}, h('b', {}, 'Working as expected. '), boldNums(`${fmt(B.tn)} of ${fmt(B.tn + B.tf)} exits were people leaving normally.${B.fine[0] ? ' ' + B.fine[0].title + '.' : ''}`)),
        h('p', {}, h('b', {}, 'Read with care. '), boldNums(B.faults.length ? B.faults.map((f) => f.title + '.').join(' ') : 'No tracking problems in this range.'))),
      h('div', { class: 'b-foot' }, copyBtn, h('button', { type: 'button', class: 'btn-line', onclick: () => window.print() }, 'Print (one A4 page)'), ticketBtn,
        aiBtns,
        h('button', { type: 'button', class: 'btn-text link', ...fk('brief-gen'), onclick: () => { state.briefOpen = false; rerender('brief-gen'); announce('Brief folded'); } }, 'Fold brief'),
        h('span', { class: 'sub' }, 'Source: synthetic sample data, ' + rangeLabel() + '. Money figures are estimated values, not measured.'))),];
  }

  /* ---------- Cohorts ---------- */
  function cohortInfo(c) {
    const k = (UI().cohorts || {})[c.name];
    if (k && k.who) return [k.who, k.todo, k.rel ? new RegExp(k.rel, 'i') : null, k.biz];
    const problem = c.tone === 'crit' || c.tone === 'warn';
    return ['People grouped together by a simple rule about how they behave.', problem ? 'Look into what these people run into first.' : 'Nothing to fix. Check whether this share grows or shrinks.', null,
      problem ? 'These people are the ones most likely to be lost, so their share is worth watching.' : 'Shows how much of your active users behave this way.'];
  }
  function renderCohorts(v) {
    const C = v.cohorts, items = C.items.filter((c) => c.share > 0), peak = Math.max(1, ...items.map((x) => x.share));
    const activeUsers = Number(((/(\d[\d,]*) users active/.exec(C.note || '') || [])[1] || '0').replace(/,/g, ''));
    const all = v.insight_ids.map(insightById).filter(Boolean);
    const rows = items.map((c) => {
      const info = cohortInfo(c), rel = info && info[2] ? all.find((i) => info[2].test(i.title)) : null;
      const sum = h('summary', {}, h('span', { class: 'n' }, c.name, c.is_new ? h('span', { class: 'newbadge' }, 'NEW') : null),
        h('div', { class: 'bar', 'aria-hidden': 'true' }, h('i', { style: `width:${(100 * c.share / peak).toFixed(1)}%;background:${COHORT_COLOR[c.tone] || COHORT_COLOR.muted}` })), h('span', { class: 's' }, h('b', {}, c.share + '%'), activeUsers ? h('small', {}, '~' + fmt(Math.round(activeUsers * c.share / 100)) + ' users') : null),
        h('span', { class: 'coh-c', 'aria-hidden': 'true' }, icon('M6 9l6 6 6-6', 16)));
      return h('details', { class: 'coh' }, sum, info ? h('div', { class: 'coh-b' },
        h('p', {}, h('b', {}, 'Who they are. '), info[0]),
        h('p', {}, h('b', {}, 'Business value. '), info[3] || '', rel && rel.impact && rel.impact.per_week_value > 0 ? ` Related finding at risk: about ${money(rel.impact.per_week_value)} a week (estimated value).` : ''),
        h('p', {}, h('b', {}, 'What to do. '), info[1]),
        rel ? (() => { const btn = h('button', { type: 'button', class: 'btn-line', onclick: () => openDrawer({ type: 'insight', id: rel.id }, btn) }, 'See the related finding'); return btn; })() : null) : null);
    });
    const cohortsCard = card('Behavioral cohorts', 'Behavioral cohorts', subTip('Open a group to see who they are and what to do.', 'People are put into groups using simple rules, such as stalled at the OTP code. Each bar shows the share of active users in that group. Groups with nobody in them are hidden.'), null,
      h('div', { class: 'cohlist' }, rows), h('p', { class: 'sub' }, C.note));
    return [pageHead('Cohorts', false), cohortsCard, cohortCompare()];
  }

  /* How Squint works: five plain steps, who does each (code, AI or you), and a real example from this data. */
  function howWorksCard(withExample = true) {
    const steps = [
      ['M12 3v12M7 10l5 5 5-5M5 21h14', 'Ingest your data', 'Reads your events from an uploaded JSON file or a BigQuery table. This demo has a sample dataset already loaded.', 'Intake', ['Code', 'code']],
      ['M4 7h6M14 7h6M4 17h6M14 17h6M10 7l4 10M14 7l-4 10', 'Translate to plain steps', `Turns raw event names into the steps people recognise, such as ${(UI().how || {}).examples || 'a phone number or a checkout'}, and groups them into journeys.`, 'Semantic Agent', ['Code, you verify', 'code']],
      ['M3 12h4l3-8 4 16 3-8h4', 'Identify issues', 'Sets aside sessions hit by tracking gaps, then flags every screen, group and time window that jumps past its usual level.', 'Guardian and Watchdog', ['Code', 'code']],
      [SPARKLE, 'Explain why', 'Reads the numbers for each flagged problem and writes the likely reason and a next step. Code throws away any number it quotes that is not in the data.', 'Diagnostic Agent (Gemini)', ['AI, checked by code', 'ai']],
      ['M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h6', 'Report and decide', 'Drafts a one-page brief and ticket notes for each finding. You decide what to do. Nothing is changed in your product on its own.', 'Brief and tickets', ['You decide', 'you']],
    ];
    const open = (D().insights || []).filter((i) => i.severity !== 'healthy' && !(i.persona_ids || []).every((p) => HIDDEN_PERSONAS.includes(p)) && (i.persona_ids || []).length).sort((a, b) => ((b.impact || {}).score || 0) - ((a.impact || {}).score || 0));
    const exRe = new RegExp((UI().how || {}).example_re || '$^', 'i'), ex = withExample ? (open.find((i) => exRe.test(i.title)) || open[0]) : null;
    const exLines = ex ? [['Spotted', ex.title], ['Checked', `Before counting, ${fmt((D().meta.counts || {}).sessions_quarantined || 0)} sessions inside a tracking fault were set aside, so they cannot distort this.`], ['Flagged', ((ex.facts || [])[0] || '') + ' ' + fmt(ex.n_sessions) + ' sessions are affected.'],
      ['Explained', ((ex.diagnosis || {}).summary || '').split(/(?<=[.!?])\s/)[0] || 'The analyst names a likely reason and a next step.'], ['Your move', ((((ex.diagnosis || {}).next_steps || [])[0]) || {}).text || 'Pick an owner and look into it.']] : [];
    return foldCardKeyed({ key: 'how', open: false, icon: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM16 8l-2 6-6 2 2-6z' }, 'How this works', 'How Squint works', 'From raw taps to a finding you can act on, in five steps. Each step says whether code, AI or you does the work.',
      h('ol', { class: 'hw-flow' }, steps.map(([ico, name, text, agent, [tag, kind]], n) => h('li', { class: 'hw-step' },
        h('span', { class: 'hw-n' }, String(n + 1)), h('span', { class: 'hw-ico', 'aria-hidden': 'true' }, icon(ico, 20, 1.7)), h('b', {}, name), h('span', { class: 'hw-agent' }, agent), h('p', {}, text), h('span', { class: 'hw-tag hw-' + kind }, kind === 'ai' ? icon(SPARKLE, 11, 2) : null, tag)))),
      ex ? h('div', { class: 'hw-ex' }, h('span', { class: 'd-lab' }, 'A real example from this data'),
        h('ul', {}, exLines.map(([k, v]) => h('li', {}, h('b', {}, k), h('span', {}, rt(v)))))) : null,
      h('div', { class: 'hw-two' },
        h('div', {}, h('b', {}, 'What the AI does'), h('p', {}, 'Reads the numbers, writes the explanation, and on request checks each line of it. It can make mistakes, so every AI line is tagged and every number in it is checked by code.')),
        h('div', {}, h('b', {}, 'What code does'), h('p', {}, 'Counts everything, decides what gets flagged, sets bad data aside, computes the money figures (always marked as estimated), and rejects any AI number that is not in the data.'))));
  }

  /* ---------- Settings (read-only view of what was mapped) ---------- */
  function mappingTable(mj) {
    return scroller('Event mapping table for ' + mj.name + ', scroll sideways', h('div', { class: 'maptable' }, h('div', { class: 'mrow head' }, h('span', {}, '#'), h('span', {}, 'Journey step'), h('span', {}, 'Source event'), h('span', { class: 'r' }, 'Confidence'), h('span', { class: 'r' }, 'Status')),
      mj.steps.map((x, i) => h('div', { class: 'mrow' }, h('span', { class: 'muted num' }, String(i + 1)), h('span', { style: 'font-weight:500' }, x.name), h('code', {}, 'screen_name = ' + x.event),
        h('span', { class: 'r num' }, x.conf == null ? '—' : x.conf.toFixed(2)), h('span', { class: 'mstat ' + x.status }, x.status === 'matched' ? 'Matched' : 'Review')))));
  }
  const ENGINES = [['json', 'Upload JSON', 'File upload'], ['bq', 'Your own BigQuery', 'Database connection']];
  const dsDef = (id) => state.registry.find((d) => d.id === id) || null;
  /* Step 2 checks one flow (the screens each journey goes through) against the events the chosen dataset's source logs. Both flow files and the
     event lists are static files read once when the page starts; the check itself runs here, with no request. The flow defaults to the chosen
     dataset's own flow; picking the other one shows the mismatch. */
  const flowDef = (id) => state.flows[id] || null;
  const flowId = () => state.flowPick || state.dsId;
  const flowCount = (f) => ({ j: f.journeys.length, s: f.journeys.reduce((a, j) => a + (j.steps || []).length, 0) });
  function runFlowCheck() {
    const flow = flowDef(flowId()), events = state.srcEvents[state.dsId] || [];
    if (!flow || !events.length) return { ok: false, mismatch: false, journeys: 0, steps: 0, match: { found: 0, total: 0 }, better: null, problems: [{ code: 'unreadable', journey: null, step: null, journeyName: null, stepName: null, message: 'The flow or the list of events could not be read.', fix: 'Reload the page and try again.' }] };
    const res = SquintFlowCheck.check(flow, events), match = SquintFlowCheck.match(flow, events);
    const better = SquintFlowCheck.rank(state.flowIds.map(flowDef).filter(Boolean), events).filter((r) => r.id !== flow.id && r.found > match.found)[0] || null;
    return { ...res, match, better, mismatch: match.found < match.total };
  }
  const fillText = (t, vars) => String(t).replace(/\{(\w+)\}/g, (m, k) => (vars[k] == null ? m : vars[k]));
  const nProblems = (n) => `${n} ${n === 1 ? 'problem' : 'problems'}`;
  // Step 1: choosing a dataset loads it right away (so Steps 1 and 2 show its own numbers) and puts the flow back to that dataset's own.
  async function choosePick(id) {
    if (!dsDef(id) || state.dsBusy) return;
    if (id === state.dsId) { if (state.bq) { state.bq = false; rerender('pick-' + id); } return; }     // back from the BigQuery table to the file-based sample
    await switchDataset(id, 'pick-' + id);
  }
  // The wallet sample can also be read from a BigQuery table (the pipeline does that, not the page): same results, shown with the table's details.
  async function chooseBigQuery() {
    if (state.dsBusy || !state.bqMeta || state.bq) return;
    if (state.dsId !== 'wallet' && !(await switchDataset('wallet', 'pick-bq'))) return;
    state.bq = true; rerender('pick-bq'); announce('BigQuery table chosen. The wallet sample, read from BigQuery.');
  }
  function startFlowCheck(focusKey) {
    const S = state.set;
    if (S.flow || S.flowLoading || state.dsBusy) return;
    const gen = state.gen;
    S.flowLoading = true; S.flowResult = null; rerender(focusKey);
    window.setTimeout(() => {
      if (gen !== state.gen || S !== state.set) return;   // the dataset or the flow was changed while the check ran: drop it
      const res = runFlowCheck(), label = (dsDef(state.dsId) || {}).label || 'chosen';
      S.flowLoading = false; S.flowResult = res; S.flow = res.ok; rerender(focusKey);
      announce(res.ok ? 'Sample flow analyzed' : res.mismatch ? `This flow does not match this data. ${res.match.found} of ${res.match.total} events appear in the ${label} data.` : `Could not analyze this flow. ${nProblems(res.problems.length)} found.`);
    }, 700);
  }
  // Picking a flow starts again from the top of Step 2; picking the recommended one also runs the check straight away.
  function chooseFlow(id, run) {
    if (state.set.flowLoading || state.dsBusy || (id === flowId() && !run)) return;
    state.flowPick = id; state.set = perDataset().set;
    if (run) startFlowCheck('verify-steps-btn'); else { rerender('flow-' + id); announce(`${(flowDef(id) || {}).name || 'Flow'} chosen`); }
  }
  function flowProblemsPanel(res, ds) {
    const item = (p) => h('li', { 'data-code': p.code },
      p.journeyName || p.stepName ? h('span', { class: 'pf-where' }, [p.journeyName, p.stepName].filter(Boolean).join(' › ')) : null,
      h('b', {}, p.message), h('span', { class: 'pf-fix' }, h('i', {}, 'How to fix: '), p.fix));
    const items = res.problems.map(item), head = items.slice(0, 4), rest = items.slice(4), b = res.better;
    return h('div', { class: 'flow-fail', role: 'group', 'aria-label': 'Flow check result' },
      h('h3', {}, res.mismatch ? 'This flow does not match this data' : 'Could not analyze this flow'),
      res.mismatch ? h('p', { class: 'ff-sum' }, `${res.match.found} of ${res.match.total} events in this flow appear in the ${ds.label} data.`) : null,
      b ? h('div', { class: 'ff-better' }, h('span', {}, `The ${(flowDef(b.id) || {}).name || b.name} matches this data (${b.found} of ${b.total} events).`),
        h('button', { type: 'button', class: 'btn', 'aria-label': `Use the ${(flowDef(b.id) || {}).name || b.name}`, ...fk('use-better'), onclick: () => chooseFlow(b.id, true) }, 'Use it')) : null,
      h('p', {}, `Squint checked the flow in your browser and found ${nProblems(res.problems.length)}. Nothing was uploaded and no server was asked. ${res.mismatch ? 'Pick the flow that was made for this data, or choose another dataset in Step 1.' : 'Fix them in the flow definition, or pick another flow.'}`),
      h('ol', { class: 'ff-problems' }, head),
      rest.length ? h('details', { class: 'ff-more' }, h('summary', {}, `Show the other ${nProblems(rest.length)}`), h('ol', { class: 'ff-problems cont' }, rest)) : null);
  }
  function renderSettings() {
    const m = D().meta, sc = D().scope, S = state.set, cnt = m.counts || {};
    const ds = dsDef(state.dsBusy || state.dsId) || { id: state.dsId, label: 'Sample', tagline: '', kind: 'Synthetic sample' };
    const flow = flowDef(flowId()), fc = flow ? flowCount(flow) : { j: 0, s: 0 }, fm = flow ? SquintFlowCheck.match(flow, state.srcEvents[state.dsId] || []) : { total: 0 };
    const failed = !!(S.flowResult && !S.flowResult.ok), ownFlow = flowId() === state.dsId;
    if (state.mapJourney === undefined || state.mapJourney === null && !state.mapTouched) state.mapJourney = (sc.journeys[0] || {}).id || null;
    const allSteps = sc.journeys.flatMap((x) => x.steps);
    const matchedN = allSteps.filter((x) => x.status === 'matched').length, reviewN = allSteps.filter((x) => x.status === 'review').length;
    const faults = (D().guardian.faults || []).filter((f) => f.sev !== 'resolved');
    const mark = (n, done) => h('span', { class: 'sp-mark' + (done ? '' : ' todo'), 'aria-hidden': 'true' }, done ? '✓' : String(n));
    const pills = [['Choose dataset', true], ['Pick a flow', S.verified], ['Open dashboard', S.opened]].map(([l, done], n) => h('span', { class: 'step-pill' }, mark(n + 1, done), l, h('span', { class: 'sr' }, done ? ', done' : ', not done yet')));
    const tile = (l, v, tone) => h('div', { class: 'tile' }, h('span', { class: 't-l' }, l), h('span', { class: 't-v', style: 'font-size:15px' + (tone ? ';color:var(--' + tone + ')' : '') }, v));
    const bqOn = !!state.bq && ds.id === 'wallet' && !!state.bqMeta;
    const pickTile = (d) => { const on = d.id === ds.id && !(bqOn && d.id === 'wallet');
      return h('button', { type: 'button', class: 'engine pick' + (on ? ' on' : ''), 'aria-pressed': String(on), 'aria-disabled': state.dsBusy ? 'true' : null, 'data-ds': d.id, ...fk('pick-' + d.id), onclick: () => choosePick(d.id) },
        h('span', { class: 'e-n' }, d.label), h('span', { class: 'e-d' }, d.tagline), h('span', { class: 'e-k' }, d.kind)); };
    const flowTile = (id) => { const f = flowDef(id), on = id === flowId(), c = flowCount(f);
      return h('button', { type: 'button', class: 'engine pick' + (on ? ' on' : ''), 'aria-pressed': String(on), 'aria-disabled': S.flowLoading || state.dsBusy ? 'true' : null, 'data-flow': id, ...fk('flow-' + id), onclick: () => chooseFlow(id) },
        h('span', { class: 'e-n' }, f.name), h('span', { class: 'e-d' }, f.tagline), h('span', { class: 'e-k' }, `${c.j} journeys · ${c.s} steps`), h('span', { class: 'e-k' }, f.synthetic === false ? 'Sample' : 'Synthetic sample')); };
    const bqTile = state.bqMeta ? h('button', { type: 'button', class: 'engine pick' + (bqOn ? ' on' : ''), 'aria-pressed': String(bqOn), 'aria-disabled': state.dsBusy ? 'true' : null, 'data-src': 'bigquery', ...fk('pick-bq'), onclick: chooseBigQuery },
      h('span', { class: 'e-n' }, 'BigQuery table'), h('span', { class: 'e-d' }, 'The wallet sample, read from a BigQuery table. No login.'), h('span', { class: 'e-k' }, 'Synthetic sample')) : null;
    const bqm = state.bqMeta;
    const bqFacts = bqOn ? h('div', { class: 'facts-grid bq-facts', 'aria-label': 'BigQuery source' },
      tile('BigQuery table', bqm.dataset + '.' + bqm.table), tile('Raw events in the table', fmt(bqm.rows)),
      tile('Last read by the pipeline', dateFmt(String(bqm.read_at).slice(0, 10), { month: 'short', day: 'numeric', year: 'numeric' }) + ' · job ' + String(bqm.read_job_id || '').slice(0, 8)), tile('Access', 'Read-only, no login')) : null;
    const own = ENGINES.map(([id, name, kind]) => h('button', { type: 'button', class: 'engine', disabled: true, 'aria-pressed': 'false' }, h('span', { class: 'e-n' }, name), h('span', { class: 'e-k' }, kind), h('span', { class: 'e-tag' }, 'Ping us to unlock')));
    const connPill = state.dsBusy ? h('span', { class: 'pill', style: 'background:var(--chip);color:var(--ink-2);box-shadow:none' }, h('span', { class: 'flow-spinner', 'aria-hidden': 'true' }), 'Loading…')
      : h('span', { class: 'pill', style: 'background:var(--ok-bg);color:var(--ok);box-shadow:none' }, dot('ok'), 'Ready to use');
    const nameInput = h('input', { id: 'user-name', type: 'text', maxlength: '24', autocomplete: 'off', value: state.userName, ...fk('user-name'),
      oninput: (e) => {
        const v = e.target.value.trim().slice(0, 24); if (!v) return;
        state.userName = v; try { localStorage.setItem(NAME_KEY, v); } catch (err) { /* fine */ } renderChrome();
      } });
    const step0 = h('section', { class: 'card', 'aria-label': 'Step 0, your name' },
      h('div', { class: 'card-h' }, h('div', {}, h('span', { class: 'eyebrow', style: 'font-size:12px' }, 'Step 0'), h('h2', { style: 'font-size:22px' }, 'What should we call you?'),
        h('span', { class: 'sub', style: 'font-size:14px' }, 'We picked a name so you do not have to. Change it if you like. It is only used to greet you here and stays in this browser.'))),
      h('div', { class: 'name-row' }, h('label', { for: 'user-name', class: 'sr' }, 'Your name'), nameInput));
    const pickNote = state.dsBusy ? `Loading the ${ds.label}…` : state.dsMsg ? state.dsMsg : bqOn ? 'The pipeline reads this synthetic table with its own read-only access. You do not log in, and nothing is queried from this page.' : 'Synthetic sample data is bundled with the demo; no connection details are needed.';
    const step1 = h('section', { class: 'card', 'aria-label': 'Step 1, choose a data source' },
      h('div', { class: 'card-h' }, h('div', {}, h('span', { class: 'eyebrow', style: 'font-size:12px' }, 'Step 1'), h('h2', { style: 'font-size:22px' }, 'Choose a data source'),
        h('span', { class: 'sub', style: 'font-size:14px' }, 'Pick a synthetic sample: the wallet app (from a file or from BigQuery) or the dining app. Uploading your own JSON or connecting your own database is not available in this demo.')), connPill),
      h('span', { class: 'flabel', id: 'l-samples' }, 'Sample datasets'),
      h('div', { class: 'engines picks', role: 'group', 'aria-labelledby': 'l-samples' }, [...state.registry.map(pickTile), bqTile]),
      h('span', { class: 'flabel', id: 'l-own' }, 'Your own data'),
      h('div', { class: 'engines engines-sm', role: 'group', 'aria-labelledby': 'l-own' }, own),
      h('div', { class: 'cta-row' }, h('button', { type: 'button', class: 'btn', disabled: true, 'aria-disabled': 'true' }, state.dsBusy ? 'Loading dataset…' : 'Dataset selected'),
        h('span', { class: 'sub', role: state.dsMsg ? 'alert' : 'status', 'aria-live': 'polite' }, pickNote)),
      h('div', { class: 'facts-grid', 'aria-label': 'Sample dataset contents' },
        tile('Dataset', 'demo · ' + (m.dataset || 'sample')), tile('Events', fmt(cnt.events || 0)), tile('Sessions and users', `${fmt(cnt.sessions || 0)} sessions · ${fmt(cnt.users || 0)} users`),
        tile('Telemetry Guardian', faults.length ? `${faults.length} active ${faults.length > 1 ? 'faults' : 'fault'}, ${fmt(cnt.sessions_quarantined || 0)} sessions held out` : 'Schema OK', faults.length ? 'warn' : 'ok')),
      bqFacts);
    const flowBtnLabel = S.flowLoading ? 'Analyzing sample flow…' : S.flow ? 'Sample flow in use' : failed ? 'Check again' : 'Use sample flow';
    const flowBody = S.flow ? [
      h('p', { class: 'flow-pass', role: 'status' }, dot('ok'), `Flow check passed: ${S.flowResult.journeys} journeys and ${S.flowResult.steps} steps, no problems found. All ${S.flowResult.match.total} events in this flow appear in the ${ds.label} data. Checked in your browser: nothing was uploaded and no server was asked.`),
      h('div', { class: 'd-sec' }, h('span', { class: 'd-lab' }, 'Detected journeys')),
      h('div', { class: 'jcards' }, sc.journeys.map((jd) => {
        const on = jd.id === state.mapJourney;
        const review = jd.steps.filter((x) => x.status === 'review').length;
        return h('div', { class: 'jcard' + (on ? ' on' : ''), 'data-j': jd.id },
          h('div', { class: 'top' }, h('div', {}, h('b', {}, jd.name), h('span', { class: 'sub' }, `${jd.steps.length} steps · ${jd.steps.filter((x) => x.status === 'matched').length} matched · ${review} to review`)),
            h('button', { type: 'button', class: 'btn-line', 'aria-expanded': String(on), 'aria-controls': on ? 'map-' + jd.id : null, ...fk('map-' + jd.id), onclick: () => { state.mapTouched = true; state.mapJourney = on ? null : jd.id; rerender('map-' + jd.id); if (!on) { const t = document.getElementById('map-' + jd.id); if (t) t.scrollIntoView({ block: 'nearest' }); } } }, on ? 'Hide event mapping' : 'Show event mapping')),
          h('div', { class: 'steps' }, jd.steps.map((x, i) => [h('span', { class: 's' }, x.name), i < jd.steps.length - 1 ? icon('M9 6l6 6-6 6', 12) : null])),
          on ? h('div', { class: 'map-open', id: 'map-' + jd.id }, h('div', { class: 'card-h' }, h('div', {}, h('b', {}, 'Event mapping · ' + jd.name), h('span', { class: 'sub' }, 'Source event matched to each journey step. ' + `${jd.steps.filter((x) => x.status === 'matched').length} of ${jd.steps.length} matched automatically`))), mappingTable(jd)) : null);
      }))]
      : failed ? flowProblemsPanel(S.flowResult, ds)
      : h('p', { class: 'sub', style: 'font-size:14px' }, S.flowLoading ? 'Looking for journeys…' : 'The journeys found in the sample flow appear here once it has been analyzed.');
    const step2 = h('section', { class: 'card', 'aria-label': 'Step 2, pick a flow' },
      h('div', { class: 'card-h' }, h('div', {}, h('span', { class: 'eyebrow', style: 'font-size:12px' }, 'Step 2'), h('h2', { style: 'font-size:22px' }, 'Pick a flow'),
        h('span', { class: 'sub', style: 'font-size:14px' }, 'A flow is the list of screens each journey goes through. Squint checks the flow you pick against the data from Step 1, in your browser, before the Semantic Agent matches each journey step to a source event.'))),
      h('span', { class: 'flabel', id: 'l-flows' }, 'Sample flows'),
      h('div', { class: 'engines picks', role: 'group', 'aria-labelledby': 'l-flows' }, state.flowIds.filter(flowDef).map(flowTile)),
      h('div', { class: 'cta-row' }, h('button', { type: 'button', class: 'btn', ...fk('flow-btn'), 'aria-disabled': String(S.flow || S.flowLoading || !!state.dsBusy), 'aria-busy': String(S.flowLoading), onclick: () => startFlowCheck('flow-btn') }, flowBtnLabel)),
      h('div', { class: 'flowfile' + (failed ? ' bad' : '') }, h('div', { class: 'ff-ico', 'aria-hidden': 'true' }, h('span', {}, 'SAMPLE')),
        h('div', { class: 'ff-txt' }, h('b', {}, 'Sample flow (synthetic)'),
          h('span', { class: 'sub', id: 'flow-numbers' }, ownFlow ? `${sc.journeys.length} journeys · ${allSteps.length} steps · ${matchedN} matched automatically · ${reviewN} to review` : `${fc.j} journeys · ${fc.s} steps · ${fm.total} event names`)),
        S.flow ? h('span', { class: 'ff-ok', role: 'status', 'aria-live': 'polite' }, dot('ok'), 'Analyzed') : S.flowLoading ? h('span', { class: 'ff-pending', role: 'status', 'aria-live': 'polite' }, h('span', { class: 'flow-spinner', 'aria-hidden': 'true' }), 'Analyzing…')
          : failed ? h('span', { class: 'ff-fail', role: 'status', 'aria-live': 'polite' }, dot('crit'), S.flowResult.mismatch ? 'Does not match this data' : 'Could not analyze') : h('span', { class: 'ff-pending' }, dot('muted'), 'Ready to analyze')),
      flowBody,
      h('div', { class: 'cta-row' }, h('button', { type: 'button', class: 'btn-line', ...fk('verify-steps-btn'), disabled: !S.flow, 'aria-pressed': String(S.verified), onclick: () => { if (S.verified) return; S.verified = true; rerender('verify-steps-btn'); announce('Journey steps verified. Step 3 unlocked.'); } }, S.verified ? 'Journey steps verified' : 'Verify journey steps'),
        h('span', { class: 'sub', role: 'status', 'aria-live': 'polite' }, S.verified ? 'Step 3 is unlocked.' : failed ? 'Fix the problems above, or pick another flow, to continue.' : 'Review the matched events above, then verify to continue.')));
    const step3 = h('section', { class: 'card' + (S.verified ? '' : ' step-locked'), 'aria-label': `Step 3, apply${S.verified ? '' : ', locked until journey steps are verified'}`, 'aria-disabled': String(!S.verified) },
      h('div', { class: 'apply' }, h('div', { class: 'ap-txt' }, h('span', { class: 'eyebrow', style: 'font-size:12px' }, 'Step 3'), h('b', {}, 'Dashboard tailored to the sample data'),
        h('span', { class: 'sub', style: 'font-size:14px' }, S.verified ? `The dashboard is already running on the ${ds.label} sample dataset, with ${sc.journeys.length} journeys in scope. Nothing needs to be applied.` : 'Verify the journey steps in Step 2 to unlock this step.')),
        h('button', { type: 'button', class: 'btn', ...fk('open-btn'), disabled: !S.verified, onclick: () => { S.opened = true; location.hash = '#overview'; } }, 'Open dashboard')));
    const aboutText = fillText((UI().about || 'This is a made-up (synthetic) sample: {users} users in {groups} groups, {nprod} kinds of products ({products}), from {start} to {end}. No real customer data is included.'), {
      users: fmt(visiblePersonas().reduce((a, p) => a + (p.users || 0), 0)), groups: visiblePersonas().length, nprod: (sc.products || []).length, products: (sc.products || []).map((p) => p.label).join(', '),
      start: dateFmt(m.window.start, { month: 'short', day: 'numeric' }), end: dateFmt(m.window.end, { month: 'short', day: 'numeric', year: 'numeric' }) });
    return [h('div', { style: 'display:flex;flex-direction:column;gap:14px' },
      h('h1', { class: 'title', id: 'page-title' }, 'Onboarding'),
      h('p', { class: 'lead' }, 'Four quick steps: say hi, pick your data, pick a flow that fits it, open your dashboard.'),
      h('div', { class: 'gate', role: 'note' }, h('span', {}, h('b', {}, 'Read-only demo. '), 'Uploading a flow and connecting your own database are turned off here. The dashboard runs on the bundled sample.'))),
    h('div', { class: 'step-pills', role: 'group', 'aria-label': 'Setup progress' }, pills, h('span', { class: 'sub' }, 'Progress is kept in memory only')),
    step0, step1, step2, step3,
    howWorksCard(),
    foldCardKeyed({ key: 'data', open: false, icon: 'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6' }, 'Sample dataset contents', 'What’s in the sample dataset', null,
      h('p', {}, aboutText))];
  }

  /* ---------- drawer ---------- */
  /* The evidence as small charts instead of a wall of sentences: what changed against usual, who is affected, what people hit. */
  const SIG_LABEL = { drop_off: 'People who leave here', rage: 'Repeated taps', error: 'Errors', dead: 'Taps that did nothing', back: 'Went back a step', dwell: 'Long wait on this screen' };
  const pc = (x) => (x * 100 >= 10 || x === 0 ? Math.round(x * 100) : (x * 100).toFixed(1).replace(/\.0$/, '')) + '%';
  const evBar = (frac, cls, tick) => h('span', { class: 'ev-bar' }, h('i', { class: cls, style: `width:${Math.max(1.5, Math.min(100, frac * 100)).toFixed(1)}%` }), tick != null ? h('u', { style: `left:${Math.min(99, tick * 100).toFixed(1)}%` }) : null);
  function evidenceCharts(i) {
    const sigs = (i.signals || []).filter((x) => x && x.value != null), bd = (i.breakdown || []).filter((x) => x && x.rate != null && !(x.dim === 'persona' && (HIDDEN_PERSONAS.includes(x.value) || x.value === 'unknown')));
    const g =((i.evidence_stats || {}).group) || {}, secs = [];
    if (sigs.length) {
      const top = Math.max(0.0001, ...sigs.flatMap((x) => [x.value, x.reference || 0]));
      secs.push(h('div', { class: 'ev-sec' }, h('h4', {}, 'Compared with usual'), h('div', { class: 'ev-key' }, h('span', {}, h('i', { class: 'now' }), 'Now'), h('span', {}, h('i', { class: 'usual' }), 'Usual')),
        sigs.map((x) => h('div', { class: 'ev-row' }, h('span', { class: 'ev-l' }, SIG_LABEL[x.metric] || x.metric),
          h('span', { class: 'ev-bars' }, evBar(x.value / top, 'now'), evBar((x.reference || 0) / top, 'usual')),
          h('span', { class: 'ev-v' }, h('b', {}, pc(x.value)), ' vs ' + pc(x.reference || 0), x.ratio >= 2 ? h('em', {}, `${x.ratio >= 10 ? Math.round(x.ratio) : x.ratio.toFixed(1)}×`) : null)))));
    }
    if (bd.length) {
      const dims = []; bd.forEach((x) => { let d = dims.find((y) => y.label === x.dim_label); if (!d) { d = { label: x.dim_label, rows: [] }; dims.push(d); } d.rows.push(x); });
      const top = Math.max(0.0001, ...bd.map((x) => x.rate));
      secs.push(h('div', { class: 'ev-sec' }, h('h4', {}, 'Who is affected'), h('p', { class: 'ev-note' }, 'Bar: share who left now. Tick: the usual share.'),
        dims.map((d) => h('div', { class: 'ev-grp' }, h('span', { class: 'ev-gl' }, plain(d.label)), d.rows.slice(0, 6).map((x) => h('div', { class: 'ev-row' + (x.in_segment ? ' in-seg' : '') }, h('span', { class: 'ev-l' }, x.label),
          h('span', { class: 'ev-bars' }, evBar(x.rate / top, 'now', x.rate_before != null ? x.rate_before / top : null)), h('span', { class: 'ev-v' }, h('b', {}, pc(x.rate)), h('small', {}, ` ${fmt(x.n)} sessions`))))))));
    }
    const codes = (g.top_error_codes || []).filter((x) => x.events > 0), taps = (g.top_rage_tap_elements || []).filter((x) => x.taps > 0);
    if (codes.length || taps.length) {
      const list = (title, arr, key, unit) => { const mx = Math.max(1, ...arr.map((x) => x[unit])); return h('div', { class: 'ev-grp' }, h('span', { class: 'ev-gl' }, title), arr.slice(0, 4).map((x) => h('div', { class: 'ev-row' }, h('span', { class: 'ev-l ev-mono' }, x[key]), h('span', { class: 'ev-bars' }, evBar(x[unit] / mx, 'now')), h('span', { class: 'ev-v' }, h('b', {}, fmt(x[unit]))))));
      };
      secs.push(h('div', { class: 'ev-sec' }, h('h4', {}, 'What people ran into'), codes.length ? list('Errors shown', codes, 'code', 'events') : null, taps.length ? list('Most repeated taps', taps, 'element', 'taps') : null));
    }
    return secs.length ? h('div', { class: 'd-sec ev-card' }, h('span', { class: 'd-lab' }, 'The evidence at a glance'), ...secs) : null;
  }
  /* "Fact-check with AI": one Gemini call per click (see docs/factcheck-endpoint.md). The saved explanation never changes; the check
     says, line by line, whether the numbers support it. The server falls back to a plain code check, so the button always answers. */
  const FC_VERDICT = { supported: ['Supported', 'ok'], partly: ['Partly', 'warn'], not_supported: ['Not supported', 'bad'], cannot_check: ['Cannot check', 'na'] };
  const FC_SUMMARY = { supported: 'Every line holds up against the numbers.', mixed: 'Some lines hold up, others do not.', not_supported: 'The numbers do not support this explanation.', cannot_check: 'Nothing here could be checked against numbers.' };
  let fcTimer = null;
  function fcRefresh() {
    if (!state.drawer) return;    // the drawer was closed while the answer was on its way: nothing to redraw
    const box = $('drawer'), y = box ? box.scrollTop : 0;
    renderDrawer(false);
    if (box) box.scrollTop = y;
    const b = $('fc-btn'); if (b && document.activeElement === document.body) b.focus();
  }
  async function runFactCheck(i, again) {
    const st = (state.fc[i.id] = state.fc[i.id] || { phase: 'idle' });
    if (st.phase === 'loading' || Date.now() < (st.until || 0)) return;
    const gen = state.gen;   // an answer that arrives after the sample was switched belongs to the other dataset and is dropped
    st.phase = 'loading'; st.error = null; fcRefresh(); announce('Asking Gemini to fact-check this finding');
    try {
      const res = await fetch('/api/factcheck', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: i.id, again: !!again, dataset: state.dsId }) });
      const data = await res.json().catch(() => null);
      if (gen !== state.gen) return;
      if (!res.ok || !data || !Array.isArray(data.claims)) throw new Error('bad_response');
      st.data = data; st.phase = 'done'; st.until = Date.now() + (data.retry_in_s != null ? data.retry_in_s : 30) * 1000;
      announce(data.source === 'gemini' ? 'Fact-check done' : 'Code check done');
    } catch (e) {
      if (gen !== state.gen) return;
      st.phase = st.data ? 'done' : 'idle'; st.error = 'The checker could not be reached. Nothing was changed. Try again in a moment.';
    }
    fcRefresh(); fcTick();
  }
  function fcTick() {
    clearInterval(fcTimer);
    fcTimer = setInterval(() => {
      const spec = state.drawer, b = $('fc-btn');
      if (!spec || spec.type !== 'insight' || !b) { clearInterval(fcTimer); return; }
      const st = state.fc[spec.id]; if (!st) { clearInterval(fcTimer); return; }
      const wait = Math.ceil(((st.until || 0) - Date.now()) / 1000);
      if (wait > 0 && st.phase === 'done') b.lastChild.textContent = `Check again in ${wait}s`;
      else { b.disabled = false; if (st.phase === 'done') b.lastChild.textContent = 'Check again'; clearInterval(fcTimer); }
    }, 500);
  }
  function factCheckBox(i) {
    const claims = ((i.diagnosis || {}).claims || []), ds = diagState(i);
    if (!claims.length || !(ds === 'ai' || ds === 'cached')) return null;
    const st = (state.fc[i.id] = state.fc[i.id] || { phase: 'idle' }), d = st.data;
    const wait = Math.max(0, Math.ceil(((st.until || 0) - Date.now()) / 1000));
    const label = st.phase === 'loading' ? 'Asking Gemini…' : st.phase === 'done' ? (wait > 0 ? `Check again in ${wait}s` : 'Check again') : 'Fact-check with AI';
    const btn = h('button', { type: 'button', class: 'btn fc-btn', id: 'fc-btn', 'aria-busy': String(st.phase === 'loading'), disabled: st.phase === 'loading' || wait > 0, onclick: () => runFactCheck(i, st.phase === 'done') },
      st.phase === 'loading' ? h('span', { class: 'flow-spinner', 'aria-hidden': 'true' }) : icon(SPARKLE, 15, 2), h('span', {}, label));
    const rows = d ? d.claims.map((r) => { const [vl, vk] = FC_VERDICT[r.verdict] || FC_VERDICT.cannot_check;
      return h('li', { class: 'fc-row' }, h('span', { class: 'fc-chip fc-' + vk }, vl), h('div', {}, h('span', { class: 'fc-t' }, rt(r.text)),
        r.note || r.number ? h('span', { class: 'fc-n' }, r.number ? h('code', { class: 'q' }, r.number) : null, r.note ? ' ' + r.note : '') : null)); }) : null;
    const counts = d ? d.claims.filter((r) => r.verdict === 'supported').length : 0;
    const foot = d ? (d.source === 'gemini' ? `Checked by Gemini at ${d.generated_at}${d.cached ? ' (saved result)' : ''}. ${d.notice}` : `${d.reason} ${d.notice}`) : null;
    return h('div', { class: 'd-sec fc-card' }, h('span', { class: 'd-lab' }, 'Check this explanation'),
      h('div', { class: 'fc-head' }, h('div', {}, h('b', {}, d ? FC_SUMMARY[d.overall] || 'Checked.' : 'Is this explanation backed by the numbers?'),
          h('p', { class: 'sub' }, d ? `${counts} of ${d.claims.length} lines supported. ${d.source === 'gemini' ? 'Written by the AI earlier; judged now by Gemini.' : 'Plain code check, no AI.'}` : 'Gemini reads each line of the saved explanation and checks it against the numbers on this page. The saved text does not change.')), btn),
      rows ? h('ul', { class: 'fc-rows' }, rows) : null,
      d && d.missed && d.missed.length ? h('div', { class: 'fc-missed' }, h('b', {}, 'Also worth a look: '), d.missed.join(' ')) : null,
      foot ? h('p', { class: 'fc-foot' }, foot) : h('p', { class: 'fc-foot' }, 'AI can make mistakes. It only sees the numbers on this page, never your database. One click, one check.'),
      st.error ? h('p', { class: 'fc-err', role: 'alert' }, st.error) : null);
  }
  function drawerContent(spec) {
    if (spec.type === 'ask-ticket') {
      const t = spec.ticket || {};
      const key = t.title || 'ask-ticket', cur = (state.askAssign || {})[key] || null, guess = ownerOf(`${t.hypothesis || ''} ${JSON.stringify(t.evidence_json || {})}`);
      const sel = h('select', { id: 'ask-assignee', 'aria-label': 'Assign the ticket to' }, [`Me (${state.userName})`, 'Engineering', 'Product', 'Design', 'Support', 'Data'].map((o) => h('option', { value: o, selected: o === (cur || guess) }, o)));
      const assignBox = h('div', { class: 'd-sec' }, h('span', { class: 'd-lab' }, 'Assign to'),
        h('div', { class: 'assign-row' }, sel, h('button', { type: 'button', class: 'btn', onclick: () => { state.askAssign = state.askAssign || {}; state.askAssign[key] = sel.value; renderDrawer(false); const again = $('ask-assignee'); if (again) again.focus(); announce('Ticket assigned to ' + sel.value); } }, cur ? 'Reassign' : 'Assign')),
        cur ? h('p', { class: 'assign-ok' }, `✓ Assigned to ${cur}. They get the hypothesis and the evidence below.`) : h('p', { class: 'sub' }, `Suggested: ${guess}, going by what the evidence points to.`));
      return { title: t.title || 'Ask evidence ticket', sev: ['pos', 'Draft ticket'], seg: `${t.persona || 'All users'} · prepared from the loaded dataset`,
        body: [h('div', { class: 'd-box' }, h('span', { class: 'd-lab' }, 'Hypothesis (to verify)'), h('p', {}, t.hypothesis || 'No hypothesis supplied.')), assignBox,
          (() => {
            const ev = t.evidence_json || {}, bc = ev.branch_counts || {}, mx = Math.max(1, ...Object.values(bc).map(Number));
            const nice = (k) => { const s2 = k.replace(/_/g, ' '); return s2.charAt(0).toUpperCase() + s2.slice(1); };
            return h('div', { class: 'd-sec' }, h('span', { class: 'd-lab' }, 'Measured evidence'),
              ev.cohort_sessions != null ? h('p', { class: 'sub' }, `${fmt(ev.cohort_sessions)} sessions in this group${ev.active_sessions_7d ? `, out of ${fmt(ev.active_sessions_7d)} active in the last 7 days` : ''}.`) : null,
              Object.keys(bc).length ? h('div', { class: 'ev-sec' }, Object.entries(bc).map(([k, n]) => h('div', { class: 'ev-row' }, h('span', { class: 'ev-l' }, nice(k)), h('span', { class: 'ev-bars' }, evBar(Number(n) / mx, 'now')), h('span', { class: 'ev-v' }, h('b', {}, fmt(n)))))) : null,
              h('details', { class: 'more-note' }, h('summary', {}, 'Show the raw data'), h('pre', { class: 'json', tabindex: '0', 'aria-label': 'Ticket evidence JSON' }, JSON.stringify(ev, null, 2))));
          })()], acts: [] };
    }
    if (spec.type === 'insight') {
      const i = insightById(spec.id);
      const t = TONE[i.tone] || 'warn';
      const dg = i.diagnosis || {};
      const ds = diagState(i);
      const hint = !i.class && !dg.class && i.hint_class ? (Object.hasOwn(HINT, i.hint_class) ? HINT[i.hint_class] : String(i.hint_class).replace(/_/g, ' ')) : null;
      const klass = dg.class || i.class;
      const cls = klass ? classLabel(klass) : hint ? 'Rule-based hint: ' + hint : 'Not classified';
      const confRaw = (ds === 'ai' || ds === 'cached') ? (dg.confidence != null ? dg.confidence : i.confidence) : null;
      const conf = typeof confRaw === 'number' && isFinite(confRaw) ? confRaw : null;
      const causes = (i.causes || []).filter((c) => c && c.title).map((c) => ({ ...c, share: Number(c.share) || 0 })).sort((a, b) => b.share - a.share);
      const boxLabel = ds === 'rules' ? 'Rule-based result' : ds === 'failed' ? 'Needs review' : ds === 'pending' ? 'Diagnosis' : 'AI hypothesis';
      const rules = dg.rules || null;
      const claims = (Array.isArray(dg.claims) ? dg.claims : []).filter((c) => c && c.text);
      const reasoning = (Array.isArray(dg.reasoning) ? dg.reasoning : []).filter(Boolean);
      const steps = (Array.isArray(dg.next_steps) ? dg.next_steps : []).filter((x) => x && (typeof x === 'string' || x.text));
      const caveats = (Array.isArray(dg.caveats) ? dg.caveats : []).filter(Boolean);
      const diagBox = h('div', { class: 'd-box', id: 'd-diag' }, h('span', { class: 'd-lab' }, boxLabel),
        ds === 'pending' ? h('p', {}, 'Not diagnosed yet. No cause is claimed here.')
          : ds === 'failed' ? h('p', {}, 'Needs review, nothing was generated. No cause is claimed here.')
          : ds === 'rules' ? h('p', {}, pctText(dg.summary || ('A fixed rule produced the class ' + classLabel(dg.class || i.class || 'unclassified_needs_review') + '.')))
          : h('p', {}, rt(pctText(dg.summary || i.hypothesis || 'No summary was saved.'))),
        ds === 'rules' ? h('span', { class: 'rules-note' }, 'Not an AI diagnosis. ' + pctText(dg.source_note || 'A fixed rule produced this class.')) : null,
        ds === 'cached' ? h('span', { class: 'cached-note' }, pctText(dg.source_note || 'Saved result, not a live call')) : null,
        ds === 'failed' && dg.source_note ? h('span', { class: 'cached-note' }, pctText(dg.source_note)) : null);
      const flagNote = rules && rules.flagged ? h('div', { class: 'd-flag', role: 'note' }, h('b', {}, 'The rule table and the model disagree. '),
        rules.rule_text ? h('span', {}, 'Rule: ' + pctText(rules.rule_text) + (rules.class ? ' (' + classLabel(rules.class) + '). ' : '. ')) : null,
        rules.overrule_reason ? h('span', {}, 'Why the model differs: ' + pctText(rules.overrule_reason)) : null) : null;
      const claimsBox = claims.length ? h('details', { class: 'd-sec reasoning' }, h('summary', {}, 'The AI’s explanation, line by line'),
        h('ul', { class: 'claims' }, claims.map((c) => h('li', {}, h('span', {}, rt(pctText(c.text))),
          Array.isArray(c.refs) && c.refs.filter(Boolean).length ? h('span', { class: 'refs-plain' }, 'Evidence: ' + c.refs.filter(Boolean).map((r) => pctText(r.label || r.id || r.type)).join(' · ')) : null)))) : null;
      const reasonBox = reasoning.length ? h('details', { class: 'd-sec reasoning' }, h('summary', {}, 'How it was worked out'), h('ol', {}, reasoning.map((x) => h('li', {}, rt(pctText(x)))))) : null;
      const ticketBox = spec.ticket ? h('div', { class: 'd-sec ticket' }, h('span', { class: 'd-lab', id: 'd-ticket-h', tabindex: '-1' }, `Draft ticket · ${spec.ticket.owner}`),
        h('p', { class: 'sub' }, 'Local draft only. Review it, then copy it into your issue tracker.'),
        h('pre', { class: 'json ticket-pre', tabindex: '0', 'aria-label': 'Draft ticket text' }, spec.ticket.text),
        h('button', { type: 'button', class: 'btn-line', onclick: (e) => {
          const btn = e.currentTarget;   // read it now: currentTarget is null by the time the promise answers
          if (!navigator.clipboard || !navigator.clipboard.writeText) { announce('Select the draft text and copy it with Ctrl+C'); return; }
          navigator.clipboard.writeText(spec.ticket.text).then(() => { btn.textContent = 'Copied'; announce('Ticket draft copied'); }, () => announce('Could not copy the ticket draft'));
        } }, 'Copy draft')) : null;
      const stepsBox = steps.length ? h('div', { class: 'd-sec' }, h('span', { class: 'd-lab' }, 'Next steps'), h('ul', { class: 'claims' }, steps.map((x) => h('li', {}, rt(pctText(typeof x === 'string' ? x : x.text)))))) : null;
      const caveatBox = caveats.length ? h('div', { class: 'd-sec' }, h('span', { class: 'd-lab' }, 'Caveats'), h('ul', { class: 'claims' }, caveats.map((x) => h('li', {}, rt(pctText(x)))))) : null;
      return {
        title: i.title, sev: [t, SEVLABEL[i.severity] || i.label], seg: i.segment_text,
        body: [
          diagBox, flagNote,
          h('div', { class: 'd-3' }, h('div', {}, h('span', {}, 'Type'), h('span', {}, cls)), h('div', {}, h('span', {}, 'Confidence'), h('span', {}, conf == null ? '—' : conf.toFixed(2))),
            h('div', {}, h('span', {}, 'Impact'), h('span', {}, i.impact && i.impact.per_week_value > 0 ? '~' + money(i.impact.per_week_value) + '/wk' : '—'))),
          hint ? h('p', { class: 'sub' }, 'The class is a rule-based hint from the Watchdog, not an AI verdict.') : null,
          evidenceCharts(i), factCheckBox(i), claimsBox,
          causes.length ? h('div', { class: 'd-sec' }, h('span', { class: 'd-lab' }, 'Probable causes'), causes.map((c) => h('div', { class: 'cause' + (c.resolved || c.share < 0.005 ? ' ruled' : '') },
            h('span', { class: 'pct t-' + CAUSE_CLS(c) + (c.resolved || c.share < 0.005 ? ' pct-ruled' : '') }, c.resolved || c.share < 0.005 ? 'Not the cause' : Math.round(c.share * 100) + '%'),
            h('div', { class: 'body' }, h('span', { class: 'head' }, h('span', { class: 'typechip ' + c.type }, CAUSE_LABEL[c.type] || c.type), h('b', {}, c.title)), h('span', { class: 'why' }, rt(c.why)))))) : null,
          stepsBox || h('div', { class: 'd-sec' }, h('span', { class: 'd-lab' }, 'Recommendation'), h('p', {}, pctText(i.recommendation) || 'None yet. Not diagnosed.')),
          caveatBox,
          i.impact && i.impact.assumption ? h('div', { class: 'd-sec' }, h('span', { class: 'd-lab' }, 'About the money figure'), h('p', { class: 'sub' }, i.impact.assumption)) : null,
          reasonBox, ticketBox],
        acts: [],
      };
    }
    // a journey step with no finding attached: built only from the counts in the view
    const v = view();
    const j = v && v.journeys.find((x) => x.id === spec.journey);
    const st = j && j.steps.find((x) => x.id === spec.step);
    const linked = D().insights.find((i) => i.journey === spec.journey && i.step === spec.step && v.insight_ids.includes(i.id));
    if (linked) return drawerContent({ type: 'insight', id: linked.id, ticket: spec.ticket });
    const def = stepDef(spec.journey, spec.step) || {};
    const rate = st ? 100 * st.exits / Math.max(1, st.sessions) : 0;
    const t = TONE[st ? st.tone : 'healthy'] || 'ok';
    return {
      title: stepName(spec.journey, spec.step), sev: [t, st ? TONENAME[st.tone] : 'Seamless'], seg: `${jName(spec.journey)} · ${st ? fmt(st.sessions) : 0} sessions`,
      body: [h('div', { class: 'd-box' }, h('span', { class: 'd-lab' }, 'What the data shows'),
        h('p', {}, st ? (st.low_sample ? `Few sessions (${fmt(st.sessions)}): too few to judge, so no rate is read from this step.` : `${fmt(st.exits)} of ${fmt(st.sessions)} sessions (${rate.toFixed(1)}%) end here, which looks like ${(EXIT[st.exit_class] || EXIT.natural)[0].toLowerCase()}. No finding is attached to this step.`) : 'No sessions in this view.')),
      h('div', { class: 'd-3' }, h('div', {}, h('span', {}, 'Type'), h('span', {}, st ? (st.tone === 'positive' ? 'Positive friction' : 'Seamless') : '—')), h('div', {}, h('span', {}, 'Confidence'), h('span', {}, def.conf == null ? '—' : def.conf.toFixed(2))), h('div', {}, h('span', {}, 'Impact'), h('span', {}, '—'))),
      h('div', { class: 'd-sec' }, h('span', { class: 'd-lab' }, 'Recommendation'), h('p', {}, st && st.tone === 'positive' ? 'Do not add pop-ups or forced friction here; this is healthy comparison behavior.' : 'No action needed. Keep monitoring against baseline.')),
      h('div', { class: 'd-sec' }, h('span', { class: 'd-lab' }, 'Step summary'), h('pre', { class: 'json', tabindex: '0', 'aria-label': 'Step summary' }, JSON.stringify({ step: spec.step, mapped_event: def.event || null, sessions: st ? st.sessions : 0, exits: st ? st.exits : 0 }, null, 2)))],
      acts: [],
    };
  }
  function renderDrawer(focusTicket) {
    const spec = state.drawer, box = $('drawer');
    const c = drawerContent(spec);
    box.replaceChildren(
      h('div', { class: 'd-head' }, h('div', {}, h('span', { class: 'i-lab t-' + c.sev[0], style: 'display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em' }, dot(c.sev[0]), c.sev[1]),
        h('h2', { id: 'drawer-title' }, c.title), h('span', { class: 'sub' }, c.seg)),
        h('button', { type: 'button', class: 'd-close', id: 'd-close', 'aria-label': 'Close diagnostic dialog', onclick: () => closeDrawer() }, icon('M6 6l12 12M18 6L6 18', 16))),
      ...c.body.flat().filter(Boolean), h('div', { class: 'd-acts' }, ...c.acts, h('button', { type: 'button', class: 'btn-line', onclick: () => closeDrawer() }, 'Dismiss')));
    if (focusTicket) { const th = $('d-ticket-h'); if (th) { th.scrollIntoView({ block: 'nearest' }); th.focus(); } }
  }
  function openDrawer(spec, opener) {
    state.opener = opener && opener.dataset && opener.dataset.fk ? opener.dataset.fk : null;
    if (!state.opener && opener) { opener.dataset.fk = 'op-' + Date.now(); state.opener = opener.dataset.fk; }
    if (spec.ticket && spec.type === 'insight') { state.drafted[spec.id] = true; state.dirty = true; }
    state.drawer = spec;
    renderDrawer(false);
    $('drawer').hidden = false; $('scrim').hidden = false;
    ['hdr', 'fbar'].forEach((id) => $(id).setAttribute('inert', ''));
    document.querySelector('.shell').setAttribute('inert', '');
    document.body.style.overflow = 'hidden';
    if (spec.ticket) { const th = $('d-ticket-h'); if (th) { th.scrollIntoView({ block: 'nearest' }); th.focus(); } } else $('d-close').focus();
  }
  function closeDrawer(silent) {
    if (!state.drawer) return;
    const dirty = state.dirty; state.dirty = false; state.drawer = null;
    $('drawer').hidden = true; $('scrim').hidden = true;
    ['hdr', 'fbar'].forEach((id) => $(id).removeAttribute('inert'));
    document.querySelector('.shell').removeAttribute('inert');
    document.body.style.overflow = '';
    const key = state.opener; state.opener = null;
    if (silent) return;
    if (dirty) { rerender(key); if (!key || !document.querySelector(`[data-fk="${key}"]`)) $('main').focus(); return; }
    const el = key && document.querySelector(`[data-fk="${key}"]`);
    (el || $('main')).focus();
  }
  function trapKeys(e) {
    if (!state.drawer) {
      if (e.key === 'Escape' && state.ask && state.ask.a && state.ask.a.viz && state.ask.a.viz.ticket && !state.ask.hideSnack) { state.ask = { ...state.ask, hideSnack: true }; rerender('ask-input'); }
      return;
    }
    if (e.key === 'Escape') { e.preventDefault(); closeDrawer(); return; }
    if (e.key !== 'Tab') return;
    const f = [...$('drawer').querySelectorAll('button, [href], input, select, pre[tabindex], [tabindex]:not([tabindex="-1"])')].filter((x) => x.offsetParent !== null);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  /* ---------- render ---------- */
  function renderView() {
    const out = $('view');
    syncDatasetSwitch();
    document.title = `${VIEWS.find((x) => x[0] === state.view)[1]} · ${NAME}`;
    let nodes;
    if (state.view === 'settings') {
      $('fbar').hidden = true;
      nodes = renderSettings();
    } else {
      $('fbar').hidden = state.view === 'ask';   // Ask answers from the saved 30-day results, so the timeframe and user-group filters would do nothing
      const v = view();
      if (!v) nodes = [pageHead(VIEWS.find((x) => x[0] === state.view)[1], false), noData()];
      else nodes = ({ ask: () => [pageHead('Ask', false), ...askBlock()], overview: renderOverview, brief: renderBrief, journeys: renderJourneys, friction: renderFriction, cohorts: renderCohorts })[state.view](v);
    }
    // a sample that could not be opened from the header: say so on whichever tab is showing (Onboarding says it in Step 1)
    if (state.dsMsg && state.view !== 'settings') nodes = [h('div', { class: 'err', role: 'alert' }, state.dsMsg, ' ', h('button', { type: 'button', class: 'btn-line', onclick: () => { state.dsMsg = ''; rerender(null); } }, 'Dismiss')), ...nodes.flat(2)];
    out.replaceChildren(...nodes.flat(2).filter(Boolean));
    // Charts grow in once per tab: the class stays until a chart animation has finished on that tab, so the renders during load
    // do not use it up, while later filter and range changes re-render without replaying it.
    out.classList.toggle('grow-in', !grownViews.has(state.view));
    applyFocus();
  }
  const grownViews = new Set();
  $('view').addEventListener('animationend', (e) => { if (/^(grow-|reveal-|donut-)/.test(e.animationName)) grownViews.add(state.view); });
  function showError(msg, ds, retry) {
    const alt = ds && ds.id !== state.defaultDs ? dsDef(state.defaultDs) : null;
    $('view').replaceChildren(h('div', { class: 'err', role: 'alert' }, h('strong', {}, 'Could not load the data. '), msg, ' ', h('button', { type: 'button', class: 'btn-line', onclick: () => (retry ? retry() : load(ds && ds.id)) }, 'Try again'),
      alt ? [' ', h('button', { type: 'button', class: 'btn-line', onclick: () => { history.replaceState(null, '', location.pathname + location.hash); load(alt.id); } }, `Open the ${alt.label} instead`)] : null));
  }
  /* The demo does not feature these personas (owner's call, 2026-10-14). The data keeps them; the page just never shows them:
     their findings, replays, intent examples, Ask answers and the cohort built for them are dropped here, once, at load. */
  const HIDDEN_PERSONAS = ['fraudster'];
  let HIDDEN_TEXT = /fraud|shared-device/i;   // set from the dataset's ui.hidden_text before each scrub
  function scrub(d) {
    HIDDEN_TEXT = new RegExp(UI().hidden_text || 'fraud|shared-device', 'i');
    const hidden = (ids) => Array.isArray(ids) && ids.length > 0 && ids.every((p) => HIDDEN_PERSONAS.includes(p));
    const gone = new Set((d.insights || []).filter((i) => hidden(i.persona_ids)).map((i) => i.id));
    d.insights = (d.insights || []).filter((i) => !gone.has(i.id));
    Object.values(d.views || {}).forEach((v) => {
      v.insight_ids = (v.insight_ids || []).filter((id) => !gone.has(id));
      if (v.blind && Array.isArray(v.blind.bars)) {
        // The blind-spot chart was built around a hidden persona: drop that bar, and keep the card only if another bar still stands out.
        const B = v.blind, bars = B.bars.filter((b) => !HIDDEN_TEXT.test(b.l1 + ' ' + b.l2));
        const peak = Math.max(0, ...bars.map((b) => b.value));
        if (bars.length < 2 || !(B.baseline > 0) || peak < 1.5 * B.baseline) v.blind = null;
        else { B.bars = bars.map((b) => ({ ...b, hot: b.value >= 1.5 * B.baseline })); B.badge = `${(peak / B.baseline).toFixed(1)}x the overall rate`; }
      }
      if (v.cohorts && Array.isArray(v.cohorts.items)) {
        v.cohorts.items = v.cohorts.items.filter((c) => !HIDDEN_TEXT.test(c.name || ''));
        if (typeof v.cohorts.note === 'string') v.cohorts.note = v.cohorts.note.split(/(?<=\.)\s+/).filter((s) => !HIDDEN_TEXT.test(s)).join(' ');
      }
    });
    d.stuck_sessions = (d.stuck_sessions || []).filter((s) => !HIDDEN_PERSONAS.includes(s.persona) && !gone.has(s.insight_id));
    d.intents = (d.intents || []).filter((x) => !HIDDEN_TEXT.test(JSON.stringify(x)));
    d.ask = (d.ask || []).filter((x) => !HIDDEN_TEXT.test(JSON.stringify(x)));
    return d;
  }
  /* ---------- datasets: the sample list, loading one, switching between them ---------- */
  async function fetchResults(ds) {
    const res = await fetch(ds.results, { cache: 'no-store' });
    if (!res.ok) throw new Error('The server answered ' + res.status + '.');
    const data = await res.json();
    if (!data.views || !data.scope || !data.meta) throw new Error(ds.results + ' is in an older format (no "views" and "scope"). See docs/ui-results-needs.md.');
    return data;
  }
  async function loadRegistry() {
    const res = await fetch('datasets.json', { cache: 'no-store' });
    if (!res.ok) throw new Error('The list of samples answered ' + res.status + '.');
    const reg = await res.json();
    if (!reg || !Array.isArray(reg.datasets) || !reg.datasets.length) throw new Error('The list of samples is empty.');
    state.registry = reg.datasets; state.defaultDs = reg.default || reg.datasets[0].id;
    // The flow files and the lists of events each dataset's source logs are static files, read once now: the check in Step 2 then runs without a request.
    const get = async (f) => { try { const r = await fetch(f, { cache: 'no-store' }); return r.ok ? await r.json() : null; } catch (e) { return null; } };
    state.flows = {}; state.flowIds = [];
    const flows = await Promise.all((reg.flows || []).map(get));
    flows.filter((f) => f && f.id && Array.isArray(f.journeys)).forEach((f) => { state.flows[f.id] = f; state.flowIds.push(f.id); });
    state.srcEvents = (reg.events ? await get(reg.events) : null) || {};
    const bq = await get('bigquery_source.json');       // summary of the BigQuery table the wallet sample can be read from (written by pipeline/bq_source.py); no tile without it
    state.bqMeta = bq && bq.table && bq.rows ? bq : null;
  }
  /* Make `ds` the loaded dataset. Everything that belongs to the previous one is dropped first (see perDataset), and any answer still
     on its way (Ask, fact-check, brief rewrite, flow check) is ignored because gen and askSeq have moved on. */
  function applyDataset(ds, data) {
    closeDrawer(true); clearInterval(fcTimer); mergeCache.clear();
    Object.assign(state, perDataset(), { gen: state.gen + 1, askSeq: state.askSeq + 1 });
    state.dsId = ds.id; state.ui = ds.ui || {}; state.dsMsg = '';
    state.extraPlain = (state.ui.plain || []).map(([src, flags, to]) => [new RegExp(src, flags), to]);
    state.data = scrub(data);
    if (!state.data.scope.ranges.includes(state.range)) state.range = state.data.scope.ranges[0];
    grownViews.clear();
  }
  async function load(id) {
    const ds = dsDef(id) || dsDef(state.defaultDs);
    let data;
    try { data = await fetchResults(ds); } catch (e) { showError(String(e.message || e), ds); return; }
    applyDataset(ds, data);
    init();
  }
  async function switchDataset(id, focusKey) {
    const ds = dsDef(id);
    if (!ds || state.dsBusy) return false;
    if (id === state.dsId) return true;
    state.dsBusy = id; state.dsMsg = ''; syncDatasetSwitch();
    if (state.view === 'settings') rerender(focusKey);
    let data;
    try { data = await fetchResults(ds); } catch (e) {
      state.dsBusy = null;
      state.dsMsg = `Could not load the ${ds.label} sample. ${String(e.message || e)} The ${(dsDef(state.dsId) || {}).label || 'current'} sample stays open.`;
      syncDatasetSwitch(); rerender(focusKey); announce(state.dsMsg); return false;
    }
    state.dsBusy = null;
    applyDataset(ds, data);
    renderChrome(); buildFilters(); renderNav(); syncDatasetSwitch(); rerender(focusKey);
    if (state.view !== 'settings') window.scrollTo(0, 0);
    announce(`Showing the ${ds.label} sample data`);
    return true;
  }
  /* The "Sample data" switch in the header: only the samples that can open a dashboard, hidden on Onboarding (Step 1 is the chooser there). */
  function buildDatasetSwitch() {
    const list = state.registry, box = $('dataset');
    box.replaceChildren(...list.map((d) => h('button', { type: 'button', role: 'radio', 'data-v': d.id, 'aria-checked': 'false', tabindex: '-1', 'aria-label': `${d.label}, sample data`,
      onclick: () => switchDataset(d.id),
      onkeydown: (e) => {
        if (!['ArrowRight', 'ArrowLeft', 'ArrowDown', 'ArrowUp'].includes(e.key)) return;
        e.preventDefault();
        const i = list.findIndex((x) => x.id === state.dsId), next = list[(i + (e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : list.length - 1)) % list.length];
        switchDataset(next.id).then(() => { const b = box.querySelector(`[data-v="${next.id}"]`); if (b) b.focus(); });
      } }, h('span', { class: 'ds-long' }, d.label), h('span', { class: 'ds-short', 'aria-hidden': 'true' }, d.short || d.label))));
    syncDatasetSwitch();
  }
  function syncDatasetSwitch() {
    const box = $('dataset'); if (!box) return;
    box.setAttribute('aria-busy', String(!!state.dsBusy));
    box.querySelectorAll('button').forEach((b) => { const on = b.dataset.v === state.dsId; b.setAttribute('aria-checked', String(on)); b.tabIndex = on ? 0 : -1; });
    $('g-dataset').hidden = state.registry.length < 2 || state.view === 'settings';
  }
  function init() {
    state.view = routeFromHash() || 'settings';   // no address given: every visit starts on Onboarding (an address such as #overview still wins)
    renderChrome(); buildFilters(); renderNav(); renderView(); buildDatasetSwitch();
    if (!state.inited) {
      state.inited = true;
      window.addEventListener('hashchange', onHash);
      document.addEventListener('keydown', trapKeys);
      $('scrim').addEventListener('click', () => closeDrawer());
    }
  }
  // ?dataset=dining (or wallet) opens the dashboard on that sample; without it every fresh load starts on the default one.
  async function boot() {
    try { await loadRegistry(); } catch (e) { showError(String(e.message || e), null, boot); return; }
    const hit = dsDef(new URLSearchParams(location.search).get('dataset'));
    await load(hit ? hit.id : state.defaultDs);
  }
  document.title = NAME;
  $('brand-name').textContent = NAME;
  $('brand').setAttribute('aria-label', NAME + ', go to Overview');
  $('logo').alt = '';
  $('foot').textContent = `${NAME} · Built for AI Builder Cup 2026 · Gemini on Google Cloud`;
  initTheme();
  boot();
})();
