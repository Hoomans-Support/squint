SQ.define("AskFlow1", function (DCLogic) {
class Component extends DCLogic {
  renderVals() {
    const A = SQ.ask;
    const q = this.state.q ?? (typeof SQ.state.askQuestion === 'string' ? SQ.state.askQuestion : '');
    const submit = (text) => { if (String(text || '').trim()) A.ask(text); };
    const link = (fn) => (e) => { if (e && e.preventDefault) e.preventDefault(); fn(); };
    const day = (t) => { const d = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(t).setHours(0, 0, 0, 0)) / 864e5); return d <= 0 ? 'Today' : d === 1 ? 'Yesterday' : d + ' days ago'; };
    const hist = A.threads().slice(0, 3).map((t) => { const c = A.threadChip(t); return { title: t.title, scope: c.scope, problem: c.problem, hasProblem: !!c.problem, when: day(t.at), open: link(() => { A.open(t.id); SQ.go('Ask'); }) }; });
    const top = SQ.problems()[0];
    const from = A.fromLabel();
    return {
      q, hasQ: q.trim().length > 0,
      onInput: (e) => { this.state.q = e.target.value; SQ.redraw(); A.focus('q1', true); },
      onKey: (e) => { if (e.key === 'Enter') submit(e.target.value); },
      go: () => submit(q), goLink: link(() => submit(q)),
      from, hasFrom: !!from, scopeChip: 'Sample data \u00b7 up to ' + SQ.asOf(),
      hist, hasHist: hist.length > 0,
      suggest: A.suggestions(null).slice(0, 3).map((text) => ({ q: text, go: link(() => submit(text)) })),
      headline: top ? A.headline(top).text : 'Nothing needs attention this week'
    };
  }
}
return Component;
});
