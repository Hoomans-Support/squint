SQ.define("NavRail", function (DCLogic) {
class Component extends DCLogic {
  renderVals() {
    const active = this.props.active ?? 'overview';
    const base = 'display: flex; align-items: center; gap: 14px; height: 44px; padding: 0 16px 0 28px; border-radius: 0 22px 22px 0; text-decoration: none; ';
    const on = base + 'background: #E8F0FE; color: #174EA6; font-weight: 500;';
    const off = base + 'background: transparent; color: #3C4043; font-weight: 400;';
    const keys = ['overview', 'journeys', 'audiences', 'ask', 'brief', 'data'];
    const s = {}, cur = {};
    keys.forEach((k) => {
      s[k] = k === active ? on : off;
      cur[k] = k === active ? 'page' : 'false';
    });
    const crit = SQ.problems().filter((p) => p.severity === 'critical').length;
    const hasBadge = crit > 0 && !SQ.settings.alertsCriticalOnly;
    const badge = String(crit), badgeLabel = crit + ' open critical problem' + (crit === 1 ? '' : 's') + ' in this scope';

    return { s, cur, hasBadge, badge, badgeLabel };
  }
}
return Component;
});
