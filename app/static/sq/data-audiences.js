/* Audience and data-source view models from the additive ui-v3 results blocks. */
(function () {
  'use strict';
  const SQ = window.SQ;
  const pct = (v) => v == null ? 'Not enough history' : (Number(v) * 100).toFixed(1).replace(/\.0$/, '') + '%';
  const n = (v) => SQ.fmt(v);
  const palette = {
    win_back: ['Win back', '#E8F0FE', '#174EA6'],
    target: ['Target', '#FEF7E0', '#B06000'],
    keep: ['Keep', '#E6F4EA', '#137333'],
    protect: ['Protect', '#F1F3F4', '#3C4043']
  };
  SQ.audienceModel = () => {
    const root = SQ.data.audiences;
    const A = root.scopes && root.scopes[SQ.scope.platform + '|' + SQ.scope.persona];
    if (!A) throw new Error('Missing Audiences results for scope ' + SQ.scope.platform + '|' + SQ.scope.persona);
    const rangeWinBack = (A.win_back.by_range || {})[SQ.scope.range];
    const visibleInsightIds = new Set(SQ.view().insight_ids);
    const visibleCandidates = (A.win_back.by_insight || []).filter((candidate) => visibleInsightIds.has(candidate.insight_id) && candidate.people > 0);
    const winBack = rangeWinBack || (visibleCandidates.length ? { ...A.win_back, top: visibleCandidates[0] } : A.win_back);
    const top = winBack.top;
    const states = top.states.map((s, i) => ({
      label: s.label, people: n(s.people), width: (s.share * 100).toFixed(2) + '%',
      color: ['#1A73E8', '#F9AB00', '#1E8E3E'][i] || '#5F6368'
    }));
    // the featured "Top audience to act on" card is drawn from the same win-back pick as one of A.cards;
    // drop that duplicate from the grid below so every card there is a distinct audience.
    const cards = A.cards.filter((c) => !top.insight_id || c.insight_id !== top.insight_id).map((c) => {
      const [verb, bg, fg] = palette[c.kind] || ['Audience', '#F1F3F4', '#3C4043'];
      return {
        kind: c.kind, verb, bg, fg, title: c.title, basis: c.basis, action: c.action,
        people: n(c.size.people), share: pct(c.size.share),
        tag: c.source === 'ai_idea' ? 'AI idea' : 'Calculated', ai: c.source === 'ai_idea', tagClass: c.source === 'ai_idea' ? 'tag tag-ai' : 'chip',
        fill: c.size.people ? Math.max(3, Math.min(100, c.size.share * 100)).toFixed(1) + '%' : '0%',
        minWidth: c.size.people ? Math.max(3, Math.min(100, c.size.share * 100)).toFixed(1) + '%' : '0%'
      };
    });
    const cardGroups = Object.keys(palette).map((kind) => ({
      kind, verb: palette[kind][0], cards: cards.filter((card) => card.kind === kind)
    })).filter((group) => group.cards.length > 0);
    const rv = A.signals.return_visits;
    // once the scope is already narrowed to one named persona, every other group has 0 people here
    // by construction (this block only holds that persona's own sessions) — drop empty rows instead
    // of a wall of "Not enough history" placeholders for groups that aren't in view at all.
    const groupRows = rv.d1.by_group.filter((g) => g.people > 0).map((g) => ({
      name: g.label, people: n(g.people), value: pct(g.rate),
      width: Math.max(0, Math.min(100, (g.rate || 0) * 100)).toFixed(1) + '%'
    })).sort((a, b) => parseFloat(b.value) - parseFloat(a.value));
    const r14 = A.signals.repeat_purchases.last_14_days;
    const repeat = r14.buckets.map((b) => ({ label: b.label, people: n(b.people), share: pct(b.share), width: (b.share || 0) * 100 + '%' }));
    const segColor = { straight_through: '#1E8E3E', high_value_topup: '#1A73E8', stalled_otp: '#F9AB00', load_first: '#5F6368', shared_device: '#8AB4F8', not_grouped: '#DADCE0' };
    // a segment with nobody in it in this scope is not an audience to show; a "0%" legend entry
    // reads as broken, not as "none" - drop it instead of printing a figure with nothing behind it.
    const segments = A.segments.items.filter((s) => s.people > 0).map((s) => ({
      label: s.label, people: n(s.people), share: s.pct + '%', width: (s.share || 0) * 100 + '%',
      color: segColor[s.id] || '#5F6368'
    }));
    const d = (days, key, i) => ({ days, label: days + (days === 1 ? ' day' : ' days'), rate: pct(rv[key].rate), height: rv[key].rate == null ? '0px' : (rv[key].rate * 96).toFixed(1) + 'px', color: ['#8AB4F8', '#669DF6', '#1A73E8'][i] });
    return {
      total: n(A.active_users), topPeople: n(top.people), topScreen: top.screen_label, topInsightId: top.insight_id,
      topTitle: top.title, topAdvice: top.advice, topStates: states,
      cards, cardGroups, groupRows, returns: [d(1, 'd1', 0), d(7, 'd7', 1), d(30, 'd30', 2)],
      returnNote: rv.note,
      repeat, repeatBuyers: n(r14.buyers),
      segments, ungrouped: segments.find((s) => s.label === 'Not yet grouped') || null,
      gaps: A.gaps.map((g) => g.reason)
    };
  };
  SQ.dataSourceModel = () => {
    const D = SQ.data.data_sources, connected = D.connected, h = D.health;
    const colors = { ready: ['Ready', '#E6F4EA', '#137333'], available: ['Available', '#E8F0FE', '#174EA6'], partial: ['Partial', '#FEF7E0', '#B06000'], needs_backend: ['Needs backend', '#F1F3F4', '#3C4043'], later: ['Later', '#FFFFFF', '#5F6368'] };
    const signals = D.signals.map((s) => { const [status, bg, fg] = colors[s.status]; return { name: s.name, source: s.source, use: s.used_for, note: s.note, status, bg, fg }; });
    const change = h.event_volume.change;
    const silent = (h.trackers.silent || []).map((s) => s.title).join('; ');
    const app = connected.app_tracker, steps = connected.journey_steps, match = h.events_matched;
    const tables = D.backend_sample.tables.map((t) => ({ name: t.table, rows: n(t.rows), description: t.description }));
    const unmappedFault = ((SQ.data.guardian || {}).faults || []).find((f) => f.guardian_kind === 'unmapped');
    const unmappedProp = unmappedFault ? unmappedFault.title.replace(/^Unmapped property /, '') : null;
    const unmappedSince = unmappedFault && unmappedFault.start ? new Date(unmappedFault.start).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : null;
    const health = [
      { label: 'Event volume', value: (change > 0 ? '+' : '') + (change * 100).toFixed(1) + '%', note: 'vs ' + h.event_volume.compared_with, color: '#1E8E3E' },
      { label: 'Events matched', value: pct(match.share), note: n(match.unmatched_events) + ' events need review', color: '#1E8E3E' },
      { label: 'Trackers firing', value: h.trackers.firing + ' of ' + h.trackers.total, note: silent || 'All tracked signals are firing', color: h.trackers.firing < h.trackers.total ? '#F9AB00' : '#1E8E3E' },
      { label: 'Sessions set aside', value: n(h.sessions_set_aside), note: 'inside a tracking fault', color: '#F9AB00' }
    ];
    return {
      signals, health, tables, appEvents: n(app.events), appSessions: n(app.sessions), appUsers: n(app.users),
      stepsMatched: steps.matched, stepsTotal: steps.total, stepsReview: steps.to_review,
      synthetic: D.synthetic && app.synthetic && D.backend_sample.synthetic,
      dataset: app.dataset, tableDataset: D.backend_sample.dataset, location: D.backend_sample.location,
      locked: signals.filter((s) => s.status === 'Needs backend').length,
      eventsMatchedPct: pct(match.share), eventsUnmatched: n(match.unmatched_events),
      eventsTotal: n(match.events), eventsMatched: n(match.events - match.unmatched_events),
      unmappedProp, unmappedSince
    };
  };
})();
