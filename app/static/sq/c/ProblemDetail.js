SQ.define("ProblemDetail", function (DCLogic) {
class Component extends DCLogic {
  renderVals() {
    const pid = this.props.pid;
    if (!this.__init) {
      this.__init = true;
      if (pid) { const hit = SQ.pickInsight('drawerInsight', pid); if (hit) SQ.state.drawerInsight = hit.id; }
      SQ.state.ticketOpen = false;
      this.__focus = true;
    }
    const i = SQ.pickInsight('drawerInsight');
    if (!i) return { none: true, has: false, goBack: () => SQ.closeDrawer() };
    const m = SQ.drawerModel(i);
    const r = m.rec;
    const conf = [1, 2, 3].map((n) => (n <= r.confN ? '#1A73E8' : '#DADCE0'));
    const probs = SQ.problems();
    const go = (k) => { const t = probs[(m.idx + k + probs.length) % probs.length]; SQ.state.drawerInsight = t.id; SQ.state.ticketOpen = false; this.state.copied = false; this.__focus = true; SQ.redraw(); };
    const ticketOpen = !!SQ.state.ticketOpen;
    if (this.__focus) { this.__focus = false; setTimeout(() => { const el = document.querySelector('[data-fk="pd-title"]'); if (el) el.focus({ preventScroll: true }); }, 0); }
    return {
      has: true, none: false, m, r, conf0: conf[0], conf1: conf[1], conf2: conf[2],
      hasNav: m.hasNav, prev: () => go(-1), next: () => go(1),
      hasSub: !!m.sub, hasClaims: m.claims.length > 0, hasEvidence: m.evidence.length > 0, hasTl: !!m.tl, hasWho: m.who.length > 0,
      hasIn: m.ruledIn.length > 0, hasOut: m.ruledOut.length > 0, hasCaveats: m.caveats.length > 0, hasNext: m.next.length > 0,
      noCauses: m.ruledIn.length === 0 && m.ruledOut.length === 0,
      tl: m.tl || { bars: [], first: '', last: '', metric: '', onset: '' }, hasOnset: !!(m.tl && m.tl.onset),
      hasWatch: ((SQ.watchFor(i.id) || {}).sessions || []).length > 0,
      close: () => SQ.closeDrawer(),
      watch: () => { SQ.state.watchInsight = i.id; SQ.go('SessionPlayer'); },
      ticketOpen, ticketClosed: !ticketOpen,
      toggleTicket: () => SQ.keepFocus(() => { SQ.state.ticketOpen = !SQ.state.ticketOpen; this.state.copied = false; SQ.redraw(); }),
      ticket: m.ticket, ticketFile: SQ.ticketFile(i),
      copy: () => {
        let ok = false;
        const done = (v) => SQ.keepFocus(() => { this.setState({ copied: v ? 'Copied to the clipboard' : 'Copy is blocked here. Select the text and copy it by hand.' }); });
        try { navigator.clipboard.writeText(m.ticket).then(() => done(true), () => done(false)); ok = true; } catch (e) { /* fall through */ }
        if (!ok) done(false);
      },
      download: () => SQ.keepFocus(() => { this.setState({ copied: SQ.downloadText(SQ.ticketFile(i), m.ticket) ? 'Downloaded ' + SQ.ticketFile(i) : 'The download is blocked here.' }); }),
      copied: this.state.copied || '', hasCopied: !!this.state.copied
    };
  }
}
return Component;
});
