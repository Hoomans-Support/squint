SQ.define("NavRail", function (DCLogic) {
class Component extends DCLogic {
  renderVals() {
    const active = this.props.active ?? 'overview';
    const base = 'display: flex; align-items: center; gap: 14px; height: 44px; padding: 0 16px 0 28px; border-radius: 0 22px 22px 0; text-decoration: none; ';
    const on = base + 'background: #E8F0FE; color: #174EA6; font-weight: 500;';
    const off = base + 'background: transparent; color: #3C4043; font-weight: 400;';
    const keys = ['overview', 'journeys', 'audiences', 'ask', 'brief', 'data'];
    const s = {}, cur = {}, dot = {};
    const dockBase = 'display: flex; align-items: center; justify-content: center; width: 40px; height: 40px; border-radius: 50%; text-decoration: none; flex: none; ';
    keys.forEach((k) => {
      s[k] = k === active ? on : off;
      cur[k] = k === active ? 'page' : 'false';
      dot[k] = dockBase + (k === active ? 'background: #E8F0FE; color: #1A73E8;' : 'background: transparent; color: #5F6368;');
    });
    const crit = SQ.problems().filter((p) => p.severity === 'critical').length;
    const hasBadge = crit > 0 && !SQ.settings.alertsCriticalOnly;
    const badge = String(crit), badgeLabel = crit + ' open critical problem' + (crit === 1 ? '' : 's') + ' in this scope';

    // ---- collapse: the labeled panel hides, a slim icon-only dock stays so navigation is never fully lost ----
    const collapsed = !!SQ.settings.navCollapsed;
    const toggleCollapse = () => { SQ.setSetting('navCollapsed', !collapsed); SQ.refocus('nav-toggle'); };

    // ---- section groups: collapsible, state remembered per visitor ----
    const sections = SQ.settings.navSections || {};
    const sectionOpen = (id) => sections[id] !== false;
    const toggleSection = (id) => () => { SQ.setSetting('navSections', { ...sections, [id]: !sectionOpen(id) }); SQ.refocus('sec-' + id); };
    const chevron = (open) => 'transform: rotate(' + (open ? '0' : '-90') + 'deg); transition: transform .15s ease';

    return {
      s, cur, dot, hasBadge, badge, badgeLabel,
      collapsed, notCollapsed: !collapsed, collapsedStr: String(collapsed),
      toggleCollapse, toggleLabel: collapsed ? 'Expand navigation' : 'Collapse navigation',
      toggleChevronStyle: 'transform: rotate(' + (collapsed ? '180' : '0') + 'deg); transition: transform .15s ease',
      exploreOpen: sectionOpen('explore'), exploreStr: String(sectionOpen('explore')), toggleExplore: toggleSection('explore'), exploreChevron: chevron(sectionOpen('explore')),
      insightsOpen: sectionOpen('insights'), insightsStr: String(sectionOpen('insights')), toggleInsights: toggleSection('insights'), insightsChevron: chevron(sectionOpen('insights'))
    };
  }
}
return Component;
});
