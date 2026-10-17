SQ.define("SessionPlayer", function (DCLogic) {
class Component extends DCLogic {
  constructor() { super(); this.state = { sel: 0, at: 0, playing: false, speed: 4, more: false, infoOpen: false }; this.__timer = null; }
  stop() { if (this.__timer) { clearInterval(this.__timer); this.__timer = null; } }
  renderVals() {
    const pid = this.props.pid;
    if (!this.__init) {
      this.__init = true; this.__focus = true;
      if (pid) { const hit = SQ.pickInsight('watchInsight', pid); if (hit) SQ.state.watchInsight = hit.id; }
    }
    const i = SQ.pickInsight('watchInsight');
    const W = i ? SQ.watchFor(i.id) : null;
    const sessions = (W && W.sessions) || [];
    const rec = i ? SQ.problemRec(i) : null;
    const footer = (SQ.data.watch || {}).footer || 'Rebuilt from tracked events, inputs masked, no video';
    const reduced = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    const head = { pid: i ? (i.__p || 'Healthy') : '', action: rec ? rec.action : '', item: rec ? rec.item : '', who: rec ? rec.who : '', footer };
    const back = () => SQ.closeWatch();
    if (this.__focus) { this.__focus = false; setTimeout(() => { const el = document.querySelector('[data-fk="sp-title"]'); if (el) el.focus({ preventScroll: true }); }, 0); }
    if (!i || !sessions.length) {
      this.stop();
      return { empty: true, has: false, head, back, hasDrawer: !!i, openDrawer: () => { if (i) SQ.state.drawerInsight = i.id; SQ.go('ProblemDetail'); } };
    }
    const sel = Math.min(this.state.sel, sessions.length - 1);
    const S = sessions[sel];
    const dur = Math.max(1, S.duration_s || 1);
    const at = Math.min(dur, Math.max(0, this.state.at));
    const steps = S.steps || [];
    const upd = (patch) => SQ.keepFocus(() => this.setState(patch));
    const pick = (k) => { this.stop(); upd({ sel: k, at: 0, playing: false }); };
    const struggle = steps.find((e) => e.kind === 'error' || e.kind === 'rage_tap') || (S.marks || []).find((m) => m.kind === 'error' || m.kind === 'rage_tap') || steps.find((e) => e.kind === 'idle') || null;
    const nextEvent = () => { const e = steps.find((x) => x.t_seconds > at + 0.05); return e ? e.t_seconds : 0; };

    const play = () => {
      if (reduced) { upd({ at: nextEvent(), playing: false }); return; }
      if (this.state.playing) { this.stop(); upd({ playing: false }); return; }
      this.stop();
      const start = at >= dur ? 0 : at;
      upd({ playing: true, at: start });
      this.__timer = setInterval(() => {
        if (!/SessionPlayer/.test(location.hash)) { this.stop(); return; }
        const next = this.state.at + 0.25 * this.state.speed;
        if (next >= dur) { this.stop(); SQ.keepFocus(() => this.setState({ at: dur, playing: false })); return; }
        SQ.keepFocus(() => this.setState({ at: next }));
      }, 250);
    };
    const seekTo = (t) => { this.stop(); upd({ at: Math.min(dur, Math.max(0, t)), playing: false }); };

    /* ---- list of sessions ---- */
    const showAll = this.state.more || sel >= 5;
    const vis = showAll ? sessions : sessions.slice(0, 5);
    const rows = vis.map((x, k) => {
      const o = SQ.watchOut(x.outcome), d = Math.max(1, x.duration_s || 1);
      return {
        persona: x.persona, device: x.device, durTxt: SQ.fmtT(x.duration_s), outcome: o[0], outBg: o[1], outFg: o[2], dot: SQ.watchDot(x.persona),
        comparison: x.role === 'comparison', fk: 'sp-row-' + k,
        marks: (x.marks || []).filter((m) => m.kind === 'rage_tap' || m.kind === 'error').map((m) => ({ left: Math.min(98, m.t_seconds / d * 100).toFixed(1) + '%', c: m.kind === 'rage_tap' ? '#D93025' : '#F9AB00' })),
        on: sel === k ? 'true' : 'false', style: sel === k ? 'background: #E8F0FE;' : '', pick: () => pick(k)
      };
    });
    const hidden = sessions.length - vis.length;

    /* ---- the screen at this moment ---- */
    let lastStep = null;
    steps.forEach((e) => { if (e.kind === 'step' && e.t_seconds <= at) lastStep = e; });
    const stepT = lastStep ? lastStep.t_seconds : 0;
    const screenName = lastStep ? String(lastStep.label).replace(/^Opened\s+/i, '') : 'Start';
    let err = null, tap = null, idle = null, end = null, curIdx = -1;
    steps.forEach((e, k) => {
      if (e.t_seconds <= at) curIdx = k;
      if (e.t_seconds < stepT || e.t_seconds > at) return;
      if (e.kind === 'error') err = e;
      if ((e.kind === 'tap' || e.kind === 'rage_tap') && at - e.t_seconds <= 3) tap = e;
      if (e.kind === 'idle' && at <= e.t_seconds + (e.seconds || 0)) idle = e;
      if (e.kind === 'exit' || e.kind === 'done') end = e;
    });
    const sn = screenName.toLowerCase();
    const kind = /otp|code/.test(sn) ? 'otp' : /checkout|pin/.test(sn) ? 'checkout' : /personal|tin|detail|register|number/.test(sn) ? 'form' : 'generic';
    const cta = kind === 'checkout' ? 'Pay' : kind === 'otp' ? 'Verify' : 'Continue';
    const el = tap ? String(tap.element || '') : '';
    const ctaTap = /^(pay|continue|verify|submit|next|confirm)/.test(el);
    const gTop = /resend/.test(el) ? 290 : 190;   // only used off the CTA button, which now positions its own glow/badge relative to itself
    const rageN = tap && tap.kind === 'rage_tap' ? ((String(tap.label).match(/(\d+) times/) || [])[1] || '') : '';
    const phone = {
      title: screenName, isOtp: kind === 'otp', isCheckout: kind === 'checkout', isForm: kind === 'form', isGeneric: kind === 'generic', cta,
      hasErr: !!err, err: err ? String(err.error || err.label) : '',
      hasTap: !!tap && !ctaTap, onCta: !!tap && ctaTap, glow: 'left: 100px; top: ' + gTop + 'px', badge: 'left: 132px; top: ' + (gTop - 10) + 'px',
      hasBadge: !!(tap && tap.kind === 'rage_tap' && !ctaTap), onCtaBadge: !!(tap && tap.kind === 'rage_tap' && ctaTap), badgeText: rageN ? '×' + rageN : 'Repeated taps',
      hasIdle: !!idle, idleText: idle ? 'Paused ' + Math.round(idle.seconds || 0) + 's' : '',
      hasEnd: !!end, endText: end ? (end.kind === 'done' ? 'Finished' : 'Left the app') : '', endBg: end && end.kind === 'done' ? 'rgba(230,244,234,.92)' : 'rgba(32,33,36,.78)', endFg: end && end.kind === 'done' ? '#137333' : '#FFFFFF',
      aria: screenName + ' screen at ' + SQ.fmtT(at) + (err ? ', error ' + (err.error || err.label) : '') + (tap ? ', latest tap on ' + (el || 'the screen') : '')
    };

    /* ---- strip ---- */
    const segments = (S.marks || []).filter((m) => m.kind === 'idle' && m.t_end != null).map((m) => ({ left: (m.t_seconds / dur * 100).toFixed(1) + '%', width: ((m.t_end - m.t_seconds) / dur * 100).toFixed(1) + '%' }));
    const marks = (S.marks || []).map((m) => SQ.watchMark(m, dur)).filter(Boolean);
    const log = steps.map((e, k) => {
      const ev = SQ.watchEV[e.kind] || SQ.watchEV.step, strong = e.kind === 'rage_tap' || e.kind === 'error';
      return { t: SQ.fmtT(e.t_seconds), text: e.label, c: ev.c, r: ev.r, fk: 'sp-ev-' + k, cur: k === curIdx ? 'true' : 'false',
        rowStyle: k === curIdx ? 'background: #E8F0FE;' : '', textStyle: k === curIdx ? 'font-weight: 500; color: #174EA6' : (strong ? 'color: #202124' : 'color: #5F6368'), go: () => seekTo(e.t_seconds) };
    });
    const o = SQ.watchOut(S.outcome);
    const ev = SQ.state.watchEvidence || (SQ.state.watchEvidence = {});
    const added = !!ev[S.id];
    const nAdded = Object.keys(ev).filter((k) => ev[k] && sessions.some((x) => x.id === k)).length;
    // actual playback speed is 4x the shown label (default label "1x" plays at a brisk, demo-friendly real speed of 4x)
    const speeds = [4, 8, 16].map((v) => ({ label: (v / 4) + '×', on: this.state.speed === v ? 'true' : 'false', fk: 'sp-speed-' + v, style: this.state.speed === v ? 'background: #E8F0FE; color: #174EA6; border-color: #1A73E8;' : '', set: () => upd({ speed: v }) }));
    const when = S.start_utc ? new Date(S.start_utc).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' }) + ' UTC' : 'n/a';
    const playing = !!this.state.playing && !reduced;
    const infoOpen = !!this.state.infoOpen;
    return {
      infoOpen, infoStr: infoOpen ? 'true' : 'false', toggleInfo: () => upd({ infoOpen: !infoOpen }),
      empty: false, has: true, head, back, rows, hidden, hasHidden: hidden > 0, moreText: 'Show ' + hidden + ' more', showMore: () => upd({ more: true }),
      shown: vis.length, total: sessions.length,
      s: { n: sel + 1, persona: S.persona, device: S.device, product: S.product || '', outcome: o[0], outBg: o[1], outFg: o[2], when, durTxt: SQ.fmtT(dur), atTxt: SQ.fmtT(at), atStep: screenName,
        playLeft: (at / dur * 100).toFixed(1) + '%', segments, marks, log, summary: S.summary || '', comparison: S.role === 'comparison',
        struggleTxt: struggle ? SQ.fmtT(struggle.t_seconds) : '', hasStruggle: !!struggle, dur: Math.round(dur), now: Math.round(at) },
      phone, playing, paused: !playing, reduced, normal: !reduced,
      playLabel: reduced ? 'Next event' : (playing ? 'Pause' : 'Play'), togglePlay: play,
      skip: () => { if (struggle) seekTo(struggle.t_seconds); },
      speeds,
      stripClick: (e) => { const r = e.currentTarget.getBoundingClientRect(); if (r.width) seekTo((e.clientX - r.left) / r.width * dur); },
      stripKey: (e) => {
        const d = { ArrowLeft: -5, ArrowRight: 5, Home: -1e9, End: 1e9 }[e.key];
        if (d == null) return; e.preventDefault(); seekTo(at + d);
      },
      added, notAdded: !added, nAdded, hasAdded: nAdded > 0,
      addEv: () => SQ.keepFocus(() => { ev[S.id] = !ev[S.id]; SQ.redraw(); }),
      next: () => pick((sel + 1) % sessions.length),
      sampleNote: sessions.length + ' sessions sampled for this finding', popNote: W.population ? 'Of ' + SQ.fmt(W.population.sessions) + ' sessions at this step, ' + SQ.fmt(W.population.ended_here) + ' ended here.' : ''
    };
  }
}
return Component;
});
