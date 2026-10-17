/* Squint front-end runtime. Renders the ported design components (sq/c/<Name>.html + <Name>.js) from the data in SQ.data.
   Templates are static files we ship; data only ever enters through text nodes and attributes, never as markup.
   No eval: components register a factory with SQ.define(). */
(function () {
  'use strict';
  const SQ = (window.SQ = { factories: {}, classes: {}, tpl: {}, data: null, titles: {}, state: {} });

  class DCLogic {
    constructor() { this.props = {}; this.state = {}; }
    setState(patch) { Object.assign(this.state, typeof patch === 'function' ? patch(this.state) : patch); schedule(); }
    forceUpdate() { schedule(); }
  }
  SQ.define = (name, factory) => { SQ.factories[name] = factory; };
  SQ.redraw = () => schedule();
  SQ.go = (route) => { location.hash = '#' + route; };

  const HOLE = /\{\{\s*([^}]+?)\s*\}\}/g;
  const ONE = /^\s*\{\{\s*([^}]+?)\s*\}\}\s*$/;
  function lookup(expr, scope) {
    expr = expr.trim();
    if (expr === 'true') return true;
    if (expr === 'false') return false;
    if (expr === 'null') return null;
    if (/^-?\d+(\.\d+)?$/.test(expr)) return Number(expr);
    if (/^'.*'$|^".*"$/.test(expr)) return expr.slice(1, -1);
    let v = scope;
    for (const part of expr.split('.')) { if (v == null) return undefined; v = v[part]; }
    return v;
  }
  function attrValue(raw, scope) {
    const one = raw.match(ONE);
    if (one) return lookup(one[1], scope);
    return raw.replace(HOLE, (_, e) => { const v = lookup(e, scope); return v == null ? '' : String(v); });
  }
  const camel = (s) => s.replace(/-([a-z])/g, (_, c) => c.toUpperCase());

  // Journeys links open the version where See why and Watch sessions slide in as overlays.
  const ALIAS = { Journeys: 'FlowPrototype' };
  const instances = new Map();
  let route = 'Main';

  function renderComponent(name, props, key) {
    const Cls = SQ.classes[name];
    if (!Cls) return [document.createTextNode('[missing ' + name + ']')];
    let inst = instances.get(key);
    if (!inst || inst.__name !== name) { inst = new Cls(); inst.__name = name; instances.set(key, inst); }
    inst.props = props;
    const vals = inst.renderVals ? inst.renderVals() : {};
    return renderNodes(SQ.tpl[name].content.childNodes, vals, { key, n: 0 });
  }

  function renderNodes(nodes, scope, ctx) {
    const out = [];
    for (const node of nodes) {
      if (node.nodeType === 3) {
        out.push(document.createTextNode(node.nodeValue.replace(HOLE, (_, e) => { const v = lookup(e, scope); return v == null ? '' : String(v); })));
        continue;
      }
      if (node.nodeType !== 1) continue;
      const tag = node.tagName.toLowerCase();
      if (tag === 'template' && node.dataset.sc === 'if') {
        if (attrValue(node.getAttribute('value') || '', scope)) out.push(...renderNodes(node.content.childNodes, scope, ctx));
        continue;
      }
      if (tag === 'template' && node.dataset.sc === 'for') {
        const list = attrValue(node.getAttribute('list') || '', scope) || [];
        const as = node.getAttribute('as') || 'item';
        list.forEach((item, i) => {
          const child = Object.create(scope);
          child[as] = item; child.$index = i;
          out.push(...renderNodes(node.content.childNodes, child, ctx));
        });
        continue;
      }
      if (tag === 'dc-import') {
        const props = {};
        let name = '';
        for (const a of node.attributes) {
          if (a.name === 'name') { name = a.value; continue; }
          if (a.name.startsWith('hint-')) continue;
          props[camel(a.name)] = attrValue(a.value, scope);
        }
        out.push(...renderComponent(name, props, ctx.key + '/' + name + '#' + (ctx.n++)));
        continue;
      }
      const el = node.namespaceURI === 'http://www.w3.org/2000/svg'
        ? document.createElementNS(node.namespaceURI, node.tagName)
        : document.createElement(tag);
      for (const a of node.attributes) {
        const v = attrValue(a.value, scope);
        if (a.name.startsWith('on') && a.name.length > 2) {
          if (typeof v === 'function') el.addEventListener(a.name.slice(2), (e) => { v(e); });
          continue;
        }
        if (a.name === 'checked' || a.name === 'disabled' || a.name === 'selected') {
          if (v === false || v === 'false' || v == null) continue;
          el.setAttribute(a.name, '');
          continue;
        }
        if (a.name === 'href' && typeof v === 'string') {
          const m = v.match(/^\.?\/?([A-Za-z0-9_-]+)\.dc\.html$/);
          if (m) { el.setAttribute('href', '#' + (ALIAS[m[1]] || m[1])); continue; }
        }
        el.setAttribute(a.name, v == null ? '' : String(v));
      }
      for (const c of renderNodes(node.childNodes, scope, ctx)) el.appendChild(c);
      out.push(el);
    }
    return out;
  }

  const app = () => document.getElementById('app');
  let pending = false;
  function schedule() { if (pending) return; pending = true; Promise.resolve().then(() => { pending = false; draw(); }); }
  function draw() {
    const x = window.scrollX, y = window.scrollY;
    app().replaceChildren(...renderComponent(route, {}, 'root:' + route));
    window.scrollTo(x, y);
  }
  function go() {
    const h = decodeURIComponent(location.hash.replace(/^#/, ''));
    const next = SQ.classes[h] ? h : (h ? null : 'Main');
    if (next === null) return;   // an in-page anchor such as #signals
    if (next !== route) { route = next; instances.clear(); window.scrollTo(0, 0); }
    draw();
    document.title = 'Squint · ' + (SQ.titles[route] || route);
    // a close control can ask to have focus returned to whatever opened it, once the new
    // route has actually rendered (SQ.refocus itself only waits one microtask, too early here).
    if (SQ.state.pendingRefocus) { const fk = SQ.state.pendingRefocus; delete SQ.state.pendingRefocus; SQ.refocus(fk); }
  }

  async function boot() {
    const names = Object.keys(SQ.factories);
    const [titles, data] = await Promise.all([
      fetch('sq/titles.json').then((r) => r.json()),
      fetch('results.json').then((r) => r.json()),
      ...names.map(async (n) => {
        const t = document.createElement('template');
        t.innerHTML = await (await fetch('sq/c/' + n + '.html')).text();
        SQ.tpl[n] = t;
      }),
    ]);
    SQ.titles = titles; SQ.data = data;
    for (const n of names) SQ.classes[n] = SQ.factories[n](DCLogic);
    document.addEventListener('submit', (e) => e.preventDefault());
    window.addEventListener('hashchange', go);
    go();
  }
  document.addEventListener('DOMContentLoaded', () => { boot().catch((e) => { app().textContent = 'Squint could not load: ' + e.message; }); });
})();
