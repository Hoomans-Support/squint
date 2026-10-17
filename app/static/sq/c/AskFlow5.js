SQ.define("AskFlow5", function (DCLogic) {
class Component extends DCLogic {
  renderVals() {
    const A = SQ.ask;
    const deck = A.deck();
    const all = deck.slides;
    const cur = Math.min(this.state.cur ?? 0, all.length - 1);
    const on = (s) => !A.off[s.key];
    const slides = all.map((s, i) => ({
      ...s, include: on(s), on: cur === i ? 'true' : 'false',
      style: cur === i ? 'background: #E8F0FE; border-color: #AECBFA;' : '',
      pick: () => this.setState({ cur: i }),
      toggle: (e) => { A.off[s.key] = !e.target.checked; if (s.key === 'app') A.appendix = e.target.checked; SQ.redraw(); }
    }));
    const chosen = all.filter(on);
    const s = all[cur] || {};
    const sel = {
      ...s,
      body: s.isSummary ? s.summaryLine : s.why,
      hasAI: /AI/.test(s.whyTag || ''),
      bars: s.bars || []
    };
    const fmts = [['pdf', 'PDF (print the slides)'], ['md', 'Text (.md, copy of the slides)']];
    const formats = fmts.map(([id, label]) => ({
      label, checked: A.fmt === id, style: A.fmt === id ? 'border-color: #1A73E8; background: #F8FBFF' : '',
      pick: () => { A.fmt = id; SQ.redraw(); }
    }));
    const n = chosen.length;
    // the print deck reuses the full-size slide component, numbered by position among the chosen slides
    return {
      slides, sel, formats, deckLabel: deck.title + ' · ' + (deck.models.length === 1 ? '1 answer' : deck.models.length + ' answers'),
      formatHint: A.fmt === 'pdf' ? 'Opens your browser’s print dialog: choose Save as PDF.' : 'Downloads a plain Markdown file you can paste into any slide tool.',
      appendixOn: !A.off.app, notesOn: A.notes,
      toggleAppendix: (e) => { A.off.app = !e.target.checked; A.appendix = e.target.checked; SQ.redraw(); },
      toggleNotes: (e) => { A.notes = e.target.checked; SQ.redraw(); },
      footNote: deck.note || 'This chat is private. The deck is a copy: anyone you share it with sees these numbers. Sample data (synthetic).',
      noneOn: n === 0,
      exportLabel: 'Export ' + n + (n === 1 ? ' slide' : ' slides'),
      doExport: () => {
        if (!n) return;
        if (A.fmt === 'pdf') { try { window.print(); } catch (_) { /* print not available */ } } else A.download('squint-slides.md', A.deckText(deck, chosen), 'text/markdown');
      },
      printSlides: chosen.map((x) => ({ n: x.n }))
    };
  }
}
return Component;
});
