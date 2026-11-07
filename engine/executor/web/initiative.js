/* The initiative explorer. It renders from the embedded model only: no network
   and no clock. Selection lives in the URL hash, so a link reopens the same
   section with the same item selected. */
(() => {
  "use strict";
  const { render } = preact;
  const { html, useState, useEffect, useMemo, useRef, Icon, Glyph, GlyphShapes, stateOf, labelOf,
    Pill, Chips, SearchField, DataTable, Kpi, Empty, Palette, ThemeSwitch, StoreBanner,
    parseHash, useRoute, routeTo, storedTheme, applyTheme, useTheme, filterByText, groupBy,
    countBy, fmtUtc, fmtDay, fmtDur, pct, truncate } = window.EX;

  const M = JSON.parse(document.getElementById("executor-model").textContent);

  const SECTIONS = [
    { id: "overview", label: "Overview", icon: "layers" },
    { id: "graph", label: "Graph", icon: "branch" },
    { id: "tasks", label: "Tasks", icon: "list" },
    { id: "dispatches", label: "Dispatches", icon: "arrow-up-right" },
    { id: "evidence", label: "Evidence", icon: "target" },
    { id: "decisions", label: "Decisions", icon: "file" },
    { id: "artifacts", label: "Artifacts", icon: "file" },
    { id: "timeline", label: "Timeline", icon: "clock" },
  ];
  const SECTION_OF = {
    task: "tasks", artifact: "artifacts", entity: "graph", dispatch: "dispatches",
    evidence: "evidence", change: "decisions", ruling: "decisions",
  };
  const KIND_LABEL = {
    task: "Task", artifact: "Artifact", entity: "Entity", dispatch: "Dispatch",
    evidence: "Evidence", change: "Change", ruling: "Decision",
  };

  // One lookup for every addressable id. Tasks and artifacts win over the entity that repeats them.
  const byId = new Map();
  const put = (id, kind, item) => { if (id && !byId.has(id)) byId.set(id, { kind, item }); };
  M.tasks.forEach((t) => put(t.id, "task", t));
  M.artifacts.forEach((a) => put(a.id, "artifact", a));
  M.entities.forEach((e) => put(e.id, "entity", e));
  M.dispatches.forEach((d) => put(d.id, "dispatch", d));
  M.evidence.forEach((e) => put(e.id, "evidence", e));
  M.changes.forEach((c) => put(c.id, "change", c));
  M.rulings.forEach((r) => put(r.id, "ruling", r));
  const entityById = new Map(M.entities.map((e) => [e.id, e]));

  function labelFor(kind, item) {
    switch (kind) {
      case "dispatch": return `${item.role} dispatch`;
      case "evidence": return item.criterion || item.id;
      case "ruling": return item.decision;
      default: return item.title || item.id;
    }
  }

  const navHref = (id, selectedId) => `#${id}${selectedId ? `/${encodeURIComponent(selectedId)}` : ""}`;

  function openItem(id) {
    const hit = byId.get(id);
    if (hit) routeTo(SECTION_OF[hit.kind], id);
    else routeTo(parseHash(location.hash).section || "overview", "");
  }

  function PageHead({ title, sub, tools }) {
    return html`<header class="page-head"><div><h1>${title}</h1>${sub ? html`<p class="sub">${sub}</p>` : null}</div>${tools || null}</header>`;
  }

  // ---------------------------------------------------------------- overview

  function OverviewView({ ctx }) {
    const init = M.init;
    const k = M.kpis;
    const recent = M.timeline.slice(-8).reverse();
    return html`<div class="stack">
      <header class="hero">
        <div>
          <h1>${init.title || init.id}</h1>
          <p class="hero-id mono">${init.id}</p>
        </div>
        <div class="hero-status">
          <${Pill} state=${init.phase_state} label=${`phase: ${labelOf(init.phase)}`} />
          ${init.done ? html`<${Pill} state="complete" label="run done" />` : null}
          <span class="meta">Last event <span class="mono">${fmtDay(init.last_ts)} ${fmtUtc(init.last_ts)} UTC</span> · ${init.events} events</span>
        </div>
      </header>

      <section class="block" aria-labelledby="track-h">
        <h2 id="track-h">Phase track</h2>
        <ol class="track">${M.phases.map((p) => html`<li class="track-step" aria-current=${p.current ? "step" : undefined}>
          <span class="track-name"><${Glyph} kind=${stateOf(p.state)[0]} />${labelOf(p.name)}</span>
          <span class="track-dur mono">${p.seconds != null ? fmtDur(p.seconds) : p.entered ? "" : "not reached"}</span>
        </li>`)}</ol>
      </section>

      <section class="kpis" aria-label="Summary">
        <${Kpi} label="Tasks complete" value=${`${k.tasks.complete} / ${k.tasks.total}`} ratio=${pct(k.tasks.complete, k.tasks.total)} />
        <${Kpi} label="Evidence proven" value=${`${k.evidence.proven} / ${k.evidence.criteria}`}
          sub=${k.evidence.unproven ? `${k.evidence.unproven} unproven` : "all proven"} ratio=${pct(k.evidence.proven, k.evidence.criteria)} />
        <${Kpi} label="Dispatches answered" value=${`${k.dispatches.answered} / ${k.dispatches.total}`}
          sub=${`${k.dispatches.open} open · ${k.dispatches.abandoned} abandoned`} />
        <${Kpi} label="Changes pending" value=${k.changes.pending} sub=${`${k.changes.total} recorded`} />
      </section>

      <section class="block" aria-labelledby="att-h">
        <h2 id="att-h">Needs attention <span class="count">${M.attention.length}</span></h2>
        ${M.attention.length === 0
          ? html`<${Empty} title="Nothing is blocked or unproven" body="Every task, criterion, and change in this run is settled." />`
          : html`<ul class="attention">${M.attention.map((a) => html`<li><button type="button" class="att-btn" onClick=${() => openItem(a.ref)}>
              <${Pill} state=${a.severity === "bad" ? "blocked" : a.severity === "warn" ? "needs_context" : "pending"} label=${labelOf(a.kind)} />
              <span>${a.label}</span></button></li>`)}</ul>`}
      </section>

      <section class="block" aria-labelledby="feed-h">
        <h2 id="feed-h">Recent activity</h2>
        <ol class="feed">${recent.map((e) => html`<li class="feed-row">
          <span class="mono muted">${fmtUtc(e.ts)}</span>
          <span class="event-kind">${labelOf(e.kind)}</span>
          ${byId.has(e.entity) ? html`<button type="button" class="link-btn mono" onClick=${() => openItem(e.entity)}>${e.entity}</button>`
            : html`<span class="mono muted">${e.entity}</span>`}
        </li>`)}</ol>
        <p><a class="link" href="#timeline">Open the full timeline</a></p>
      </section>

      <details class="policy"><summary>Run policy</summary>${Object.keys(M.policy).length
        ? html`<dl class="kv">${Object.entries(M.policy).map(([key, value]) => html`<div><dt class="mono">${key}</dt><dd class="mono">${JSON.stringify(value)}</dd></div>`)}</dl>`
        : html`<p class="muted">No policy recorded.</p>`}</details>
    </div>`;
  }

  // ---------------------------------------------------------------- graph

  const tierFor = (k) => (k < 0.5 ? "far" : k < 0.8 ? "mid" : "near");
  const MIN_READABLE = 0.7; // below this the graph opens at this scale and pans, rather than shrinking
  const TITLE_CHARS = 26;

  // Word-wrapped title lines. A line that still overflows the last slot ends in an ellipsis.
  function wrapTitle(text, width, maxLines) {
    const lines = [];
    let line = "";
    for (let word of String(text || "").split(/\s+/).filter(Boolean)) {
      if (word.length > width) word = `${word.slice(0, width - 1)}…`;
      const next = line ? `${line} ${word}` : word;
      if (next.length <= width) line = next;
      else {
        if (line) lines.push(line);
        line = word;
      }
    }
    if (line) lines.push(line);
    if (lines.length > maxLines) {
      lines.length = maxLines;
      lines[maxLines - 1] = `${lines[maxLines - 1].slice(0, width - 1).trimEnd()}…`;
    }
    return lines;
  }
  const EDGE_CLASS = { "": "edge-dep", contains: "edge-contains", cites: "edge-cites" };

  function GraphView({ ctx }) {
    const [mode, setMode] = useState("deps");
    const [focus, setFocus] = useState(false);
    const control = useRef(null);
    const layout = mode === "deps" ? M.dag : M.entity_graph;
    const hasSelection = ctx.selectedId !== "" && layout.nodes.some((n) => n.id === ctx.selectedId);
    useEffect(() => { if (!hasSelection && focus) setFocus(false); }, [hasSelection]);
    const summary = mode === "deps"
      ? `${M.tasks.length} tasks and ${M.dag.edges.length} dependency edges`
      : `${M.entities.length} entities and ${M.entity_edges.length} containment and citation edges`;
    const tools = html`<div class="graph-tools">
      <div class="seg" role="group" aria-label="Graph mode">
        <button type="button" class="seg-btn" aria-pressed=${String(mode === "deps")} onClick=${() => setMode("deps")}>Dependencies</button>
        <button type="button" class="seg-btn" aria-pressed=${String(mode === "lanes")} onClick=${() => setMode("lanes")}>Entities</button>
      </div>
      <button type="button" class="btn icon" aria-label="Zoom in" title="Zoom in" onClick=${() => control.current && control.current.zoomBy(1.25)}><${Icon} name="zoom-in" size=${15} /></button>
      <button type="button" class="btn icon" aria-label="Zoom out" title="Zoom out" onClick=${() => control.current && control.current.zoomBy(0.8)}><${Icon} name="zoom-out" size=${15} /></button>
      <button type="button" class="btn icon" aria-label="Fit to view" title="Fit to view" onClick=${() => control.current && control.current.fit(true)}><${Icon} name="fit" size=${15} /></button>
      <button type="button" class="btn" aria-pressed=${String(focus)} disabled=${!hasSelection} onClick=${() => setFocus(!focus)}><${Icon} name="target" size=${14} /><span>Focus selection</span></button>
    </div>`;
    return html`<div class="stack">
      <${PageHead} title="Graph" sub=${summary} tools=${tools} />
      ${layout.nodes.length === 0
        ? html`<${Empty} title="No graph yet" body=${mode === "deps" ? "No task dependencies were planned." : "No entities were recorded."} />`
        : html`<${GraphStage} key=${mode} layout=${layout} mode=${mode} ctx=${ctx} focus=${focus} control=${control} />`}
      <${Legend} mode=${mode} />
    </div>`;
  }

  function GraphStage({ layout, mode, ctx, focus, control }) {
    const svgRef = useRef(null);
    const worldRef = useRef(null);
    const box = layout.box;
    const selectedId = ctx.selectedId;
    const neighbours = useMemo(() => {
      const node = layout.nodes.find((n) => n.id === selectedId);
      return new Set(node ? node.neighbours : []);
    }, [layout, selectedId]);

    useEffect(() => {
      const svg = d3.select(svgRef.current);
      const world = worldRef.current;
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const zoom = d3.zoom().scaleExtent([0.2, 2.5]).on("zoom", (event) => {
        world.setAttribute("transform", event.transform.toString());
        world.dataset.tier = tierFor(event.transform.k);
      });
      svg.call(zoom).on("dblclick.zoom", null);
      // Fit when the whole graph reads at a usable size. Otherwise open at the
      // readable scale from the top-left, so the reader pans rather than squints.
      const frame = (animate) => {
        const { width, height } = svgRef.current.getBoundingClientRect();
        const pad = 36;
        const fitK = Math.min((width - pad * 2) / layout.width, (height - pad * 2) / layout.height, 1.25);
        const readable = fitK >= MIN_READABLE;
        const k = readable ? fitK : MIN_READABLE;
        const t = readable
          ? d3.zoomIdentity.translate((width - layout.width * k) / 2, (height - layout.height * k) / 2).scale(k)
          : d3.zoomIdentity.translate(pad, pad).scale(k);
        (animate && !reduce ? svg.transition().duration(240) : svg).call(zoom.transform, t);
      };
      control.current = {
        fit: frame,
        zoomBy: (factor) => svg.transition().duration(reduce ? 0 : 160).call(zoom.scaleBy, factor),
      };
      frame(false);
      return () => { svg.on(".zoom", null); control.current = null; };
    }, [layout]);

    const stepFocus = (from, dir) => {
      const cx = (n) => n.x + box.w / 2;
      const cy = (n) => n.y + box.h / 2;
      let best = null;
      let bestScore = Infinity;
      layout.nodes.forEach((n) => {
        if (n.id === from.id) return;
        const dx = cx(n) - cx(from);
        const dy = cy(n) - cy(from);
        const along = { right: dx, left: -dx, down: dy, up: -dy }[dir];
        if (along <= 0) return;
        const across = dir === "left" || dir === "right" ? Math.abs(dy) : Math.abs(dx);
        const score = along + across * 2;
        if (score < bestScore) { best = n; bestScore = score; }
      });
      if (best) {
        const el = svgRef.current.querySelector(`[data-id="${CSS.escape(best.id)}"]`);
        if (el) el.focus();
      }
    };

    const edgeClass = (e) => {
      const hot = selectedId && (e.from === selectedId || e.to === selectedId);
      const dim = focus && selectedId && !hot;
      return ["edge", EDGE_CLASS[e.kind] || "edge-dep", hot ? "is-hot" : "", dim ? "is-dim" : ""].join(" ").trim();
    };

    return html`<div class="stage">
      <svg ref=${svgRef} class="graph" role="group" aria-label=${mode === "deps" ? "Task dependency graph" : "Entity graph"}
        onClick=${(e) => { if (e.target === svgRef.current) ctx.select(""); }}>
        <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path class="arrow" d="M0 0 10 5 0 10z" /></marker></defs>
        <g ref=${worldRef} class="world" data-tier="near">
          ${mode === "lanes" ? layout.lanes.map((l) => html`<text key=${l.name} class="lane-label" x=${l.x} y=${l.y}>${l.name.toUpperCase()}</text>`) : null}
          ${layout.edges.map((e) => html`<path key=${`${e.from}>${e.to}:${e.kind}`} class=${edgeClass(e)} d=${e.d}
            marker-end=${mode === "deps" ? "url(#arrow)" : undefined} />`)}
          ${layout.nodes.map((n) => html`<${NodeView} key=${n.id} node=${n} box=${box}
            selected=${n.id === selectedId}
            dimmed=${Boolean(focus && selectedId && n.id !== selectedId && !neighbours.has(n.id))}
            onSelect=${ctx.select} onStep=${stepFocus} />`)}
        </g>
      </svg>
      <p class="stage-hint">Drag to pan. Scroll or pinch to zoom. Arrow keys move between nodes; Enter selects.</p>
    </div>`;
  }

  function NodeView({ node, box, selected, dimmed, onSelect, onStep }) {
    const ent = entityById.get(node.id);
    const hit = byId.get(node.id);
    const title = ent ? ent.title : node.id;
    const state = hit && hit.kind === "task" ? hit.item.state
      : hit && hit.kind === "artifact" ? (hit.item.status || "") : "";
    const sub = hit && hit.kind === "task" ? `${hit.item.short} · ${labelOf(hit.item.state)}`
      : ent ? `${labelOf(ent.type)}${ent.sub ? ` · ${ent.sub}` : ""}` : "";
    const [glyph, tone] = stateOf(state);
    const cls = ["node", selected ? "is-selected" : "", dimmed ? "is-dim" : "", tone === "bad" ? "is-bad" : ""].join(" ").trim();
    const arrows = { ArrowRight: "right", ArrowLeft: "left", ArrowDown: "down", ArrowUp: "up" };
    const onKey = (e) => {
      if (arrows[e.key]) { e.preventDefault(); onStep(node, arrows[e.key]); }
      else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(node.id); }
    };
    const lines = wrapTitle(title, TITLE_CHARS, 2);
    return html`<g class=${cls} data-id=${node.id} transform=${`translate(${node.x} ${node.y})`} tabindex="0" role="button"
        aria-pressed=${String(selected)} aria-label=${`${title}. ${labelOf(state) || labelOf(ent ? ent.type : "")}`}
        onClick=${(e) => { e.stopPropagation(); onSelect(node.id); }} onKeyDown=${onKey}>
      <title>${title}</title>
      <rect class="node-box" width=${box.w} height=${box.h} rx="10" />
      <g class=${`node-glyph tone-${tone}`} transform="translate(18 16)"><${GlyphShapes} kind=${glyph} /></g>
      <text class="node-title">${lines.map((line, i) => html`<tspan key=${i} x="36" y=${22 + i * 17}>${line}</tspan>`)}</text>
      <text class="node-sub" x="36" y=${box.h - 12}>${truncate(sub, 36)}</text>
    </g>`;
  }

  function Legend({ mode }) {
    const shapes = [["complete", "complete"], ["active", "in progress"], ["pending", "pending"],
      ["warn", "needs attention"], ["bad", "blocked or failed"]];
    return html`<ul class="legend" aria-label="Legend">
      ${shapes.map(([kind, label]) => html`<li><svg class="glyph" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><${GlyphShapes} kind=${kind} /></svg>${label}</li>`)}
      ${mode === "lanes"
        ? html`<li><span class="line" aria-hidden="true"></span>contains</li><li><span class="line line-dash" aria-hidden="true"></span>cites</li>`
        : html`<li><span class="line" aria-hidden="true"></span>depends on (the arrow points to the dependent task)</li>`}
    </ul>`;
  }

  // ---------------------------------------------------------------- tables

  function TasksView({ ctx }) {
    const [query, setQuery] = useState("");
    const [state, setState] = useState("all");
    const rows = useMemo(() => filterByText(
      M.tasks.filter((t) => state === "all" || t.state === state), query, (t) => t.id,
      ["id", "title", "goal", "plan"]), [query, state]);
    const options = [{ value: "all", label: "All", count: M.tasks.length }].concat(
      [...new Set(M.tasks.map((t) => t.state))].map((s) => ({
        value: s, label: labelOf(s), count: M.tasks.filter((t) => t.state === s).length })));
    const columns = [
      { key: "short", label: "Task", render: (t) => html`<span class="mono">${t.short}</span>` },
      { key: "title", label: "Title" },
      { key: "state", label: "State", value: (t) => labelOf(t.state), render: (t) => html`<${Pill} state=${t.state} />` },
      { key: "depends", label: "Depends", num: true, value: (t) => t.depends_on.length, render: (t) => t.depends_on.length },
      { key: "dependents", label: "Required by", num: true, value: (t) => t.dependents.length, render: (t) => t.dependents.length },
      { key: "dispatches", label: "Dispatches", num: true, render: (t) => t.dispatches },
      { key: "fix", label: "Fix rounds", num: true, value: (t) => t.fix_rounds, render: (t) => t.fix_rounds },
    ];
    return html`<div class="stack">
      <${PageHead} title="Tasks" sub=${`${M.tasks.length} tasks in ${M.init.id}`} />
      <div class="toolbar">
        <${Chips} label="Filter tasks by state" options=${options} value=${state} onChange=${setState} />
        <${SearchField} label="Search tasks" value=${query} onInput=${setQuery} />
      </div>
      <${DataTable} caption="Tasks" columns=${columns} rows=${rows} rowId=${(t) => t.id}
        selected=${ctx.selectedId} onSelect=${ctx.select} empty="No task matches this filter." />
    </div>`;
  }

  function DispatchesView({ ctx }) {
    const [role, setRole] = useState("all");
    const [outcome, setOutcome] = useState("all");
    const outcomes = ["answered", "open", "abandoned", "spawn_error"];
    const rows = M.dispatches.filter((d) => (role === "all" || d.role === role) && (outcome === "all" || d.outcome === outcome));
    const roleOptions = [{ value: "all", label: "All roles", count: M.dispatches.length }].concat(
      [...new Set(M.dispatches.map((d) => d.role))].sort().map((r) => ({
        value: r, label: r, count: M.dispatches.filter((d) => d.role === r).length })));
    const outcomeOptions = [{ value: "all", label: "Any outcome", count: M.dispatches.length }].concat(
      outcomes.map((o) => ({ value: o, label: labelOf(o), count: M.dispatches.filter((d) => d.outcome === o).length })));
    const columns = [
      { key: "id", label: "Dispatch", render: (d) => html`<span class="mono">${d.id}</span>` },
      { key: "at", label: "Sent (UTC)", render: (d) => html`<span class="mono">${fmtUtc(d.at)}</span>` },
      { key: "role", label: "Role" },
      { key: "entity", label: "Entity", render: (d) => html`<button type="button" class="link-btn mono"
        onClick=${(e) => { e.stopPropagation(); openItem(d.entity); }}>${d.entity}</button>` },
      { key: "outcome", label: "Outcome", value: (d) => labelOf(d.outcome), render: (d) => html`<${Pill} state=${d.outcome} />` },
    ];
    return html`<div class="stack">
      <${PageHead} title="Dispatches" sub=${`${M.dispatches.length} dispatches; ${M.kpis.dispatches.open} still open`} />
      <div class="toolbar">
        <${Chips} label="Filter by role" options=${roleOptions} value=${role} onChange=${setRole} />
        <${Chips} label="Filter by outcome" options=${outcomeOptions} value=${outcome} onChange=${setOutcome} />
      </div>
      <${DataTable} caption="Dispatches" columns=${columns} rows=${rows} rowId=${(d) => d.id}
        selected=${ctx.selectedId} onSelect=${ctx.select} empty="No dispatch matches these filters." />
    </div>`;
  }

  function EvidenceView({ ctx }) {
    const [verdict, setVerdict] = useState("all");
    const counts = countBy(M.evidence, (e) => e.verdict);
    const total = M.evidence.length || 1;
    const rows = M.evidence.filter((e) => verdict === "all" || e.verdict === verdict);
    const options = [{ value: "all", label: "All", count: M.evidence.length }].concat(
      Object.keys(counts).sort().map((v) => ({ value: v, label: labelOf(v), count: counts[v] })));
    const spread = Object.entries(counts).map(([v, n]) => `${n} ${labelOf(v)}`).join(", ") || "none";
    const columns = [
      { key: "id", label: "Criterion", render: (e) => html`<span class="mono">${e.id}</span>` },
      { key: "criterion", label: "Check", render: (e) => e.criterion || "—" },
      { key: "verdict", label: "Verdict", value: (e) => labelOf(e.verdict), render: (e) => html`<${Pill} state=${e.verdict} />` },
      { key: "runs", label: "Runs", num: true, render: (e) => e.runs },
      { key: "commit", label: "Commit", render: (e) => html`<span class="mono">${e.commit || "—"}</span>` },
      { key: "cites", label: "Cites", num: true, value: (e) => e.cites.length, render: (e) => e.cites.length },
    ];
    return html`<div class="stack">
      <${PageHead} title="Evidence" sub=${`${M.evidence.length} criteria; ${M.kpis.evidence.proven} proven`} />
      <div class="stack-bar" role="img" aria-label=${`Verdicts: ${spread}`}>${Object.entries(counts).map(([v, n]) =>
        html`<span class=${`seg-fill tone-${stateOf(v)[1]}`} style=${{ width: `${(n / total) * 100}%` }}></span>`)}</div>
      <div class="toolbar">
        <${Chips} label="Filter by verdict" options=${options} value=${verdict} onChange=${setVerdict} />
      </div>
      <${DataTable} caption="Evidence criteria" columns=${columns} rows=${rows} rowId=${(e) => e.id}
        selected=${ctx.selectedId} onSelect=${ctx.select} empty="No criterion has this verdict." />
    </div>`;
  }

  function DecisionsView({ ctx }) {
    const columns = [
      { key: "id", label: "Change", render: (c) => html`<span class="mono">${c.id}</span>` },
      { key: "title", label: "Title" },
      { key: "state", label: "State", value: (c) => labelOf(c.state), render: (c) => html`<${Pill} state=${c.state || "pending"} label=${labelOf(c.state) || "open"} />` },
      { key: "radius", label: "Touches", render: (c) => `${c.radius.artifacts} artifacts · ${c.radius.tasks} tasks · ${c.radius.plans} plans` },
    ];
    return html`<div class="stack">
      <${PageHead} title="Decisions" sub=${`${M.rulings.length} rulings and ${M.changes.length} change requests`} />
      <section class="block" aria-labelledby="rul-h">
        <h2 id="rul-h">Rulings</h2>
        ${M.rulings.length === 0 ? html`<${Empty} title="No rulings yet" />`
          : html`<ol class="rulings">${M.rulings.map((r) => html`<li class=${`ruling ${ctx.selectedId === r.id ? "is-on" : ""}`}>
              <div class="ruling-head"><span class="mono muted">${r.id}</span>
                <button type="button" class="link-btn" onClick=${() => ctx.select(r.id)}>Inspect</button></div>
              <p class="ruling-decision">${r.decision}</p>
              <dl class="kv"><div><dt>Why</dt><dd>${r.why || "—"}</dd></div><div><dt>If wrong</dt><dd>${r.cost_if_wrong || "—"}</dd></div></dl>
            </li>`)}</ol>`}
      </section>
      <section class="block" aria-labelledby="chg-h">
        <h2 id="chg-h">Change requests</h2>
        <${DataTable} caption="Change requests" columns=${columns} rows=${M.changes} rowId=${(c) => c.id}
          selected=${ctx.selectedId} onSelect=${ctx.select} empty="No change request has been recorded." />
      </section>
    </div>`;
  }

  function ArtifactsView({ ctx }) {
    const [kind, setKind] = useState("all");
    const [query, setQuery] = useState("");
    const rows = useMemo(() => filterByText(
      M.artifacts.filter((a) => kind === "all" || a.kind === kind), query, (a) => a.id,
      ["title", "summary", "kind", "id"]), [kind, query]);
    const options = [{ value: "all", label: "All", count: M.artifacts.length }].concat(
      [...new Set(M.artifacts.map((a) => a.kind))].sort().map((k) => ({
        value: k, label: k, count: M.artifacts.filter((a) => a.kind === k).length })));
    return html`<div class="stack">
      <${PageHead} title="Artifacts" sub=${`${M.artifacts.length} artifacts`} />
      <div class="toolbar">
        <${Chips} label="Filter by kind" options=${options} value=${kind} onChange=${setKind} />
        <${SearchField} label="Search artifacts" value=${query} onInput=${setQuery} />
      </div>
      ${rows.length === 0
        ? html`<${Empty} title="No artifact matches" body="Clear the search or pick another kind." />`
        : html`<ul class="cards">${rows.map((a) => html`<li><button type="button"
            class=${`card-btn ${ctx.selectedId === a.id ? "is-on" : ""}`} aria-pressed=${String(ctx.selectedId === a.id)}
            onClick=${() => ctx.select(a.id)}>
            <span class="card-kind mono">${a.kind}</span>
            <span class="card-title">${a.title}</span>
            ${a.summary ? html`<span class="card-summary">${a.summary}</span>` : null}
            <span class="card-meta"><${Pill} state=${a.status || "pending"} label=${labelOf(a.status) || "no status"} />
              ${a.cites.length ? html`<span class="meta">cites ${a.cites.length}</span>` : null}
              ${a.cited_by.length ? html`<span class="meta">cited by ${a.cited_by.length}</span>` : null}</span>
          </button></li>`)}</ul>`}
    </div>`;
  }

  // ---------------------------------------------------------------- timeline

  function DailyChart({ timeline }) {
    const ref = useRef(null);
    useEffect(() => {
      const days = d3.rollups(timeline, (v) => v.length, (e) => e.day).sort((a, b) => (a[0] < b[0] ? -1 : 1));
      const width = 640;
      const height = 96;
      const margin = { top: 8, right: 8, bottom: 20, left: 8 };
      const x = d3.scaleBand().domain(days.map((d) => d[0])).range([margin.left, width - margin.right]).padding(0.25);
      const y = d3.scaleLinear().domain([0, d3.max(days, (d) => d[1]) || 1]).nice().range([height - margin.bottom, margin.top]);
      const svg = d3.select(ref.current);
      svg.selectAll("*").remove();
      svg.attr("viewBox", `0 0 ${width} ${height}`);
      svg.append("g").attr("class", "bars").selectAll("rect").data(days).join("rect")
        .attr("x", (d) => x(d[0])).attr("y", (d) => y(d[1])).attr("width", x.bandwidth())
        .attr("height", (d) => y(0) - y(d[1])).attr("rx", 2)
        .append("title").text((d) => `${d[0]}: ${d[1]} events`);
      if (days.length) {
        svg.append("text").attr("class", "chart-label").attr("x", margin.left).attr("y", height - 4).text(days[0][0]);
        svg.append("text").attr("class", "chart-label").attr("x", width - margin.right).attr("y", height - 4)
          .attr("text-anchor", "end").text(days[days.length - 1][0]);
      }
    }, [timeline]);
    return html`<figure class="chart"><figcaption>Events per day (UTC)</figcaption>
      <svg ref=${ref} class="chart-svg" role="img" aria-label=${`${timeline.length} journal events across ${new Set(timeline.map((e) => e.day)).size} days`}
        preserveAspectRatio="none"></svg></figure>`;
  }

  function TimelineView({ ctx }) {
    const [kind, setKind] = useState("all");
    const [query, setQuery] = useState("");
    const counts = countBy(M.timeline, (e) => e.kind);
    const rows = useMemo(() => {
      const q = query.trim().toLowerCase();
      return M.timeline.filter((e) => (kind === "all" || e.kind === kind)
        && (!q || [e.kind, e.entity, e.actor, e.dispatch, e.ts].join(" ").toLowerCase().includes(q)));
    }, [kind, query]);
    const days = useMemo(() => groupBy(rows, (e) => e.day), [rows]);
    const options = [{ value: "all", label: "All", count: M.timeline.length }].concat(
      Object.keys(counts).sort().map((k) => ({ value: k, label: labelOf(k), count: counts[k] })));
    return html`<div class="stack">
      <${PageHead} title="Timeline" sub=${`${M.timeline.length} journal events`} />
      <${DailyChart} timeline=${M.timeline} />
      <div class="toolbar">
        <${Chips} label="Filter by event kind" options=${options} value=${kind} onChange=${setKind} />
        <${SearchField} label="Search events" value=${query} onInput=${setQuery} />
      </div>
      ${rows.length === 0
        ? html`<${Empty} title="No event matches" body="Clear the search or pick another kind." />`
        : html`<div class="days">${[...days].map(([day, list]) => html`<section class="day" aria-label=${day}>
            <h2 class="day-head"><span class="mono">${day}</span><span class="count">${list.length} events</span></h2>
            <ol class="events">${list.map((e) => html`<li class="event">
              <span class="mono muted">${fmtUtc(e.ts)}</span>
              <span class="mono muted">#${e.seq}</span>
              <span class="event-kind">${labelOf(e.kind)}</span>
              ${byId.has(e.entity) ? html`<button type="button" class="link-btn mono" onClick=${() => openItem(e.entity)}>${e.entity}</button>`
                : e.entity ? html`<span class="mono muted">${e.entity}</span>` : null}
              ${e.dispatch ? html`<span class="mono muted">${e.dispatch}</span>` : null}
            </li>`)}</ol></section>`)}</div>`}
    </div>`;
  }

  // ---------------------------------------------------------------- inspector

  function RefList({ title, ids, ctx }) {
    if (!ids.length) return html`<div class="ref-block"><h3>${title}</h3><p class="muted">None.</p></div>`;
    return html`<div class="ref-block"><h3>${title} <span class="count">${ids.length}</span></h3><ul class="refs">${ids.map((id) => {
      const hit = byId.get(id);
      const label = hit ? labelFor(hit.kind, hit.item) : id;
      return html`<li><button type="button" class="ref-btn" onClick=${() => ctx.select(id)}>
        <span class="ref-label">${truncate(label, 80)}</span><span class="mono">${id}</span></button></li>`;
    })}</ul></div>`;
  }

  function Tags({ title, items, mono }) {
    return html`<div class="ref-block"><h3>${title} <span class="count">${items.length}</span></h3><ul class="tags">${items.map((x) =>
      html`<li class=${mono ? "mono" : ""}>${x}</li>`)}</ul></div>`;
  }

  function TaskDetail({ item: t, ctx }) {
    return html`<div class="inspector-section">
      <dl class="kv">
        <div><dt>State</dt><dd><${Pill} state=${t.state} /></dd></div>
        <div><dt>Plan</dt><dd class="mono">${t.plan}</dd></div>
        <div><dt>Dispatches</dt><dd class="num">${t.dispatches}</dd></div>
        <div><dt>Fix rounds</dt><dd class="num">${t.fix_rounds}</dd></div>
      </dl>
      ${t.goal ? html`<p class="prose">${t.goal}</p>` : null}
      <${RefList} title="Depends on" ids=${t.depends_on} ctx=${ctx} />
      <${RefList} title="Required by" ids=${t.dependents} ctx=${ctx} />
      ${t.unresolved.length ? html`<p class="warn-line">Unresolved references: <span class="mono">${t.unresolved.join(", ")}</span></p>` : null}
      ${t.provides.length ? html`<${Tags} title="Provides" items=${t.provides} />` : null}
      ${t.consumes.length ? html`<${Tags} title="Consumes" items=${t.consumes} />` : null}
      ${t.files.length ? html`<${Tags} title="Files" items=${t.files} mono=${true} />` : null}
    </div>`;
  }

  function EntityDetail({ item: e, ctx }) {
    const out = M.entity_edges.filter((x) => x.from === e.id);
    const incoming = M.entity_edges.filter((x) => x.to === e.id);
    const ids = (list, kind, field) => list.filter((x) => x.kind === kind).map((x) => x[field]);
    return html`<div class="inspector-section">
      <dl class="kv"><div><dt>Type</dt><dd>${labelOf(e.type)}</dd></div>${e.sub
        ? html`<div><dt>Artifact kind</dt><dd>${e.sub}</dd></div>` : null}</dl>
      <${RefList} title="Contains" ids=${ids(out, "contains", "to")} ctx=${ctx} />
      <${RefList} title="Contained by" ids=${ids(incoming, "contains", "from")} ctx=${ctx} />
      <${RefList} title="Cites" ids=${ids(out, "cites", "to")} ctx=${ctx} />
      <${RefList} title="Cited by" ids=${ids(incoming, "cites", "from")} ctx=${ctx} />
    </div>`;
  }

  function ArtifactDetail({ item: a, ctx }) {
    return html`<div class="inspector-section">
      <dl class="kv">
        <div><dt>Kind</dt><dd class="mono">${a.kind}</dd></div>
        <div><dt>Status</dt><dd><${Pill} state=${a.status || "pending"} label=${labelOf(a.status) || "no status"} /></dd></div>
        <div><dt>Round</dt><dd class="num">${a.round}</dd></div>
      </dl>
      ${a.summary ? html`<p class="prose">${a.summary}</p>` : null}
      <${RefList} title="Cites" ids=${a.cites} ctx=${ctx} />
      <${RefList} title="Cited by" ids=${a.cited_by} ctx=${ctx} />
    </div>`;
  }

  function DispatchDetail({ item: d, ctx }) {
    return html`<div class="inspector-section"><dl class="kv">
      <div><dt>Role</dt><dd>${d.role}</dd></div>
      <div><dt>Entity</dt><dd><button type="button" class="link-btn mono" onClick=${() => ctx.select(d.entity)}>${d.entity}</button></dd></div>
      <div><dt>Sent (UTC)</dt><dd class="mono">${fmtDay(d.at)} ${fmtUtc(d.at)}</dd></div>
      <div><dt>Outcome</dt><dd><${Pill} state=${d.outcome} /></dd></div>
    </dl></div>`;
  }

  function EvidenceDetail({ item: e, ctx }) {
    return html`<div class="inspector-section">
      ${e.criterion ? html`<p class="prose">${e.criterion}</p>` : null}
      <dl class="kv">
        <div><dt>Verdict</dt><dd><${Pill} state=${e.verdict} /></dd></div>
        <div><dt>Runs</dt><dd class="num">${e.runs}</dd></div>
        <div><dt>Commit</dt><dd class="mono">${e.commit || "—"}</dd></div>
      </dl>
      <${RefList} title="Cites" ids=${e.cites} ctx=${ctx} />
    </div>`;
  }

  function ChangeDetail({ item: c }) {
    const r = c.radius;
    return html`<div class="inspector-section">
      <dl class="kv">
        <div><dt>State</dt><dd><${Pill} state=${c.state || "pending"} label=${labelOf(c.state) || "open"} /></dd></div>
        <div><dt>Touches</dt><dd class="num">${r.artifacts} artifacts · ${r.tasks} tasks · ${r.plans} plans</dd></div>
      </dl>
      ${c.reason ? html`<p class="prose"><span class="strong">Reason.</span> ${c.reason}</p>` : null}
      ${c.why ? html`<p class="prose">${c.why}</p>` : null}
    </div>`;
  }

  function RulingDetail({ item: r }) {
    return html`<div class="inspector-section">
      <p class="prose strong">${r.decision}</p>
      <dl class="kv"><div><dt>Why</dt><dd>${r.why || "—"}</dd></div><div><dt>If wrong</dt><dd>${r.cost_if_wrong || "—"}</dd></div></dl>
    </div>`;
  }

  const DETAIL = {
    task: TaskDetail, entity: EntityDetail, artifact: ArtifactDetail, dispatch: DispatchDetail,
    evidence: EvidenceDetail, change: ChangeDetail, ruling: RulingDetail,
  };

  function QuickFacts() {
    const blocked = M.tasks.filter((t) => t.state === "blocked").length;
    return html`<dl class="kv">
      <div><dt>Blocked tasks</dt><dd class="num">${blocked}</dd></div>
      <div><dt>Unproven criteria</dt><dd class="num">${M.kpis.evidence.unproven}</dd></div>
      <div><dt>Open dispatches</dt><dd class="num">${M.kpis.dispatches.open}</dd></div>
      <div><dt>Pending changes</dt><dd class="num">${M.kpis.changes.pending}</dd></div>
    </dl>`;
  }

  function Inspector({ ctx }) {
    const sel = ctx.selection;
    if (!sel) {
      return html`<div class="inspector-body">
        <h2>Nothing selected</h2>
        <p class="muted">Select a node, row, or card to read it here. Press <kbd>/</kbd> to find anything.</p>
        <${QuickFacts} />
      </div>`;
    }
    return html`<div class="inspector-body">
      <div class="inspector-head">
        <div>
          <p class="meta">${KIND_LABEL[sel.kind]}</p>
          <h2 class="inspector-title">${labelFor(sel.kind, sel.item)}</h2>
          <p class="mono muted">${sel.id}</p>
        </div>
        <button type="button" class="btn icon" aria-label="Clear selection" title="Clear selection" onClick=${() => ctx.select("")}><${Icon} name="x" size=${14} /></button>
      </div>
      <${DETAIL[sel.kind]} item=${sel.item} ctx=${ctx} />
    </div>`;
  }

  // ---------------------------------------------------------------- shell

  function buildPalette() {
    const items = [];
    SECTIONS.forEach((s) => items.push({ key: `section:${s.id}`, kind: "Section", label: s.label, sub: "", go: () => routeTo(s.id, "") }));
    M.tasks.forEach((t) => items.push({ key: `task:${t.id}`, kind: "Task", label: t.title, sub: `${t.short} · ${labelOf(t.state)}`, go: () => routeTo("tasks", t.id) }));
    M.artifacts.forEach((a) => items.push({ key: `artifact:${a.id}`, kind: "Artifact", label: a.title, sub: a.kind, go: () => routeTo("artifacts", a.id) }));
    M.evidence.forEach((e) => items.push({ key: `evidence:${e.id}`, kind: "Evidence", label: e.criterion || e.id, sub: `${e.id} · ${labelOf(e.verdict)}`, go: () => routeTo("evidence", e.id) }));
    M.dispatches.forEach((d) => items.push({ key: `dispatch:${d.id}`, kind: "Dispatch", label: `${d.role} → ${d.entity}`, sub: `${d.id} · ${labelOf(d.outcome)}`, go: () => routeTo("dispatches", d.id) }));
    M.changes.forEach((c) => items.push({ key: `change:${c.id}`, kind: "Change", label: c.title, sub: `${c.id} · ${labelOf(c.state)}`, go: () => routeTo("decisions", c.id) }));
    M.rulings.forEach((r) => items.push({ key: `ruling:${r.id}`, kind: "Decision", label: r.decision, sub: r.id, go: () => routeTo("decisions", r.id) }));
    return items;
  }

  const VIEWS = {
    overview: OverviewView, graph: GraphView, tasks: TasksView, dispatches: DispatchesView,
    evidence: EvidenceView, decisions: DecisionsView, artifacts: ArtifactsView, timeline: TimelineView,
  };

  function HelpDialog({ open, onClose }) {
    const ref = useRef(null);
    useEffect(() => {
      const dialog = ref.current;
      if (!dialog) return;
      if (open && !dialog.open) dialog.showModal();
      if (!open && dialog.open) dialog.close();
    }, [open]);
    return html`<dialog class="help" ref=${ref} aria-labelledby="help-title" onClose=${onClose}>
      <div class="help-body">
        <h2 id="help-title">Keyboard</h2>
        <dl class="kv keys">
          <div><dt><kbd>/</kbd> or <kbd>Ctrl</kbd> <kbd>K</kbd></dt><dd>Find anything</dd></div>
          <div><dt><kbd>?</kbd></dt><dd>Show this list</dd></div>
          <div><dt><kbd>Esc</kbd></dt><dd>Clear the selection</dd></div>
          <div><dt><kbd>←</kbd> <kbd>→</kbd> <kbd>↑</kbd> <kbd>↓</kbd></dt><dd>Move between graph nodes</dd></div>
          <div><dt><kbd>Enter</kbd></dt><dd>Select the focused node or row</dd></div>
        </dl>
        <div class="help-foot"><button type="button" class="btn" onClick=${onClose}>Close</button></div>
      </div>
    </dialog>`;
  }

  function App() {
    const route = useRoute();
    const [theme, setTheme] = useTheme();
    const [finding, setFinding] = useState(false);
    const [helping, setHelping] = useState(false);
    const section = SECTIONS.some((s) => s.id === route.section) ? route.section : "overview";
    const hit = route.id ? byId.get(route.id) : undefined;
    const selection = hit ? { id: route.id, kind: hit.kind, item: hit.item } : null;
    const ctx = {
      section,
      selection,
      selectedId: selection ? selection.id : "",
      select: (id) => routeTo(section, id),
      openItem,
    };
    const paletteItems = useMemo(buildPalette, []);
    const live = useRef({});
    live.current = { section, selected: Boolean(selection), overlay: finding || helping };

    useEffect(() => {
      const onKey = (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setFinding(true); return; }
        const tag = e.target && e.target.tagName ? e.target.tagName : "";
        if (live.current.overlay || /^(INPUT|TEXTAREA|SELECT)$/.test(tag) || (e.target && e.target.isContentEditable)) return;
        if (e.key === "/") { e.preventDefault(); setFinding(true); }
        else if (e.key === "?") setHelping(true);
        else if (e.key === "Escape" && live.current.selected) routeTo(live.current.section, "");
      };
      document.addEventListener("keydown", onKey);
      return () => document.removeEventListener("keydown", onKey);
    }, []);

    const counts = {
      overview: M.kpis.attention.total,
      graph: M.tasks.length,
      tasks: M.tasks.length,
      dispatches: M.dispatches.length,
      evidence: M.evidence.length,
      decisions: M.rulings.length + M.changes.length,
      artifacts: M.artifacts.length,
      timeline: M.timeline.length,
    };
    const View = VIEWS[section];

    return html`<div class=${`app${section === "graph" ? " is-wide" : ""}${selection ? " has-selection" : ""}`}>
      <a class="skip" href="#main">Skip to content</a>
      <header class="topbar">
        <nav class="crumbs" aria-label="Breadcrumb">
          <a class="crumb" href=${M.init.parent_href}>All initiatives</a>
          <span class="crumb-sep" aria-hidden="true">/</span>
          <span class="crumb-current mono">${M.init.id}</span>
        </nav>
        <div class="top-actions">
          <button type="button" class="btn" onClick=${() => setFinding(true)}><${Icon} name="search" size=${14} /><span>Find</span><kbd>/</kbd></button>
          <button type="button" class="btn icon" aria-label="Keyboard shortcuts" title="Keyboard shortcuts" onClick=${() => setHelping(true)}><${Icon} name="keyboard" size=${14} /></button>
          <${ThemeSwitch} theme=${theme} onChange=${setTheme} />
        </div>
      </header>

      <nav class="rail" aria-label="Sections">
        <p class="rail-title">${M.init.title || M.init.id}</p>
        <ul class="rail-list">${SECTIONS.map((s) => html`<li key=${s.id}><a class="nav-item" href=${navHref(s.id, ctx.selectedId)}
            aria-current=${section === s.id ? "page" : undefined}><${Icon} name=${s.icon} size=${15} /><span>${s.label}</span>
            <span class="nav-count num">${counts[s.id]}</span></a></li>`)}</ul>
        <div class="rail-foot">
          <div class="rail-phase"><span class="meta">Phase</span><${Pill} state=${M.init.phase_state} label=${labelOf(M.init.phase)} /></div>
        </div>
      </nav>

      <main id="main" class="main" tabindex="-1">
        <${StoreBanner} store=${M.store} />
        <${View} ctx=${ctx} />
      </main>

      <aside class="inspector" aria-label="Details"><${Inspector} ctx=${ctx} /></aside>
      <${Palette} open=${finding} items=${paletteItems} onClose=${() => setFinding(false)} />
      <${HelpDialog} open=${helping} onClose=${() => setHelping(false)} />
    </div>`;
  }

  applyTheme(storedTheme());
  render(html`<${App} />`, document.getElementById("app"));
})();
