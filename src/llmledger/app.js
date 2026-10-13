/* llmledger results page: model lookup, compare, prompt cost, best value, last 7 days, top lists.
   Reads window.LLMLEDGER, written by page.py from the daily pipeline, and
   window.LLMCOST from cost.js. */
(function () {
  const D = window.LLMLEDGER;
  if (!D) return;
  const FIELDS = ["key", "maker", "name", "host", "mode", "status", "added",
    "removed", "retire", "input", "output", "repriced", "last", "exit", "age", "skills", "size", "media"];
  const models = D.models.map(r => Object.fromEntries(FIELDS.map((f, i) => [f, r[i]])));
  const byKey = new Map(models.map(m => [m.key, m]));
  const groups = new Map();
  for (const m of models) {
    const id = m.maker + " / " + m.name;
    if (!groups.has(id)) groups.set(id, []);
    groups.get(id).push(m);
  }
  const compare = [];
  const MAX_COMPARE = 5;
  const SHOWN = 100;
  const STEP = 7;
  const $ = id => document.getElementById(id);

  /* ---------- formatting ---------- */
  const esc = s => String(s ?? "").replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = v => v == null ? "–" :
    "$" + (v >= 0.01 || v === 0 ? v.toFixed(2) : v.toPrecision(2));
  const pct = v => (100 * v).toFixed(1) + "%";
  const range = (lo, hi) => (100 * lo).toFixed(1) + " to " + (100 * hi).toFixed(1);
  const norm = s => String(s).toLowerCase()
    .replace(/(\d)[-_p](?=\d(?![\d.bkm]))/g, "$1.")   // 3-5 and 4p5 are versions: 3.5, 4.5
    .replace(/(?<!\d)\.|\.(?!\d)/g, " ")              // a dot that is not inside a version splits words
    .replace(/[-_:/@\s]+/g, " ").trim();
  const isTokenPrice = f => /per_token|token_cost/.test(f);

  function value(field, v) {
    if (v == null) return "–";
    if (typeof v === "number" && isTokenPrice(field)) return money(v * 1e6) + " per 1M tokens";
    return esc(typeof v === "object" ? JSON.stringify(v) : v);
  }

  const FLAGS = { bulk: "bulk clean up", unit: "unit fix", reverted: "reverted" };
  const tag = flag => flag ? ' <span class="tag" title="Left out of the real changes only estimates">' +
    FLAGS[flag] + "</span>" : "";

  function change(kind, field, oldV, newV) {
    if (kind === "added") return "Added";
    if (kind === "removed") return "Removed";
    if (kind === "start") return "In the first version";
    if (kind === "deprecation") {
      if (oldV == null) return "Retirement date set";
      if (newV == null) return "Retirement date removed";
      return "Retirement date moved";
    }
    if (oldV == null) return "Price set: " + esc(field);
    if (newV == null) return "Price removed: " + esc(field);
    return "Price change: " + esc(field);
  }

  function table(head, rows, key) {
    const th = head.map(h => "<th>" + h + "</th>").join("");
    const body = rows.map(r => "<tr>" + r.map(c => "<td>" + c + "</td>").join("") + "</tr>").join("");
    return '<div class="scroll"><table data-key="' + key + '"><thead><tr>' + th +
      "</tr></thead><tbody>" + body + "</tbody></table></div>";
  }

  /* ---------- remembered settings (this browser only) ---------- */
  const STORE = "llmledger:page";
  const saved = (() => { try { return JSON.parse(localStorage.getItem(STORE) || "{}"); } catch (e) { return {}; } })();
  let costSettings = () => ({});   // filled in by the prompt cost section
  let onTab = () => {};            // likewise: moves the shared model picker
  function remember() {
    try {
      localStorage.setItem(STORE, JSON.stringify({
        tab: currentTab, grouped: $("view-grouped").checked, maker: $("maker").value, host: $("host").value,
        status: $("status").value, search: $("search").value, compare, weekKind, weekReal,
        topN: $("top-n").value, topGrouped: $("top-grouped").checked, ...costSettings(),
      }));
    } catch (e) { /* storage off: settings are just not remembered */ }
  }

  /* ---------- one model's outlook ---------- */
  function chanceRow(m, horizon) {
    if (m.status !== "listed" || !m.added || m.exit || m.age == null) return null;
    const group = D.curves[m.host] ? m.host : "all";
    const start = Math.floor(m.age / STEP) * STEP;
    return (D.curves[group][horizon] || []).find(r => r[0] === start) || null;
  }
  const chance = (m, horizon) => { const r = chanceRow(m, horizon); return r ? pct(r[2]) : "–"; };

  const modelLink = m => '<a href="#" data-model="' + esc(m.key) + '">' + esc(m.key) + "</a>";
  const groupLink = id => '<a href="#" data-group="' + esc(id) + '">' + esc(id) + "</a>";

  /* ---------- tabs ---------- */
  const TABS = ["lookup", "cost", "value", "week", "top", "overview"];
  let currentTab = "lookup";
  function showTab(name) {
    if (!TABS.includes(name)) name = "lookup";
    currentTab = name;
    for (const t of TABS) {
      $("tab-" + t).hidden = t !== name;
      document.querySelector('[data-tab="' + t + '"]').setAttribute("aria-selected", t === name);
    }
    onTab(name);
  }
  document.querySelectorAll("[data-tab]").forEach(b =>
    b.addEventListener("click", () => {
      history.replaceState(null, "", "#" + b.dataset.tab); showTab(b.dataset.tab); remember();
    }));
  showTab(location.hash.slice(1) || saved.tab);

  /* ---------- look up ---------- */
  function fillSelect(select, counts, all) {
    const items = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    select.innerHTML = '<option value="">' + all + "</option>" +
      items.map(([k, n]) => '<option value="' + esc(k) + '">' + esc(k || "unknown") + " (" + n + ")</option>").join("");
  }
  const count = key => { const c = new Map(); for (const m of models) c.set(m[key], (c.get(m[key]) || 0) + 1); return c; };
  fillSelect($("maker"), count("maker"), "Any maker");
  fillSelect($("host"), count("host"), "Any host");

  const grouped = () => $("view-grouped").checked;

  function matches(m, words, maker, host, status) {
    if (maker && m.maker !== maker) return false;
    if (host && m.host !== host) return false;
    if (status && m.status !== status) return false;
    const hay = norm(m.key + " " + m.name + " " + m.host + " " + m.maker).split(" ");
    return words.every(w => hay.some(token => token.startsWith(w)));
  }

  function renderResults() {
    const words = norm($("search").value).split(" ").filter(Boolean);
    const maker = $("maker").value, host = $("host").value, status = $("status").value;
    const hits = models.filter(m => matches(m, words, maker, host, status));
    let html;
    if (grouped()) {
      const ids = [...new Set(hits.map(m => m.maker + " / " + m.name))];
      const rows = ids.slice(0, SHOWN).map(id => {
        const all = groups.get(id), listed = all.filter(m => m.status === "listed");
        const prices = f => listed.map(m => m[f]).filter(v => v != null);
        const span = f => { const p = prices(f); return p.length ? money(Math.min(...p)) + (Math.min(...p) !== Math.max(...p) ? " to " + money(Math.max(...p)) : "") : "–"; };
        return [groupLink(id), all.length, new Set(all.map(m => m.host)).size, listed.length,
          span("input"), span("output"), all.reduce((s, m) => s + m.repriced, 0),
          all.map(m => m.last).sort().pop()];
      });
      html = '<p class="muted">' + ids.length.toLocaleString() + " models match" +
        (ids.length > SHOWN ? "; showing the first " + SHOWN + ". Narrow the search to see more." : ".") +
        " Grouped by naming rules, which can be wrong; switch to <b>As listed</b> to see LiteLLM's own names.</p>" +
        table(["Model (grouped)", "Listings", "Hosts", "Listed now", "Input $/1M", "Output $/1M", "Price changes", "Last change"], rows, "results-grouped");
    } else {
      const rows = hits.slice(0, SHOWN).map(m => [
        '<input type="checkbox" data-compare="' + esc(m.key) + '"' + (compare.includes(m.key) ? " checked" : "") +
        ' aria-label="Compare ' + esc(m.key) + '">',
        modelLink(m), esc(m.host), esc(m.maker), m.status, money(m.input), money(m.output),
        chance(m, "90"), chance(m, "365"), m.repriced, m.last]);
      html = '<p class="muted">' + hits.length.toLocaleString() + " listings match" +
        (hits.length > SHOWN ? "; showing the first " + SHOWN + ". Narrow the search to see more." : ".") + "</p>" +
        table(["Compare", "Model as listed", "Host", "Maker", "Status", "Input $/1M", "Output $/1M",
          "Price change chance, 90 days", "Price change chance, 1 year", "Price changes", "Last change"],
        rows, "results-listed") +
        '<p class="muted">The chances are shown for listed models that have not changed since they were added; ' +
        "click a model for the full outlook with ranges.</p>";
    }
    $("results").innerHTML = html;
  }

  function outlookFor(m) {
    if (m.status !== "listed") return "<p>No longer listed, so there is no outlook.</p>";
    if (!m.added) return "<p>Listed before the history starts (September 2023), so its age is unknown and there is no outlook.</p>";
    if (m.exit) return "<p>This model has already had its first change (" + esc(m.exit) +
      "). The outlook covers a model's first change only.</p>";
    if (m.age == null) return "<p>No outlook available.</p>";
    const group = D.curves[m.host] ? m.host : "all";
    const parts = [];
    for (const h of ["90", "365"]) {
      const row = chanceRow(m, h);
      const label = h === "90" ? "next 90 days" : "next year";
      if (!row) { parts.push("<li>" + label + ": not enough models of this age to estimate.</li>"); continue; }
      const cell = i => pct(row[i]) + ' <span class="muted">(' + range(row[i + 1], row[i + 2]) + ")</span>";
      parts.push("<li><b>" + label + ":</b> price change " + cell(2) + ", retirement date " + cell(5) +
        ", removed " + cell(8) + ", none of these " + cell(11) +
        ' <span class="muted">· ' + row[1].toLocaleString() + " models still followed at the end</span></li>");
    }
    const who = group === "all" ? "all models (this host has too few models for its own estimate)" : "models hosted on " + esc(group);
    return "<p>This model is " + Math.round(m.age) + " days old and has not changed since it was added. " +
      "Among " + who + " that reached this age without a change:</p><ul>" + parts.join("") +
      '</ul><p class="muted">Aalen-Johansen estimates conditional on reaching this age, with 95% bootstrap intervals. ' +
      "They describe what usually happens to entries in LiteLLM's catalogue, not a forecast for this model alone.</p>";
  }

  function showModel(key) {
    const m = byKey.get(key);
    if (!m) return;
    const id = m.maker + " / " + m.name;
    const events = (D.events[key] || []).slice().reverse().map(e => [
      e[0], change(e[1], e[2], e[3], e[4]) + tag(e[5]), value(e[2], e[3]), value(e[2], e[4])]);
    $("detail").innerHTML =
      "<h3>" + esc(key) + "</h3>" +
      '<p class="muted">Host <b>' + esc(m.host || "unknown") + "</b> · grouped as " + groupLink(id) +
      " · " + esc(m.mode || "mode unknown") + " · <b>" + m.status + "</b></p>" +
      '<div class="facts">' +
      "<div><span>Added</span>" + (m.added || "before Sept 2023") + "</div>" +
      "<div><span>Removed</span>" + (m.removed || "–") + "</div>" +
      "<div><span>Retirement date</span>" + esc(m.retire || "–") + "</div>" +
      "<div><span>Input per 1M tokens</span>" + money(m.input) + "</div>" +
      "<div><span>Output per 1M tokens</span>" + money(m.output) + "</div>" +
      "<div><span>Price changes</span>" + m.repriced + "</div></div>" +
      '<p><button type="button" data-add="' + esc(key) + '">Add to compare</button></p>' +
      "<h4>Outlook</h4>" + outlookFor(m) +
      "<h4>Timeline</h4>" + table(["Date", "Change", "Before", "After"], events, "timeline");
    $("detail").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function showGroup(id) {
    const all = groups.get(id);
    if (!all) return;
    const rows = all.map(m => [modelLink(m), esc(m.host), m.status, money(m.input), money(m.output), m.repriced, m.last]);
    $("detail").innerHTML = "<h3>" + esc(id) + "</h3>" +
      '<p class="muted">' + all.length + " listings on " + new Set(all.map(m => m.host)).size + " hosts, " +
      all.filter(m => m.status === "listed").length + " listed now. Grouped by naming rules, which can be wrong: " +
      "every listing is shown below under LiteLLM's own name.</p>" +
      table(["Model as listed", "Host", "Status", "Input $/1M", "Output $/1M", "Price changes", "Last change"], rows, "group-listings");
    $("detail").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderCompare() {
    const box = $("compare");
    if (!compare.length) { box.innerHTML = ""; return; }
    const rows = compare.map(k => byKey.get(k)).filter(Boolean).map(m => {
      return [modelLink(m), esc(m.host), m.status, m.added || "before Sept 2023", money(m.input), money(m.output),
        m.repriced, m.last, esc(m.retire || "–"), chance(m, "90"), chance(m, "365"),
        '<button type="button" data-remove="' + esc(m.key) + '">Remove</button>'];
    });
    box.innerHTML = "<h3>Compare (" + compare.length + " of " + MAX_COMPARE + ")</h3>" +
      table(["Model", "Host", "Status", "Added", "Input $/1M", "Output $/1M", "Price changes", "Last change",
        "Retirement date", "Price change chance, 90 days", "Price change chance, 1 year", ""],
        rows, "compare") +
      '<p><button type="button" id="clear-compare">Clear</button></p>';
  }

  function toggleCompare(key, on) {
    const at = compare.indexOf(key);
    if (on && at < 0) {
      if (compare.length >= MAX_COMPARE) { alertBox("You can compare up to " + MAX_COMPARE + " models."); return false; }
      compare.push(key);
    }
    if (!on && at >= 0) compare.splice(at, 1);
    renderCompare();
    remember();
    return true;
  }

  function alertBox(text) {
    $("notice").textContent = text;
    setTimeout(() => { $("notice").textContent = ""; }, 4000);
  }

  document.addEventListener("click", e => {
    const t = e.target;
    if (t.dataset.model) { e.preventDefault(); showModel(t.dataset.model); }
    else if (t.dataset.group) { e.preventDefault(); showGroup(t.dataset.group); }
    else if (t.dataset.add) { toggleCompare(t.dataset.add, true); renderResults(); }
    else if (t.dataset.remove) { toggleCompare(t.dataset.remove, false); renderResults(); }
    else if (t.id === "clear-compare") { compare.length = 0; renderCompare(); renderResults(); remember(); }
  });
  document.addEventListener("change", e => {
    const t = e.target;
    if (t.dataset.compare) { if (!toggleCompare(t.dataset.compare, t.checked)) t.checked = false; }
  });
  ["search", "maker", "host", "status", "view-listed", "view-grouped"].forEach(id =>
    $(id).addEventListener("input", () => { renderResults(); remember(); }));
  if (saved.grouped) $("view-grouped").checked = true;
  for (const id of ["maker", "host", "status", "search"]) {
    if (typeof saved[id] === "string" && (id === "search" || [...$(id).options].some(o => o.value === saved[id]))) {
      $(id).value = saved[id];
    }
  }
  for (const k of saved.compare || []) if (byKey.has(k) && compare.length < MAX_COMPARE) compare.push(k);
  renderCompare();
  renderResults();

  /* ---------- prompt cost and best value ---------- */
  // The prompt text never leaves this page and is not remembered; only the numbers are.
  const C = window.LLMCOST;
  const SKILL_LABELS = { vision: "Read images", pdf: "Read PDFs", audio: "Hear audio", video: "Watch video",
    tools: "Use tools", reasoning: "Think step by step", web: "Search the web", schema: "Return JSON",
    cache: "Cache prompts", computer: "Use a computer" };
  const WANTS = {
    text: { noun: "text answer", count: null, unit: null },
    image: { noun: ["image", "images"], count: "Images", unit: ["Price per image", 1] },
    video: { noun: ["second of video", "seconds of video"], count: "Seconds of video", unit: ["Price per second", 1] },
    speech: { noun: ["character to read aloud", "characters to read aloud"], count: "Characters to read aloud",
      unit: ["Price per 1,000 characters", 1000] },
  };
  const listed = models.filter(m => m.status === "listed");
  const dollars = v => v == null ? "–" : v === 0 ? "$0" : "$" + (v >= 1
    ? v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : v.toFixed(Math.min(20, 2 - Math.floor(Math.log10(v)))));
  const whole = (id, low) => Math.max(low, Math.floor(Number($(id).value) || 0));
  const amount = id => Math.max(0, Number($(id).value) || 0);
  const familyKey = m => { const [f, v] = C.familyOf(m.name); return [m.maker + " / " + f, m.maker + " / " + f + " / " + v, f, v]; };
  const pick = { makers: null, families: null, versions: null, hosts: null };   // null means all
  for (const k of Object.keys(pick)) if (Array.isArray(saved["pick_" + k]) && saved["pick_" + k].length) pick[k] = new Set(saved["pick_" + k]);
  let costAll = false;

  function query(want) {
    const len = $("cost-len").value;
    return {
      want: want || $("cost-want").value, inTok: whole("cost-in", 0),
      outTok: len === "custom" ? whole("cost-out", 0) : C.ANSWERS[len].tokens,
      images: amount("att-images"), pages: amount("att-pages"),
      audioSeconds: amount("att-audio") * 60, videoSeconds: amount("att-video") * 60,
      count: whole("cost-count", 0), calls: whole("cost-calls", 1),
    };
  }
  const needs = () => [...document.querySelectorAll("#skill-boxes input:checked")].map(b => b.value);
  const eligible = (m, want) => C.priceFor(m, { want, inTok: 0, outTok: 0, count: 1 }) != null;
  function passes(m, q, words) {
    if (pick.makers && !pick.makers.has(m.maker)) return false;
    if (pick.hosts && !pick.hosts.has(m.host)) return false;
    const [fam, ver] = familyKey(m);
    if (pick.families && !pick.families.has(fam)) return false;
    if (pick.versions && !pick.versions.has(ver)) return false;
    if (q.want === "text") {
      const size = Number($("cost-size").value);
      if (size && !(m.size >= size)) return false;
      if (!needs().every(s => (m.skills || []).includes(s))) return false;
    }
    return matches(m, words, "", "", "");
  }
  function priced(q, search = true) {
    const words = search ? norm($("cost-search").value).split(" ").filter(Boolean) : [];
    const free = $("cost-free").checked;
    let hidden = 0;
    const rows = [];
    for (const m of listed) {
      if (!passes(m, q, words)) continue;
      const cost = C.priceFor(m, q);
      if (cost == null) continue;
      if (cost === 0 && !free) { hidden++; continue; }
      rows.push({ m, cost });
    }
    return { rows, hidden };
  }
  function describe(q) {
    if (q.want !== "text") return q.count.toLocaleString() + " " + WANTS[q.want].noun[q.count === 1 ? 0 : 1];
    const extra = [["images", "image"], ["pages", "PDF page"]].filter(([k]) => q[k] > 0)
      .map(([k, n]) => q[k] + " " + n + (q[k] === 1 ? "" : "s"))
      .concat(q.audioSeconds > 0 ? [q.audioSeconds / 60 + " min of audio"] : [])
      .concat(q.videoSeconds > 0 ? [q.videoSeconds / 60 + " min of video"] : []);
    const must = needs().map(s => SKILL_LABELS[s].toLowerCase());
    return q.inTok.toLocaleString() + " prompt tokens and " + q.outTok.toLocaleString() + " answer tokens" +
      (extra.length ? ", with " + extra.join(", ") : "") + (must.length ? "; must " + must.join(", ") : "");
  }

  // ----- makers, models, versions and hosts: All or some -----
  function renderPick() {
    const want = currentTab === "value" ? "text" : $("cost-want").value;
    const pool = listed.filter(m => eligible(m, want));
    const counts = (rows, keyOf) => { const c = new Map(); for (const m of rows) { const k = keyOf(m); c.set(k, (c.get(k) || 0) + 1); } return c; };
    const list = (id, level, counter, show) => {
      const items = [...counter.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1));
      const chosen = pick[level];
      $(id).innerHTML = '<label><input type="checkbox" data-pick="' + level + '" value=""' + (chosen ? "" : " checked") +
        "> <b>All</b></label>" + items.map(([k, n]) => '<label><input type="checkbox" data-pick="' + level +
        '" value="' + esc(k) + '"' + (chosen && chosen.has(k) ? " checked" : "") + "> " + show(k) + ' <span class="muted">' + n + "</span></label>").join("");
    };
    list("pick-makers", "makers", counts(pool, m => m.maker), esc);
    const inMakers = pool.filter(m => !pick.makers || pick.makers.has(m.maker));
    list("pick-families", "families", counts(inMakers, m => familyKey(m)[0]), k => esc(k.split(" / ")[1]));
    const inFamilies = inMakers.filter(m => !pick.families || pick.families.has(familyKey(m)[0]));
    list("pick-versions", "versions", counts(inFamilies, m => familyKey(m)[1]),
      k => { const [, f, v] = k.split(" / "); return esc(f) + " " + (v ? esc(v) : '<span class="muted">(no number)</span>'); });
    list("pick-hosts", "hosts", counts(pool, m => m.host), k => esc(k || "unknown"));
    const n = Object.values(pick).filter(Boolean).length;
    $("pick-summary").textContent = "Choose makers, models, versions and hosts (" + (n ? n + " narrowed" : "all") + ")";
  }
  $("pick").addEventListener("change", e => {
    const level = e.target.dataset.pick;
    if (!level) return;
    if (e.target.value === "") pick[level] = null;
    else {
      const set = pick[level] || new Set();
      if (e.target.checked) set.add(e.target.value); else set.delete(e.target.value);
      pick[level] = set.size ? set : null;
    }
    if (level === "makers") { pick.families = null; pick.versions = null; }
    if (level === "families") pick.versions = null;
    costAll = false; renderPick(); renderCost(); renderValue(); remember();
  });

  // ----- prompt cost -----
  function renderCost() {
    const q = query();
    const want = WANTS[q.want];
    document.querySelectorAll(".for-text").forEach(el => { el.hidden = q.want !== "text"; });
    document.querySelectorAll(".for-media").forEach(el => { el.hidden = q.want === "text"; });
    $("cost-out-box").hidden = q.want !== "text" || $("cost-len").value !== "custom";
    if (want.count) $("cost-count-label").textContent = want.count;
    const every = $("cost-every").checked;
    const { rows, hidden } = priced(q);
    const ranked = every ? C.cheapestPerGroup(rows, r => r.m.key, r => r.cost)
      : C.cheapestPerGroup(rows, r => r.m.maker + " / " + r.m.name, r => r.cost);
    const shown = costAll ? ranked : ranked.slice(0, SHOWN);
    const timesLabel = q.calls === 1 ? "Cost for 1 time" : "Cost for " + q.calls.toLocaleString() + " times";
    const priceHead = want.unit ? [want.unit[0]] : ["Input $/1M", "Output $/1M"];
    const body = shown.map((r, i) => {
      const m = r.row.m;
      const start = every ? [i + 1, modelLink(m), esc(m.host)]
        : [i + 1, groupLink(r.id), modelLink(m), groups.get(r.id).filter(g => g.status === "listed").length];
      const price = want.unit ? [dollars(C.priceFor(m, { want: q.want, count: want.unit[1] }))] : [money(m.input), money(m.output)];
      return start.concat(price, [dollars(r.cost), dollars(r.cost * q.calls), chance(m, "90"), esc(m.retire || "–")]);
    });
    const head = (every ? ["Rank", "Model as listed", "Host"] : ["Rank", "Model (grouped)", "Cheapest listing", "Listings"])
      .concat(priceHead, ["Cost per time", timesLabel, "Price change chance, 90 days", "Retirement date"]);
    $("cost-note").innerHTML = ranked.length.toLocaleString() + (every ? " listings" : " models") + " for " +
      esc(describe(q)) + ", cheapest first." + (hidden ? " " + hidden.toLocaleString() + " free listings (price 0) are hidden." : "");
    $("cost-table").innerHTML = table(head, body, (every ? "cost-listed-" : "cost-grouped-") + q.want) +
      (ranked.length > shown.length ? '<p><button type="button" id="cost-all">Show all ' +
        ranked.length.toLocaleString() + "</button></p>" : "");
  }

  // ----- best value (Arena ratings) -----
  function renderValue() {
    const A = D.arena;
    if (!A) {
      $("value-best").innerHTML = "<p>Arena ratings could not be loaded with today's data. The other tabs are not affected.</p>";
      $("value-table").innerHTML = ""; return;
    }
    const task = $("value-task").value;
    const q = query("text");
    const cheapest = new Map();
    for (const r of priced(q, false).rows) {
      const id = r.m.maker + " / " + r.m.name, kept = cheapest.get(id);
      if (!kept || r.cost < kept.cost) cheapest.set(id, r);
    }
    let rows = (A.tasks[task] || []).filter(a => cheapest.has(a[0])).map(a => ({
      id: a[0], arenaName: a[1], rating: a[2], low: a[3], high: a[4], votes: a[5], ...cheapest.get(a[0]) }));
    const best = C.bestValue(rows);
    const top = rows[0];
    rows.forEach(r => { r.tied = top && r.high >= top.low; });
    if ($("value-tied").checked) rows = rows.filter(r => r.tied);
    $("value-using").textContent = "Priced for " + describe(q) + ", " + q.calls.toLocaleString() +
      (q.calls === 1 ? " time" : " times") + ". Change these on the Prompt cost tab.";
    $("value-best").innerHTML = best ? "<p><b>Best value: " + esc(best.id) + "</b> on " + esc(best.m.host) + ", " +
      dollars(best.cost) + " per time. Its rating (" + best.rating.toFixed(0) + ") cannot be told apart from the top model, " +
      esc(top.id) + " (" + top.rating.toFixed(0) + ", " + dollars(top.cost) + ")" +
      (top.cost > best.cost ? ", which costs " + (top.cost / best.cost).toFixed(1) + " times as much" : "") + ".</p>"
      : "<p>No rated model matches these choices.</p>";
    $("value-table").innerHTML = table(["Rank", "Model (grouped)", "Arena rating", "Votes", "Cheapest listing",
      "Cost per time", "Tied with the top", "Price change chance, 90 days"], rows.slice(0, 200).map((r, i) => [
      i + 1, groupLink(r.id) + (r === best ? ' <span class="tag">best value</span>' : "") + "<small>" + esc(r.arenaName) + "</small>",
      r.rating.toFixed(0) + "<small>" + r.low.toFixed(0) + " to " + r.high.toFixed(0) + "</small>",
      r.votes.toLocaleString(), modelLink(r.m), dollars(r.cost), r.tied ? "yes" : "–", chance(r.m, "90")]), "value-" + task);
    $("value-credit").innerHTML = 'Ratings: <a href="' + esc(A.source) + '">Arena leaderboard</a>, published ' +
      esc(A.date) + ", licensed CC BY 4.0. " + A.matched + " of " + A.total +
      " Arena models were matched to the catalogue by naming rules; the rest are not shown. " +
      "A rating is for the version Arena tested (shown under each name); the price is for the cheapest listing of that model.";
  }

  // ----- set up, restore and wire -----
  $("cost-len").innerHTML = Object.entries(C.ANSWERS).map(([k, a]) =>
    '<option value="' + k + '">' + esc(a.label) + " (" + a.tokens.toLocaleString() + " tokens)</option>").join("") +
    '<option value="custom">Custom</option>';
  $("cost-len").value = "medium";
  $("skill-boxes").innerHTML = Object.entries(SKILL_LABELS).map(([k, label]) =>
    '<label class="check"><input type="checkbox" value="' + k + '"> ' + esc(label) + "</label>").join(" ");
  if (D.arena) {
    $("value-task").innerHTML = D.arena.labels.map(([k, label]) => '<option value="' + k + '">' + esc(label) + "</option>").join("");
  }
  const restore = (id, ok) => { if (ok(saved["c_" + id])) $(id).value = saved["c_" + id]; };
  const isCount = v => /^\d+(\.\d+)?$/.test(String(v ?? ""));
  ["cost-out", "cost-count", "cost-calls", "att-images", "att-pages", "att-audio", "att-video"].forEach(id => restore(id, isCount));
  restore("cost-want", v => v in WANTS);
  restore("cost-len", v => v in C.ANSWERS || v === "custom");
  restore("cost-size", v => [...$("cost-size").options].some(o => o.value === v));
  restore("value-task", v => [...$("value-task").options].some(o => o.value === v));
  if (typeof saved.c_search === "string") $("cost-search").value = saved.c_search;
  if (saved.c_every) $("cost-every").checked = true;
  if (saved.c_free) $("cost-free").checked = true;
  if (saved.c_tied) $("value-tied").checked = true;
  for (const box of document.querySelectorAll("#skill-boxes input")) box.checked = (saved.c_needs || []).includes(box.value);
  costSettings = () => {
    const out = { c_search: $("cost-search").value, c_every: $("cost-every").checked, c_free: $("cost-free").checked,
      c_tied: $("value-tied").checked, c_needs: needs() };
    for (const id of ["cost-out", "cost-count", "cost-calls", "att-images", "att-pages", "att-audio", "att-video",
      "cost-want", "cost-len", "cost-size", "value-task"]) out["c_" + id] = $(id).value;
    for (const k of Object.keys(pick)) out["pick_" + k] = pick[k] ? [...pick[k]] : [];
    return out;
  };
  $("cost-text").addEventListener("input", () => {
    $("cost-in").value = C.estimateTokens($("cost-text").value);
    if ($("cost-want").value === "speech") $("cost-count").value = Array.from($("cost-text").value).length;
    costAll = false; renderCost(); renderValue();
  });
  $("tab-cost").addEventListener("input", e => {
    if (e.target.id === "cost-text" || e.target.dataset.pick !== undefined) return;
    if (e.target.id === "cost-want") {
      const defaults = { image: 1, video: 10, speech: Math.max(1000, Array.from($("cost-text").value).length) };
      if (defaults[e.target.value]) $("cost-count").value = defaults[e.target.value];
      pick.makers = pick.families = pick.versions = pick.hosts = null;
      renderPick();
    }
    costAll = false; renderCost(); renderValue(); remember();
  });
  $("tab-value").addEventListener("input", e => {
    if (e.target.dataset.pick !== undefined) return;
    renderValue(); remember();
  });
  $("cost-table").addEventListener("click", e => { if (e.target.id === "cost-all") { costAll = true; renderCost(); } });
  onTab = name => {
    if (name !== "cost" && name !== "value") return;
    document.querySelector("#tab-" + name + " [data-pick-slot]").appendChild($("pick"));
    renderPick();
  };
  onTab(currentTab);
  renderPick();
  renderCost();
  renderValue();

  /* ---------- licences, checked on every build ---------- */
  if (D.licences) {
    const used = D.licences.filter(r => r.role !== "tests");
    $("licences").textContent = "Licences checked when this page was built: " +
      used.map(r => r.source + " " + (r.licence || "unchecked") + " (" + r.status + ")").join(", ") + ".";
  }

  /* ---------- last 7 days ---------- */
  const KINDS = { price: "Price changes", deprecation: "Retirement dates", removed: "Removed", added: "Added" };
  let weekKind = KINDS[saved.weekKind] ? saved.weekKind : "", weekAll = false;
  let weekReal = !!saved.weekReal;
  function renderWeek() {
    const pool = D.recent.filter(r => !weekReal || !r[6]);
    const counts = {};
    for (const r of pool) counts[r[2]] = (counts[r[2]] || 0) + 1;
    $("week-filters").innerHTML = ['<button type="button" data-kind=""' + (weekKind === "" ? ' aria-pressed="true"' : "") +
      ">All (" + pool.length + ")</button>"].concat(Object.entries(KINDS).map(([k, label]) =>
      '<button type="button" data-kind="' + k + '"' + (weekKind === k ? ' aria-pressed="true"' : "") + ">" +
      label + " (" + (counts[k] || 0) + ")</button>")).join(" ") +
      ' <label class="check"><input type="checkbox" id="week-real"' + (weekReal ? " checked" : "") +
      "> Hide corrections and bulk clean ups</label>";
    const rows = pool.filter(r => !weekKind || r[2] === weekKind).slice().reverse();
    const shown = weekAll ? rows : rows.slice(0, SHOWN);
    $("week-table").innerHTML = table(["Date", "Model", "Host", "Change", "Before", "After"], shown.map(r => {
      const m = byKey.get(r[1]) || { key: r[1], host: "" };
      return [r[0], modelLink(m), esc(m.host), change(r[2], r[3], r[4], r[5]) + tag(r[6]), value(r[3], r[4]), value(r[3], r[5])];
    }), "week") + (rows.length > shown.length ? '<p><button type="button" id="week-all">Show all ' +
      rows.length.toLocaleString() + "</button></p>" : "");
  }
  $("week-filters").addEventListener("change", e => {
    if (e.target.id !== "week-real") return;
    weekReal = e.target.checked; weekAll = false; renderWeek(); remember();
  });
  $("week-filters").addEventListener("click", e => {
    if (e.target.dataset.kind === undefined) return;
    weekKind = e.target.dataset.kind; weekAll = false; renderWeek(); remember();
  });
  $("week-table").addEventListener("click", e => { if (e.target.id === "week-all") { weekAll = true; renderWeek(); } });
  renderWeek();

  /* ---------- top lists ---------- */
  function renderTop() {
    const n = $("top-n").value === "all" ? Infinity : Number($("top-n").value);
    let rows;
    if ($("top-grouped").checked) {
      rows = [...groups.entries()].map(([id, all]) => [id, all.reduce((s, m) => s + m.repriced, 0), all])
        .filter(r => r[1] > 0).sort((a, b) => b[1] - a[1]).slice(0, n)
        .map((r, i) => [i + 1, groupLink(r[0]), r[2].length, r[1], r[2].map(m => m.last).sort().pop()]);
      $("top-repriced").innerHTML = table(["Rank", "Model (grouped)", "Listings", "Price changes", "Last change"], rows, "top-grouped");
    } else {
      rows = models.filter(m => m.repriced > 0).sort((a, b) => b.repriced - a.repriced).slice(0, n)
        .map((m, i) => [i + 1, modelLink(m), esc(m.host), m.repriced, m.last]);
      $("top-repriced").innerHTML = table(["Rank", "Model as listed", "Host", "Price changes", "Last change"], rows, "top-listed");
    }
    const ranked = D.providers.slice().sort((a, b) => b[3] - a[3]).slice(0, n).map((p, i) => [
      i + 1, esc(p[0]), p[1].toLocaleString(), p[2].toLocaleString(),
      pct(p[3]) + "<small>" + range(p[4], p[5]) + "</small>",
      pct(p[6]) + "<small>" + range(p[7], p[8]) + "</small>",
      pct(p[9]) + "<small>" + range(p[10], p[11]) + "</small>"]);
    $("top-hosts").innerHTML = table(["Rank", "Host", "Models followed", "Still followed at 1 year",
      "Price change within 1 year", "Retirement date within 1 year", "Removed within 1 year"], ranked, "top-hosts");
  }
  ["top-n", "top-listed", "top-grouped"].forEach(id => $(id).addEventListener("input", () => { renderTop(); remember(); }));
  if (["10", "20", "all"].includes(saved.topN)) $("top-n").value = saved.topN;
  if (saved.topGrouped) $("top-grouped").checked = true;
  renderTop();
})();
