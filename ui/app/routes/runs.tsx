import { useEffect, useMemo, useState } from "react";
import { fmt, fmtx, useStatus, type Experiment, type IterationRow } from "../lib/api";
import { BindingLandscape } from "../components/BindingLandscape";

export function meta() {
  return [{ title: "Runs · Agentic PureCLIP" }];
}

const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const CELL_LINES = ["K562", "HepG2"];

interface Change { key: string; from: unknown; to: unknown }
interface RunIter {
  iter: number | null;
  run_id: string;
  changed: Change[];
  reproducibility: number | null;
  motif: number | null;
  recall: number | null;
  n_sites: number | null;
  composite: number | null;
  reasoning: string | null;
}
interface Run {
  job_id: string;
  dataset: string;
  optimizer: string;
  n_iters: number;
  best_composite: number | null;
  iterations: RunIter[];
}

function splitDataset(name: string): { rbp: string; cell: string | null } {
  const parts = name.split("_");
  const last = parts[parts.length - 1];
  if (CELL_LINES.some((c) => c.toLowerCase() === last.toLowerCase())) {
    return { rbp: parts.slice(0, -1).join("_"), cell: last };
  }
  return { rbp: name, cell: null };
}

function bestByOptimizer(it: IterationRow[]) {
  const byOpt: Record<string, number> = {};
  for (const r of it) {
    const o = r.optimizer || "llm";
    if (r.composite != null && (byOpt[o] === undefined || r.composite > byOpt[o])) byOpt[o] = r.composite;
  }
  return byOpt;
}

function winnerOf(it: IterationRow[]): "llm" | "optuna" | "tie" | null {
  const b = bestByOptimizer(it);
  if (b.llm === undefined || b.optuna === undefined) return null;
  return b.llm === b.optuna ? "tie" : b.llm > b.optuna ? "llm" : "optuna";
}

function bestIter(e: Experiment): IterationRow | null {
  let best: IterationRow | null = null;
  for (const r of e.iterations) {
    if (r.composite != null && (!best || (best.composite ?? -1) < r.composite)) best = r;
  }
  return best;
}

export default function Runs() {
  const { data, error } = useStatus(8000);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    let alive = true;
    async function tick() {
      try {
        const res = await fetch(`${API_BASE}/api/runs`);
        if (res.ok) {
          const d = await res.json();
          if (alive) setRuns(d.runs ?? []);
        }
      } catch { /* decision trails are best-effort */ }
    }
    tick();
    const t = setInterval(tick, 12000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const experiments = data?.experiments ?? [];

  // Group datasets by RBP.
  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const byRbp = new Map<string, Experiment[]>();
    for (const e of experiments) {
      if (q && !e.name.toLowerCase().includes(q)) continue;
      const { rbp } = splitDataset(e.name);
      const arr = byRbp.get(rbp) ?? [];
      arr.push(e);
      byRbp.set(rbp, arr);
    }
    return [...byRbp.entries()]
      .map(([rbp, exps]) => ({
        rbp,
        exps: exps.sort((a, b) => a.name.localeCompare(b.name)),
        best: Math.max(...exps.map((e) => e.best_composite ?? -1)),
      }))
      .sort((a, b) => b.best - a.best);
  }, [experiments, query]);

  useEffect(() => {
    if (experiments.length && !experiments.some((e) => e.name === selected)) {
      setSelected(experiments[0].name);
    }
  }, [experiments, selected]);

  const exp = experiments.find((e) => e.name === selected) ?? null;

  if (error && !data) {
    return (
      <>
        <div className="page-title">Runs</div>
        <div className="banner err">Cannot reach monitor API ({error}). Is the SSH tunnel up?</div>
      </>
    );
  }
  if (!data) {
    return (<><div className="page-title">Runs</div><div className="page-sub">Loading…</div></>);
  }
  if (!experiments.length) {
    return (
      <>
        <div className="page-title">Runs</div>
        <div className="page-sub">No runs recorded yet.</div>
      </>
    );
  }

  return (
    <div className="runs-page">
      <div className="page-title no-print">Runs — by dataset</div>
      <div className="page-sub no-print">
        Browse results grouped by RBP. Pick a dataset to see its optimization trajectory,
        where the protein docked, and the full decision trail. Export any dataset as a PDF report.
      </div>

      <div className="runs-layout">
        {/* dataset index */}
        <aside className="runs-index no-print">
          <input
            className="runs-search"
            placeholder="Filter datasets…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="runs-index-scroll">
            {groups.map((g) => (
              <div className="rbp-group" key={g.rbp}>
                <div className="rbp-group-head">
                  <span className="rbp-name">{g.rbp}</span>
                  <span className="rbp-best">{g.best >= 0 ? fmt(g.best, 3) : "—"}</span>
                </div>
                {g.exps.map((e) => {
                  const { cell } = splitDataset(e.name);
                  const w = winnerOf(e.iterations);
                  return (
                    <button
                      key={e.name}
                      className={`ds-item${e.name === selected ? " sel" : ""}`}
                      onClick={() => setSelected(e.name)}
                    >
                      <span className="ds-item-cell">{cell ?? e.name}</span>
                      <span className="ds-item-meta">
                        <span className="ds-item-comp">{fmt(e.best_composite, 3)}</span>
                        {w && <span className={`win ${w} xs`}>{w === "tie" ? "=" : w[0].toUpperCase()}</span>}
                      </span>
                    </button>
                  );
                })}
              </div>
            ))}
            {!groups.length && <div className="landscape-empty">No datasets match “{query}”.</div>}
          </div>
        </aside>

        {/* detail / report */}
        {exp ? <DatasetReport exp={exp} runs={runs} /> : null}
      </div>
    </div>
  );
}

