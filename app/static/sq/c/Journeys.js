SQ.define("Journeys", function (DCLogic) {
class Component extends DCLogic {
  renderVals() {
    setTimeout(() => SQ.animateCounts('.sq-count'), 180);
    const fmt = (n) => SQ.fmt(n);
    const confBars = (n) => [1, 2, 3].map((i) => (i <= n ? '#1A73E8' : '#DADCE0'));
    const sevDot = { Critical: '#D93025', Warning: '#F9AB00', Watch: '#BDC1C6', 'Data gap': '#F9AB00', Segment: '#1A73E8', 'Blind spot': '#1A73E8' };
    const chipC = { Critical: ['#FCE8E6', '#C5221F'], Warning: ['#FEF7E0', '#B06000'], Watch: ['#F1F3F4', '#3C4043'], 'Data gap': ['#FEF7E0', '#B06000'], Segment: ['#E8F0FE', '#174EA6'], 'Blind spot': ['#E8F0FE', '#174EA6'] };
    const barC = { Critical: '#D93025', Warning: '#F9AB00' };   // red only for critical, yellow for a warning, blue for the rest
    // Re-rendering replaces the DOM, so remember which control had focus and put it back.
    const upd = (patch) => {
      const a = document.activeElement;
      const fk = a && a.getAttribute ? a.getAttribute('data-fk') : null;
      this.setState(patch);
      if (fk) setTimeout(() => { const el = document.querySelector('[data-fk="' + fk + '"]'); if (el) el.focus(); }, 0);
    };

    // ---------- Journey data, all counted from results.json (see data-journeys.js) ----------
    const MODEL = SQ.journeyModel();
    if (!this.__init) {
      this.__init = true;
      const want = SQ.state.journeyInsight; delete SQ.state.journeyInsight;
      const hit = want && SQ.insight(want);
      const saved = SQ.state.journeysSel;
      if (hit && MODEL.byId[hit.journey]) {
        const k = MODEL.byId[hit.journey].issues.find((x) => x.insightId === hit.id);
        this.state.journey = hit.journey; this.state.curKey = k ? k.key : undefined; this.state.from = hit.__p || (SQ.problems().find((p) => p.id === hit.id) || {}).__p || '';
      } else if (saved && MODEL.byId[saved.journey]) { this.state.journey = saved.journey; this.state.curKey = saved.curKey; }
    }
    const jid = MODEL.byId[this.state.journey] ? this.state.journey : MODEL.defaultId;
    const JD = MODEL.byId[jid];
    const PLACEHOLDER = { key: 'none', kind: 'watch', type: 'Watch', chip: 'Nothing flagged', action: 'Nothing to fix', item: 'in this scope', who: 'these users', ctx: '', short: 'Nothing flagged', step: 0, metric: 'exit', value: '', unit: '', share: '', conf: 1, signal: '', vs: '', vis: 'step', stats: [], whyLabel: 'Why', whyTag: 'Calculated', why: 'No step has enough sessions in this scope to flag anything.', primary: 'Ask a question', route: 'Ask', hasWatch: false, whoMeasure: 'exit rate here', whoTick: null, whoVals: [], whoMax: 10 };
    const ISSUES = JD.issues.length ? JD.issues : [PLACEHOLDER];
    const found = ISSUES.findIndex((x) => x.key === this.state.curKey);
    const cur = found >= 0 ? found : 0;
    const listOpen = !!this.state.listOpen;
    const I = ISSUES[cur];
    const remember = (jv, key) => { SQ.state.journeysSel = { journey: jv, curKey: key }; };
    const pick = (i) => { remember(jid, ISSUES[i].key); upd({ curKey: ISSUES[i].key, metric: undefined, listOpen: false, pathStep: undefined }); };
    const setJourney = (j) => { remember(j, undefined); upd({ journey: j, curKey: undefined, from: '', metric: undefined, listOpen: false, pathStep: undefined }); };
    const jtabs = MODEL.tabs.map((t) => ({
      label: t.name + (t.badge ? ' ' : ''), badge: t.badge, hasBadge: !!t.badge, on: jid === t.id ? 'true' : 'false', fk: 'tab-' + t.id,
      title: t.badge ? 'Open problems: ' + t.badge : 'No open problems in this scope',
      style: jid === t.id ? 'background: #E8F0FE; color: #174EA6;' : '',
      pick: () => setJourney(t.id)
    }));

    const strip = ISSUES.slice(0, 4).map((x, i) => ({
      n: i + 1, name: x.short, share: x.share, dot: sevDot[x.type], on: cur === i ? 'true' : 'false', fk: 'strip-' + i,
      tag: x.pid || 'Risk', tagColor: x.pid ? '#C5221F' : '#9AA0A6',
      style: cur === i ? 'color: #174EA6; font-weight: 500; border-bottom-color: #1A73E8;' : '',
      rkStyle: '',
      pick: () => pick(i)
    }));
    const issues = ISSUES.map((x, i) => {
      const [c1, c2, c3] = confBars(x.conf);
      return {
        n: i + 1, action: x.action, item: x.item, who: x.who, signal: x.signal, vs: x.vs, type: (x.pid ? x.pid : 'Risk') + ' · ' + x.type, dot: sevDot[x.type], fk: 'list-' + i,
        c1, c2, c3, confLabel: ['', 'Low', 'Medium', 'High'][x.conf], on: cur === i ? 'true' : 'false',
        rowStyle: cur === i ? 'background: #F8FBFF; color: #174EA6;' : '',
        pick: () => pick(i)
      };
    });

    const whoColor = barC[I.type] || '#1A73E8';
    const whoRows = (I.whoVals || []).slice().sort((a, b) => b[1] - a[1])
      .map(([name, v], i) => ({ name, v: v.toFixed(1) + '%', w: Math.min(100, v / I.whoMax * 100).toFixed(1) + '%', c: i === 0 ? whoColor : '#BDC1C6', ls: i === 0 ? 'font-weight: 500; color: #202124' : 'color: #3C4043' }));
    const raw = JD.steps.map((s, i) => [s.name, s.reached, s.left, (i === I.step && I.cause && s.cause !== 'done') ? I.cause : s.cause, s.loop]);
    const stepNames = raw.map((r) => r[0]);
    const focus = I.step;
    const focusStep = JD.steps[focus] || JD.steps[0];
    const hero = {
      n: cur + 1, stripName: I.short,
      rankLabel: (cur === 0 ? 'Biggest leak in this journey' : `${cur + 1} of ${ISSUES.length} in this journey`) + (I.pid ? ' · problem ' + I.pid : (I.key === 'none' ? '' : ' · risk, not yet a problem')),
      notTop: cur !== 0,
      chip: I.chip, chipBg: chipC[I.type][0], chipFg: chipC[I.type][1], dot: sevDot[I.type],
      hasSegment: !!I.segment, segment: I.segment || '',
      value: I.value, valueUnit: I.unit, valueStyle: I.hasValue ? '' : 'font-size: 13px; font-weight: 400; color: #5F6368',
      action: I.action, item: I.item, who: I.who, ctx: I.ctx,
      stats: I.stats.map(([label, v, sub, hi]) => ({ label, v, sub, box: hi ? 'border-color: #F6AEA9; background: #FFFBFA;' : '', valStyle: hi ? 'font-weight: 500; color: #C5221F' : '' })),
      hasStats: I.stats.length > 0,
      whyLabel: I.whyLabel, whyTag: I.whyTag, why: I.why,
      whyTagStyle: I.whyTag === 'Calculated' ? '' : 'background: #E8F0FE; color: #174EA6',
      hasWho: (I.whoVals || []).length > 0 && I.whoTick != null, whoMeasure: I.whoMeasure, whoTick: I.whoTick != null ? I.whoTick.toFixed(1) + '%' : '',
      tickPos: I.whoTick != null ? Math.min(100, I.whoTick / I.whoMax * 100).toFixed(1) + '%' : '0%', whoRows,
      primary: I.primary, hasWatch: !!I.hasWatch,
      openPrimary: () => { if (I.route === 'ProblemDetail' && I.insightId) SQ.state.drawerInsight = I.insightId; SQ.go(I.route); },
      openWatch: () => { SQ.state.watchInsight = I.insightId; SQ.go('SessionPlayer'); }
    };

    // phone screen drawn for the focused step; glows come from measured rage-tap spots
    const VISKEY = { 'register_login.otp': 'otp', 'register_login.personal_data': 'form', 'register_login.tin': 'single', 'register_login.kyc_selfie': 'selfie', 'transaction.confirm': 'checkout', 'transaction.details': 'details' };
    const vk = VISKEY[jid + '.' + focusStep.id] || 'generic';
    const hs = I.hotspot && (vk === 'otp' || vk === 'checkout') ? I.hotspot : null;
    const spots = hs ? hs.spots.slice(0, 3) : [];
    const maxTaps = Math.max(1, ...spots.map((p) => p[3]));
    const glows = spots.map((p, i) => {
      const size = Math.round(48 + 80 * p[3] / maxTaps);
      const red = i === 0;
      return {
        gStyle: `width: ${size}px; height: ${size}px; left: calc(${p[1]}% - ${size / 2}px); top: calc(${p[0]}% - ${size / 2}px); background: ` + (red ? 'radial-gradient(circle, rgba(217,48,37,.55) 0%, rgba(217,48,37,.18) 45%, rgba(217,48,37,0) 70%)' : 'radial-gradient(circle, rgba(249,171,0,.6) 0%, rgba(249,171,0,0) 70%)'),
        bStyle: `left: calc(${p[1]}% - 10px); top: calc(${p[0]}% - 10px); background: ${red ? '#D93025; color: #FFFFFF' : '#F9AB00; color: #202124'}`, n: i + 1
      };
    });
    const stuckV = focusStep.sig ? Number(focusStep.sig[3]) : null;
    const leaveV = focusStep.reached ? focusStep.left / focusStep.reached * 100 : null;
    const badgeTxt = (I.segmentVis || I.kind === 'risk') ? I.signal : (stuckV != null && stuckV >= 8 ? 'Stuck ' + stuckV.toFixed(1) + '%' : (leaveV != null ? leaveV.toFixed(1) + '% leave' : ''));
    const vis = {
      otp: vk === 'otp', form: vk === 'form', single: vk === 'single', selfie: vk === 'selfie', checkout: vk === 'checkout', details: vk === 'details', generic: vk === 'generic',
      selfieStyle: I.kind === 'gap' ? 'border-style: dashed' : '',
      fieldStyle: I.segmentVis && vk === 'form' ? 'border: 2px dashed #1A73E8' : '',
      badgeBg: I.segmentVis ? '#1A73E8' : '#669DF6', badgeTxt, hasBadge: !!badgeTxt && vk !== 'otp' && vk !== 'selfie',
      glows, stepName: stepNames[focus],
      aria: stepNames[focus] + ' screen, drawn as a wireframe.' + (spots.length ? ' ' + spots.map((p) => `${p[3]} repeated taps on ${p[4]}`).join('; ') + '.' : '') + (I.kind === 'gap' ? ' Drawn dashed because its tracker is silent.' : ''),
      caption: I.key === 'none' ? '' : stepNames[focus] + (spots.length ? ' · glow = repeated taps' : '') + (I.segmentVis && I.segment ? ' · as seen by ' + I.segment.toLowerCase() : '')
    };

    // ---------- replay of one stuck session, when the data has one for this problem ----------
    let replay = { has: false };
    const rs = I.replay;
    if (rs && rs.bands && rs.bands.length) {
      const dur = Math.max(...rs.bands.map((b) => b[1]), 1);
      const axis = Math.max(60, Math.ceil(dur * 1.15 / 30) * 30);
      const x = (t) => (t / axis * 100).toFixed(2);
      const bandsR = rs.bands.map((b) => {
        const hit = b[2] === I.item || b[2] === stepNames[focus];
        return { st: `left: ${x(b[0])}%; width: ${(x(b[1]) - x(b[0])).toFixed(2)}%; background: ${hit ? '#FCE8E6' : '#E8EAED'}`, lb: `left: calc(${x(b[0])}% + 8px); color: ${hit ? '#C5221F' : '#5F6368'}`, name: b[2] };
      });
      const marks = [];
      rs.marks.forEach((m) => {
        if (m[0] === 'rage') marks.push(`left: ${x(m[1])}%; top: 14px; width: max(3px, ${(x(m[2]) - x(m[1])).toFixed(2)}%); height: 16px; border-radius: 1px; background: #D93025`);
        else if (m[0] === 'idle') marks.push(`left: ${x(m[1])}%; top: 22px; width: ${(x(m[2]) - x(m[1])).toFixed(2)}%; height: 0; border-top: 2px dotted #9AA0A6`);
        else if (m[0] === 'tap') marks.push(`left: ${x(m[1])}%; top: 17px; width: 2px; height: 10px; background: #9AA0A6`);
        else if (m[0] === 'back') marks.push(`left: ${x(m[1])}%; top: 17px; width: 10px; height: 10px; margin-left: -5px; border-radius: 5px; background: #1A73E8`);
        else marks.push(`left: ${x(m[1])}%; top: 16px; width: 12px; height: 12px; margin-left: -6px; border-radius: 2px; background: #202124`);
      });
      const ticks = []; for (let t = 0; t <= axis; t += 30) ticks.push(t + 's');
      replay = { has: true, who: rs.who, outcome: rs.outcome, bands: bandsR, marks: marks.map((st) => ({ st })), ticks: ticks.map((t) => ({ t })), tickCols: `repeat(${ticks.length - 1}, 1fr) auto`, aria: `Timeline of one stuck session, ${rs.outcome.toLowerCase()}: ` + rs.bands.map((b) => `${b[2]} from ${b[0]} to ${b[1]} seconds`).join(', ') + '.' };
    }

    // ---------- Evidence, driven by the selected issue ----------
    const ps = Math.min(this.state.pathStep ?? focus, raw.length - 1);
    const metric = this.state.metric ?? I.metric;
    const view = this.state.view ?? 'chart';
    const C = { bug: '#D93025', word: '#1A73E8', ux: '#F9AB00', natural: '#BDC1C6', done: '#1E8E3E' };
    const CN = { bug: 'Technical bug', word: 'Confusing wording', ux: 'UX friction', natural: 'Natural exit', done: 'Completed' };
    const nSteps = raw.length;
    const totalExits = Math.max(1, raw.reduce((t, r) => t + r[2], 0));
    const maxReached = Math.max(1, ...raw.map((r) => r[1]));
    const colW = 1000 / nSteps;
    const cx = (i) => i * colW + colW / 2;
    const pc = (v) => (v / 10).toFixed(2) + '%';
    const nodes = raw.map(([name, reached, left, ck, loop], i) => {
      const isSel = ps === i;
      const share = left / totalExits * 100;
      return {
        name, loop, reachedTxt: fmt(reached), onTxt: ck === 'done' ? '—' : fmt(reached - left), leftTxt: ck === 'done' ? '—' : fmt(left), leftN: left,
        rateTxt: ck === 'done' ? '—' : (reached < 30 ? 'few' : (left / reached * 100).toFixed(1) + '%'),
        shareTxt: left ? share.toFixed(1) + '%' : '—', share, shareStyle: share >= 20 ? 'font-weight: 500; color: #C5221F' : '',
        cause: CN[ck], color: C[ck],
        btnStyle: isSel ? 'background: #E8F0FE; color: #174EA6;' : 'color: #5F6368;',
        labelStyle: isSel ? 'color: #174EA6; font-weight: 500' : 'color: #5F6368',
        rowStyle: isSel ? 'background: #F8FBFF;' : '',
        pressed: isSel ? 'true' : 'false', fk: 'node-' + i, pickPath: () => upd({ pathStep: i })
      };
    });
    const s = nodes[ps];
    const merged = this.props.mergeBack === 'yes' || this.props.mergeBack === true;
    const isEnd = raw[ps][3] === 'done';
    const sel = {
      label: ps === focus ? "This issue's step" : 'Selected step',
      name: s.name, cause: s.cause, reachedTxt: s.reachedTxt, onTxt: s.onTxt, leftTxt: s.leftTxt,
      leftStyle: s.share >= 20 ? 'color: #C5221F; font-weight: 500' : '',
      sentence: isEnd ? `${s.reachedTxt} sessions finished the journey.`
        : `${s.rateTxt} leave here, which is ${s.shareTxt} of everyone who leaves this journey.` + (s.loop ? ` ${s.loop[1]} went back to ${s.loop[0]}.` : ''),
      notIssue: ps !== focus, reset: () => upd({ pathStep: undefined })
    };

    // ---------- Sankey: every direction out of and into each step ----------
    const F = JD.flows;
    const nIn = raw.map(() => 0), nOut = raw.map(() => 0);
    F.forEach(([a, b, n]) => { if (typeof a === 'number') nOut[a] += n; if (typeof b === 'number') nIn[b] += n; });
    const nodeV = raw.map((_, i) => Math.max(nIn[i], nOut[i]));
    const Y0 = 8, HM = 200;
    const skS = HM / Math.max(1, ...nodeV);
    const exitY = Y0 + HM + 56;
    const skH = exitY + 50;
    const outRank = (f) => (f[1] === f[0] + 1 ? 0 : typeof f[1] === 'number' ? 1 : f[3] === 'other' ? 2 : 3);
    const inRank = (f) => (f[0] === 'start' ? 2 : f[0] === f[1] - 1 ? 0 : 1);
    const ordered = (key) => F.map((f, i) => [f, i]).sort((x, y) => key(x[0]) - key(y[0]) || x[1] - y[1]).map((x) => x[0]);
    const pos = new Map(F.map((f) => [f, {}]));
    const oy = raw.map(() => Y0), iy = raw.map(() => Y0);
    ordered(outRank).forEach((f) => { if (typeof f[0] !== 'number') return; const h = Math.max(1.5, f[2] * skS); Object.assign(pos.get(f), { a0: oy[f[0]], b0: oy[f[0]] + h }); oy[f[0]] += h; });
    ordered(inRank).forEach((f) => { if (typeof f[1] !== 'number') return; const h = Math.max(1.5, f[2] * skS); Object.assign(pos.get(f), { a1: iy[f[1]], b1: iy[f[1]] + h }); iy[f[1]] += h; });
    const NODEC = { natural: '#34A853', word: '#1A73E8', ux: '#F9AB00', bug: '#D93025', done: '#1E8E3E' };
    const FWDC = { natural: '#DCEFE2', word: '#DCE8FC', ux: '#FDF0C5', bug: '#FADBD8' };
    const EXC = { quit: ['#E8EAED', '#9AA0A6', '#5F6368'], word: ['#D2E3FC', '#1A73E8', '#174EA6'], ux: ['#FDE9A8', '#F9AB00', '#B06000'], bug: ['#FAD2CF', '#D93025', '#C5221F'], other: ['#CBF0F8', '#12B5CB', '#007B83'] };
    const r1 = (v) => v.toFixed(1);
    const ribbon = (x0, a0, b0, x1, a1, b1) => { const m = (x0 + x1) / 2; return `M${r1(x0)},${r1(a0)} C${r1(m)},${r1(a0)} ${r1(m)},${r1(a1)} ${r1(x1)},${r1(a1)} L${r1(x1)},${r1(b1)} C${r1(m)},${r1(b1)} ${r1(m)},${r1(b0)} ${r1(x0)},${r1(b0)} Z`; };
    const skPaths = [], skRects = [], skLabels = [];
    F.forEach((f) => {
      const [a, b, n, k, label] = f;
      const P = pos.get(f);
      const hot = a === ps || b === ps;
      const op = hot ? 1 : 0.85;
      if (a === 'start') {
        if (b === 0) return;
        skPaths.push({ d: ribbon(0, P.a1, P.b1, cx(b), P.a1, P.b1), fill: '#EEF0F2', op: 1 });
        if (label) skLabels.push({ txt: `${fmt(n)} started here`, left: '4px', top: r1((P.a1 + P.b1) / 2 - 8) + 'px', tf: 'none', style: 'color: #5F6368' });
      } else if (typeof b === 'number') {
        const skip = b !== a + 1;
        skPaths.push({ d: ribbon(cx(a), P.a0, P.b0, cx(b), P.a1, P.b1), fill: skip ? '#DADCE0' : FWDC[raw[a][3]], op });
        if (skip && label) skLabels.push({ txt: `${fmt(n)} ${label}`, left: pc((cx(a + 1) + cx(b - 1)) / 2), top: r1((P.a1 + P.b1) / 2 - 8) + 'px', tf: 'translateX(-50%)', style: 'color: #3C4043; font-weight: 500' });
      } else {
        const kk = raw[a][3] === 'natural' ? 'quit' : raw[a][3]; const ek = EXC[kk] ? kk : 'quit';
        const xe = cx(a) + colW * (k === 'other' ? 0.64 : 0.36);
        const h = P.b0 - P.a0;
        const w2 = Math.max(1.2, h * 0.4);
        const x0 = cx(a);
        skPaths.push({ d: `M${r1(x0)},${r1(P.a0)} C${r1(xe + w2)},${r1(P.a0)} ${r1(xe + w2)},${r1(P.a0)} ${r1(xe + w2)},${exitY} L${r1(xe - w2)},${exitY} C${r1(xe - w2)},${r1(P.b0)} ${r1(xe - w2)},${r1(P.b0)} ${r1(x0)},${r1(P.b0)} Z`, fill: EXC[ek][0], op: hot ? 1 : 0.7 });
        const bw = Math.max(8, h);
        skRects.push({ left: `calc(${pc(xe)} - ${r1(bw / 2)}px)`, w: r1(bw) + 'px', top: exitY + 'px', h: '6px', fill: EXC[ek][1], ring: '' });
        skLabels.push({ txt: `${fmt(n)} left`, left: pc(xe), top: (exitY + 10) + 'px', tf: 'translateX(-50%)', style: `color: ${EXC[ek][2]};` + (hot ? ' font-weight: 500;' : '') });
      }
    });
    raw.forEach(([name, , , ck], i) => {
      const h = Math.max(3, nodeV[i] * skS);
      skRects.push({ left: `calc(${pc(cx(i))} - 6px)`, w: '12px', top: Y0 + 'px', h: r1(h) + 'px', fill: NODEC[ck], ring: i === ps ? 'box-shadow: 0 0 0 2px #FFFFFF, 0 0 0 4px #1A73E8;' : '' });
      if (ck === 'done') skLabels.push({ txt: 'completed', left: pc(cx(i)), top: r1(Y0 + h + 6) + 'px', tf: 'translateX(-50%)', style: 'color: #137333; font-weight: 500' });
    });
    const sk = {
      h: skH + 'px', vb: `0 0 1000 ${skH}`, paths: skPaths, rects: skRects, labels: skLabels,
      aria: 'Flow of sessions: ' + F.filter((f) => f[0] !== 'start').map(([a, b, n]) => `${raw[a][0]} to ${typeof b === 'number' ? raw[b][0] : 'left the app'} ${fmt(n)}`).join('; ') + '. Use the table view for exact numbers.'
    };
    const hasBypass = F.some((f) => f[3] === 'skip');

    // ---------- Back-and-forth ----------
    const arcMax = Math.max(1, ...JD.arcs.map((a) => a[2]));
    const arcs = JD.arcs.map(([from, to, n, color]) => {
      const w = Math.max(3, Math.round(n / arcMax * 12));
      const touches = from === ps || to === ps;
      return { left: pc(cx(to)), width: ((cx(from) - cx(to)) / 10).toFixed(2) + '%', color: touches ? color : '#DADCE0', anim: touches && color === '#D93025' ? 'sq-back-arc-red' : '', w: w + 'px', h: Math.round(48 + n / arcMax * 52) + 'px', n, labelTop: (-24 - w) + 'px' };
    });
    const arcsAria = JD.arcs.length ? 'Loops: ' + JD.arcs.map(([from, to, n]) => `${raw[from][0]} back to ${raw[to][0]} ${n}`).join(', ') + '.' : 'No loops in this journey in this range.';
    const dots = raw.map((_, i) => ({ x: pc(cx(i)), fill: i === ps ? '#1A73E8' : '#FFFFFF', stroke: i === ps ? '#1A73E8' : '#9AA0A6' }));
    const redTile = 'border-color: #F6AEA9; background: #FFFBFA;';
    const biggest = Math.max(0, ...JD.loops.map((l) => l.count));
    const loopOut = JD.loops.filter((l) => l.from === ps).sort((a, b) => b.count - a.count)[0];
    const loopsIn = JD.loops.filter((l) => l.to === ps);
    const inN = loopsIn.reduce((t, l) => t + l.count, 0);
    const inFrom = loopsIn.sort((a, b) => b.count - a.count)[0];
    const arcColor = (l) => (l.kind === 'pos' ? '#1E8E3E' : (JD.steps[l.from].tone === 'critical' ? '#D93025' : '#F9AB00'));
    const t1 = loopOut
      ? { label: 'Loop out of this step', title: `${raw[loopOut.from][0]} → ${raw[loopOut.to][0]}`, num: '· ' + loopOut.count, hot: arcColor(loopOut) === '#D93025',
          sub: (loopOut.kind === 'pos' ? 'Good: comparing options, not friction' : (arcColor(loopOut) === '#D93025' ? 'Bad: out of a critical step' + (loopOut.count === biggest ? ', the biggest loop in the journey' : '') : 'Bad: frustrated loop')) + (inN ? ` · ${inN} came back here from ${raw[inFrom.from][0]}` : '') }
      : { label: 'Loops at this step', title: inN ? `${inN} came back here from ${raw[inFrom.from][0]}` : 'No loops at this step', num: '', sub: inN ? `No loops out of ${raw[ps][0]}` : 'Nobody went back from or to this step in this range' };
    const bw = JD.backWho[ps];
    const t2 = bw && bw.v > 0
      ? { label: 'Who goes back most here', title: bw.label, num: '· ' + bw.v.toFixed(1) + '%', hot: bw.overall != null && bw.v >= bw.overall * 2 && bw.v >= 3, sub: bw.overall != null ? `vs ${bw.overall.toFixed(1)}% for everyone at ${raw[ps][0]}` + (bw.overall > 0 && bw.v / bw.overall >= 1.5 ? ` · ${(bw.v / bw.overall).toFixed(1)}×` : '') : '' }
      : { label: 'Who goes back most here', title: 'No one', num: bw ? '· 0%' : '', sub: bw ? `Going back isn't the issue at ${raw[ps][0]}` : '' };
    const bfTiles = [t1, t2].map((t) => ({ ...t, style: t.hot ? redTile : '', numStyle: t.hot ? 'color: #C5221F' : '' }));
    const DARK = { '#D93025': '#C5221F', '#F9AB00': '#B06000', '#1E8E3E': '#137333' };
    const marcs = JD.arcs.map(([from, to, n, color]) => {
      const w = Math.max(2, Math.round(n / arcMax * 8));
      const touches = from === ps || to === ps;
      return { left: pc(cx(to)), width: ((cx(from) - cx(to)) / 10).toFixed(2) + '%', h: Math.round(26 + n / arcMax * 48) + 'px', w: w + 'px', color: touches ? color : '#E8EAED', txt: touches ? DARK[color] : '#9AA0A6', n, labelTop: (-10 - w) + 'px' };
    });
    const posLoop = JD.loops.filter((l) => l.kind === 'pos').sort((a, b) => b.count - a.count)[0];
    const good = posLoop
      ? { title: `${raw[posLoop.from][0]} → ${raw[posLoop.to][0]} · ${posLoop.count}`, sub: 'People compare options before going on. Leave this alone.' }
      : { title: 'No comparison loops in this journey', sub: 'Expected: they show up in shopping journeys, like price checks' };
    const goodHere = JD.arcs.some(([from, to, , color]) => color === '#1E8E3E' && (from === ps || to === ps));
    const mTiles = bfTiles.concat(goodHere ? [{ label: 'Good friction', title: good.title, num: '', sub: good.sub, style: 'border-color: #CEEAD6; background: #F6FBF7;', numStyle: '' }] : []);
    const loopTotal = JD.loops.reduce((t, l) => t + l.count, 0);

    // ---------- By user group ----------
    const gridNames = JD.gridIdx.map((i) => raw[i][0]);
    const META = {
      exit: { label: 'Exit rate', name: 'exit at this step', cuts: [3, 8, 14, 25] },
      taps: { label: 'Repeated taps', name: 'repeated taps', cuts: [1, 3, 5, 7] },
      back: { label: 'Going back', name: 'going back and forth', cuts: [1, 2, 4, 6] },
      dead: { label: 'Dead taps', name: 'taps that did nothing', cuts: [1, 2, 4, 6] },
      stuck: { label: 'Stuck >30s', name: 'stuck over 30 seconds', cuts: [3, 8, 14, 20] }
    };
    const M = META[metric] || META.exit;
    const rows = JD.D[metric] || JD.D.exit;
    const scaleC = ['#F1F3F4', '#D2E3FC', '#AECBFA', '#669DF6', '#1967D2'];
    const focusRow = JD.gridIdx.indexOf(focus);
    const segCol = I.personaId ? JD.personaIds.indexOf(I.personaId) : -1;
    // In compare mode (2+ selected groups, see data-journeys.js), bold the worst-performing group per
    // row and spell out the gap, so a comparison reads as a contrast instead of a flat table of numbers.
    const grid = rows.map((vals, r) => {
      const cells = vals.map((v, c) => {
        const hit = r === focusRow && c === segCol;
        if (v === null) return { v: 'few', bg: '#FFFFFF', fg: '#5F6368', ring: '', raw: null };
        let k = 0; while (k < M.cuts.length && v >= M.cuts[k]) k++;
        return { v: v.toFixed(1) + '%', bg: scaleC[k], fg: k >= 3 ? '#FFFFFF' : '#202124', ring: hit ? 'font-weight: 700; outline: 2px solid #202124; outline-offset: -4px; border-radius: 6px' : '', raw: v };
      });
      let contrast = '';
      if (JD.isCompareMode) {
        const valid = cells.map((c, i) => ({ i, v: c.raw })).filter((x) => x.v != null);
        if (valid.length >= 2) {
          valid.sort((a, b) => b.v - a.v);
          const hi = valid[0], lo = valid[valid.length - 1];
          if (hi.v > lo.v) {
            cells[hi.i].ring += (cells[hi.i].ring ? ' ' : '') + 'box-shadow: inset 0 0 0 2px #1967D2; font-weight: 700;';
            contrast = JD.personaCols[hi.i] + ' highest · +' + (hi.v - lo.v).toFixed(1) + ' pts vs ' + JD.personaCols[lo.i];
          }
        }
      }
      return { name: gridNames[r], nameStyle: r === focusRow ? 'box-shadow: inset 4px 0 0 #1A73E8; color: #174EA6' : '', cells, contrast, hasContrast: !!contrast };
    });
    const on = 'background: #E8F0FE; color: #174EA6;';
    const metrics = Object.keys(META).map((k) => ({ label: META[k].label, sel: metric === k ? 'true' : 'false', fk: 'metric-' + k, style: metric === k ? on : '', pick: () => upd({ metric: k }) }));
    const more = ISSUES.length - 4;

    // ---------- Transaction completion by product (whole sample) ----------
    const PC = SQ.productCompletion();
    const CAUSEWHY = { technical: 'after an error or a tap that did nothing', language: 'stuck on the wording', ux: 'after going back a step', natural: 'mostly browsing' };
    const products = PC.rows.map((r) => {
      const pct = r.completion * 100;
      const low = r.completion < PC.avg - 0.095;
      return {
        name: r.label, sessions: fmt(r.sessions), pct: pct.toFixed(0) + '%', w: pct.toFixed(1) + '%',
        where: r.worst ? `${r.worst.name} (${(r.worst.exit_rate * 100).toFixed(1)}%), ${CAUSEWHY[r.worst.exit_class] || 'no clear cause'}` : '',
        color: low ? '#D93025' : '#8AB4F8', pctStyle: low ? 'font-weight: 500; color: #C5221F' : ''
      };
    });

    const crumb = this.state.from ? ' · opened from ' + this.state.from : '';
    const infoFlowOpen = !!this.state.infoFlowOpen, infoLoopsOpen = !!this.state.infoLoopsOpen;

    return {
      infoFlowOpen, infoFlowStr: infoFlowOpen ? 'true' : 'false', toggleInfoFlow: () => upd({ infoFlowOpen: !infoFlowOpen }),
      infoLoopsOpen, infoLoopsStr: infoLoopsOpen ? 'true' : 'false', toggleInfoLoops: () => upd({ infoLoopsOpen: !infoLoopsOpen }),
      jtabs, crumb, keepText: JD.keepText, hasKeep: !!JD.keepText, topName: ISSUES[0].short,
      cols: `repeat(${nSteps}, minmax(0, 1fr))`, hasBypass, arcsAria, good,
      strip, issues, hero, vis, replay,
      formFields: ['38%', '46%', '30%', '52%'], formFields3: ['42%', '56%', '34%'],
      extraSel: cur >= 4, listOpen, listOpenStr: listOpen ? 'true' : 'false',
      moreLabel: listOpen ? 'Hide list' : (more > 0 ? `+${more} more` : 'See as list'),
      toggleList: () => upd({ listOpen: !listOpen }),
      goTop: () => pick(0),
      nodes, bypass: null, sel, arcs, dots, bfTiles, sk, marcs, mTiles,
      merged, notMerged: !merged, showMTiles: merged && mTiles.length > 0,
      journeyEmpty: !!JD.noJourneyData,
      emptyNote: 'Not enough ' + JD.name.toLowerCase() + ' sessions in this scope for a step-by-step view. Try a wider date range or All users.',
      isChart: view === 'chart' && !JD.noJourneyData, isTable: view === 'table' && !JD.noJourneyData,
      chartPressed: view === 'chart' ? 'true' : 'false', tablePressed: view === 'table' ? 'true' : 'false',
      chartBtn: view === 'chart' ? on : '', tableBtn: view === 'table' ? on : '',
      showChart: () => upd({ view: 'chart' }), showTable: () => upd({ view: 'table' }),
      tableCaption: `${JD.name}, ${SQ.rangeDates()} · ${SQ.personaLabel(SQ.scope.persona)}`,
      loopsNote: `${fmt(loopTotal)} backward moves, ${SQ.RANGES[SQ.scope.range].short.toLowerCase()}`,
      metrics, grid, metricName: M.name, personaCols: JD.personaCols.map((label) => ({ label })), hasGrid: grid.length > 0,
      isCompareMode: JD.isCompareMode, notCompareMode: !JD.isCompareMode, compareNames: SQ.personaLabel(SQ.scope.persona),
      products, productNote: 'Counted over the whole sample, not filtered by the scope bar. Red marks products 9.5 points or more below the average of ' + (PC.avg * 100).toFixed(0) + '%.'
    };
  }
}
return Component;
});
