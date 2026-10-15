/* Flow check for Onboarding Step 2. Pure functions, no network, no DOM: it runs in the visitor's browser on a flow definition and says
   in plain English what is wrong with it.

   A flow definition is { journeys: [{ id, name, steps: [{ id, name, event, next?, success? }] }] }; the known events are the list of raw event
   names the data logs, passed to check() (or held in flow.events).
   - event may list alternatives separated by "|" (every alternative must be a known event).
   - next (optional) names the step that follows; without it a step is followed by the next one in the list.
   - success (optional) marks a step as the end of the journey; a step whose id is "done", "success" or "complete" counts as one too.

   check(flow) returns { ok, problems, journeys, steps }; each problem is { code, journey, step, message, fix } with the journey and step
   named in the message (journey and step hold ids, null when the problem is not about one). */
(function (root) {
  'use strict';
  const q = (t) => '“' + t + '”';
  const clean = (x) => (x == null ? '' : String(x).trim());
  const label = (o) => clean(o && o.name) || clean(o && o.id) || '(unnamed)';
  const isSuccess = (st) => st.success === true || /^(done|success|complete|completed)$/i.test(clean(st.id));
  const alternatives = (ev) => clean(ev).split('|').map((x) => x.trim()).filter(Boolean);

  // small edit distance, only used to suggest "did you mean" for a misspelt event name
  function distance(a, b) {
    const m = a.length, n = b.length;
    let prev = Array.from({ length: n + 1 }, (_, j) => j);
    for (let i = 1; i <= m; i++) {
      const cur = [i];
      for (let j = 1; j <= n; j++) cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = cur;
    }
    return prev[n];
  }
  function closest(name, known) {
    const pre = known.find((k) => k.length >= 3 && (name.startsWith(k) || k.startsWith(name)));
    if (pre) return pre;
    let best = null, bd = 99;
    known.forEach((k) => { const d = distance(name, k); if (d < bd) { bd = d; best = k; } });
    return best !== null && bd <= Math.max(2, Math.floor(name.length / 3)) ? best : null;
  }

  function check(flow, events) {
    const problems = [];
    const add = (code, j, st, message, fix) => problems.push({ code, journey: j ? clean(j.id) || null : null, step: st ? clean(st.id) || null : null, journeyName: j ? label(j) : null, stepName: st ? label(st) : null, message, fix });
    const journeys = flow && Array.isArray(flow.journeys) ? flow.journeys : [];
    const known = new Set((events || (flow && flow.events) || []).map(clean).filter(Boolean));
    let stepCount = 0;
    if (!journeys.length) add('no_journeys', null, null, 'The flow has no journeys, so there is nothing to analyze.', 'Add at least one journey with its steps.');
    const seenJourney = new Set();
    journeys.forEach((j) => {
      const jn = q(label(j));
      if (!clean(j.id)) add('missing_id', j, null, `A journey called ${jn} has no id.`, 'Give every journey a short, unique id.');
      else if (seenJourney.has(clean(j.id))) add('duplicate_journey', j, null, `Two journeys share the id ${q(clean(j.id))} (${jn}).`, 'Give each journey its own id.');
      seenJourney.add(clean(j.id));
      const steps = Array.isArray(j.steps) ? j.steps : [];
      stepCount += steps.length;
      if (!steps.length) { add('empty_journey', j, null, `Journey ${jn} has no steps.`, 'Add the screens people go through, in order, ending with a success step. Or remove the journey.'); return; }
      const seen = new Map();
      steps.forEach((st) => {
        const sn = q(label(st));
        const id = clean(st.id);
        if (!id) add('missing_id', j, st, `Step ${sn} in ${jn} has no id.`, 'Give every step a short id that is unique inside its journey.');
        else if (seen.has(id)) add('duplicate_step', j, st, `Journey ${jn} uses the step id ${q(id)} twice (${q(label(seen.get(id)))} and ${sn}), so the two steps cannot be told apart.`, 'Give each step in a journey its own id.');
        else seen.set(id, st);
        const evs = alternatives(st.event);
        if (!evs.length) add('missing_event', j, st, `Step ${sn} in ${jn} has no event, so no data can be matched to it.`, 'Name the event this step reads from your data.');
        evs.filter((e) => !known.has(e)).forEach((e) => {
          const near = closest(e, [...known]);
          add('unknown_event', j, st, `Step ${sn} in ${jn} reads the event ${q(e)}, which does not appear in this data.`,
            near ? `Did you mean ${q(near)}? Use an event name that the data logs, or pick the flow that was made for this data.` : 'Use an event name that the data logs, or pick the flow that was made for this data.');
        });
      });
      // follow the order: each step goes to its "next" step, or to the one after it in the list
      const at = (id) => steps.findIndex((s) => clean(s.id) === id);
      steps.forEach((st) => { if (clean(st.next) && at(clean(st.next)) < 0) add('bad_next', j, st, `Step ${q(label(st))} in ${jn} points to a next step ${q(clean(st.next))} that does not exist.`, 'Point it at a step in this journey, or remove the link.'); });
      let i = 0; const visited = new Set();
      while (i >= 0 && i < steps.length) {
        if (visited.has(i)) break;
        visited.add(i);
        const st = steps[i], nx = clean(st.next);
        const to = nx ? at(nx) : (i + 1 < steps.length ? i + 1 : -1);
        if (to >= 0 && visited.has(to)) {
          add('loop', j, st, `In ${jn}, step ${q(label(st))} sends people back to ${q(label(steps[to]))}, so the order loops and the journey never reaches its end.`,
            'Point the step at the one that comes after it, or remove the link that goes back.');
          break;
        }
        i = to;
      }
      const last = steps[steps.length - 1];
      if (!isSuccess(last)) add('no_success', j, last, `Journey ${jn} has no final success step: it ends at ${q(label(last))}.`, 'End the journey with a step that marks success, such as a “done” step.');
    });
    return { ok: problems.length === 0, problems, journeys: journeys.length, steps: stepCount };
  }

  // How many of the event names a flow reads appear in a list of known events (each name counted once).
  function match(flow, events) {
    const known = new Set((events || []).map(clean));
    const names = [...new Set(((flow && flow.journeys) || []).flatMap((j) => (j.steps || []).flatMap((s) => alternatives(s.event))))];
    const found = names.filter((n) => known.has(n));
    return { total: names.length, found: found.length, missing: names.filter((n) => !known.has(n)) };
  }
  // Every flow measured against one list of known events, best match first.
  function rank(flows, events) {
    return flows.map((f) => ({ id: f.id, name: f.name, ...match(f, events) })).sort((a, b) => (b.found / Math.max(1, b.total)) - (a.found / Math.max(1, a.total)));
  }

  const api = { check, match, rank };
  root.SquintFlowCheck = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
