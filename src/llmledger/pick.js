/* llmledger "Which model?": small pure functions for comparing models side by side,
   used by the page (app.js) and checked by tests/test_pick.py. No page code here. */
(function (root) {
  // Thinking effort levels, lowest first (the same list as catalog.py's EFFORTS).
  const LEVELS = ["none", "minimal", "low", "medium", "high", "xhigh", "max"];
  // Arena tasks where more thinking usually pays off.
  const HARD_TASKS = ["coding", "webdev", "math", "hard_prompts", "expert", "software", "science"];
  // Words that ask for deep work, and words that ask for light work.
  const DEEP = /\b(architect\w*|design\w*|from scratch|refactor\w*|debug\w*|root cause|prove|proof|optimi[sz]\w*|migrat\w*|security|concurren\w*|race condition|trade-?offs?|specification|multi-?step|end to end|production)\b/i;
  const LIGHT = /\b(summari[sz]e|translate|rewrite|rephrase|proofread|typos?|reformat|format|short|quick(ly)?|one line|tl;?dr|classify|extract)\b/i;
  const SCORE_LEVEL = ["low", "medium", "high", "high", "xhigh", "max"];

  // The closest level a model takes: the nearest one below, else the lowest one above.
  function clamp(level, levels) {
    if (!levels || !levels.length) return null;
    if (levels.includes(level)) return level;
    const at = LEVELS.indexOf(level);
    for (let i = at; i >= 0; i--) if (levels.includes(LEVELS[i])) return LEVELS[i];
    return levels.find(l => LEVELS.indexOf(l) > at) || levels[0];
  }

  // A suggested effort level for a prompt. A rule of thumb from the task and the prompt's
  // words and length, not a measurement. Returns { level, why: [...] }; level is null when
  // the model has no levels, and the model's default (or null) when there is no prompt.
  function suggestEffort(text, task, levels, promptTokens, fallback) {
    if (!levels || !levels.length) return { level: null, why: [] };
    text = String(text || "");
    if (!text.trim()) return { level: fallback && levels.includes(fallback) ? fallback : null, why: [] };
    const why = [];
    let score = 1;
    if (HARD_TASKS.includes(task)) { score += 1; why.push("a task where thinking helps"); }
    const deep = text.match(DEEP);
    const light = deep ? null : text.match(LIGHT);
    if (deep) { score += 2; why.push('it asks for "' + deep[0].toLowerCase() + '"'); }
    if (light) { score -= 1; why.push('it asks for "' + light[0].toLowerCase() + '"'); }
    const tokens = promptTokens || 0;
    if (tokens > 8000) { score += 2; why.push("a very long prompt"); }
    else if (tokens > 2000) { score += 1; why.push("a long prompt"); }
    else if (tokens < 40 && !deep) { score -= 1; why.push("a short prompt"); }
    const level = SCORE_LEVEL[Math.max(0, Math.min(SCORE_LEVEL.length - 1, score))];
    return { level: clamp(level, levels), why };
  }

  // How fast each choice uses a plan, compared with the choice that uses it least
  // (1 for that one). Assumes a plan is used up in proportion to API prices.
  // costs: dollars per task (null when unknown). Returns multiples, null when unknown.
  function planMultiples(costs) {
    const known = costs.filter(c => c != null && c > 0);
    if (!known.length) return costs.map(() => null);
    const least = Math.min(...known);
    return costs.map(c => (c == null || c <= 0 ? null : c / least));
  }

  // Whether two Arena ratings cannot be told apart: their 95% ranges overlap.
  const tied = (a, b) => a.high >= b.low && b.high >= a.low;

  const times = x => (x < 10 ? x.toFixed(1) : x.toFixed(0)) + "×";
  const percent = x => Math.round(100 * x) + "%";
  // "about 2.5× as much", "about 40% less", "about 1/200 as much", "about the same"
  function compared(ratio) {
    if (ratio >= 1.05) return "about " + times(ratio) + " as much";
    if (ratio <= 0.1) return "about 1/" + Math.round(1 / ratio) + " as much";
    if (ratio <= 0.95) return "about " + percent(1 - ratio) + " less";
    return "about the same";
  }

  // One plain sentence per choice saying how it compares with the highest rated one (or the
  // first one when none is rated), then the break-even: how few answer tokens a choice with
  // pricier tokens must use to cost less, or how many more a cheaper one can use.
  // rows: [{ name, rating, low, high, cost, out }] in table order; cost is dollars per task,
  // out the answer price per 1M tokens. opts: { task, plan, most }.
  function verdict(rows, opts) {
    opts = opts || {};
    const priced = rows.filter(r => r.cost != null);
    if (priced.length < 2) return ["Add another model to compare."];
    const rated = priced.filter(r => r.rating != null);
    const anchor = rated.length ? rated.reduce((a, b) => (b.rating > a.rating ? b : a)) : priced[0];
    const task = opts.task || "this task";
    const lines = rated.length ? [anchor.name + " has the highest " + task + " rating here (" + anchor.rating.toFixed(0) + ")."] : [];
    for (const r of priced.filter(x => x !== anchor).slice(0, opts.most || 3)) {
      const ratio = anchor.cost > 0 ? r.cost / anchor.cost : null;
      let line = r.name + (ratio == null ? " cannot be compared" :
        opts.plan ? (ratio >= 1.05 ? " uses the plan " + compared(ratio).replace(" as much", "") + " as fast"
          : ratio <= 0.95 ? " uses " + compared(ratio) + " of the plan" : " uses the plan at about the same rate")
          : " costs " + compared(ratio) + " per task");
      if (r.rating == null) line += ", with no " + task + " rating";
      else if (anchor.rating != null) {
        line += tied(r, anchor) ? ", and the votes cannot tell its rating apart (" + r.rating.toFixed(0) + ")"
          : ", with a lower rating (" + r.rating.toFixed(0) + " against " + anchor.rating.toFixed(0) + ")";
      }
      const k = r.out > 0 && anchor.out > 0 ? r.out / anchor.out : null;
      if (k != null && k > 0.1 && k < 10 && Math.abs(k - 1) >= 0.05) {
        const less = opts.plan ? "use less of the plan" : "cost less";
        line += k > 1 ? "; to " + less + " it would have to use under " + percent(1 / k) + " of " + anchor.name + "'s answer tokens"
          : "; it stays " + (opts.plan ? "lighter on the plan" : "cheaper") + " unless it uses over " + times(1 / k) + " " + anchor.name + "'s answer tokens";
      }
      lines.push(line + ".");
    }
    return lines;
  }

  const api = { LEVELS, HARD_TASKS, clamp, suggestEffort, planMultiples, tied, verdict };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.LLMPICK = api;
})(this);
