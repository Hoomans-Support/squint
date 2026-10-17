SQ.define("Audiences", function (DCLogic) {
class Component extends DCLogic {
  renderVals() {
    const M = SQ.audienceModel();
    const item = M.topInsightId && SQ.problems().find((p) => p.id === M.topInsightId);
    const rank = item ? item.__p : 'Linked finding';
    const copy = () => {
      const text = `${M.topTitle}. ${M.topStates.map((s) => `${s.label}: ${s.people}`).join('; ')}. Synthetic sample data.`;
      const done = (ok) => { this.setState({ copied: !!ok, copyFailed: !ok }); setTimeout(() => SQ.refocus && SQ.refocus('audience-copy'), 0); };
      const fallbackCopy = () => {
        const field = document.createElement('textarea');
        field.value = text; field.readOnly = true; field.style.position = 'fixed'; field.style.opacity = '0';
        document.body.append(field); field.select();
        let ok = false;
        try { ok = document.execCommand('copy'); } catch (_) { ok = false; }
        field.remove(); done(ok);
      };
      if (!navigator.clipboard || !navigator.clipboard.writeText) { fallbackCopy(); return; }
      navigator.clipboard.writeText(text).then(() => done(true), fallbackCopy);
    };
    const openJourney = () => { SQ.state.journeyInsight = M.topInsightId; SQ.go('Journeys'); };
    const copyMessage = this.state.copied ? "Summary copied." : this.state.copyFailed ? "Copy is unavailable here." : "";
    return {
      ...M, rank, copyMessage, copy, openJourney,
      repeatHelp: 'How to read: of the buyers in the last 14 days, how many completed-purchase events each had. Longer bars toward "4 or more" mean more repeat buyers.'
    };
  }
}
return Component;
});
