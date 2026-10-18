SQ.define("ScopeBar", function (DCLogic) {
class Component extends DCLogic {
  renderVals() {
    const sc = SQ.scope;
    // a showcase page may pass open="true" to show the user menu before anyone has clicked
    const menu = SQ.state.menu === undefined ? (this.props.open ? 'user' : null) : SQ.state.menu;
    const btn = 'display: inline-flex; align-items: center; gap: 8px; height: 36px; padding: 0 10px 0 14px; border-radius: 8px; font-family: inherit; font-size: 14px; font-weight: 500; cursor: pointer; ';
    const idle = 'border: 1px solid #DADCE0; background: #FFFFFF; color: #3C4043;';
    const live = 'border: 1px solid #1A73E8; background: #E8F0FE; color: #174EA6;';
    const pick = (patch) => () => { SQ.state.menu = null; SQ.setScope(patch); SQ.refocus('menu-' + menu); };

    const datesFor = (r) => { const keep = sc.range; sc.range = r; const d = SQ.rangeDates(); sc.range = keep; return d; };
    const ranges = Object.keys(SQ.RANGES).map((r) => ({ label: SQ.RANGES[r].label, dates: datesFor(r), selected: sc.range === r, pick: pick({ range: r }), fk: 'opt-' + r }));

    const personas = SQ.personas();
    const selected = sc.persona === 'all' ? [] : sc.persona.split('+');
    const allGroups = [{ id: 'all', label: 'All users', users: SQ.fmt(personas.reduce((a, p) => a + SQ.personaUserCount(p), 0)), checked: sc.persona === 'all' }]
      .concat(personas.map((p) => ({ id: p.id, label: p.label, users: SQ.fmt(SQ.personaUserCount(p)), checked: sc.persona === 'all' ? false : selected.includes(p.id) })));
    const groups = allGroups.map((g) => ({
      ...g, color: g.checked ? '#1A73E8' : '#5F6368', fk: 'opt-' + g.id,
      isAll: g.id === 'all', isUnregistered: g.id === 'unregistered', isLargeBusiness: g.id === 'large_business',
      isRetail: g.id === 'sari_sari', isTrader: g.id === 'individual_trader', isIndividual: g.id === 'individual',
      pick: () => {
        let next;
        if (g.id === 'all') next = 'all';
        else if (g.id === 'unregistered') next = sc.persona === 'unregistered' ? 'all' : 'unregistered';
        else {
          const ids = sc.persona === 'all' || sc.persona === 'unregistered' ? [] : sc.persona.split('+');
          next = ids.includes(g.id) ? ids.filter((id) => id !== g.id) : ids.concat(g.id);
          next = next.length ? next.sort().join('+') : 'all';
        }
        SQ.state.menu = 'user';
        SQ.setScope({ persona: next });
        SQ.refocus('menu-user');
      }
    }));

    const have = SQ.data.meta.platforms || [];
    const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
    const platforms = ['app', 'web'].map((id) => {
      const has = have.indexOf(id) >= 0;
      const isSel = sc.platform === id;
      return {
        label: cap(id), disabled: !has, selected: isSel, reason: has ? '' : 'No ' + id + ' events in this sample',
        style: 'display: flex; align-items: center; gap: 12px; width: 100%; height: 36px; min-height: 36px; padding: 0 16px; border: 0; background: '
          + (isSel ? '#E8F0FE' : 'transparent') + '; font-family: inherit; font-size: 14px; text-align: left; cursor: ' + (has ? 'pointer' : 'not-allowed')
          + '; color: ' + (isSel ? '#174EA6' : '#202124') + '; font-weight: ' + (isSel ? '600' : '400') + '; transition: background-color .15s ease',
        pick: has ? pick({ platform: isSel ? 'all' : id }) : () => {}, fk: 'opt-' + id
      };
    });
    const platLabel = sc.platform === 'all' ? 'All platforms' : cap(sc.platform);
    const showUserGroups = !this.props.hideUserGroups;

    return {
      showUserGroups,
      rangeLabel: SQ.RANGES[sc.range].label, rangeDates: SQ.rangeDates(), ranges,
      openRange: menu === 'range', openUser: menu === 'user', openPlatform: menu === 'platform',
      rangeStr: String(menu === 'range'), userStr: String(menu === 'user'), platformStr: String(menu === 'platform'),
      rangeChip: btn + (menu === 'range' ? live : idle),
      userChip: btn + (menu === 'user' || sc.persona !== 'all' ? live : idle),
      platformChip: btn + (menu === 'platform' || sc.platform !== 'all' ? live : idle),
      groups, userLabel: selected.length > 1 ? selected.length + ' groups' : SQ.personaLabel(sc.persona), userCount: SQ.fmt(SQ.userCount()),
      platforms, platLabel,
      toggleRange: () => SQ.openMenu('range'), toggleUser: () => SQ.openMenu('user'), togglePlatform: () => SQ.openMenu('platform'),
      asOf: 'Sample data · as of ' + SQ.asOf()
    };
  }
}
return Component;
});
