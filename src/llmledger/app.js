/* llmledger results page: model lookup, compare, last 7 days, top lists.
   Reads window.LLMLEDGER, written by page.py from the daily pipeline. */
(function () {
  const D = window.LLMLEDGER;
  if (!D) return;
  const FIELDS = ["key", "maker", "name", "host", "mode", "status", "added",
    "removed", "retire", "input", "output", "repriced", "last", "exit", "age"];
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
  const norm = s => String(s).toLowerCase().replace(/[-_.:/@\s]+/g, " ").trim();
  const isTokenPrice = f => /per_token|token_cost/.test(f);

  function value(field, v) {
    if (v == null) return "–";
    if (typeof v === "number" && isTokenPrice(field)) return money(v * 1e6) + " per 1M tokens";
    return esc(typeof v === "object" ? JSON.stringify(v) : v);
  }

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
  function remember() {
    try {
      localStorage.setItem(STORE, JSON.stringify({
        tab: currentTab, grouped: $("view-grouped").checked, maker: $("maker").value, host: $("host").value,
        status: $("status").value, search: $("search").value, compare, weekKind,
        topN: $("top-n").value, topGrouped: $("top-grouped").checked,
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
  const TABS = ["lookup", "week", "top", "overview"];
  let currentTab = "lookup";
  function showTab(name) {
    if (!TABS.includes(name)) name = "lookup";
    currentTab = name;
    for (const t of TABS) {
      $("tab-" + t).hidden = t !== name;
      document.querySelector('[data-tab="' + t + '"]').setAttribute("aria-selected", t === name);
    }
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
      e[0], change(e[1], e[2], e[3], e[4]), value(e[2], e[3]), value(e[2], e[4])]);
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

  /* ---------- last 7 days ---------- */
  const KINDS = { price: "Price changes", deprecation: "Retirement dates", removed: "Removed", added: "Added" };
  let weekKind = KINDS[saved.weekKind] ? saved.weekKind : "", weekAll = false;
  function renderWeek() {
    const counts = {};
    for (const r of D.recent) counts[r[2]] = (counts[r[2]] || 0) + 1;
    $("week-filters").innerHTML = ['<button type="button" data-kind=""' + (weekKind === "" ? ' aria-pressed="true"' : "") +
      ">All (" + D.recent.length + ")</button>"].concat(Object.entries(KINDS).map(([k, label]) =>
      '<button type="button" data-kind="' + k + '"' + (weekKind === k ? ' aria-pressed="true"' : "") + ">" +
      label + " (" + (counts[k] || 0) + ")</button>")).join(" ");
    const rows = D.recent.filter(r => !weekKind || r[2] === weekKind).slice().reverse();
    const shown = weekAll ? rows : rows.slice(0, SHOWN);
    $("week-table").innerHTML = table(["Date", "Model", "Host", "Change", "Before", "After"], shown.map(r => {
      const m = byKey.get(r[1]) || { key: r[1], host: "" };
      return [r[0], modelLink(m), esc(m.host), change(r[2], r[3], r[4], r[5]), value(r[3], r[4]), value(r[3], r[5])];
    }), "week") + (rows.length > shown.length ? '<p><button type="button" id="week-all">Show all ' +
      rows.length.toLocaleString() + "</button></p>" : "");
  }
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
