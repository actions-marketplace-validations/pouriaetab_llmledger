/* Table protocol for plain HTML pages (no framework). FRONTEND_UX.md C, F17.
 *
 * Pouria, 2026-10-10: "for all the tables ... I always want to be able to sort by the columns ... when the
 * table is very long ... the header row to come down as well ... And also being able to move the column, change
 * their positions. These are like the three things I always ask."
 *
 * Every <table> on the page gets, with no change to its HTML:
 *   1. Sort: click a header (or Enter/Space on it): ascending, again: descending. Numbers sort as numbers
 *      ($, %, commas, "1,000+" understood), blanks and dashes always last, ties keep their order. A cell's
 *      data-sort="..." overrides its text (use it for bars, badges, dates written in words).
 *   2. Header row stays in view: <th> cells are sticky. A table inside a sideways-scrolling wrapper gets
 *      that wrapper capped at 80% of the window height, because sticky only works inside the box that scrolls.
 *   3. Move columns: drag a header onto another header. The order is remembered per table in this browser.
 *   4. The last sort is remembered too, and comes back when the table is redrawn or the page is reloaded.
 *      Give a table that is redrawn a stable name with data-key="..." so its memory follows it.
 * Opt out with <table data-plain>. Tables added later are picked up too (MutationObserver).
 * React apps: do not use this on tables React renders (it moves DOM nodes React owns). Render from a columns
 * array and keep sort key, direction and column order in state instead (FRONTEND_UX.md F17).
 */
