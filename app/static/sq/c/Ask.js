SQ.define("Ask", function (DCLogic) {
class Component extends DCLogic {
  renderVals() {
    const A = SQ.ask;
    A.consume();                       // a question typed in the top bar, read once
    const D = SQ.data;
    SQ.problems();
    const th = A.cur();
    let historyOpen = false;
    try { historyOpen = sessionStorage.getItem('sq.ask.history.open') === 'true'; } catch (_) { /* keep history hidden by default when storage is unavailable */ }
    const toggleHistory = () => {
      historyOpen = !historyOpen;
      try { sessionStorage.setItem('sq.ask.history.open', String(historyOpen)); } catch (_) { /* session-only preference is optional */ }
      A.historyMenu = false;
      SQ.redraw();
    };
    const toggleHistoryMenu = () => { A.historyMenu = !A.historyMenu; A.menu = false; SQ.redraw(); };
    const clearHistory = () => { A.clearAll(); };
    const entries = A.entries();
    const hasThread = !!th;
    const landing = !hasThread;
    const scopeChip = 'Sample data · up to ' + SQ.asOf();
    const ask = (q) => () => A.submit(q);

    const groups = A.groups().map((g) => ({
      label: g.label,
      items: g.items.map((t) => {
        const sel = t.id === A.curId, chip = A.threadChip(t);
        return {
          title: t.title, scope: chip.scope, problem: chip.problem, hasProblem: !!chip.problem,
          sel: sel ? 'background: #E8F0FE;' : '', cur: sel ? 'true' : 'false',
          titleStyle: sel ? 'font-weight: 500; color: #174EA6' : '',
          open: () => A.open(t.id)
        };
      })
    }));
    const allThreads = A.threads();

    let turns = [];
    if (th) {
      const last = th.turns.length - 1;
      turns = th.turns.map((u, i) => {
        const e = u.eid ? A.entry(u.eid) : null;
        const a = e ? A.model(e) : null;
        const open = i === last || !!A.expanded[th.id + ':' + i];
        const pending = !!u.pending;
        const key = th.id + ':' + i;
        const steps = A.steps().map((text, k) => ({ text, done: u.step > k, now: u.step === k, todo: u.step < k }));
        return {
          q: u.q, a, hid: 'ans-' + i,
          showFrom: !!u.first && !!u.from, from: u.from, fromHref: A.fromHref(), scope: scopeChip,
          followCap: i > 0,
          showLoading: pending, steps, stop: () => A.stop(th, u),
          showCollapsed: !pending && !!a && !open, toggle: () => { A.expanded[key] = true; SQ.redraw(); },
          showRefusal: !pending && !a, tryList: entries.slice(0, 4).map((x) => ({ q: x.question, ask: ask(x.question) })),
          showAnswer: !pending && !!a && open,
          pin: () => A.togglePin(th),
          copy: () => a && A.copy(A.textOf(a), 'ans' + key),
          copyLabel: A.copied === 'ans' + key ? 'Copied' : 'Copy as text'
        };
      });
      turns.forEach((t) => {
        if (t.a) {
          t.a.noMoney = !t.a.hasMoney;
          t.a.whyClass = t.a.whyIsAI ? 'tag-ai' : '';
          t.a.refText = t.a.refs.join('; ');
          t.a.head = t.a.head;
        }
      });
    }

    const answered = th ? th.turns.filter((u) => !u.pending && u.eid).length : 0;
    const lastTurn = th ? th.turns[th.turns.length - 1] : null;
    const pendingNow = !!(lastTurn && lastTurn.pending);
    const ans0 = th ? th.turns.find((u) => u.eid) : null;
    const dateText = th ? new Date(th.turns[0].at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '';
    const sugMapped = A.suggestions(th).map((q) => ({ q, ask: ask(q) }));
    const suggest = sugMapped.slice(0, 3);
    const suggestMore = th ? [] : sugMapped.slice(3);
    const first = entries.find((x) => x.chip) || entries[0];

    return {
      historyDisplay: historyOpen ? '' : 'display: none;',
      historyExpanded: historyOpen ? 'true' : 'false',
      historyToggleLabel: historyOpen ? 'Hide history' : 'Show history',
      toggleHistory, toggleHistoryMenu, clearHistory,
      historyMenu: !!A.historyMenu, historyMenuStr: A.historyMenu ? 'true' : 'false',
      hasAnyHistory: allThreads.length > 0,
      groups, noHistory: allThreads.length === 0, hasHistory: allThreads.length > 0,
      emptyHistory: A.search ? 'Nothing matches.' : 'Your questions will appear here.',
      search: A.search,
      onSearch: (e) => { A.search = e.target.value; SQ.redraw(); A.focus('ask-search', true); },
      newQuestion: () => A.newThread(),
      landing, hasThread,
      title: th ? th.title : '', turns,
      canExport: answered > 0,
      banner: th ? ('Answered ' + dateText + ' from data up to ' + SQ.asOf() + '. This is the newest data in the sample, so there is nothing to re-run.') : '',
      menu: A.menu, menuStr: A.menu ? 'true' : 'false',
      toggleMenu: () => { A.menu = !A.menu; A.historyMenu = false; SQ.redraw(); },
      infoTagsOpen: !!A.infoTags, infoTagsStr: A.infoTags ? 'true' : 'false',
      toggleInfoTags: () => { A.infoTags = !A.infoTags; SQ.redraw(); },
      pin: () => th && A.togglePin(th), pinLabel: th && th.pinned ? 'Unpin' : 'Pin',
      remove: () => th && A.remove(th),
      share: () => th && A.copy(A.threadText(th), 'share'),
      shareLabel: A.copied === 'share' ? 'Copied' : 'Share',
      suggest, showSug: !!th && !pendingNow && suggest.length > 0,
      suggestMore, hasMore: suggestMore.length > 0,
      draft: A.draft,
      onDraft: (e) => { A.draft = e.target.value; },
      onSubmit: () => { if (!pendingNow) A.submit(A.draft); },
      placeholder: first ? 'Ask about your users, e.g. ' + first.question : 'Ask about your users',
      composerHint: pendingNow ? 'Wait for the answer, or Stop to change the question' : 'Ask a follow-up',
      sendBg: pendingNow ? '#BDC1C6' : '#1A73E8',
      scopeChip,
      refusalHead: A.refusal.head, refusalText: A.refusal.text
    };
  }
}
return Component;
});
