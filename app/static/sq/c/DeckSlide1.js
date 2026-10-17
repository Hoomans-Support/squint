SQ.define("DeckSlide1", function (DCLogic) {
class Component extends DCLogic {
  renderVals() {
    const n = Number(this.props.n ?? 1);
    const deck = SQ.ask.deck();
    const s = deck.slides[n - 1] || deck.slides[0] || { isSummary: false, isChart: false, bars: [], stats: [] };
    // the slide is 1280 wide by design; scale it down on narrow screens so the page never scrolls sideways
    const zoom = Math.min(1, Math.max(0.2, (window.innerWidth - 32) / 1280)).toFixed(3);
    return { ...s, zoom, n: s.n || n, pos: s.pos || n, count: s.count || deck.slides.length };
  }
}
return Component;
});