function DatasetReport({ exp, runs }: { exp: Experiment; runs: Run[] }) {
  const { rbp, cell } = splitDataset(exp.name);
  const best = bestIter(exp);
  const byOpt = bestByOptimizer(exp.iterations);
  const w = winnerOf(exp.iterations);
  const repro = best?.reproducibility ?? best?.agreement ?? null;

  // Prefer the richest decision trail (with reasoning) for this dataset.
  const trailRun = useMemo(() => {
    const forDs = runs.filter((r) => r.dataset === exp.name);
    forDs.sort((a, b) => (b.best_composite ?? -1) - (a.best_composite ?? -1));
    return forDs[0] ?? null;
  }, [runs, exp.name]);

  return (
    <section className="run-report">
      <div className="report-head">
        <div>
          <span className="report-title">{rbp}</span>
          {cell && <span className="report-cell">{cell}</span>}
          <span className="report-sub">
            {exp.n_iters} iterations · best composite{" "}
            <b style={{ color: "var(--green)" }}>{fmt(exp.best_composite)}</b>
          </span>
        </div>
        <button className="btn-pdf no-print" onClick={() => window.print()}>⬇ Export PDF</button>
      </div>

      {/* KPI strip */}
      <div className="report-kpis">
        <ReportKpi v={fmt(exp.best_composite)} l="composite" primary />
        <ReportKpi v={fmt(repro, 3)} l="reproducibility" />
        <ReportKpi v={fmt(best?.motif, 3)} l={`motif (${fmtx(best?.enrichment)})`} />
        <ReportKpi v={fmt(best?.recall, 3)} l="known-site recall" />
        <ReportKpi v={best?.n_sites ?? "—"} l="binding sites" />
        <ReportKpi
          v={<><span style={{ color: "var(--blue)" }}>{byOpt.llm !== undefined ? fmt(byOpt.llm, 3) : "—"}</span>
            {" / "}
            <span style={{ color: "var(--yellow)" }}>{byOpt.optuna !== undefined ? fmt(byOpt.optuna, 3) : "—"}</span></>}
          l={<>LLM / Optuna {w && <span className={`win ${w} xs`}>{w === "tie" ? "tie" : w.toUpperCase()}</span>}</>}
        />
      </div>

      {/* composite trajectory */}
      <div className="report-block">
        <h3>Optimization trajectory</h3>
        <TrajectoryChart items={exp.iterations} />
      </div>

      {/* biological view */}
      <div className="report-block">
        <BindingLandscape dataset={exp.name} protein={rbp} cellLine={cell} />
      </div>

      {/* decision trail */}
      <div className="report-block">
        <h3>Decision trail</h3>
        {trailRun && trailRun.iterations.length ? (
          <div className="timeline">
            {trailRun.iterations.map((it, idx) => (
              <div
                key={it.run_id + idx}
                className={`titem${it.composite != null && it.composite === trailRun.best_composite ? " best" : ""}`}
              >
                <div className="titem-head">
                  <span className="it">iter {it.iter ?? idx}</span>
                  <span className="comp">composite {fmt(it.composite)}</span>
                  {it.composite != null && it.composite === trailRun.best_composite ? (
                    <span className="badge badge-done sm">best</span>
                  ) : null}
                </div>
                <div className="titem-metrics">
                  reprod {fmt(it.reproducibility)} · motif {fmt(it.motif)} · recall {fmt(it.recall)} ·{" "}
                  {it.n_sites ?? "—"} sites
                </div>
                {it.changed.length ? (
                  <div className="changes">
                    {it.changed.map((c) => (
                      <span className="change-chip" key={c.key}>
                        {c.key} {String(c.from)} <span className="arr">→</span> {String(c.to)}
                      </span>
                    ))}
                  </div>
                ) : idx > 0 ? (
                  <div className="no-change">no parameter change</div>
                ) : (
                  <div className="no-change">starting parameters</div>
                )}
                {it.reasoning ? (
                  <div className={`reason${trailRun.optimizer === "optuna" ? " tpe" : ""}`}>
                    {trailRun.optimizer === "optuna" ? "🎲 " : "💬 "}
                    {it.reasoning}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <IterTable items={exp.iterations} bestRun={exp.best_run} />
        )}
      </div>
    </section>
  );
}

function ReportKpi({ v, l, primary }: { v: React.ReactNode; l: React.ReactNode; primary?: boolean }) {
  return (
    <div className={`report-kpi${primary ? " primary" : ""}`}>
      <div className="v">{v}</div>
      <div className="l">{l}</div>
    </div>
  );
}

function IterTable({ items, bestRun }: { items: IterationRow[]; bestRun: string | null }) {
  return (
    <table>
      <thead>
        <tr><th>run</th><th>iter</th><th>sites</th><th>reprod.</th><th>motif</th><th>recall</th><th>composite</th></tr>
      </thead>
      <tbody>
        {items.map((it) => (
          <tr key={it.run_id} className={it.run_id === bestRun ? "best" : ""}>
            <td>{it.run_id}</td>
            <td>{it.iter ?? "—"}</td>
            <td>{it.n_sites ?? "—"}</td>
            <td>{fmt(it.reproducibility ?? it.agreement, 3)}</td>
            <td>{fmt(it.motif, 3)}</td>
            <td>{fmt(it.recall, 3)}</td>
            <td><b>{fmt(it.composite)}</b></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* Composite-over-iterations line chart. */
function TrajectoryChart({ items }: { items: IterationRow[] }) {
  const pts = items.map((it) => it.composite).map((v) => (v == null ? null : v));
  const vals = pts.filter((v): v is number => v != null);
  if (!vals.length) return <div className="landscape-empty">No scored iterations.</div>;
  const W = 640, H = 150, pad = 24;
  const max = Math.max(...vals), min = Math.min(...vals);
  const span = max - min || 1;
  const n = pts.length;
  const x = (i: number) => pad + (n === 1 ? (W - 2 * pad) / 2 : (i / (n - 1)) * (W - 2 * pad));
  const y = (v: number) => H - pad - ((v - min) / span) * (H - 2 * pad);
  const line = pts
    .map((v, i) => (v == null ? null : `${x(i)},${y(v)}`))
    .filter(Boolean)
    .join(" ");
  const bestIdx = pts.indexOf(max);
  return (
    <svg className="traj" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      <line x1={pad} y1={H - pad} x2={W - pad} y2={H - pad} className="traj-axis" />
      <polyline points={line} className="traj-line" />
      {pts.map((v, i) =>
        v == null ? null : (
          <circle key={i} cx={x(i)} cy={y(v)} r={i === bestIdx ? 4.5 : 3}
            className={i === bestIdx ? "traj-dot best" : "traj-dot"} />
        )
      )}
      <text x={pad} y={14} className="traj-lbl">{max.toFixed(3)}</text>
      <text x={pad} y={H - pad + 16} className="traj-lbl">iter 0 → {n - 1}</text>
    </svg>
  );
}
