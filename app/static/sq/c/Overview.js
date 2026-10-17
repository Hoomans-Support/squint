SQ.define("Overview", function (DCLogic) {
class Component extends DCLogic {
  renderVals() {
    const sc = SQ.scope;
    const view = SQ.view();
    const probs = SQ.problems().filter((i) => !SQ.settings.alertsCriticalOnly || i.severity === 'critical');
    const recs = probs.map((i) => SQ.problemRec(i));
    const critCount = probs.filter((i) => i.severity === 'critical').length;
    const period = { '24h': ['Today', 'today'], '7d': ['This week', 'this week'], '30d': ['This month', 'this month'] }[sc.range] || ['This week', 'this week'];

    // ticket draft shows inline, right under the button that opened it (no drawer, no route change);
    // only one open at a time, same as the "other problems" row expand/collapse above it
    const ticketOpenId = this.state.ticketOpenId || null;
    const toggleTicket = (id, triggerFk) => () => {
      const opening = ticketOpenId !== id;
      this.setState({ ticketOpenId: opening ? id : null, copied: '' });
      SQ.refocus(opening ? 'ticket-' + id : triggerFk);
    };
    const ticketCard = (id, triggerFk) => {
      const ins = SQ.insight(id);
      const c = SQ.ticketCardModel(ins);
      return {
        ...c, ticketOpen: ticketOpenId === id, ticketClosed: ticketOpenId !== id, toggleTicket: toggleTicket(id, triggerFk),
        copy: () => {
          let ok = false;
          const done = (v) => this.setState({ copied: v ? 'Copied to the clipboard' : 'Copy is blocked here. Select the text and copy it by hand.' });
          try { navigator.clipboard.writeText(c.ticket).then(() => done(true), () => done(false)); ok = true; } catch (e) { /* fall through */ }
          if (!ok) done(false);
        },
        download: () => this.setState({ copied: SQ.downloadText(c.ticketFile, c.ticket) ? 'Downloaded ' + c.ticketFile : 'The download is blocked here.' }),
        copied: this.state.copied || '', hasCopied: !!this.state.copied
      };
    };
    const journeys = (id) => () => { SQ.state.journeyInsight = id; };
    const askAI = (id) => () => {
      const entry = SQ.ask.entryForInsight(id);
      const ins = SQ.insight(id);
      SQ.ask.ask(entry ? entry.question : ins ? SQ.ask.headline(ins).text : 'Tell me about this finding');
    };

    // ---- the takeaway: the worst open problem in this scope ----
    const t = recs[0] || null;
    const top = t && {
      ...t,
      hasCtx: !!t.ctx,
      title: 'Problem 1 of ' + recs.length + ' in this scope',
      valueStyle: t.valueNa ? 'color: #5F6368' : '',
      valueSuffix: t.valueNa ? ' at risk, not priced' : ' at risk each week',
      c1: t.confN >= 1 ? '#1A73E8' : '#DADCE0', c2: t.confN >= 2 ? '#1A73E8' : '#DADCE0', c3: t.confN >= 3 ? '#1A73E8' : '#DADCE0',
      hasFact: !!t.topFact,
      hasWhy: !!t.why,
      evidenceNum: t.statText,
      evidenceCap: t.fact0 || (t.hasBase ? 'baseline ' + t.baseLabel : 'no baseline for this step'),
      peopleTitle: 'Sessions affected, ' + period[1],
      ticket: ticketCard(t.id, 'top-draft'), journeys: journeys(t.id), askAI: askAI(t.id)
    };

    // ---- KPI row: from view.kpis, deltas vs the previous comparable period ----
    const kpi = (id) => view.kpis.find((k) => k.id === id);
    const arrowGood = (k, d) => (d === 0 ? '#5F6368' : ((d > 0) === !!k.higher_is_better ? '#5F6368' : '#C5221F'));
    const conv = kpi('conversion'), risk = kpi('value_at_risk');
    const kpis = [];
    if (conv) {
      const d = conv.prev == null ? null : Math.round((conv.value - conv.prev) * 10) / 10;
      kpis.push({
        label: conv.label, value: SQ.pct1(conv.value), unit: '',
        hasDelta: d !== null, delta: d === null ? '' : (d > 0 ? '+' : d < 0 ? '−' : '') + Math.abs(d).toFixed(1) + ' pts', deltaColor: d === null ? '#5F6368' : arrowGood(conv, d),
        base: 'vs ' + SQ.pct1(conv.prev) + ' ' + (conv.prev_label || 'before'), title: conv.sub || ''
      });
    }
    if (risk) {
      const d = risk.prev == null ? null : risk.value - risk.prev;
      kpis.push({
        label: 'Total value at risk', value: SQ.money(risk.value), unit: ' per week',
        hasDelta: d !== null, delta: d === null ? '' : d === 0 ? 'no change' : (d > 0 ? '+' : '−') + SQ.money(Math.abs(d)), deltaColor: d === null ? '#5F6368' : arrowGood(risk, d),
        base: 'vs ' + SQ.money(risk.prev) + ' ' + (risk.prev_label || 'before'), title: ''
      });
    }
    kpis.push({
      label: 'Open problems', value: String(probs.length), unit: '',
      hasDelta: true, delta: critCount + ' critical', deltaColor: '#5F6368',
      base: 'of ' + view.insight_ids.length + ' findings checked', title: 'Open problems and findings in this scope'
    });

    // ---- one-line overall trend vs the previous comparable period, shown under the KPI row ----
    const trendNote = (() => {
      if (!conv || conv.prev == null) return '';
      const d = Math.round((conv.value - conv.prev) * 10) / 10;
      const label = conv.prev_label || 'the previous period';
      if (d === 0) return 'Conversion is flat vs ' + label + '.';
      const dir = (d > 0) === !!conv.higher_is_better ? 'improving' : 'slipping';
      return 'Conversion is ' + dir + ' ' + Math.abs(d).toFixed(1) + ' pts vs ' + label + '.';
    })();

    const tr = SQ.trust();
    const trust = {
      color: tr.color, label: tr.ok ? 'Data reliable' : tr.label.replace(/^Data: /, ''),
      line: tr.line.replace(/ ·$/, ''), strong: tr.ok ? 'Data reliable' : tr.label
    };

    // ---- other problems ----
    const openId = this.state.openId || null;
    const rows = recs.slice(1).map((p) => {
      const open = openId === p.id;
      const bars = [1, 2, 3].map((n) => (n <= p.confN ? '#1A73E8' : '#DADCE0'));
      return {
        ...p,
        c1: bars[0], c2: bars[1], c3: bars[2],
        valueStyle: p.valueNa ? 'color: #5F6368' : 'font-weight: 500',
        hasCtx: !!p.ctx, hasWhy: !!p.why,
        open, closed: !open, openStr: open ? 'true' : 'false', openBg: open ? 'background: #FAFBFF;' : '',
        fk: 'row-' + p.id,
        toggle: () => { this.setState({ openId: open ? null : p.id }); SQ.refocus('row-' + p.id); },
        ticket: ticketCard(p.id, 'row-draft-' + p.id), journeys: journeys(p.id), askAI: askAI(p.id)
      };
    });

    // ---- why people leave: view.exits by cause class ----
    const ex = view.exits || null;
    const defs = [
      { key: 'technical', name: 'Bug', label: 'Technical bug', color: '#D93025' },
      { key: 'language', name: 'Wording', label: 'Confusing wording', color: '#1A73E8' },
      { key: 'ux', name: 'UX', label: 'UX friction', color: '#F9AB00' },
      { key: 'natural', name: 'Natural', label: 'Natural exit', color: '#BDC1C6' }
    ];
    const total = ex ? defs.reduce((a, d) => a + (ex[d.key] || 0), 0) : 0;
    const parts = defs.map((d) => {
      const n = ex ? (ex[d.key] || 0) : 0, f = total ? n / total : 0;
      return { ...d, n, f, w: (f * 100) + '%', pct: Math.round(f * 100) + '%', isNatural: d.key === 'natural', isCause: d.key !== 'natural' };
    });
    const exits = {
      has: total > 0, none: total === 0,
      total: SQ.fmt(total) + ' exits',
      aria: parts.map((p) => p.label + ' ' + p.pct).join(', '),
      bars: parts.filter((p) => p.n > 0),
      legend: parts
    };

    // ---- also checked: healthy findings and resolved faults ----
    const inView = new Set(view.insight_ids);
    const healthy = SQ.data.insights.filter((i) => i.severity === 'healthy' && inView.has(i.id));
    const checked = healthy.map((i) => ({
      isKeep: true, isRuled: false, id: i.id,
      action: SQ.verbOf(i), item: i.screen_label || i.title, who: SQ.whoOf(i),
      title: (i.facts || [])[0] || SQ.firstSentence((i.diagnosis || {}).summary || i.summary, 140),
      hasLink: i.class === 'behavior_pattern'
    })).concat(((SQ.data.guardian || {}).faults || []).filter((f) => f.status === 'resolved' || f.sev === 'resolved').map((f) => ({
      isKeep: false, isRuled: true, id: f.id, text: 'Ruled out: ' + f.title + ', already fixed', title: f.desc || ''
    })));

    const nOthers = rows.length;

    // ---- combo-scope banner and explicit side-by-side comparison mode ----
    const comboN = sc.persona === 'all' || sc.persona === 'unregistered' ? 1 : sc.persona.split('+').length;
    const isCombo = comboN > 1;
    const topPersonaId = top && probs[0] && probs[0].segment ? probs[0].segment.persona : null;
    const topWho = top ? top.who : '';
    const comparisonMode = isCombo && !!SQ.state.personaComparisonMode;
    const showCombo = isCombo;

    return {
      showCombo, comboN, topWho,
      comparisonMode, notComparisonMode: !comparisonMode,
      comboMessage: comparisonMode ? `Comparing ${SQ.personaLabel(sc.persona)} below.` : `Showing combined results for ${comboN} groups. The top finding is specific to ${topWho || 'one group'}.`,
      comparisonAction: comparisonMode ? 'Exit comparison mode' : 'Comparison mode',
      toggleComparison: () => { SQ.state.personaComparisonMode = !comparisonMode; SQ.redraw(); },
      viewTopOnly: () => SQ.setScope({ persona: topPersonaId || (topWho.toLowerCase().includes('all users') ? 'all' : sc.persona) }),
      period: period[0], periodLower: period[1],
      hasTop: !!top, empty: !top, top,
      calmSub: (sc.persona === 'all' ? 'All users' : SQ.personaLabel(sc.persona)) + ', ' + SQ.RANGES[sc.range].label.toLowerCase() + ': ' + view.insight_ids.length + ' finding' + (view.insight_ids.length === 1 ? '' : 's') + ' checked, none is a problem.',
      kpis, trust, trendNote, hasTrendNote: !!trendNote,
      showOthers: !!top, hasOthers: nOthers > 0, noOthers: nOthers === 0, rows,
      otherTitle: nOthers === 1 ? 'Other problem' : 'Other problems',
      exits, checked, hasChecked: checked.length > 0, noChecked: checked.length === 0
    };
  }
}
return Component;
});
