SQ.define("DataSources", function (DCLogic) {
class Component extends DCLogic {
  renderVals() {
    const M = SQ.dataSourceModel();
    setTimeout(() => SQ.animateCounts('.ds-count'), 180);
    const showFuture = !!this.state.showFuture;
    const mapAnimClass = this.mapAnimated ? '' : 'ds-map-anim';
    this.mapAnimated = true;
    return {
      ...M,
      flipTransform: showFuture ? 'rotateY(180deg)' : 'rotateY(0deg)',
      toggleFuture: () => this.setState({ showFuture: !showFuture }),
      mapAnimClass
    };
  }
}
function animateCounts(selector) {
  document.querySelectorAll('#app ' + selector).forEach((el) => {
    if (el.dataset.countAnimated === 'running') return;
    const finalText = el.textContent;
    const numberPattern = /-?\d[\d,]*(?:\.\d+)?/g;
    const matches = [...finalText.matchAll(numberPattern)];
    if (!matches.length) return;
    const targets = matches.map((m) => Number(m[0].replace(/,/g, '')));
    el.dataset.countAnimated = 'running';
    if (el.animate) el.animate([
      { opacity: 0.15, transform: 'translateY(10px) scale(.94)' },
      { opacity: 1, transform: 'translateY(0) scale(1)' }
    ], { duration: 1800, easing: 'cubic-bezier(.2,.8,.2,1)' });
    const start = Date.now();
    const tick = () => {
      const t = Math.min(1, (Date.now() - start) / 1800);
      const eased = 1 - Math.pow(1 - t, 3);
      let i = 0;
      el.textContent = finalText.replace(numberPattern, (token) => {
        const decimals = (token.split('.')[1] || '').length;
        return (targets[i++] * eased).toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
      });
      if (t < 1) setTimeout(tick, 24);
      else { el.textContent = finalText; el.dataset.countAnimated = 'done'; }
    };
    tick();
  });
}
SQ.animateCounts = animateCounts;
return Component;
});
