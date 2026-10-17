SQ.define("ProblemDetail", function (DCLogic) {
class Component extends DCLogic {
  renderVals() {
    const modal = !!this.props.modal;
    const pid = this.props.pid;
    // as a popup, the component supplies its own content only; the modal's own
    // card (background, radius, shadow, scrolling) is drawn by whatever embeds it
    const outerStyle = (modal ? '' : 'min-height: 100vh; background: #F1F3F4; ') + "font-family: 'Google Sans Flex', 'Google Sans', Roboto, system-ui, sans-serif; font-size: 14px; line-height: 20px; color: #202124";
    const innerStyle = modal ? 'background: #FFFFFF; box-sizing: border-box' : 'max-width: 760px; margin: 0 auto; background: #FFFFFF; min-height: 100vh; box-sizing: border-box; border-left: 1px solid #DADCE0; border-right: 1px solid #DADCE0';
    if (!this.__init) {
      this.__init = true;
      if (pid) { const hit = SQ.pickInsight('drawerInsight', pid); if (hit) SQ.state.drawerInsight = hit.id; }
      if (!modal) SQ.state.ticketOpen = false;
      this.__focus = true;
    }
    const i = SQ.pickInsight('drawerInsight');
    if (!i) return { none: true, has: false, goBack: () => SQ.closeDrawer(), outerStyle, innerStyle };
    if (i.id !== this.__lastId) { this.__lastId = i.id; this.__focus = true; this.state.owner = 'Unassigned'; }
    const m = SQ.drawerModel(i);
    const r = m.rec;
    const conf = [1, 2, 3].map((n) => (n <= r.confN ? '#1A73E8' : '#DADCE0'));
    const probs = SQ.problems();
    const go = (k) => { const t = probs[(m.idx + k + probs.length) % probs.length]; SQ.state.drawerInsight = t.id; SQ.state.ticketOpen = false; this.state.copied = false; this.__focus = true; SQ.redraw(); };
    const ticketOpen = !!SQ.state.ticketOpen;
    if (this.__focus) { this.__focus = false; setTimeout(() => { const el = document.querySelector('[data-fk="pd-title"]'); if (el) el.focus({ preventScroll: true }); }, 0); }
    const ownerSel = this.state.owner || 'Unassigned';
    const ownerOptions = ['Unassigned', 'Engineering', 'Design', 'Product'].map((o) => ({ value: o, label: o, selected: o === ownerSel ? 'true' : null }));
    const evidenceLines = m.evidence.map((e) => ({ text: e.label + ': ' + e.now + ' vs ' + e.usual + (e.hasRatio ? ' (' + e.ratio + ')' : '') }));
    const sessions = SQ.sessionSummaries(i, 3).map((s) => ({
      label: s.label,
      open: () => { SQ.state.watchInsight = i.id; SQ.state.watchSessionId = s.id; SQ.go('SessionPlayer'); }
    }));
    return {
      has: true, none: false, outerStyle, innerStyle, m, r, conf0: conf[0], conf1: conf[1], conf2: conf[2],
      hasNav: m.hasNav, prev: () => go(-1), next: () => go(1),
      hasSub: !!m.sub,
      hasWatch: ((SQ.watchFor(i.id) || {}).sessions || []).length > 0,
      close: () => (modal ? SQ.closeTicketModal() : SQ.closeDrawer()),
      watch: () => { SQ.state.watchInsight = i.id; SQ.go('SessionPlayer'); },
      ticketOpen, ticketClosed: !ticketOpen,
      toggleTicket: () => SQ.keepFocus(() => { SQ.state.ticketOpen = !SQ.state.ticketOpen; this.state.copied = false; SQ.redraw(); }),
      // stage 1 (the finding drawer): reason, ruled-out causes, caveat, and who it's assigned to
      reasonTag: r.whyTag, reasonCls: r.whyTagCls, reason: m.reason,
      ruledOutLabel: r.whyTag === 'AI' ? 'Ruled out by the AI' : 'Ruled out',
      hasRuledOut: m.ruledOut.length > 0, ruledOut: m.ruledOut,
      hasCaveat: m.caveats.length > 0, caveat: m.caveats.join(' '),
      ownerSel, ownerOptions, setOwner: (e) => this.setState({ owner: e.target.value }),
      // stage 2 (the drafted ticket): team, priority, condensed cause/evidence, sample sessions, plus Copy/Download for the full text
      team: SQ.ownerOf(i), ticketPriority: (i.__p ? i.__p + ' · ' : '') + r.sev,
      hasEvidenceLines: evidenceLines.length > 0, evidenceLines,
      hasSessions: sessions.length > 0, sessions,
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
