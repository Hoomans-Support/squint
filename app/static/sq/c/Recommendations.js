SQ.define("Recommendations", function (DCLogic) {
class Component extends DCLogic {
  renderVals() {
    const A = SQ.ask;
    A.ensureBriefAiStatus();
    const b = A.brief();
    b.noTodo = !b.hasTodo; b.noKeep = !b.hasKeep;
    const comparisonActive = SQ.personaIds().length > 1 && !!SQ.state.personaComparisonMode;
    return {
      b,
      rewriteLabel: b.rewriting ? 'Rewriting…' : (b.aiRewritten ? 'Rewrite again' : 'Rewrite with Gemini'),
      doRewrite: () => A.rewriteBrief(b.rewriteIds, b.aiRewritten),
      useStandard: () => A.useStandardBrief(),
      showCombo: b.comboN > 1 && !!b.topWho,
      comparisonMode: comparisonActive ? 'true' : 'false',
      notComparisonMode: !comparisonActive,
      comparisonMessage: comparisonActive ? `Comparing ${SQ.personaLabel(SQ.scope.persona)} below.` : `Showing combined results for ${b.comboN} groups. The top finding is specific to ${b.topWho}.`,
      comparisonAction: comparisonActive ? 'Exit comparison mode' : 'Comparison mode',
      toggleComparison: () => { SQ.state.personaComparisonMode = !comparisonActive; SQ.redraw(); },
      viewTopOnly: () => SQ.setScope({ persona: b.topPersonaId || (String(b.topWho || '').toLowerCase().includes('all users') ? 'all' : SQ.scope.persona) }),
      copyText: () => A.copy(b.text, 'brief'), copyLabel: A.copied === 'brief' ? 'Copied' : 'Copy text',
      printPage: () => { try { window.print(); } catch (_) { /* print not available */ } }
    };
  }
}
return Component;
});