(function () {
  if (window.__tableProtocol) return;
  window.__tableProtocol = true;

  var css = document.createElement('style');
  css.textContent =
    'table.tp th{position:sticky;top:0;z-index:2;background:var(--panel,#fff);cursor:pointer;user-select:none;' +
    'background-clip:padding-box}' +
    'table.tp th .tp-arrow{opacity:.35;font-size:10px;margin-left:4px}' +
    'table.tp th[aria-sort] .tp-arrow{opacity:1}' +
    'table.tp th.tp-over{outline:2px dashed currentColor;outline-offset:-3px}' +
    'table.tp th.tp-drag{opacity:.45}';
  document.head.appendChild(css);

  function headerRow(table) {
    if (table.tHead && table.tHead.rows.length) return table.tHead.rows[table.tHead.rows.length - 1];
    var first = table.rows[0];
    if (!first) return null;
    for (var i = 0; i < first.cells.length; i++) if (first.cells[i].tagName !== 'TH') return null;
    var thead = table.createTHead();            // header row written without <thead>: give it one
    thead.appendChild(first);
    return first;
  }

  function value(cell) {
    if (!cell) return null;
    var raw = cell.hasAttribute('data-sort') ? cell.getAttribute('data-sort') : cell.textContent;
    var t = (raw || '').trim();
    if (!t || /^[-–—]+$/.test(t) || /^(unknown|n\/a|none)$/i.test(t)) return null;
    var s = t.replace(/[$,\s]/g, '').replace(/%$/, '').replace(/\+$/, '');
    if (/^\(?-?\d+(\.\d+)?\)?$/.test(s)) {
      var n = parseFloat(s.replace(/[()]/g, ''));
      return /^\(.*\)$/.test(s) ? -n : n;
    }
    if (/^\d{4}-\d\d(-\d\d)?/.test(t)) return t;            // ISO dates sort as text
    var m = t.match(/^-?\d+(\.\d+)?/);                      // "12% (6% to 24%)", "6 of 50", "42 days"
    if (m) return parseFloat(m[0]);
    return t.toLowerCase();
  }

  function cmp(a, b) {
    if (a === null && b === null) return 0;
    if (a === null) return 1;                    // blanks last, both directions (flipped back below)
    if (b === null) return -1;
    if (typeof a === 'number' && typeof b === 'number') return a - b;
    return String(a).localeCompare(String(b), undefined, { numeric: true });
  }

  function key(table, idx) {
    var head = headerRow(table);
    var sig = head ? Array.prototype.map.call(head.cells, function (c) { return c.textContent.trim(); }).sort().join('|') : '';
    var id = table.getAttribute('data-key') || idx;   // a stable name survives tables being redrawn
    return 'tp:' + location.pathname + ':' + id + ':' + sig;
  }

  function moveColumn(table, from, to) {
    if (from === to) return;
    Array.prototype.forEach.call(table.rows, function (row) {
      if (row.cells.length <= Math.max(from, to)) return;      // a row that spans columns is left alone
      var cell = row.cells[from];
      var ref = row.cells[to];
      row.insertBefore(cell, from < to ? ref.nextSibling : ref);
    });
  }

  function saveOrder(table) {
    try {
      var head = headerRow(table);
      localStorage.setItem(table.__tpKey, JSON.stringify(Array.prototype.map.call(head.cells, function (c) {
        return c.__tpLabel;
      })));
    } catch (e) { /* storage off: the order just isn't remembered */ }
  }

  function restoreOrder(table) {
    var saved;
    try { saved = JSON.parse(localStorage.getItem(table.__tpKey) || 'null'); } catch (e) { saved = null; }
    if (!Array.isArray(saved)) return;
    var head = headerRow(table);
    saved.forEach(function (label, want) {
      var cells = Array.prototype.slice.call(head.cells);
      var at = cells.findIndex(function (c) { return c.__tpLabel === label; });
      if (at >= 0 && at !== want && want < cells.length) moveColumn(table, at, want);
    });
  }

  function saveSort(table, th, dir) {
    try { localStorage.setItem(table.__tpKey + ':sort', JSON.stringify([th.__tpLabel, dir])); } catch (e) { /* not remembered */ }
  }

  function restoreSort(table) {
    var saved;
    try { saved = JSON.parse(localStorage.getItem(table.__tpKey + ':sort') || 'null'); } catch (e) { saved = null; }
    if (!Array.isArray(saved)) return;
    var th = Array.prototype.find.call(headerRow(table).cells, function (c) { return c.__tpLabel === saved[0]; });
    if (th) sortBy(table, th, saved[1]);
  }

  function sortBy(table, th, wanted) {
    var head = headerRow(table);
    var col = Array.prototype.indexOf.call(head.cells, th);
    var dir = wanted || (th.getAttribute('aria-sort') === 'ascending' ? 'descending' : 'ascending');
    if (!wanted) saveSort(table, th, dir);
    Array.prototype.forEach.call(head.cells, function (c) {
      c.removeAttribute('aria-sort');
      var a = c.querySelector('.tp-arrow'); if (a) a.textContent = '↕';
    });
    th.setAttribute('aria-sort', dir);
    th.querySelector('.tp-arrow').textContent = dir === 'ascending' ? '▲' : '▼';
    Array.prototype.forEach.call(table.tBodies, function (tb) {
      var rows = Array.prototype.slice.call(tb.rows).map(function (r, i) { return { r: r, i: i, v: value(r.cells[col]) }; });
      rows.sort(function (x, y) {
        var c = cmp(x.v, y.v);
        if (x.v !== null && y.v !== null && dir === 'descending') c = -c;
        return c || x.i - y.i;
      });
      rows.forEach(function (o) { tb.appendChild(o.r); });
    });
  }

  function fixScrollBox(table) {
    var p = table.parentElement;
    if (!p || p === document.body) return;
    var cs = getComputedStyle(p);
    if (/(auto|scroll)/.test(cs.overflowX + cs.overflowY) && cs.maxHeight === 'none' && table.rows.length > 15) {
      p.style.maxHeight = '80vh';
      p.style.overflowY = 'auto';
    }
  }

  var dragged = null;

  function upgrade(table, idx) {
    if (table.__tp || table.hasAttribute('data-plain')) return;
    var head = headerRow(table);
    if (!head || !table.tBodies.length) return;
    table.__tp = true;
    table.classList.add('tp');
    table.__tpKey = key(table, idx);
    Array.prototype.forEach.call(head.cells, function (th) {
      th.__tpLabel = th.textContent.trim();
      th.tabIndex = 0;
      th.draggable = true;
      th.title = (th.title ? th.title + ' · ' : '') + 'Click to sort. Drag onto another header to move this column.';
      var arrow = document.createElement('span');
      arrow.className = 'tp-arrow';
      arrow.textContent = '↕';
      th.appendChild(arrow);
      th.addEventListener('click', function () { sortBy(table, th); });
      th.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sortBy(table, th); }
      });
      th.addEventListener('dragstart', function (e) {
        dragged = { table: table, th: th };
        th.classList.add('tp-drag');
        try { e.dataTransfer.setData('text/plain', th.__tpLabel); e.dataTransfer.effectAllowed = 'move'; } catch (x) { /* old browsers */ }
      });
      th.addEventListener('dragend', function () { th.classList.remove('tp-drag'); dragged = null; });
      th.addEventListener('dragover', function (e) {
        if (dragged && dragged.table === table) { e.preventDefault(); th.classList.add('tp-over'); }
      });
      th.addEventListener('dragleave', function () { th.classList.remove('tp-over'); });
      th.addEventListener('drop', function (e) {
        e.preventDefault();
        th.classList.remove('tp-over');
        if (!dragged || dragged.table !== table) return;
        var cells = Array.prototype.slice.call(headerRow(table).cells);
        moveColumn(table, cells.indexOf(dragged.th), cells.indexOf(th));
        saveOrder(table);
      });
    });
    restoreOrder(table);
    restoreSort(table);
    fixScrollBox(table);
  }

  function run() {
    Array.prototype.forEach.call(document.querySelectorAll('table'), function (t, i) { upgrade(t, i); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run); else run();
  new MutationObserver(function () { run(); }).observe(document.documentElement, { childList: true, subtree: true });
})();
