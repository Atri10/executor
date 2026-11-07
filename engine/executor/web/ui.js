/* Shared UI kit for the explorer pages. It loads before each page script and
   exports its helpers on window.EX. It renders what it is given and knows
   nothing about one initiative. */
(() => {
  "use strict";
  const { h } = preact;
  const { useState, useEffect, useMemo, useRef } = preactHooks;
  const html = htm.bind(h);

  // Icons: 24-unit grid, stroke only. Drawn for this kit, not copied from a set.
  const ICONS = {
    search: [["circle", { cx: 11, cy: 11, r: 7 }], ["path", { d: "m20 20-3.5-3.5" }]],
    x: [["path", { d: "M18 6 6 18M6 6l12 12" }]],
    "chevron-up": [["path", { d: "m18 15-6-6-6 6" }]],
    "chevron-down": [["path", { d: "m6 9 6 6 6-6" }]],
    "arrow-up-right": [["path", { d: "M7 17 17 7M8 7h9v9" }]],
    "zoom-in": [["circle", { cx: 11, cy: 11, r: 7 }], ["path", { d: "m20 20-3.5-3.5M11 8v6M8 11h6" }]],
    "zoom-out": [["circle", { cx: 11, cy: 11, r: 7 }], ["path", { d: "m20 20-3.5-3.5M8 11h6" }]],
    fit: [["path", { d: "M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4" }]],
    target: [["circle", { cx: 12, cy: 12, r: 8 }], ["circle", { cx: 12, cy: 12, r: 2.5 }], ["path", { d: "M12 2v3M12 19v3M2 12h3M19 12h3" }]],
    sun: [["circle", { cx: 12, cy: 12, r: 4 }], ["path", { d: "M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" }]],
    moon: [["path", { d: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" }]],
    monitor: [["rect", { x: 3, y: 4, width: 18, height: 12, rx: 2 }], ["path", { d: "M8 20h8M12 16v4" }]],
    keyboard: [["rect", { x: 2, y: 6, width: 20, height: 12, rx: 2 }], ["path", { d: "M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10" }]],
    layers: [["path", { d: "m12 2 10 5-10 5L2 7z" }], ["path", { d: "m2 17 10 5 10-5M2 12l10 5 10-5" }]],
    branch: [["circle", { cx: 6, cy: 5, r: 2 }], ["circle", { cx: 6, cy: 19, r: 2 }], ["circle", { cx: 18, cy: 6, r: 2 }], ["path", { d: "M6 7v10M18 8c0 5-6 4-12 9" }]],
    file: [["path", { d: "M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" }], ["path", { d: "M14 3v6h6M8 13h8M8 17h5" }]],
    clock: [["circle", { cx: 12, cy: 12, r: 9 }], ["path", { d: "M12 7v5l3 2" }]],
    list: [["path", { d: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" }]],
  };

  function Icon({ name, size = 16, label }) {
    const paths = ICONS[name] || [];
    return html`<svg class="ic" width=${size} height=${size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"
      aria-hidden=${label ? undefined : "true"} role=${label ? "img" : undefined} aria-label=${label}
      >${paths.map(([tag, attrs], i) => h(tag, { key: i, ...attrs }))}</svg>`;
  }

  // State shapes. Shape carries the state too, so colour is never the only cue.
  const SHAPES = {
    complete: [["circle", { cx: 6, cy: 6, r: 5.25, fill: "currentColor" }],
      ["path", { class: "glyph-check", d: "M3.6 6.2 5.3 7.9 8.5 4.5", fill: "none", "stroke-width": 1.5, "stroke-linecap": "round", "stroke-linejoin": "round" }]],
    active: [["circle", { cx: 6, cy: 6, r: 4.5, fill: "none", stroke: "currentColor", "stroke-width": 1.5 }],
      ["circle", { cx: 6, cy: 6, r: 1.9, fill: "currentColor" }]],
    pending: [["circle", { cx: 6, cy: 6, r: 4.5, fill: "none", stroke: "currentColor", "stroke-width": 1.5, "stroke-dasharray": "2 1.6" }]],
    bad: [["path", { d: "M6 0.8 11.2 6 6 11.2 0.8 6z", fill: "currentColor" }]],
    warn: [["path", { d: "M6 1.2 11.2 10.6H0.8z", fill: "currentColor" }]],
    dot: [["circle", { cx: 6, cy: 6, r: 2.4, fill: "currentColor" }]],
  };

  // Usable inside an <svg> (graph nodes) and inside Glyph's own <svg>.
  function GlyphShapes({ kind }) {
    return (SHAPES[kind] || SHAPES.dot).map(([tag, attrs], i) => h(tag, { key: i, ...attrs }));
  }

  function Glyph({ kind, size = 12 }) {
    return html`<svg class="glyph" width=${size} height=${size} viewBox="0 0 12 12" aria-hidden="true"><${GlyphShapes} kind=${kind} /></svg>`;
  }

  // Each engine state maps to a shape and a tone. Unknown states fall back to a dot.
  const STATE = {
    complete: ["complete", "ok"], proven: ["complete", "ok"], passed: ["complete", "ok"],
    merged: ["complete", "ok"], applied: ["complete", "ok"], answered: ["complete", "ok"],
    in_progress: ["active", "accent"], gate_pending: ["active", "accent"], reached: ["active", "accent"],
    reported: ["active", "accent"],
    pending: ["pending", "neutral"], draft: ["pending", "neutral"], withdrawn: ["pending", "neutral"],
    abandoned: ["pending", "neutral"],
    blocked: ["bad", "bad"], failed: ["bad", "bad"], spawn_error: ["bad", "bad"],
    needs_context: ["warn", "warn"], fix_needed: ["warn", "warn"], unanswered: ["warn", "warn"],
    unavailable: ["warn", "warn"], open: ["warn", "warn"],
  };
  const stateOf = (state) => STATE[state] || ["dot", "neutral"];
  const labelOf = (value) => String(value || "").replace(/_/g, " ");

  function Pill({ state, label, tone }) {
    const [kind, fallback] = stateOf(state);
    return html`<span class=${`pill tone-${tone || fallback}`}><${Glyph} kind=${kind} /><span>${label ?? labelOf(state)}</span></span>`;
  }

  function Chips({ label, options, value, onChange }) {
    return html`<div class="chips" role="group" aria-label=${label}>${options.map((o) => html`<button
      type="button" class="chip" aria-pressed=${String(o.value === value)} onClick=${() => onChange(o.value)}
      ><span>${o.label}</span>${o.count !== undefined ? html`<span class="chip-count">${o.count}</span>` : null}</button>`)}</div>`;
  }

  function SearchField({ label, value, onInput }) {
    return html`<label class="search"><${Icon} name="search" size=${14} /><span class="sr-only">${label}</span><input
      type="search" value=${value} placeholder=${label} onInput=${(e) => onInput(e.currentTarget.value)} /></label>`;
  }

  function Bar({ value, label, tone }) {
    const v = Math.max(0, Math.min(100, Math.round(value)));
    return html`<div class="bar" role="progressbar" aria-label=${label} aria-valuemin="0" aria-valuemax="100" aria-valuenow=${v}
      ><span class=${`bar-fill ${tone ? `tone-${tone}` : ""}`} style=${{ width: `${v}%` }}></span></div>`;
  }

  function Kpi({ label, value, sub, ratio }) {
    return html`<div class="kpi"><div class="kpi-label">${label}</div><div class="kpi-value">${value}</div>${
      sub ? html`<div class="kpi-sub">${sub}</div>` : null}${ratio !== undefined ? html`<${Bar} value=${ratio} label=${label} />` : null}</div>`;
  }

  function Empty({ title, body }) {
    return html`<div class="empty"><p class="empty-title">${title}</p>${body ? html`<p class="empty-body">${body}</p>` : null}</div>`;
  }

  const cmp = (a, b) => (typeof a === "number" && typeof b === "number"
    ? a - b : String(a ?? "").localeCompare(String(b ?? ""), "en", { numeric: true }));

  // Sortable table. The first column holds the row button, so every row is reachable from the keyboard.
  function DataTable({ caption, columns, rows, rowId, selected, onSelect, empty }) {
    const [sort, setSort] = useState({ key: "", dir: 1 });
    const sorted = useMemo(() => {
      const col = columns.find((c) => c.key === sort.key);
      if (!col) return rows;
      const value = col.value || ((r) => r[col.key]);
      return [...rows].sort((a, b) => cmp(value(a), value(b)) * sort.dir || cmp(rowId(a), rowId(b)));
    }, [rows, sort, columns]);
    const toggle = (key) => setSort((s) => ({ key, dir: s.key === key ? -s.dir : 1 }));
    return html`<div class="table-wrap"><table class="table">
      <caption class="sr-only">${caption}</caption>
      <thead><tr>${columns.map((c) => {
        const active = sort.key === c.key;
        const dir = active ? (sort.dir > 0 ? "ascending" : "descending") : "none";
        return html`<th scope="col" class=${c.num ? "num" : ""} aria-sort=${dir}><button type="button" class="th-btn" onClick=${() => toggle(c.key)}
          ><span>${c.label}</span>${active ? html`<${Icon} name=${sort.dir > 0 ? "chevron-up" : "chevron-down"} size=${12} />` : null}</button></th>`;
      })}</tr></thead>
      <tbody>${sorted.length === 0
        ? html`<tr><td class="empty-cell" colSpan=${columns.length}>${empty}</td></tr>`
        : sorted.map((row) => {
          const id = rowId(row);
          const on = id === selected;
          return html`<tr key=${id} class=${on ? "is-on" : ""}>${columns.map((c, i) => {
            const cell = c.render ? c.render(row) : row[c.key];
            return html`<td class=${c.num ? "num" : ""}>${i === 0
              ? html`<button type="button" class="row-btn" aria-pressed=${String(on)} onClick=${() => onSelect(id)}>${cell}</button>`
              : cell}</td>`;
          })}</tr>`;
        })}</tbody></table></div>`;
  }

  // Routing: the URL hash is the single source of selection, so a link reopens the same view.
  function parseHash(raw) {
    let text = raw.replace(/^#/, "");
    try { text = decodeURIComponent(text); } catch (e) { /* keep the raw text */ }
    const [section, ...rest] = text.split("/");
    return { section: section || "", id: rest.join("/") };
  }

  function useRoute() {
    const [route, setRoute] = useState(() => parseHash(location.hash));
    useEffect(() => {
      const on = () => setRoute(parseHash(location.hash));
      window.addEventListener("hashchange", on);
      return () => window.removeEventListener("hashchange", on);
    }, []);
    return route;
  }

  function routeTo(section, id = "") {
    const next = `#${section}${id ? `/${encodeURIComponent(id)}` : ""}`;
    if (location.hash !== next) location.hash = next;
  }

  // Theme: "system" removes the attribute so the media query decides. Storage can be
  // blocked (a sandboxed frame has none), so every access is guarded.
  const THEMES = ["system", "light", "dark"];
  const THEME_KEY = "executor.theme";

  function storedTheme() {
    try {
      const value = localStorage.getItem(THEME_KEY);
      return THEMES.includes(value) ? value : "system";
    } catch (e) {
      return "system";
    }
  }

  function applyTheme(theme) {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* no storage here */ }
  }

  function useTheme() {
    const [theme, setTheme] = useState(storedTheme);
    useEffect(() => applyTheme(theme), [theme]);
    return [theme, setTheme];
  }

  function ThemeSwitch({ theme, onChange }) {
    const icon = { system: "monitor", light: "sun", dark: "moon" };
    return html`<div class="seg" role="group" aria-label="Theme">${THEMES.map((t) => html`<button type="button"
      class="seg-btn" aria-pressed=${String(theme === t)} title=${`${t} theme`} onClick=${() => onChange(t)}
      ><${Icon} name=${icon[t]} size=${14} /><span class="sr-only">${t} theme</span></button>`)}</div>`;
  }

  // The store's version verdict, as the engine computes it. Nothing shows when the store is current.
  function StoreBanner({ store }) {
    if (!store || store.verdict === "current") return null;
    const tooNew = store.verdict === "engine_too_old";
    const text = tooNew
      ? `Written by engine ${store.engine}; this build is ${store.running}. Upgrade executor before reading or writing this store.`
      : `Written by engine ${store.engine} with layout ${store.store_version || "unknown"}. Run executor migrate --dry-run, then executor migrate --apply.`;
    return html`<div class=${`banner tone-${tooNew ? "bad" : "warn"}`} role="status"><div>
      <p class="banner-title">${tooNew ? "This store needs a newer executor" : "This store needs a migration"}</p>
      <p>${text}</p></div></div>`;
  }

  // Search. MiniSearch gives prefix and typo-tolerant matching; rows keep their original order otherwise.
  function filterByText(rows, query, idOf, fields) {
    const q = query.trim();
    if (!q) return rows;
    const index = new MiniSearch({ idField: "_id", fields, searchOptions: { prefix: true, fuzzy: 0.2 } });
    index.addAll(rows.map((r) => ({ ...r, _id: idOf(r) })));
    const keep = new Set(index.search(q).map((hit) => hit.id));
    return rows.filter((r) => keep.has(idOf(r)));
  }

  function buildIndex(items) {
    const index = new MiniSearch({
      idField: "key", fields: ["label", "sub", "kind"], storeFields: ["key"],
      searchOptions: { prefix: true, fuzzy: 0.2, boost: { label: 3 } },
    });
    index.addAll(items);
    return index;
  }

  function rank(index, items, query) {
    const q = query.trim();
    if (!q) return items.slice(0, 14);
    const byKey = new Map(items.map((it) => [it.key, it]));
    return index.search(q).slice(0, 30).map((hit) => byKey.get(hit.id)).filter(Boolean);
  }

  function Palette({ open, items, onClose }) {
    const ref = useRef(null);
    const [query, setQuery] = useState("");
    const [active, setActive] = useState(0);
    const index = useMemo(() => buildIndex(items), [items]);
    const results = useMemo(() => rank(index, items, query), [index, items, query]);
    useEffect(() => {
      const dialog = ref.current;
      if (!dialog) return;
      if (open && !dialog.open) {
        setQuery("");
        setActive(0);
        dialog.showModal();
      }
      if (!open && dialog.open) dialog.close();
    }, [open]);
    const pick = (item) => {
      onClose();
      item.go();
    };
    const onKey = (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => Math.min(i + 1, results.length - 1)); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)); }
      else if (e.key === "Enter" && results[active]) { e.preventDefault(); pick(results[active]); }
    };
    return html`<dialog class="palette" ref=${ref} aria-label="Find" onClose=${onClose}>
      <div class="palette-field"><${Icon} name="search" size=${16} />
        <input class="palette-input" type="search" placeholder="Find a task, artifact, decision, or section"
          value=${query} role="combobox" aria-expanded="true" aria-controls="palette-results" aria-autocomplete="list"
          aria-activedescendant=${results[active] ? `pr-${active}` : undefined}
          onInput=${(e) => { setQuery(e.currentTarget.value); setActive(0); }} onKeyDown=${onKey} />
        <kbd>Esc</kbd></div>
      <ul class="palette-list" id="palette-results" role="listbox">${results.length === 0
        ? html`<li class="palette-empty">No match.</li>`
        : results.map((r, i) => html`<li key=${r.key} id=${`pr-${i}`} role="option" aria-selected=${String(i === active)}
            class=${i === active ? "is-active" : ""} onMouseEnter=${() => setActive(i)} onClick=${() => pick(r)}>
            <span class="palette-kind">${r.kind}</span><span class="palette-label">${r.label}</span>
            <span class="palette-sub">${r.sub}</span></li>`)}</ul></dialog>`;
  }

  const fmtUtc = (ts) => (ts ? ts.slice(11, 19) : "—");
  const fmtDay = (ts) => (ts ? ts.slice(0, 10) : "—");
  function fmtDur(sec) {
    if (sec == null) return "—";
    if (sec < 60) return `${sec}s`;
    if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`;
    if (sec < 86400) return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
    return `${Math.floor(sec / 86400)}d ${Math.floor((sec % 86400) / 3600)}h`;
  }
  const pct = (part, whole) => (whole ? (part / whole) * 100 : 0);
  const truncate = (text, n) => (text && text.length > n ? `${text.slice(0, n - 1)}…` : text || "");

  function groupBy(list, keyOf) {
    const groups = new Map();
    for (const item of list) {
      const key = keyOf(item);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(item);
    }
    return groups;
  }

  function countBy(list, keyOf) {
    const counts = {};
    for (const item of list) {
      const key = keyOf(item);
      counts[key] = (counts[key] || 0) + 1;
    }
    return counts;
  }

  window.EX = {
    h, html, useState, useEffect, useMemo, useRef,
    Icon, Glyph, GlyphShapes, stateOf, labelOf, Pill, Chips, SearchField, Bar, Kpi, Empty,
    DataTable, parseHash, useRoute, routeTo, storedTheme, applyTheme, useTheme, ThemeSwitch,
    StoreBanner, filterByText, Palette, fmtUtc, fmtDay, fmtDur, pct, truncate, groupBy, countBy,
  };
})();
