/* llmledger Trends: the replaying line charts (Arena ratings over time and the price race), the cost vs
   quality chart on Ask, new arrivals and the latest changes. Reads window.LLMLEDGER (data.trends, written
   by trends.py). app.js calls init() once with its helpers. The pure helpers at the top are checked by
   tests/test_trends_js.py. */
(function (root) {
  /* ---------- pure helpers ---------- */
  const DAY = 864e5;
  const dayOf = text => Date.UTC(+text.slice(0, 4), +text.slice(5, 7) - 1, +text.slice(8, 10)) / DAY;
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const dateText = d => { const t = new Date(d * DAY); return MONTHS[t.getUTCMonth()] + " " + t.getUTCDate() + ", " + t.getUTCFullYear(); };
  const monthText = d => { const t = new Date(d * DAY); return MONTHS[t.getUTCMonth()] + " " + t.getUTCFullYear(); };
  const STALE = 30;      // days a line is still drawn after its last leaderboard

  // The share of people who would pick the higher rated of two models, from the gap in their ratings.
  const odds = gap => 1 / (1 + Math.pow(10, -gap / 400));

  // Points nobody beats on both: no other point is cheaper (lower x) and rated higher (higher y).
  // points: [{x, y, ...}]. Returns them cheapest first.
  function frontier(points) {
    const sorted = points.filter(p => p.x > 0 && Number.isFinite(p.y)).slice()
      .sort((a, b) => a.x - b.x || b.y - a.y);
    const out = [];
    let best = -Infinity;
    for (const p of sorted) if (p.y > best) { out.push(p); best = p.y; }
    return out;
  }

  // A series' value at day t: straight between its points, held for STALE days after the last one,
  // nothing before the first. step: hold each value until the next point (prices).
  function valueAt(pts, t, step) {
    if (!pts.length || t < pts[0][0]) return null;
    const last = pts[pts.length - 1];
    if (t >= last[0]) return t - last[0] <= STALE ? last[1] : null;
    let lo = 0, hi = pts.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (pts[mid][0] <= t) lo = mid; else hi = mid; }
    const a = pts[lo], b = pts[hi];
    if (step || a[1] == null || b[1] == null) return a[1];
    return a[1] + (b[1] - a[1]) * (t - a[0]) / (b[0] - a[0]);
  }
  // The point in force at day t (the last one at or before it), or null.
  function pointAt(pts, t) {
    let found = null;
    for (const p of pts) { if (p[0] <= t) found = p; else break; }
    return found;
  }

  // Labels that would overlap are pushed apart to at least gap pixels, inside [top, bottom].
  // ys: wanted positions. Returns the positions in the same order.
  function spread(ys, gap, top, bottom) {
    const order = ys.map((y, i) => [y, i]).sort((a, b) => a[0] - b[0]);
    const at = order.map(([y]) => Math.min(bottom, Math.max(top, y)));
    for (let i = 1; i < at.length; i++) at[i] = Math.max(at[i], at[i - 1] + gap);
    if (at.length && at[at.length - 1] > bottom) {
      at[at.length - 1] = bottom;
      for (let i = at.length - 2; i >= 0; i--) at[i] = Math.min(at[i], at[i + 1] - gap);
    }
    const out = new Array(ys.length);
    order.forEach(([, i], k) => { out[i] = at[k]; });
    return out;
  }

  // About n round numbers between lo and hi.
  function ticks(lo, hi, n) {
    const span = hi - lo;
    if (!(span > 0)) return [lo];
    const raw = span / Math.max(1, n), mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(k => k * mag).find(s => s >= raw) || 10 * mag;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }
  // Powers of ten (and 2 and 5 times them when there are few) between lo and hi, for a log scale.
  function logTicks(lo, hi) {
    const out = [];
    for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) {
      for (const k of [1, 2, 5]) { const v = k * Math.pow(10, e); if (v >= lo && v <= hi) out.push(v); }
    }
    return out.length > 7 ? out.filter(v => Math.abs(Math.log10(v) % 1) < 1e-9) : out;
  }

  // Models new to the catalogue: grouped models whose first listing is the newest, text models with a price.
  // models: app.js rows ({maker, name, added, status, mode, input, output, host}). Newest first.
  function arrivals(models, n) {
    const by = new Map();
    for (const m of models) {
      const id = m.maker + " / " + m.name;
      if (!by.has(id)) by.set(id, { id, first: m.added || "", old: !m.added, listings: [] });
      const g = by.get(id);
      if (!m.added) g.old = true;
      else if (!g.first || m.added < g.first) g.first = m.added;
      g.listings.push(m);
    }
    const text = m => ["chat", "responses", "completion", ""].includes(m.mode || "");
    return [...by.values()]
      .filter(g => !g.old && g.first && g.listings.some(m => m.status === "listed" && text(m) && m.input > 0 && m.output > 0))
      .sort((a, b) => (a.first < b.first ? 1 : a.first > b.first ? -1 : a.id < b.id ? -1 : 1))
      .slice(0, n);
  }

  // The last days' catalogue changes, newest first: one line per listing and day (its price fields together),
  // and batches (a clean up, or many listings added, removed or priced for the first time on one day) folded into one.
  // recent: data.recent rows [day, key, kind, field, old, new, flag].
  function digest(recent, batch) {
    batch = batch || 4;
    const kindOf = r => (r[6] === "bulk" ? "bulk" : r[2] === "price" && !(r[4] > 0) && r[5] != null ? "set" : r[2]);
    const entries = new Map();
    for (const r of recent) {
      const kind = kindOf(r), k = r[0] + "|" + r[1] + "|" + kind;
      if (!entries.has(k)) entries.set(k, { day: r[0], key: r[1], kind, fields: [], flag: "" });
      const e = entries.get(k);
      e.fields.push({ field: r[3], old: r[4], now: r[5] });
      if (r[6] && r[6] !== "bulk") e.flag = r[6];
    }
    const list = [...entries.values()].sort((a, b) => (a.day < b.day ? 1 : a.day > b.day ? -1 : 0));
    const counts = new Map();
    for (const e of list) { const k = e.day + "|" + e.kind; counts.set(k, (counts.get(k) || 0) + 1); }
    const out = [], folded = new Map();
    for (const e of list) {
      const k = e.day + "|" + e.kind, n = counts.get(k);
      if (["bulk", "added", "removed", "set"].includes(e.kind) && n >= batch) {
        if (!folded.has(k)) { folded.set(k, { day: e.day, kind: e.kind, count: n, keys: [] }); out.push(folded.get(k)); }
        folded.get(k).keys.push(e.key);
      } else out.push(Object.assign(e, { count: 1 }));
    }
    return out;
  }

  const api = { odds, frontier, valueAt, pointAt, spread, ticks, logTicks, arrivals, digest, dayOf };
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.LLMTRENDS = api;

  /* ---------- page parts ---------- */
  const D = root.LLMLEDGER;
  const $ = id => document.getElementById(id);
  let H = null;              // app.js helpers: esc, dollars, taskLabel, openGroup, groupLink, chance
  const NS = "http://www.w3.org/2000/svg";
  const reduced = () => root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const short = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
  const slot = i => (i < 8 ? "var(--s" + (i + 1) + ")" : "var(--muted)");
  const tickMoney = v => "$" + (v >= 1 ? Math.round(v).toLocaleString("en-US") : v >= 0.01 ? v.toFixed(2) : String(+v.toPrecision(1)));
  const svgText = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  function tipBox(host) {
    let tip = host.querySelector(".tip");
    if (!tip) { tip = document.createElement("div"); tip.className = "tip"; tip.hidden = true; host.appendChild(tip); }
    return tip;
  }
  // tip rows: [[value, label, colour]] -> value first, label after, keyed by a short line of the colour
  function fillTip(tip, title, rows) {
    tip.textContent = "";
    const h = document.createElement("div"); h.className = "tip-h"; h.textContent = title; tip.appendChild(h);
    for (const [v, label, colour] of rows) {
      const row = document.createElement("div"); row.className = "tip-r";
      const key = document.createElement("i"); key.style.background = colour || "var(--muted)";
      const b = document.createElement("b"); b.textContent = v;
      const s = document.createElement("span"); s.textContent = label;
      row.append(key, b, s); tip.appendChild(row);
    }
  }
  function placeTip(tip, host, x, y) {
    tip.hidden = false;
    const w = tip.offsetWidth, hw = host.clientWidth;
    tip.style.left = Math.max(0, Math.min(hw - w, x + 14 > hw - w ? x - w - 14 : x + 14)) + "px";
    tip.style.top = Math.max(0, y - 10) + "px";
  }

  /* ---------- the replaying line chart ---------- */
  const T = D && D.trends;
  const S = { view: "open", t: null, playing: false, last: 0, raf: 0, lo: null, hi: null, alpha: new Map(), shown: false };
  const WINDOW = 180, SPEED = 55;   // days in view, days per second of replay
  let days = [], lines = [], makers = [], race = null;
  if (T) {
    days = T.dates.map(dayOf);
    lines = T.lines.map(([n, m, open, flat]) => {
      const pts = [];
      for (let i = 0; i < flat.length; i += 2) pts.push([days[flat[i]], flat[i + 1]]);
      return { id: "l" + n, name: T.names[n], maker: T.makers[m], open: !!open, pts };
    });
    makers = T.best.map(([m, flat]) => {
      const pts = [];
      for (let i = 0; i < flat.length; i += 3) pts.push([days[flat[i]], flat[i + 1], T.names[flat[i + 2]]]);
      return { id: "m" + m, name: T.makers[m], colour: slot(m), pts };
    });
    const col = (i, j) => T.race.filter(r => r[i] != null).map(r => [days[r[0]], r[i], T.names[r[j]], r]);
    race = [
      { id: "p1", name: "Top rated model", colour: slot(0), pts: col(1, 2) },
      { id: "p10", name: "Cheapest of the top 10", colour: slot(1), pts: col(4, 5) },
      { id: "py", name: "Cheapest as good as last year's #1", colour: slot(2), pts: col(6, 7) },
    ];
  }
  const first = () => days[0], lastDay = () => days[days.length - 1];
  function range(view) {
    return view === "price" ? [Math.min(first() + 30, lastDay()), lastDay()] : [Math.min(first() + WINDOW, lastDay()), lastDay()];
  }

  // The series on screen at day t, each { id, name, colour, dash, value, pts, extra }.
  function visible(t) {
    if (S.view === "open") {
      const at = lines.map(l => ({ l, v: valueAt(l.pts, t) })).filter(x => x.v != null).sort((a, b) => b.v - a.v);
      const top = new Set([...at.filter(x => !x.l.open).slice(0, 3), ...at.filter(x => x.l.open).slice(0, 3)].map(x => x.l.id));
      return lines.map(l => ({ id: l.id, name: l.name, colour: l.open ? slot(1) : slot(0), dash: l.open, open: l.open,
        pts: l.pts, value: valueAt(l.pts, t), on: top.has(l.id), sub: l.maker }));
    }
    if (S.view === "makers") {
      const at = makers.map(m => ({ m, v: valueAt(m.pts, t) })).filter(x => x.v != null).sort((a, b) => b.v - a.v).slice(0, 5);
      const top = new Set(at.map(x => x.m.id));
      return makers.map(m => { const p = pointAt(m.pts, t); return { id: m.id, name: m.name, colour: m.colour, pts: m.pts,
        value: valueAt(m.pts, t), on: top.has(m.id), sub: p ? p[2] : "" }; });
    }
    return race.map(r => { const p = pointAt(r.pts, t); return { id: r.id, name: r.name, colour: r.colour, pts: r.pts, step: true,
      value: valueAt(r.pts, t, true), on: true, sub: p ? p[2] : "", row: p ? p[3] : null }; });
  }

  function draw(animating) {
    const box = $("race-chart");
    if (!box || !T) return;
    const W = Math.max(300, box.clientWidth || 720), phone = W < 560;
    const Hh = Math.max(140, Math.round(box.clientHeight) || (phone ? 230 : 250)), labelW = Math.min(phone ? 112 : 190, Math.round(W * 0.3));
    const M = { l: 44, r: labelW + 10, t: 10, b: 24 }, pw = W - M.l - M.r, ph = Hh - M.t - M.b;
    const t = S.t, price = S.view === "price";
    const x0 = price ? first() : t - WINDOW, x1 = price ? lastDay() : t;
    const series = visible(t);
    const k = animating ? 0.14 : 1;
    for (const s of series) {
      const a = S.alpha.get(s.id) ?? 0, want = s.on && s.value != null ? 1 : 0;
      S.alpha.set(s.id, a + (want - a) * k);
    }
    const alpha = s => S.alpha.get(s.id) || 0;
    // Open vs closed: the best closed and the best open rating at each leaderboard in view
    let env = null;
    if (S.view === "open") {
      const marks = days.filter(d => d > x0 && d < x1).concat([x0, x1]).sort((a, b) => a - b);
      const best = open => marks.map(d => {
        let v = null;
        for (const l of lines) if (l.open === open) { const w = valueAt(l.pts, d); if (w != null && (v == null || w > v)) v = w; }
        return [d, v];
      }).filter(p => p[1] != null);
      env = { closed: best(false), open: best(true) };
    }
    // the y range: what is on screen, eased so it glides
    let lo = Infinity, hi = -Infinity;
    if (env) for (const p of env.closed.concat(env.open)) { lo = Math.min(lo, p[1]); hi = Math.max(hi, p[1]); }
    if (price) {
      for (const s of series) for (const p of s.pts) { lo = Math.min(lo, p[1]); hi = Math.max(hi, p[1]); }
      lo = Math.log10(lo * 0.8); hi = Math.log10(hi * 1.25);
    } else {
      for (const s of series) {
        if (alpha(s) < 0.4) continue;
        for (const p of s.pts) if (p[0] >= x0 && p[0] <= x1) { lo = Math.min(lo, p[1]); hi = Math.max(hi, p[1]); }
        if (s.value != null) { lo = Math.min(lo, s.value); hi = Math.max(hi, s.value); }
      }
      if (!Number.isFinite(lo)) { lo = 1000; hi = 1500; }
      const pad = Math.max(6, (hi - lo) * 0.08); lo -= pad; hi += pad;
    }
    S.lo = S.lo == null || !animating ? lo : S.lo + (lo - S.lo) * k;
    S.hi = S.hi == null || !animating ? hi : S.hi + (hi - S.hi) * k;
    const X = d => M.l + pw * (d - x0) / (x1 - x0 || 1);
    const Y = v => M.t + ph * (1 - ((price ? Math.log10(v) : v) - S.lo) / (S.hi - S.lo || 1));
    const out = [];
    // grid and axes
    const yt = price ? logTicks(Math.pow(10, S.lo), Math.pow(10, S.hi)) : ticks(S.lo, S.hi, 4);
    for (const v of yt) {
      const y = Y(v);
      if (y < M.t - 1 || y > M.t + ph + 1) continue;
      out.push('<line class="grid" x1="' + M.l + '" x2="' + (M.l + pw) + '" y1="' + y.toFixed(1) + '" y2="' + y.toFixed(1) + '"/>' +
        '<text class="tick" x="' + (M.l - 6) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="end">' +
        svgText(price ? tickMoney(v) : Math.round(v).toLocaleString("en-US")) + "</text>");
    }
    const start = new Date(x0 * DAY);
    const monthStep = price ? 3 : 1;
    for (let y = start.getUTCFullYear(), m = start.getUTCMonth() + 1; ; m++) {
      const d = Date.UTC(y, m, 1) / DAY;
      if (d > x1) break;
      const mm = new Date(d * DAY).getUTCMonth();
      if (mm % monthStep) continue;
      const x = X(d);
      out.push('<line class="mtick" x1="' + x.toFixed(1) + '" x2="' + x.toFixed(1) + '" y1="' + (M.t + ph) + '" y2="' + (M.t + ph + 4) + '"/>');
      const labelled = price ? mm % (phone ? 12 : 6) === 0 : !phone || mm % 2 === 0;
      if (x > M.l + 16 && x < M.l + pw - 16 && labelled) {
        out.push('<text class="tick" x="' + x.toFixed(1) + '" y="' + (M.t + ph + 16) + '" text-anchor="middle">' +
          (mm === 0 || price ? monthText(d) : MONTHS[mm]) + "</text>");
      }
    }
    out.push('<line class="axis" x1="' + M.l + '" x2="' + (M.l + pw) + '" y1="' + (M.t + ph) + '" y2="' + (M.t + ph) + '"/>');
    out.push('<clipPath id="race-clip"><rect x="' + M.l + '" y="0" width="' + pw + '" height="' + (M.t + ph + 2) + '"/></clipPath><g clip-path="url(#race-clip)">');
    // the gap between the best closed and the best open model, and the two best lines around it
    if (env && env.closed.length > 1 && env.open.length > 1) {
      const xy = p => X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1);
      out.push('<polygon class="gap" points="' + env.closed.map(xy).concat(env.open.slice().reverse().map(xy)).join(" ") + '"/>');
      out.push('<path class="env" d="M' + env.closed.map(xy).join("L") + '" style="stroke:' + slot(0) + '"/>' +
        '<path class="env dash" d="M' + env.open.map(xy).join("L") + '" style="stroke:' + slot(1) + '"/>');
    }
    const heads = [];
    for (const s of series) {
      const a = alpha(s);
      if (a < 0.02) continue;
      const head = price ? t : x1;
      const inside = s.pts.filter(p => p[0] > x0 && p[0] < head);
      const pts = [];
      const v0 = valueAt(s.pts, x0, s.step);
      if (v0 != null) pts.push([x0, v0]);
      for (const p of inside) pts.push([p[0], p[1]]);
      const vh = valueAt(s.pts, head, s.step);
      if (vh != null) pts.push([head, vh]);
      if (pts.length < 2) continue;
      let d = "";
      pts.forEach((p, i) => {
        if (i && s.step) d += "H" + X(p[0]).toFixed(1);
        d += (i ? "L" : "M") + X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1);
      });
      const thin = S.view === "open";       // each model thin, under the two best lines
      out.push('<path class="ln' + (s.dash ? " dash" : "") + (thin ? " thin" : "") + '" d="' + d + '" style="stroke:' + s.colour +
        ";opacity:" + (thin ? 0.6 * a : a).toFixed(2) + '"/>');
      if (vh != null && a > 0.5) heads.push({ s, x: X(head), y: Y(vh), v: vh, a });
    }
    out.push("</g>");
    // a dot at each line's head, and its name in the margin
    const placed = spread(heads.map(h => h.y), 19, M.t + 6, M.t + ph - 2);
    heads.forEach((h, i) => {
      const lx = W - M.r + 14, ly = placed[i];
      out.push('<circle class="head" cx="' + h.x.toFixed(1) + '" cy="' + h.y.toFixed(1) + '" r="4" style="fill:' + h.s.colour + ";opacity:" + h.a.toFixed(2) + '"/>');
      if (price || Math.abs(ly - h.y) > 2 || lx - h.x > 18) {
        out.push('<path class="lead" d="M' + (h.x + 5).toFixed(1) + "," + h.y.toFixed(1) + "L" + (lx - 4) + "," + ly.toFixed(1) + '"/>');
      }
      const text = price ? H.dollars(h.v) + " · " + (h.s.sub || h.s.name) : h.s.name;
      out.push('<g class="pill" style="opacity:' + h.a.toFixed(2) + '"><rect x="' + (lx - 2) + '" y="' + (ly - 9).toFixed(1) + '" width="' + (M.r - 14) +
        '" height="18" rx="9"/><circle cx="' + (lx + 7) + '" cy="' + ly.toFixed(1) + '" r="3.5" style="fill:' + h.s.colour + '"/>' +
        '<text x="' + (lx + 15) + '" y="' + (ly + 4).toFixed(1) + '">' + svgText(short(text, Math.floor((M.r - 34) / 6.2))) + "</text></g>");
    });
    if (S.cross != null && !S.playing) {
      const cx = X(S.cross);
      out.push('<line class="cross" x1="' + cx.toFixed(1) + '" x2="' + cx.toFixed(1) + '" y1="' + M.t + '" y2="' + (M.t + ph) + '"/>');
    }
    let svg = box.querySelector("svg");
    if (!svg) {
      box.innerHTML = "";
      svg = document.createElementNS(NS, "svg");
      svg.setAttribute("role", "img");
      box.appendChild(svg);
      tipBox(box);
      svg.addEventListener("pointermove", hover);
      svg.addEventListener("pointerleave", () => { S.cross = null; box.querySelector(".tip").hidden = true; if (!S.playing) draw(false); });
    }
    svg.setAttribute("viewBox", "0 0 " + W + " " + Hh);
    svg.setAttribute("width", W); svg.setAttribute("height", Hh);
    svg.innerHTML = out.join("");
    S.geom = { X, M, pw, x0, x1, W };
    words(series, t, animating);
  }

  function hover(e) {
    if (S.playing || !S.geom) return;
    const box = $("race-chart"), r = box.getBoundingClientRect(), g = S.geom;
    const px = e.clientX - r.left;
    if (px < g.M.l || px > g.M.l + g.pw) { S.cross = null; box.querySelector(".tip").hidden = true; draw(false); return; }
    const want = g.x0 + (px - g.M.l) / g.pw * (g.x1 - g.x0);
    const limit = S.view === "price" ? S.t : g.x1;
    const near = days.filter(d => d >= g.x0 && d <= limit).reduce((a, d) => (a == null || Math.abs(d - want) < Math.abs(a - want) ? d : a), null);
    if (near == null) return;
    S.cross = near;
    draw(false);
    const series = visible(near).filter(s => (S.alpha.get(s.id) || 0) > 0.5 && s.value != null)
      .sort((a, b) => b.value - a.value);
    fillTip(box.querySelector(".tip"), dateText(near), series.map(s => S.view === "price"
      ? [H.dollars(s.value), s.name + ": " + s.sub, s.colour]
      : [Math.round(s.value).toLocaleString("en-US"), s.name + (S.view === "makers" && s.sub ? " (" + s.sub + ")" : s.open ? " (open)" : ""), s.colour]));
    placeTip(box.querySelector(".tip"), box, g.X(near), e.clientY - r.top);
  }

  // The sentence above the chart, the legend, the numbers table and the controls, for day t.
  let wordsAt = 0;
  function words(series, t, animating) {
    const now = performance.now();
    if (animating && now - wordsAt < 120) return;
    wordsAt = now;
    const on = series.filter(s => s.on && s.value != null).sort((a, b) => b.value - a.value);
    const E = H.esc, view = S.view;
    let sum = "";
    if (view === "open") {
      const c = on.find(s => !s.open), o = on.find(s => s.open);
      if (c && o) {
        const lead = c.value >= o.value ? c : o, behind = lead === c ? o : c, gap = Math.round(lead.value - behind.value);
        sum = "The best " + (lead === c ? "closed" : "open") + " model, <b>" + E(lead.name) + "</b>, leads the best " +
          (lead === c ? "open" : "closed") + " one (" + E(behind.name) + ") by <b>" + gap + " points</b>: people would pick it about " +
          Math.round(100 * odds(gap)) + "% of the time.";
      }
    } else if (view === "makers") {
      if (on.length > 1) sum = "Leading: <b>" + E(on[0].name) + "</b>, with " + E(on[0].sub) + " at " + Math.round(on[0].value) + ", " +
        Math.round(on[0].value - on[1].value) + " points ahead of " + E(on[1].name) + " (people would pick it about " +
        Math.round(100 * odds(on[0].value - on[1].value)) + "% of the time).";
    } else {
      const [p1, p10, py] = series;
      const row = py && py.row;
      sum = (p1.value != null ? "Top rated: " + E(p1.sub) + ", " + H.dollars(p1.value) + ". " : "") +
        (p10.value != null ? "Cheapest of the top 10: " + E(p10.sub) + ", " + H.dollars(p10.value) + ". " : "") +
        (py.value != null && row && row[9] ? "As good as last year's #1 (" + E(T.names[row[8]]) + ", then " + H.dollars(row[9]) +
          "): <b>" + E(py.sub) + ", " + H.dollars(py.value) + ", " + Math.round(row[9] / py.value) + "× less</b>." : "");
    }
    $("race-sum").innerHTML = sum;
    $("race-when").textContent = view === "price" ? dateText(t) : monthText(t - WINDOW) + " to " + dateText(t);
    const slider = $("race-at");
    const [a, b] = range(view);
    slider.min = a; slider.max = b; slider.value = Math.round(t);
    $("race-play").textContent = S.playing ? "Pause" : t >= b - 0.5 ? "Replay" : "Play";
    $("race-play").setAttribute("aria-pressed", S.playing);
    const legend = view === "open"
      ? [["line", slot(0), "Closed models"], ["dash", slot(1), "Open models (downloadable)"], ["band", "", "Gap between the best of each"]]
      : view === "makers" ? on.map(s => ["line", s.colour, s.name])
        : series.map(s => ["line", s.colour, s.name]);
    $("race-legend").innerHTML = legend.map(([kind, c, text]) => '<span><i class="k-' + kind + '"' + (c ? ' style="--c:' + c + '"' : "") +
      "></i>" + E(text) + "</span>").join("");
    if (!animating) {
      $("race-table").innerHTML = H.table(view === "price" ? ["Line", "Price per 1M tokens", "Model"] : [view === "open" ? "Model" : "Maker", "Arena rating", view === "open" ? "Kind" : "Best model"],
        on.map(s => view === "price" ? [E(s.name), H.dollars(s.value), E(s.sub)]
          : [E(s.name), Math.round(s.value), view === "open" ? (s.open ? "open" : "closed") : E(s.sub)]), "race-" + view);
    }
    const svg = $("race-chart").querySelector("svg");
    if (svg) svg.setAttribute("aria-label", $("race-sum").textContent || "Trends chart");
  }

  function step(now) {
    const dt = Math.min(0.1, (now - S.last) / 1000);
    S.last = now;
    const [, b] = range(S.view);
    S.t = Math.min(b, S.t + dt * SPEED);
    if (S.t >= b) { S.playing = false; draw(false); return; }
    draw(true);
    S.raf = requestAnimationFrame(step);
  }
  function play(fromStart) {
    cancelAnimationFrame(S.raf);
    const [a, b] = range(S.view);
    if (fromStart || S.t == null || S.t >= b - 0.5) { S.t = a; S.alpha.clear(); S.lo = S.hi = null; }
    S.playing = true; S.cross = null;
    S.last = performance.now();
    S.raf = requestAnimationFrame(step);
  }
  function pause() { S.playing = false; cancelAnimationFrame(S.raf); draw(false); }

  function setView(view) {
    S.view = view;
    document.querySelectorAll("#race-view [data-view]").forEach(b => b.setAttribute("aria-pressed", b.dataset.view === view));
    try { localStorage.setItem("llmledger:race", view); } catch (e) { /* not remembered */ }
    S.alpha.clear(); S.lo = S.hi = null;
    if (reduced()) { S.t = range(view)[1]; draw(false); } else play(true);
  }

  function showRace() {
    if (!T) {
      $("race-chart").innerHTML = '<p class="empty">Arena\'s past leaderboards could not be read with today\'s data.</p>';
      return;
    }
    if (S.shown) { if (!S.playing) draw(false); return; }
    S.shown = true;
    let view = "open";
    try { view = localStorage.getItem("llmledger:race") || "open"; } catch (e) { /* default */ }
    if (!["open", "makers", "price"].includes(view)) view = "open";
    setView(view);
    $("race-note").innerHTML = 'Ratings: <a href="' + H.esc(T.source) + '">Arena leaderboard</a>, ' + T.dates.length +
      " leaderboards from " + monthText(days[0]) + " to " + monthText(lastDay()) + ", CC BY 4.0. Prices: LiteLLM's catalogue on each day.";
    $("race-how").textContent = "Ratings are Arena's overall text scores with style control, one point per leaderboard. Open vs closed shows the " +
      "best closed and the best open model at each date as the two bold lines, and today's top 3 of each as thin lines. A price is per 1M " +
      "tokens, counting " + T.mix[0] + " read for every " + T.mix[1] + " written, at the model's cheapest host that day, rebuilt from every " +
      "change in the catalogue. Models the catalogue cannot price are skipped, so the top rated line is the highest rated model with a price.";
  }

  /* ---------- cost vs quality, on Ask ---------- */
  let lastFront = null;
  const FLOOR = 200;     // points below the top: people picked the top model at least 76% of the time over these
  function drawFrontier(rows, opts) {
    lastFront = [rows, opts];
    const box = $("front-chart");
    if (!box || $("frontier").hidden) return;      // drawn when its tab opens
    if (!rows || !rows.length) {
      box.innerHTML = '<p class="empty">' + H.esc(opts && opts.why || "No rated model matches these choices.") + "</p>";
      $("front-list").innerHTML = ""; $("front-sum").textContent = ""; return;
    }
    const E = H.esc;
    const topRating = Math.max(...rows.map(r => r.rating));
    const all = rows.filter(r => r.cost > 0);
    const pts = all.filter(r => r.rating >= topRating - FLOOR).map(r => ({ x: r.cost, y: r.rating, r }));
    const edge = frontier(pts);
    const onEdge = new Set(edge.map(p => p.r.id));
    const W = Math.max(280, box.clientWidth || 640), phone = W < 560;
    const Hh = Math.max(160, Math.round(box.clientHeight) || (phone ? 250 : 290));
    const M = { l: 46, r: 14, t: 14, b: 30 }, pw = W - M.l - M.r, ph = Hh - M.t - M.b;
    const lx = pts.map(p => Math.log10(p.x)), xs = [Math.min(...lx), Math.max(...lx)];
    const pad = (xs[1] - xs[0]) * 0.05 || 0.5; xs[0] -= pad; xs[1] += pad;
    const ys = [Math.min(...pts.map(p => p.y)), Math.max(...pts.map(p => p.y))];
    const ypad = Math.max(5, (ys[1] - ys[0]) * 0.06); ys[0] -= ypad; ys[1] += ypad;
    const X = v => M.l + pw * (Math.log10(v) - xs[0]) / (xs[1] - xs[0]);
    const Y = v => M.t + ph * (1 - (v - ys[0]) / (ys[1] - ys[0]));
    const out = [];
    for (const v of ticks(ys[0], ys[1], 4)) {
      out.push('<line class="grid" x1="' + M.l + '" x2="' + (M.l + pw) + '" y1="' + Y(v).toFixed(1) + '" y2="' + Y(v).toFixed(1) + '"/>' +
        '<text class="tick" x="' + (M.l - 6) + '" y="' + (Y(v) + 4).toFixed(1) + '" text-anchor="end">' + Math.round(v) + "</text>");
    }
    for (const v of logTicks(Math.pow(10, xs[0]), Math.pow(10, xs[1]))) {
      const x = X(v);
      out.push('<line class="mtick" x1="' + x.toFixed(1) + '" x2="' + x.toFixed(1) + '" y1="' + (M.t + ph) + '" y2="' + (M.t + ph + 4) + '"/>' +
        '<text class="tick" x="' + x.toFixed(1) + '" y="' + (M.t + ph + 17) + '" text-anchor="middle">' + svgText(tickMoney(v)) + "</text>");
    }
    out.push('<line class="axis" x1="' + M.l + '" x2="' + (M.l + pw) + '" y1="' + (M.t + ph) + '" y2="' + (M.t + ph) + '"/>');
    out.push('<text class="corner" x="' + (M.l + pw - 4) + '" y="' + (M.t + ph - 6) + '" text-anchor="end">better: up and to the left ↖</text>');
    for (const p of pts) if (!onEdge.has(p.r.id)) {
      out.push('<circle class="pt" cx="' + X(p.x).toFixed(1) + '" cy="' + Y(p.y).toFixed(1) + '" r="3.5"/>');
    }
    // the edge, drawn as steps: each model is the best you can get until the next one costs more
    let d = "";
    edge.forEach((p, i) => { d += (i ? "H" + X(p.x).toFixed(1) + "V" : "M" + X(p.x).toFixed(1) + ",") + Y(p.y).toFixed(1); });
    out.push('<path class="edge" d="' + d + '"/>');
    const mark = { [opts.best && opts.best.id]: "Best value", [opts.top && opts.top.id]: "Top rated", [opts.low && opts.low.id]: "Cheapest rated" };
    const boxes = [];
    const labelled = edge.slice().sort((a, b) => (mark[b.r.id] ? 1 : 0) - (mark[a.r.id] ? 1 : 0));
    for (const p of edge) {
      out.push('<circle class="ept' + (mark[p.r.id] === "Best value" ? " best" : "") + '" cx="' + X(p.x).toFixed(1) + '" cy="' + Y(p.y).toFixed(1) + '" r="5.5"/>');
    }
    for (const p of labelled) {
      const x = X(p.x), y = Y(p.y), kind = mark[p.r.id];
      const text = short(p.r.id.split(" / ").slice(1).join(" / ") || p.r.id, 22) + (kind ? " · " + kind : "");
      const w = text.length * 6.1 + 6, left = x + w + 10 > M.l + pw;
      const bx = left ? x - 9 - w : x + 9, by = y - 7;
      if (boxes.some(b => bx < b[2] && bx + w > b[0] && by < b[3] && by + 14 > b[1]) || boxes.length >= (phone ? 4 : 9)) continue;
      boxes.push([bx, by, bx + w, by + 14]);
      out.push('<text class="elabel' + (kind ? " k" : "") + '" x="' + (left ? x - 9 : x + 9).toFixed(1) + '" y="' + (y + 4).toFixed(1) +
        '"' + (left ? ' text-anchor="end"' : "") + ">" + svgText(text) + "</text>");
    }
    let svg = box.querySelector("svg");
    if (!svg) {
      box.innerHTML = "";
      svg = document.createElementNS(NS, "svg");
      svg.setAttribute("role", "img");
      box.appendChild(svg);
      tipBox(box);
      svg.addEventListener("pointermove", e => {
        const F = box._front;
        if (!F) return;
        const r = box.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
        let best = null, dist = 28;
        for (const p of F.pts) { const dd = Math.hypot(F.X(p.x) - px, F.Y(p.y) - py); if (dd < dist) { dist = dd; best = p; } }
        const tip = box.querySelector(".tip");
        if (!best) { tip.hidden = true; return; }
        const rr = best.r;
        fillTip(tip, rr.id, [[H.dollars(rr.cost) + " per answer", "on " + rr.m.host, "var(--accent)"],
          [String(Math.round(rr.rating)), "Arena score (" + Math.round(rr.low) + " to " + Math.round(rr.high) + ")", "var(--muted)"]]
          .concat(F.edge.has(rr.id) ? [["On the edge", "no model is both cheaper and rated higher", "var(--accent)"]] : []));
        placeTip(tip, box, px, py);
      });
      svg.addEventListener("pointerleave", () => { box.querySelector(".tip").hidden = true; });
    }
    box._front = { pts, X, Y, edge: onEdge };
    svg.setAttribute("viewBox", "0 0 " + W + " " + Hh);
    svg.setAttribute("width", W); svg.setAttribute("height", Hh);
    svg.innerHTML = out.join("");
    const cheap = edge[0], high = edge[edge.length - 1];
    $("front-sum").innerHTML = "<b>" + edge.length + " of " + pts.length.toLocaleString() + "</b> models are on the edge for " +
      E(opts.task) + ": no other model is both cheaper and rated higher." + (edge.length > 1 ? " The cheapest of them, " + E(cheap.r.id) +
      ", costs " + H.dollars(cheap.x) + " per answer; the highest rated, " + E(high.r.id) + ", costs " +
      Math.round(high.x / cheap.x).toLocaleString("en-US") + "× as much for " + Math.round(high.y - cheap.y) + " more points." : "");
    svg.setAttribute("aria-label", $("front-sum").textContent);
    $("front-list").innerHTML = edge.slice().reverse().map(p => '<li><div><a href="#models" data-open-group="' + E(p.r.id) + '" title="' +
      E(p.r.id) + '">' + E(p.r.id) + "</a>" + (mark[p.r.id] ? "<small>" + mark[p.r.id].toLowerCase() + "</small>" : "") +
      "</div><span><b>" + Math.round(p.y) + "</b> · " + H.dollars(p.x) + "</span></li>").join("");
    $("front-note").textContent = "Each dot is a model Arena rated for this task, at its cheapest listing for your prompt and answer; " +
      "prices are on a log scale. Shown: the " + pts.length.toLocaleString() + " of " + all.length.toLocaleString() + " rated models within " + FLOOR +
      " points of the top (people picked the top model at least " + Math.round(100 * odds(FLOOR)) + "% of the time over the rest). " +
      "Close scores can be within each other's ranges.";
  }

  /* ---------- new arrivals and the latest changes ---------- */
  function renderArrivals() {
    const E = H.esc, A = D.arena;
    const label = new Map((A ? A.labels : []).map(([k, l]) => [k, l]));
    const end = dayOf(D.end.slice(0, 10));
    $("arrivals").innerHTML = arrivals(H.models, 6).map(g => {
      let rank = null;
      if (A) for (const [task, rows] of Object.entries(A.tasks)) {
        const at = rows.findIndex(r => r[0] === g.id);
        if (at >= 0 && (!rank || (at + 1) / rows.length < rank.share)) rank = { task, at: at + 1, n: rows.length, share: (at + 1) / rows.length };
      }
      const listed = g.listings.filter(m => m.status === "listed" && m.input > 0 && m.output > 0)
        .sort((a, b) => (3 * a.input + a.output) - (3 * b.input + b.output))[0];
      const ago = Math.max(0, Math.round(end - dayOf(g.first)));
      return '<li><div><a href="#models" data-open-group="' + E(g.id) + '" title="' + E(g.id) + '">' + E(g.id.split(" / ").slice(1).join(" / ")) + "</a>" +
        "<small>" + E(g.id.split(" / ")[0]) + " · " + (ago === 0 ? "today" : ago === 1 ? "yesterday" : ago + " days ago") +
        (listed ? " · " + H.money(listed.input) + " / " + H.money(listed.output) + " per 1M" : "") + "</small></div>" +
        '<div class="r">' + (rank ? "<b>#" + rank.at + "</b> of " + rank.n + "<small>" + E((label.get(rank.task) || rank.task).toLowerCase()) + "</small>"
          : '<small>not rated yet</small>') + "</div></li>";
    }).join("") || '<li class="muted">No new text models in the catalogue lately.</li>';
  }
  function renderChanges() {
    const E = H.esc, byKey = new Map(H.models.map(m => [m.key, m]));
    const nameOf = key => { const m = byKey.get(key); return m ? [m.name, m.host] : [key, ""]; };
    const fieldName = f => (/input/.test(f) ? "input" : /output/.test(f) ? "output" : f.replace(/_/g, " "));
    const num = v => (typeof v === "number" ? v : null);
    $("changes").innerHTML = digest(D.recent || []).slice(0, 8).map(it => {
      const when = "<time>" + E(dateText(dayOf(it.day)).replace(/, \d{4}$/, "")) + "</time>";
      if (it.keys) {
        const what = { added: "listings added", removed: "listings removed", bulk: "listings removed in a clean up",
          set: "listings got their first prices" }[it.kind];
        const names = [...new Set(it.keys.map(k => nameOf(k)[0]))];
        return '<li class="c-' + (it.kind === "added" || it.kind === "set" ? "add" : "out") + '">' + when + "<span><b>" + it.count +
          "</b> " + what + "<small>" + E(names.slice(0, 3).join(", ")) + (names.length > 3 ? ", …" : "") + "</small></span></li>";
      }
      const [name, host] = nameOf(it.key);
      let cls = "c-out", text;
      if (it.kind === "price" || it.kind === "set") {
        const dirs = [];
        text = it.fields.map(f => {
          const o = num(f.old), n = num(f.now), money = v => (/token/.test(f.field) ? H.money(v * 1e6) + " per 1M" : H.money(v));
          if (n == null) return fieldName(f.field) + " price removed";
          if (!(o > 0)) return fieldName(f.field) + " price set to " + money(n);
          const pc = Math.round(100 * (n - o) / o);
          dirs.push(Math.sign(n - o));
          return fieldName(f.field) + (pc < 0 ? " down " : " up ") + Math.abs(pc) + "% to " + money(n);
        }).join(", ") + (it.flag ? " (" + (it.flag === "unit" ? "unit fix" : it.flag) + ")" : "");
        cls = dirs.some(d => d > 0) ? "c-up" : dirs.some(d => d < 0) ? "c-down" : "c-add";
      } else if (it.kind === "deprecation") {
        const f = it.fields[0];
        text = f.now ? "retirement date " + (f.old ? "moved to " : "set to ") + f.now : "retirement date removed";
      } else {
        cls = it.kind === "added" ? "c-add" : "c-out";
        text = it.kind === "added" ? "added to the catalogue" : "removed from the catalogue";
      }
      const small = (host ? host + " · " : "") + text;
      return '<li class="' + cls + '">' + when + '<span><a href="#models" data-open-model="' + E(it.key) + '" title="' + E(it.key) + '">' +
        E(name) + '</a><small title="' + E(small) + '">' + E(small) + "</small></span></li>";
    }).join("") || '<li class="muted">No changes in the last 7 days.</li>';
    $("changes-all").textContent = "All " + (D.recent || []).length.toLocaleString() + " changes in the last 7 days";
  }

  /* ---------- wiring ---------- */
  function init(helpers) {
    H = helpers;
    if (!$("tab-race")) return;
    $("race-view").addEventListener("click", e => { if (e.target.dataset.view) setView(e.target.dataset.view); });
    $("race-play").addEventListener("click", () => { if (S.playing) pause(); else play(false); });
    $("race-at").addEventListener("input", e => { S.playing = false; cancelAnimationFrame(S.raf); S.t = +e.target.value; draw(false); });
    document.addEventListener("click", e => {
      const a = e.target.closest && e.target.closest("[data-open-group],[data-open-model]");
      if (!a) return;
      e.preventDefault();
      if (a.dataset.openGroup) H.openGroup(a.dataset.openGroup); else H.openModel(a.dataset.openModel);
    });
    const frontShown = () => !$("frontier").hidden && !$("tab-ask").hidden;
    $("frontier").addEventListener("dockshow", () => { if (lastFront) requestAnimationFrame(() => drawFrontier(...lastFront)); });
    // Both charts take the size their box is given, so they are redrawn when the window or the box changes size.
    let resizing = 0;
    const redraw = () => {
      clearTimeout(resizing);
      resizing = setTimeout(() => {
        if (!$("tab-race").hidden && S.shown && !S.playing) draw(false);
        if (frontShown() && lastFront) drawFrontier(...lastFront);
      }, 120);
    };
    root.addEventListener("resize", redraw);
    if (root.ResizeObserver) { const ro = new ResizeObserver(redraw); ro.observe($("race-chart")); ro.observe($("front-chart")); }
    renderArrivals();
    renderChanges();
    $("pulse-date").textContent = dateText(dayOf(D.end.slice(0, 10)));
  }

  Object.assign(root.LLMTRENDS, { init, show: showRace, frontier: drawFrontier });
})(this);
