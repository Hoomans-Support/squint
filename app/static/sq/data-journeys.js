/* Journeys selectors: turn SQ.data (results.json) + SQ.scope into the shapes the Journeys screen draws.
   Everything here is counted from results.json; nothing is invented. Where the data has no equivalent the field is left out (never faked).
   Entry point: SQ.journeyModel() -> { tabs, byId, defaultId }. */
(function () {
  'use strict';
  const SQ = window.SQ;

  const PLURAL = { unregistered: 'unregistered users', large_business: 'large businesses', sari_sari: 'retail users', individual_trader: 'individual traders', individual: 'individuals' };
  const CAUSE = { technical: 'bug', language: 'word', ux: 'ux', natural: 'natural' };
  SQ.plural = (id, label) => PLURAL[id] || (label || id || 'users').toLowerCase();

  const num = (v) => (v == null || Number.isNaN(Number(v)) ? null : Number(v));
  const P = (frac) => (frac == null ? 'n/a' : (Number(frac) * 100).toFixed(Number(frac) < 0.1 ? 1 : 0) + '%');   // fraction -> text
  const PP = (v) => (v == null ? 'n/a' : Number(v).toFixed(1) + '%');                                              // percent units -> text
  const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
  const niceMax = (v) => { const steps = [5, 10, 20, 30, 40, 50, 60, 80, 100]; return steps.find((s) => s >= v * 1.1) || 100; };

  const viewOf = (persona) => SQ.data.views[SQ.scope.range + '|all|' + persona] || null;
  const stepIn = (view, jid, sid) => {
    if (!view) return null;
    const j = view.journeys.find((x) => x.id === jid);
    return j ? j.steps.find((s) => s.id === sid) || null : null;
  };
  const sigIn = (view, jid, sid) => ((view && view.signals && view.signals[jid]) || {})[sid] || null;

  /* one metric for one persona at one step, in percent units; null when the sample is too small */
  const METRICS = ['exit', 'taps', 'back', 'dead', 'stuck'];
  function metricAt(view, jid, sid, metric) {
    const st = stepIn(view, jid, sid);
    if (!st || st.low_sample || st.sessions < 20) return null;
    if (metric === 'exit') return (st.exits / st.sessions) * 100;
    const sig = sigIn(view, jid, sid);
    if (!sig) return null;
    return num(sig[{ taps: 0, back: 1, dead: 2, stuck: 3 }[metric]]);
  }

  function pathEdges() {
    const D = SQ.data, sc = SQ.scope;
    return (D.journeys[sc.platform + '|' + sc.persona] || D.journeys['all|' + sc.persona] || D.journeys['all|all'] || { edges: [] }).edges || [];
  }

  /* Flow decomposition. Per step: reached and exits are counted in the selected range. The sessions that did not exit are split
     between the next step and later steps in the proportions of the sample's path edges (those are not range-specific).
     Sessions that reached a step without coming from the previous one are "started here" (or skipped ahead). */
  function buildFlows(jid, steps, def) {
    const idx = {};
    def.steps.forEach((sd, i) => { String(sd.event).split('|').forEach((e) => { idx[e.trim()] = i; }); });
    const W = steps.map(() => ({}));
    pathEdges().forEach((e) => {
      const a = idx[e.from], b = idx[e.to];
      if (a == null || b == null || b <= a) return;
      W[a][b] = (W[a][b] || 0) + e.sessions;
    });
    const n = steps.length;
    const flows = [];
    const inflow = steps.map(() => 0);
    const maxReached = Math.max(...steps.map((s) => s.reached), 1);
    steps.forEach((s, i) => {
      if (i === n - 1) return;
      const R = Math.max(0, s.reached - s.left);
      if (R <= 0) return;
      let w = W[i];
      let tot = Object.values(w).reduce((a, b) => a + b, 0);
      if (!tot) { w = { [i + 1]: 1 }; tot = 1; }
      // keep every adjacent flow, drop skip-ahead flows under 2% of the step's sessions
      let keys = Object.keys(w).map(Number).filter((b) => b === i + 1 || w[b] / tot * R >= Math.max(1, s.reached * 0.02));
      const t2 = keys.reduce((a, b) => a + w[b], 0) || 1;
      let left = R;
      keys.sort((x, y) => x - y).forEach((b, k) => {
        const v = k === keys.length - 1 ? left : Math.round(R * w[b] / t2);
        left -= v;
        if (v <= 0) return;
        inflow[b] += v;
        flows.push([i, b, v, b === i + 1 ? 'fwd' : 'skip']);
      });
    });
    const out = [];
    steps.forEach((s, j) => {
      const start = s.reached - inflow[j];
      if (j === 0) { if (s.reached > 0) out.push(['start', 0, s.reached, 'start']); }
      else if (start >= Math.max(1, maxReached * 0.005)) out.push(['start', j, Math.round(start), 'start']);
    });
    flows.forEach((f) => out.push(f));
    steps.forEach((s, i) => { if (s.left > 0) out.push([i, 'exit', s.left, s.cause === 'natural' ? 'quit' : s.cause]); });
    // labels: only for flows big enough to read
    const big = Math.max(...steps.map((s) => s.reached), 1) * 0.04;
    out.forEach((f) => {
      if (f[3] === 'start' && f[1] !== 0 && f[2] >= big) f[4] = 'joined mid-journey';
      if (f[3] === 'skip' && f[2] >= big) f[4] = 'skipped to ' + steps[f[1]].name;
    });
    return out;
  }

  function dataGaps(jid, steps) {
    const faults = ((SQ.data.guardian || {}).faults || []).filter((f) => f.link && f.link.journey === jid && f.sev !== 'resolved' && f.status !== 'resolved' && (f.quarantine || f.sev === 'critical'));
    return faults.map((f) => {
      const si = steps.findIndex((s) => s.id === f.link.step);
      if (si < 0) return null;
      const s = steps[si];
      return {
        key: 'gap:' + f.id, kind: 'gap', type: 'Data gap', chip: 'Data gap', action: 'Check', item: s.name + ' tracking', who: 'the affected app version', ctx: '', short: s.name,
        step: si, metric: 'stuck', value: 'Likely undercounted', unit: '', share: '', conf: 2, signal: 'undercounted', vs: '', vis: 'selfie-gap', segmentVis: false,
        stats: [['Sessions held out', f.share != null ? P(f.share) : 'n/a', 'of sessions that got past this step', true], ['Leave here', s.left ? PP(s.left / Math.max(1, s.reached) * 100) : 'n/a', 'likely higher'], ['Reached here', SQ.fmt(s.reached), 'sessions counted']],
        whyLabel: 'What\'s missing', whyTag: 'Calculated', why: f.title + '. ' + (f.desc || ''),
        primary: 'Check data health', route: 'DataSources', hasWatch: false, whoMeasure: 'exit rate here', whoTick: null, whoVals: []
      };
    }).filter(Boolean);
  }

  function build(jid, ctx) {
    const D = SQ.data, view = SQ.view();
    const def = D.scope.journeys.find((j) => j.id === jid);
    // Some scopes have no data for a journey at all (e.g. the "Unregistered" group never
    // reaches Wallet top-up or Transaction, so results.json's view.journeys only lists
    // Register and login for them). Fall back to all-zero steps rather than crash; the
    // per-step fallback just below already renders a zero-session journey sensibly.
    const vj = view.journeys.find((j) => j.id === jid) || { steps: [] };
    const allView = viewOf('all') || view;
    // Journeys' "By user group" comparison table normally shows every named group. When 2+ named
    // groups are selected together, auto-switch it into comparative mode: only those groups' own
    // columns, so the table matches what was actually picked instead of always showing everyone.
    const comboIds = (SQ.scope.persona !== 'all' && SQ.scope.persona !== 'unregistered') ? SQ.scope.persona.split('+') : null;
    const isCompareMode = !!(comboIds && comboIds.length > 1);
    const personas = isCompareMode ? SQ.personas().filter((p) => comboIds.indexOf(p.id) >= 0) : SQ.personas();

    const noJourneyData = vj.steps.length === 0 || vj.steps.every((x) => !x.sessions);
    const steps = def.steps.map((sd) => {
      const v = vj.steps.find((x) => x.id === sd.id) || { sessions: 0, exits: 0, exit_class: 'natural', tone: 'healthy', low_sample: true };
      const terminal = sd.id === 'done';
      return { id: sd.id, name: sd.name, reached: v.sessions, left: terminal ? 0 : v.exits, cause: terminal ? 'done' : (CAUSE[v.exit_class] || 'natural'), tone: v.tone, low: !!v.low_sample, loop: null, sig: sigIn(view, jid, sd.id) };
    });
    const sidx = {}; steps.forEach((s, i) => { sidx[s.id] = i; });

    const rawLoops = ((view.loops || {})[jid] || []).filter((l) => sidx[l.from] != null && sidx[l.to] != null);
    const loops = rawLoops.map((l) => ({ from: sidx[l.from], to: sidx[l.to], count: l.count, kind: l.kind }));
    loops.forEach((l) => { const s = steps[l.from]; if (!s.loop || l.count > s.loop[1]) s.loop = [steps[l.to].name, l.count]; });
    const arcs = loops.map((l) => [l.from, l.to, l.count, l.kind === 'pos' ? '#1E8E3E' : (steps[l.from].tone === 'critical' ? '#D93025' : '#F9AB00')]);

    const totalExits = steps.reduce((t, s) => t + s.left, 0);
    const flows = buildFlows(jid, steps, def);

    /* heat table: rows = steps people can leave or struggle on, columns = user groups */
    const gridIdx = steps.map((s, i) => i).filter((i) => steps[i].id !== 'done' && steps[i].id !== 'prices' && steps[i].reached >= 30);
    const pViews = personas.map((p) => viewOf(p.id));
    const D5 = {};
    METRICS.forEach((m) => { D5[m] = gridIdx.map((i) => pViews.map((pv) => metricAt(pv, jid, steps[i].id, m))); });

    /* "who goes back most here" per step */
    const backWho = steps.map((s) => {
      const vals = personas.map((p, k) => ({ p, v: metricAt(pViews[k], jid, s.id, 'back') })).filter((x) => x.v != null);
      if (!vals.length) return null;
      vals.sort((a, b) => b.v - a.v);
      return { id: vals[0].p.id, label: vals[0].p.label, v: vals[0].v, overall: s.sig ? num(s.sig[1]) : null };
    });

    /* ---- issues ---- */
    const problems = SQ.problems().filter((i) => i.journey === jid && sidx[i.step] != null);
    const totalLeft = Math.max(1, totalExits);
    const issues = [];

    const whoFromViews = (si, metric) => personas.map((p, k) => ({ label: p.label, id: p.id, v: metricAt(pViews[k], jid, steps[si].id, metric) })).filter((r) => r.v != null);

    problems.forEach((ins) => {
      const si = sidx[ins.step], s = steps[si];
      const seg = ins.segment || {};
      const isSeg = ins.scope === 'segment' && Object.keys(seg).length > 0;
      const drop = (ins.signals || []).find((x) => x.metric === 'drop_off');
      const gs = ((ins.evidence_stats || {}).group) || {};
      const klass = ins.class || (ins.diagnosis || {}).class;
      const rate = s.reached ? s.left / s.reached : null;
      const sharePct = s.left ? s.left / totalLeft * 100 : null;
      const personaId = seg.persona || null;
      const prodLabel = seg.product ? ((D.scope.products.find((p) => p.id === seg.product) || {}).label || seg.product) : null;
      const bd = (ins.breakdown || []).filter((b) => b.dim === 'persona' && personas.some((p) => p.id === b.value));
      let whoVals = bd.map((b) => ({ label: b.label, v: b.rate * 100, id: b.value }));
      let tick = drop ? drop.reference * 100 : null;
      if (!whoVals.length) whoVals = whoFromViews(si, 'exit');
      if (tick == null) { const bn = bd.reduce((a, b) => a + b.n, 0); tick = bn ? bd.reduce((a, b) => a + b.n * b.rate, 0) / bn * 100 : (rate != null ? rate * 100 : null); }
      let ctxText = '';
      if (prodLabel) ctxText = '· ' + prodLabel + ' only';
      else if (ins.window && ins.window.start) {
        const d0 = new Date(ins.window.start), d1 = new Date(ins.window.end);
        const day = d0.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
        const hh = (d) => String(d.getUTCHours()).padStart(2, '0') + ':00';
        ctxText = '· ' + day + ', ' + hh(d0) + '–' + hh(d1) + ' UTC';
      } else if (whoVals.length > 1) {
        const top = whoVals.slice().sort((a, b) => b.v - a.v)[0];
        if (tick != null && top.v >= tick * 1.3) ctxText = '· worst for ' + SQ.plural(top.id, top.label);
      }
      const act = klass === 'technical_bug' ? (isSeg ? 'Fix' : 'Investigate') : klass === 'language_cognitive_overload' ? 'Rewrite' : klass === 'ux_friction' ? 'Review' : 'Investigate';
      const tech = klass === 'technical_bug';
      const stats = [];
      const lbl = (e) => cap(String(e || '').replace(/_/g, ' '));
      if (isSeg && drop) stats.push(['Leave here', P(drop.value), 'vs ' + P(drop.reference) + ' for everyone else', true]);
      else {
        stats.push(['Share of all exits', sharePct != null ? PP(sharePct) : 'n/a', s.left + ' of ' + SQ.fmt(totalExits) + ' who left', true]);
        stats.push(['Leave here', rate != null ? PP(rate * 100) : 'n/a', drop ? P(drop.value) + ' in the spike, ' + P(drop.reference) + ' outside' : 'of ' + SQ.fmt(s.reached) + ' who reached it']);
      }
      const taps = (gs.top_rage_tap_elements || [])[0];
      const errs = (gs.top_error_codes || [])[0];
      const stuckV = s.sig ? num(s.sig[3]) : null;
      const loopOut = loops.filter((l) => l.from === si).sort((a, b) => b.count - a.count)[0];
      const cTaps = taps && taps.taps > 0 ? ['Repeated taps', SQ.fmt(taps.taps), 'on ' + lbl(taps.element)] : null;
      const cErr = errs && errs.events > 0 ? ['Errors', SQ.fmt(errs.events), errs.code] : null;
      const cStuck = stuckV != null ? ['Stuck over 30s', PP(stuckV), 'of sessions at this step'] : null;
      const cLoop = loopOut ? ['Loops back', SQ.fmt(loopOut.count), 'to ' + steps[loopOut.to].name] : null;
      (tech ? [cTaps, cErr, cStuck, cLoop] : [cStuck, cLoop, cTaps, cErr]).filter(Boolean).forEach((t) => { if (stats.length < 4) stats.push(t); });
      const dg = ins.diagnosis || {};
      const ai = dg.source === 'gemini' || dg.source === 'cached';
      const conf = ins.confidence != null ? ins.confidence : dg.confidence;
      const text = String(dg.summary || ins.summary || ins.hypothesis || '');
      let why = text.split(/(?<=[.!?])\s/)[0] || text;
      if (why.length > 190) why = why.slice(0, 187).replace(/\s+\S*$/, '') + '…';
      const val = ins.impact && ins.impact.per_week_dollars > 0 ? SQ.money(ins.impact.per_week_dollars) : null;
      issues.push({
        key: ins.id, kind: 'problem', insightId: ins.id, pid: ins.__p, type: ins.severity === 'critical' ? 'Critical' : 'Warning', chip: (ins.severity === 'critical' ? 'Critical' : 'Warning') + ' · ' + ({ technical_bug: 'Bug', ux_friction: 'UX', language_cognitive_overload: 'Wording', natural_exit: 'Natural exit' }[klass] || 'Needs review'), cause: { technical_bug: 'bug', ux_friction: 'ux', language_cognitive_overload: 'word' }[klass] || null,
        action: act, item: ins.screen_label || s.name, who: personaId ? SQ.plural(personaId) : 'all users', ctx: ctxText, short: s.name,
        step: si, metric: tech ? 'taps' : 'stuck', value: val || 'n/a', hasValue: !!val, unit: val ? ' /wk at risk' : '',
        share: !isSeg && sharePct != null ? PP(sharePct) : '', conf: conf >= 0.8 ? 3 : conf >= 0.5 ? 2 : 1,
        signal: isSeg && drop ? P(drop.value) + ' leave' : (sharePct != null ? PP(sharePct) + ' of exits' : ''),
        vs: isSeg && drop ? 'vs ' + P(drop.reference) + (drop.ratio ? ' · ' + Number(drop.ratio).toFixed(1) + '×' : '') : (rate != null ? '· ' + PP(rate * 100) + ' leave' : ''),
        vis: 'step', segment: isSeg ? [personaId && SQ.plural(personaId), prodLabel].filter(Boolean).map(cap).join(', ') : '', personaId, segmentVis: isSeg,
        stats, whyLabel: 'Why', whyTag: ai ? (conf != null && conf < 0.6 ? 'AI · low confidence' : 'AI') : (dg.source === 'unclassified' ? 'Needs review' : 'Calculated'), why,
        primary: 'See why', route: 'ProblemDetail', hasWatch: (ins.replays || 0) > 0,
        whoMeasure: 'exit rate here', whoTick: tick, whoVals: whoVals.map((r) => [r.label, r.v])
      });
    });

    /* a Watch item when the journey has no diagnosed problem: its steepest step */
    const covered = new Set(issues.map((x) => x.step));
    if (!problems.length) {
      const cands = steps.map((s, i) => ({ s, i })).filter((x) => x.s.cause !== 'done' && x.s.id !== 'prices' && x.s.reached >= 30 && x.s.left > 0).sort((a, b) => b.s.left - a.s.left);
      if (cands.length) {
        const { s, i } = cands[0];
        const rate = s.left / s.reached;
        issues.push({
          key: 'watch:' + jid + ':' + s.id, kind: 'watch', type: 'Watch', chip: 'Watch · ' + ({ bug: 'Technical', word: 'Wording', ux: 'UX friction', natural: 'Natural exit' }[s.cause] || 'Exit'), action: 'Investigate', item: s.name, who: 'all users', ctx: '· steepest step in this journey',
          short: s.name, step: i, metric: 'exit', value: 'n/a', unit: '', share: PP(s.left / totalLeft * 100), conf: s.reached >= 200 ? 2 : 1, signal: PP(s.left / totalLeft * 100) + ' of exits', vs: '· ' + PP(rate * 100) + ' leave', vis: 'step', segmentVis: false,
          stats: [['Share of all exits', PP(s.left / totalLeft * 100), s.left + ' of ' + SQ.fmt(totalExits) + ' who left', true], ['Leave here', PP(rate * 100), 'of ' + SQ.fmt(s.reached) + ' who reached it'], ['Stuck over 30s', s.sig ? PP(s.sig[3]) : 'n/a', 'of sessions at this step']],
          whyLabel: 'Why', whyTag: 'Calculated', why: 'No diagnosed problem here yet. This is the step where the most sessions leave, so it is the first place to look.',
          primary: 'Investigate', route: 'Ask', hasWatch: false, whoMeasure: 'exit rate here', whoTick: rate * 100, whoVals: whoFromViews(i, 'exit').map((r) => [r.label, r.v])
        });
      }
    }
    dataGaps(jid, steps).forEach((g) => issues.push(g));

    /* segment risks and blind spots: one user group clearly worse than everyone else at a step, with enough sessions */
    const MIN = { exit: 5, dead: 3, back: 3, stuck: 12 };
    const NAME = { exit: 'leaving here', dead: 'taps that do nothing', back: 'going back and forth', stuck: 'stuck on the screen' };
    const LAB = { exit: 'Leave here', dead: 'Taps that did nothing', back: 'Going back', stuck: 'Stuck over 30s' };
    const pinned = SQ.scope.persona === 'all' ? null : new Set(SQ.personaIds());
    const cand = [];
    personas.forEach((p, k) => {
      if (pinned && !pinned.has(p.id)) return;
      steps.forEach((s, si) => {
        if (s.cause === 'done' || s.id === 'prices') return;
        if (problems.some((x) => x.step === s.id && ((x.persona_ids || []).includes(p.id)))) return;
        const pst = stepIn(pViews[k], jid, s.id);
        if (!pst || pst.low_sample || pst.sessions < 50) return;
        let best = null;
        ['exit', 'dead', 'back', 'stuck'].forEach((m) => {
          const v = metricAt(pViews[k], jid, s.id, m), b = metricAt(allView, jid, s.id, m);
          if (v == null || b == null || v < MIN[m]) return;
          const ratio = v / Math.max(b, 0.5);
          const excess = (v - b) / 100 * pst.sessions;
          if (ratio < 1.5 || excess < 5) return;
          if (!best || excess > best.excess) best = { m, v, b, ratio, excess };
        });
        if (best) cand.push({ p, k, si, s, pst, ...best });
      });
    });
    cand.sort((a, b) => b.excess - a.excess).slice(0, 3).forEach((c) => {
      const overallTone = (stepIn(allView, jid, c.s.id) || {}).tone;
      const blind = overallTone === 'healthy';
      const pl = SQ.plural(c.p.id, c.p.label);
      const others = ['exit', 'stuck', 'dead', 'back'].filter((m) => m !== c.m).map((m) => ({ m, v: metricAt(pViews[c.k], jid, c.s.id, m), b: metricAt(allView, jid, c.s.id, m) })).filter((x) => x.v != null && x.b != null);
      const stats = [[LAB[c.m], PP(c.v), 'vs ' + PP(c.b) + ' for everyone', true]];
      others.slice(0, 2).forEach((x) => stats.push([LAB[x.m], PP(x.v), 'vs ' + PP(x.b) + ' for everyone']));
      const gv = whoFromViews(c.si, c.m);
      issues.push({
        key: 'risk:' + jid + ':' + c.s.id + ':' + c.p.id + ':' + c.m, kind: 'risk', type: blind ? 'Blind spot' : 'Segment', chip: blind ? 'Blind spot' : 'Segment risk', segment: cap(pl), personaId: c.p.id,
        action: 'Investigate', item: c.s.name, who: pl, ctx: blind ? '· hidden by a healthy average' : '· ' + NAME[c.m], short: c.s.name + ' · ' + pl,
        step: c.si, metric: c.m, value: '', unit: '', share: '', conf: c.pst.sessions >= 200 ? 2 : 1, signal: PP(c.v) + ' ' + ({ exit: 'exit', dead: 'dead taps', back: 'going back', stuck: 'stuck' }[c.m]), vs: 'vs ' + PP(c.b) + ' · ' + c.ratio.toFixed(1) + '×', vis: 'step', segmentVis: true,
        stats, whyLabel: 'Why', whyTag: 'Calculated', why: cap(pl) + ' show ' + PP(c.v) + ' ' + NAME[c.m].replace('leaving here', 'leaving') + ' at ' + c.s.name + ', against ' + PP(c.b) + ' for everyone' + (blind ? '. The overall average looks healthy, so this goes unnoticed.' : '.'),
        primary: 'Investigate', route: 'Ask', hasWatch: false, whoMeasure: NAME[c.m], whoTick: c.b, whoVals: gv.map((r) => [r.label, r.v])
      });
    });

    /* attach the phone-screen hotspot (rage-tap glow) and a stuck-session replay when the data has them */
    issues.forEach((x) => {
      const s = steps[x.step];
      const hs = (D.hotspots || []).find((h) => h.journey === jid && h.step === s.id);
      x.hotspot = hs || null;
      x.replay = x.insightId ? ((D.stuck_sessions || []).find((r) => r.insight_id === x.insightId && !r.good) || null) : null;
      x.whoMax = niceMax(Math.max(1, ...x.whoVals.map((r) => r[1]), x.whoTick || 0));
      const t = x.whoVals.length ? x.whoVals : [];
      if (!t.length) x.noWho = true;
    });

    /* keep list: the steps with the lowest exit rate and enough sessions */
    const flagged = new Set(issues.map((x) => x.step));
    const keep = steps.map((s, i) => ({ s, i })).filter((x) => x.s.cause !== 'done' && x.s.reached >= 100 && !flagged.has(x.i)).sort((a, b) => a.s.left / a.s.reached - b.s.left / b.s.reached).slice(0, 2).sort((a, b) => a.i - b.i).map((x) => x.s.name);

    return { id: jid, name: def.name, steps, flows, loops, arcs, totalExits, gridIdx, D: D5, personaCols: personas.map((p) => p.label), personaIds: personas.map((p) => p.id), backWho, issues, keepText: keep.length ? 'Keep: ' + keep.join(', ') : '', sessions: steps[0] ? Math.max(...steps.map((x) => x.reached)) : 0, isCompareMode, compareNames: personas.map((p) => p.label), noJourneyData };
  }

  SQ.journeyModel = () => {
    const D = SQ.data;
    const problems = SQ.problems();
    const byId = {};
    D.scope.journeys.forEach((j) => { byId[j.id] = build(j.id); });
    const tabs = D.scope.journeys.map((j) => ({
      id: j.id, name: j.name,
      badge: problems.filter((p) => p.journey === j.id).map((p) => p.__p).sort((a, b) => Number(a.slice(1)) - Number(b.slice(1))).slice(0, 3).join(' · ')
    }));
    const first = problems[0];
    return { tabs, byId, defaultId: first && byId[first.journey] ? first.journey : D.scope.journeys[0].id };
  };

  /* products: completion of the transaction journey per product (whole sample, not range-specific) */
  SQ.productCompletion = () => {
    const pf = SQ.data.product_funnels || {};
    const rows = Object.keys(pf).map((k) => {
      const f = pf[k];
      const worst = f.steps.filter((s) => s.exit_rate != null && s.id !== 'done').sort((a, b) => b.exit_rate - a.exit_rate)[0];
      return { label: f.label, sessions: f.sessions, completion: f.completion, worst };
    });
    const tot = rows.reduce((a, r) => a + r.sessions, 0) || 1;
    const avg = rows.reduce((a, r) => a + r.sessions * r.completion, 0) / tot;
    return { rows: rows.sort((a, b) => a.completion - b.completion), avg };
  };
})();
