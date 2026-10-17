SQ.define("TopBar", function (DCLogic) {
class Component extends DCLogic {
  renderVals() {
    const menu = SQ.state.menu;
    const m = SQ.data.meta;
    const dateRange = (a, b) => new Date(a).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' - ' + new Date(b).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const goAsk = () => { SQ.state.menu = null; if (location.hash !== '#ChatNow') SQ.go('ChatNow'); };
    const crit = SQ.problems().filter((p) => p.severity === 'critical').length;
    const workspaceKey = 'sq.workspaces';
    const activeWorkspaceKey = 'sq.activeWorkspace';
    let workspaces = [{ id: 'demo', name: 'Demo workspace' }];
    try {
      const saved = JSON.parse(localStorage.getItem(workspaceKey) || '[]');
      if (Array.isArray(saved)) workspaces = workspaces.concat(saved.filter((w) => w && w.id && w.name && w.id !== 'demo'));
    } catch (_) { /* workspace labels stay in memory only when browser storage is unavailable */ }
    let activeWorkspace = 'demo';
    try { activeWorkspace = localStorage.getItem(activeWorkspaceKey) || 'demo'; } catch (_) { /* use the demo workspace */ }
    if (!workspaces.some((w) => w.id === activeWorkspace)) activeWorkspace = 'demo';
    const workspaceName = workspaces.find((w) => w.id === activeWorkspace).name;
    const selectWorkspace = (id) => () => {
      try { localStorage.setItem(activeWorkspaceKey, id); } catch (_) { /* this selection lasts for this visit */ }
      SQ.state.menu = null;
      SQ.redraw();
    };
    const workspaceOptions = workspaces.map((w) => ({ ...w, current: w.id === activeWorkspace, select: selectWorkspace(w.id) }));
    return {
      goAsk,
      workspaceName,
      workspaceOpen: menu === 'workspace',
      workspaces: workspaceOptions,
      toggleWorkspace: () => SQ.openMenu('workspace'),
      helpOpen: menu === 'help',
      datasetLine: SQ.fmt(m.counts.users) + ' users, ' + SQ.fmt(m.counts.sessions) + ' sessions, ' + dateRange(m.window.start, m.window.end) + ', a simulated wallet app',
      valueAssumption: m.value_assumption,
      settingsOpen: menu === 'settings',
      toggleHelp: () => SQ.openMenu('help'),
      toggleSettings: () => SQ.openMenu('settings'),
      isDark: SQ.settings.theme === 'dark',
      themeLight: SQ.settings.theme !== 'dark', themeDark: SQ.settings.theme === 'dark',
      toggleTheme: () => SQ.setSetting('theme', SQ.settings.theme === 'dark' ? 'light' : 'dark'),
      themeTrackBg: SQ.settings.theme === 'dark' ? '#1A73E8' : '#DADCE0',
      themeKnobLeft: SQ.settings.theme === 'dark' ? '18px' : '2px',
      usdOnly: SQ.settings.currency === 'usd',
      toggleCurrency: () => SQ.setSetting('currency', SQ.settings.currency === 'usd' ? 'both' : 'usd'),
      usdOnlyTrackBg: SQ.settings.currency === 'usd' ? '#1A73E8' : '#DADCE0',
      usdOnlyKnobLeft: SQ.settings.currency === 'usd' ? '18px' : '2px',
      alertsAll: !SQ.settings.alertsCriticalOnly, alertsCrit: !!SQ.settings.alertsCriticalOnly,
      toggleAlerts: () => SQ.setSetting('alertsCriticalOnly', !SQ.settings.alertsCriticalOnly),
      alertsTrackBg: SQ.settings.alertsCriticalOnly ? '#1A73E8' : '#DADCE0',
      alertsKnobLeft: SQ.settings.alertsCriticalOnly ? '18px' : '2px',
      critCount: String(crit)
    };
  }
}
return Component;
});
