SQ.define("PersonaCompare", function (DCLogic) {
  class Component extends DCLogic {
    renderVals() { return SQ.personaComparisonModel(this.props.page); }
  }
  return Component;
});