/* The parent index: every initiative in this store, with a sandboxed preview of
   the selected one. It renders from the embedded model only. */
(() => {
  "use strict";
  const { render } = preact;
  const { html, useState, useEffect, useMemo, Icon, Pill, Chips, SearchField, Kpi, Bar, Empty,
    ThemeSwitch, StoreBanner, useTheme, storedTheme, applyTheme, labelOf, filterByText,
    fmtDay, fmtUtc, pct } = window.EX;

  const M = JSON.parse(document.getElementById("executor-model").textContent);

  function idFromHash() {
    const raw = location.hash.replace(/^#/, "");
    try { return decodeURIComponent(raw); } catch (e) { return raw; }
  }

  function useSelected() {
    const [id, setId] = useState(idFromHash);
    useEffect(() => {
      const on = () => setId(idFromHash());
      window.addEventListener("hashchange", on);
      return () => window.removeEventListener("hashchange", on);
    }, []);
    return [id, (next) => { if (idFromHash() !== next) location.hash = encodeURIComponent(next); }];
  }

  const ORDER = {
    recent: (a, b) => (b.last_ts || "").localeCompare(a.last_ts || "") || a.id.localeCompare(b.id),
    attention: (a, b) => b.attention - a.attention || a.id.localeCompare(b.id),
    progress: (a, b) => pct(a.tasks_done, a.tasks_total) - pct(b.tasks_done, b.tasks_total) || a.id.localeCompare(b.id),
  };

  function Stat({ label, value, tone }) {
    return html`<div class="stat"><span class="stat-label">${label}</span><span class=${`stat-value num ${tone ? `tone-${tone}` : ""}`}>${value}</span></div>`;
  }

  function InitiativeList({ rows, selectedId, onPick }) {
    const listRef = useRefList();
    const move = (e) => {
      const buttons = [...listRef.current.querySelectorAll("button[data-row]")];
      const at = buttons.indexOf(document.activeElement);
      if (at < 0) return;
      const target = { ArrowDown: at + 1, ArrowUp: at - 1, Home: 0, End: buttons.length - 1 }[e.key];
      if (target === undefined) return;
      e.preventDefault();
      buttons[Math.max(0, Math.min(buttons.length - 1, target))].focus();
    };
    if (rows.length === 0) return html`<p class="muted">Nothing matches this search.</p>`;
    return html`<ul class="rows" ref=${listRef} onKeyDown=${move}>${rows.map((r) => html`<li key=${r.id}>
      <button type="button" class=${`row ${r.id === selectedId ? "is-on" : ""}`} data-row="1"
        aria-pressed=${String(r.id === selectedId)} onClick=${() => onPick(r.id)}>
        <span class="row-top"><span class="row-title">${r.title || r.id}</span>${r.attention
          ? html`<span class="row-flag">${r.attention} to review</span>` : null}</span>
        <span class="row-meta"><span class="mono">${r.id}</span><span>${labelOf(r.phase)}</span>${r.done ? html`<span>done</span>` : null}</span>
        <${Bar} value=${pct(r.tasks_done, r.tasks_total)} label=${`Tasks complete for ${r.id}`} />
      </button></li>`)}</ul>`;
  }

  // Refs are plain objects inside hooks; this keeps the list's DOM handle stable across renders.
  function useRefList() {
    const [box] = useState(() => ({ current: null }));
    return box;
  }

  function Detail({ row }) {
    return html`<article class="detail">
      <header class="detail-head">
        <div>
          <h2>${row.title || row.id}</h2>
          <p class="mono muted">${row.id}</p>
        </div>
        <a class="btn primary" href=${row.href}>Open initiative <${Icon} name="arrow-up-right" size=${14} /></a>
      </header>
      <div class="detail-status">
        <${Pill} state=${row.phase_state} label=${`phase: ${labelOf(row.phase)}`} />
        ${row.done ? html`<${Pill} state="complete" label="run done" />` : null}
        ${row.store_verdict !== "current" ? html`<${Pill} state="needs_context" label="store needs a migration" />` : null}
      </div>
      <section class="kpis" aria-label="Summary">
        <${Kpi} label="Tasks complete" value=${`${row.tasks_done} / ${row.tasks_total}`} ratio=${pct(row.tasks_done, row.tasks_total)} />
        <${Kpi} label="Evidence proven" value=${`${row.evidence_proven} / ${row.evidence_total}`} ratio=${pct(row.evidence_proven, row.evidence_total)} />
        <${Kpi} label="Open dispatches" value=${row.open_dispatches} />
        <${Kpi} label="Needs attention" value=${row.attention} />
      </section>
      <p class="meta">Last event <span class="mono">${fmtDay(row.last_ts)} ${fmtUtc(row.last_ts)} UTC</span> · ${row.events} journal events</p>
      <figure class="preview-frame">
        <figcaption class="sr-only">Preview of ${row.title || row.id}</figcaption>
        <iframe key=${row.id} src=${row.href} title=${`Initiative ${row.id}`} sandbox="allow-scripts" loading="lazy" referrerpolicy="no-referrer"></iframe>
      </figure>
    </article>`;
  }

  function App() {
    const [theme, setTheme] = useTheme();
    const [selectedId, choose] = useSelected();
    const [filter, setFilter] = useState("all");
    const [sort, setSort] = useState("recent");
    const [query, setQuery] = useState("");
    const options = [
      { value: "all", label: "All", count: M.initiatives.length },
      { value: "active", label: "Active", count: M.totals.active },
      { value: "done", label: "Done", count: M.totals.done },
      { value: "attention", label: "Needs attention", count: M.initiatives.filter((r) => r.attention > 0).length },
    ];
    const rows = useMemo(() => {
      const scoped = M.initiatives.filter((r) => filter === "all"
        || (filter === "active" ? !r.done : filter === "done" ? r.done : r.attention > 0));
      return [...filterByText(scoped, query, (r) => r.id, ["id", "title", "phase"])].sort(ORDER[sort]);
    }, [filter, sort, query]);
    const current = M.initiatives.find((r) => r.id === selectedId) || rows[0] || null;

    return html`<div class="p-app">
      <a class="skip" href="#list">Skip to initiatives</a>
      <header class="p-top">
        <div>
          <p class="brand">Executor</p>
          <h1>Initiatives</h1>
        </div>
        <${ThemeSwitch} theme=${theme} onChange=${setTheme} />
      </header>
      <${StoreBanner} store=${M.store} />
      <section class="totals" aria-label="Totals">
        <${Stat} label="Initiatives" value=${M.totals.initiatives} />
        <${Stat} label="Active" value=${M.totals.active} />
        <${Stat} label="Done" value=${M.totals.done} />
        <${Stat} label="Tasks complete" value=${`${M.totals.tasks_done} / ${M.totals.tasks_total}`} />
        <${Stat} label="Needing attention" value=${M.totals.attention} tone=${M.totals.attention ? "warn" : ""} />
      </section>
      ${M.initiatives.length === 0
        ? html`<${Empty} title="No initiatives in this store" body="Start one with executor new, then run executor views." />`
        : html`<main id="main" class="p-main">
            <section class="p-list" id="list" aria-labelledby="list-h">
              <h2 id="list-h" class="sr-only">Initiatives</h2>
              <${SearchField} label="Search initiatives" value=${query} onInput=${setQuery} />
              <${Chips} label="Filter initiatives" options=${options} value=${filter} onChange=${setFilter} />
              <label class="sort"><span>Sort</span><select value=${sort} onChange=${(e) => setSort(e.currentTarget.value)}>
                <option value="recent">Most recent</option>
                <option value="attention">Needs attention</option>
                <option value="progress">Least progress</option>
              </select></label>
              <${InitiativeList} rows=${rows} selectedId=${current ? current.id : ""} onPick=${choose} />
            </section>
            <section class="p-detail" aria-live="polite">${current
              ? html`<${Detail} row=${current} />`
              : html`<${Empty} title="No initiative matches" body="Clear the search or change the filter." />`}</section>
          </main>`}
    </div>`;
  }

  applyTheme(storedTheme());
  render(html`<${App} />`, document.getElementById("app"));
})();
