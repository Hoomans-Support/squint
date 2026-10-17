/* Side-by-side views from already-published per-group synthetic results. */
(function () {
  'use strict';
  const SQ = window.SQ;
  const val = (view, id) => ((view.kpis || []).find((k) => k.id === id) || {}).value;
  SQ.personaComparisonModel = (page) => {
    const ids = SQ.personaIds().filter(Boolean);
    const combo = ids.length > 1;
    const active = combo && !!SQ.state.personaComparisonMode;
    const rows = ids.map((id) => {
      const persona = SQ.personas().find((p) => p.id === id) || { id, label: id };
      const metrics = [];
      let headline = 'No finding in this group';
      let detail = 'No open finding is available for this scope.';
      let nextAction = 'No group-specific issue is available; review the group evidence before assigning a fix.';
      if (page === 'overview' || page === 'brief') {
        const view = SQ.data.views[SQ.scope.range + '|' + SQ.scope.platform + '|' + id];
        if (!view) return { id, label: persona.label, unavailable: true, metrics: [
          { label: 'Register and login completion', value: 'n/a' }, { label: 'Weekly value at risk', value: 'n/a' }, { label: 'Open problems', value: 'n/a' }
        ], headline: 'Comparison unavailable', detail: 'No results for this group and platform.', nextAction: 'No result is available for this group and platform; check the selected scope.', overviewValue: 'n/a', overviewFill: 0, overviewGap: 'No comparison data available', overviewContext: 'Business measures are unavailable.' };
        const conversion = val(view, 'conversion');
        const risk = val(view, 'value_at_risk');
        metrics.push({ label: 'Register and login completion', value: conversion == null ? 'n/a' : Number(conversion).toFixed(1) + '%' });
        metrics.push({ label: 'Weekly value at risk', value: risk == null ? 'n/a' : SQ.money(risk) });
        const problems = (view.insight_ids || []).map((key) => SQ.data.insights.find((i) => i.id === key)).filter((i) => i && i.severity !== 'healthy');
        metrics.push({ label: 'Open problems', value: String(problems.length) });
        const groupProblems = problems.filter((i) => (i.persona_ids || []).includes(id) || (i.segment || {}).persona === id);
        const leading = groupProblems[0];
        if (leading) {
          headline = SQ.verbOf(leading) + ' ' + (leading.screen_label || leading.title);
          detail = SQ.whoOf(leading) + ' · ' + ((leading.facts || [])[0] || 'Finding from this group’s results.');
          const steps = ((leading.diagnosis || {}).next_steps || []).map((s) => typeof s === 'string' ? s : s.text).filter(Boolean);
          nextAction = steps[0] || leading.recommendation || 'Review the finding evidence with the product and engineering owners, then agree on a fix to validate.';
        }
      } else {
        const aud = SQ.data.audiences && SQ.data.audiences.scopes && SQ.data.audiences.scopes[SQ.scope.platform + '|' + id];
        if (!aud) return { id, label: persona.label, unavailable: true, metrics: [
          { label: 'Active people', value: 'n/a' }, { label: 'People to win back', value: 'n/a' }, { label: 'People to target', value: 'n/a' }, { label: 'Returned within a day', value: 'n/a' }
        ], headline: 'Comparison unavailable', detail: 'No audience results for this group and platform.' };
        metrics.push({ label: 'Active people', value: SQ.fmt(aud.active_users) });
        const top = aud.win_back && aud.win_back.top;
        metrics.push({ label: 'People to win back', value: top ? SQ.fmt(top.people) : '0' });
        const target = (aud.cards || []).find((c) => c.kind === 'target');
        metrics.push({ label: 'People to target', value: target ? SQ.fmt(target.size.people) : '0' });
        const returnRate = aud.signals && aud.signals.return_visits && aud.signals.return_visits.d1 && aud.signals.return_visits.d1.rate;
        metrics.push({ label: 'Returned within a day', value: returnRate == null ? 'Not enough history' : (returnRate * 100).toFixed(1) + '%' });
        headline = top ? top.screen_label + ' · ' + SQ.fmt(top.people) + ' people' : 'No win-back group in this scope';
        detail = top ? top.advice : 'No stalled users were counted for this group.';
      }
      const conversionRaw = page === 'overview' || page === 'brief' ? Number(val(SQ.data.views[ SQ.scope.range + '|' + SQ.scope.platform + '|' + id ], 'conversion')) : null;
      return { id, label: persona.label, unavailable: false, metrics, headline, detail, nextAction, conversionRaw };
    });
    const names = SQ.personaLabel(SQ.scope.persona);
    const bestConversion = Math.max(0, ...rows.map((r) => Number.isFinite(r.conversionRaw) ? r.conversionRaw : 0));
    rows.forEach((r) => {
      if (page === 'overview') {
        r.overviewValue = Number.isFinite(r.conversionRaw) ? r.conversionRaw.toFixed(1) + '%' : 'n/a';
        r.overviewFill = bestConversion ? Math.max(0, r.conversionRaw / bestConversion * 100) : 0;
        r.overviewGap = Number.isFinite(r.conversionRaw) && bestConversion > r.conversionRaw ? (bestConversion - r.conversionRaw).toFixed(1) + ' points below the highest group' : 'Highest completion in this selection';
        r.overviewContext = `${r.metrics[2] ? r.metrics[2].value : '0'} open problems · ${r.metrics[1] ? r.metrics[1].value : 'n/a'} weekly value at risk`;
      }
    });
    return {
      visible: combo && (active || page === 'audiences'),
      active, prompt: !active, count: rows.length, names,
      title: page === 'overview' ? 'Group performance at a glance' : (page === 'brief' ? 'Recommendations by group' : 'Audience opportunities by group'),
      rows, overviewMode: page === 'overview', briefMode: page === 'brief', audienceMode: page === 'audiences', showToggle: page === 'audiences',
      promptText: page === 'audiences' ? `Compare audience size and follow-up opportunities across ${names}.` : (page === 'overview' ? `A high-level view of signup health and business impact across ${names}.` : `Group-specific priorities and evidence for ${names}.`),
      activeText: page === 'audiences' ? `Audience sizes and next actions for ${names}.` : (page === 'overview' ? `Signup completion and business impact across ${names}. Open Recommendations for the underlying findings.` : `Priority findings and supporting measures for ${names}.`),
      toggle: () => { SQ.state.personaComparisonMode = !active; SQ.redraw(); }
    };
  };
  const base = SQ.audienceModel;
  SQ.audienceModel = () => ({ ...base(), notComparisonMode: !(SQ.scope.persona.split('+').length > 1 && SQ.state.personaComparisonMode) });
})();
