import { useEffect, useMemo, useState } from "react";
import { fmt, useStatus, armMeta, ARM_ORDER, type ArmKey, type Experiment } from "../lib/api";
import { BindingLandscape } from "../components/BindingLandscape";

export function meta() {
  return [{ title: "Method comparison · Agentic PureCLIP" }];
}

const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const CELL_LINES = ["K562", "HepG2"];

// Difficulty tiers (Results.md) — orders the protein index along the axis the
// thesis actually studies. Proteins not listed fall under "other".
const TIER: Record<string, string> = {
  RBFOX2: "crisp", QKI: "crisp", PUM1: "crisp", PUM2: "crisp",
  HNRNPK: "degenerate", SRSF1: "degenerate", HNRNPM: "degenerate",
  U2AF1: "positional", U2AF2: "positional", SF3B1: "positional", SF3B4: "positional",
  RBM22: "positional",
};
const TIER_ORDER = ["crisp", "degenerate", "positional", "other"];

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
  arm?: string;
  no_priors?: boolean;
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

function armOf(r: Run): ArmKey {
  if ((r.arm as ArmKey) && ARM_ORDER.includes(r.arm as ArmKey)) return r.arm as ArmKey;
  if ((r.optimizer || "").toLowerCase() === "optuna") return "optuna";
  if (r.no_priors || /no[_-]?prior/i.test(r.job_id)) return "llm_noprior";
  return "llm";
}

/** The iteration that achieved this run's best composite. */
function bestIterOf(r: Run): RunIter | null {
  let best: RunIter | null = null;
  for (const it of r.iterations) {
    if (it.composite != null && (!best || (best.composite ?? -1) < it.composite)) best = it;
  }
  return best;
}

/** Best-composite-so-far at each iteration index (the convergence curve). */
function convergence(r: Run): (number | null)[] {
  const sorted = [...r.iterations].sort((a, b) => (a.iter ?? 0) - (b.iter ?? 0));
  let running: number | null = null;
  return sorted.map((it) => {
    if (it.composite != null) running = running == null ? it.composite : Math.max(running, it.composite);
    return running;
  });
}

export default function Runs() {
  const { data, error } = useStatus(8000);
  const [runs, setRuns] = useState<Run[]>([]);
  const [protein, setProtein] = useState<string>("");
  const [cell, setCell] = useState<string>("");
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
      } catch { /* best-effort */ }
    }
    tick();
    const t = setInterval(tick, 12000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  // protein -> { cell -> Run[] }, plus per-protein best composite for the index.
  const byProtein = useMemo(() => {
    const m = new Map<string, { cells: Map<string, Run[]>; best: number }>();
    for (const r of runs) {
      const { rbp, cell } = splitDataset(r.dataset);
      const c = cell ?? "—";
      const entry = m.get(rbp) ?? { cells: new Map(), best: -1 };
      const arr = entry.cells.get(c) ?? [];
      arr.push(r);
      entry.cells.set(c, arr);
      entry.best = Math.max(entry.best, r.best_composite ?? -1);
      m.set(rbp, entry);
    }
    return m;
  }, [runs]);

  // Group the protein index by difficulty tier.
  const tiers = useMemo(() => {
    const q = query.trim().toLowerCase();
    const groups = new Map<string, { rbp: string; best: number; cells: string[] }[]>();
    for (const [rbp, entry] of byProtein) {
      if (q && !rbp.toLowerCase().includes(q)) continue;
      const tier = TIER[rbp] ?? "other";
      const arr = groups.get(tier) ?? [];
      arr.push({ rbp, best: entry.best, cells: [...entry.cells.keys()] });
      groups.set(tier, arr);
    }
    return TIER_ORDER
      .filter((t) => groups.has(t))
      .map((t) => ({ tier: t, items: groups.get(t)!.sort((a, b) => b.best - a.best) }));
  }, [byProtein, query]);

  // Default selection: highest-scoring protein, first cell line.
  useEffect(() => {
    if (!protein && byProtein.size) {
      let bestRbp = "", best = -Infinity;
      for (const [rbp, e] of byProtein) if (e.best > best) { best = e.best; bestRbp = rbp; }
      setProtein(bestRbp);
    }
  }, [byProtein, protein]);

  const proteinEntry = protein ? byProtein.get(protein) : undefined;
  const cells = proteinEntry ? [...proteinEntry.cells.keys()] : [];
  const activeCell = cell && cells.includes(cell) ? cell : cells[0] ?? "";
  const armRuns = proteinEntry?.cells.get(activeCell) ?? [];
  const dataset = armRuns[0]?.dataset ?? (activeCell !== "—" ? `${protein}_${activeCell}` : protein);

  if (error && !runs.length) {
    return (<><div className="page-title">Method comparison</div>
      <div className="banner err">Cannot reach monitor API ({error}). Is the SSH tunnel up?</div></>);
  }
  if (!runs.length) {
    return (<><div className="page-title">Method comparison</div>
      <div className="page-sub">{data ? "No completed optimization runs recorded yet." : "Loading…"}</div></>);
  }

  return (
    <div className="cmp-page">
      <div className="page-title no-print">Method comparison</div>
      <div className="page-sub no-print">
        How the three sampling strategies — <b style={{ color: "var(--blue)" }}>LLM (with prior)</b>,{" "}
        <b style={{ color: "var(--purple)" }}>LLM (no prior)</b> and{" "}
        <b style={{ color: "var(--yellow)" }}>Optuna</b> — do on the <i>same</i> dataset. Pick a protein,
        then a cell line.
      </div>

      <div className="cmp-layout">
        <aside className="cmp-index no-print">
          <input className="runs-search" placeholder="Filter proteins…" value={query}
            onChange={(e) => setQuery(e.target.value)} />
          <div className="cmp-index-scroll">
            {tiers.map((g) => (
              <div className="tier-group" key={g.tier}>
                <div className="tier-head">{g.tier}</div>
                {g.items.map((it) => (
                  <button key={it.rbp}
                    className={`protein-item${it.rbp === protein ? " sel" : ""}`}
                    onClick={() => { setProtein(it.rbp); setCell(""); }}>
                    <span className="protein-name">{it.rbp}</span>
                    <span className="protein-best">{it.best >= 0 ? fmt(it.best, 3) : "—"}</span>
                  </button>
                ))}
              </div>
            ))}
            {!tiers.length && <div className="landscape-empty">No proteins match “{query}”.</div>}
          </div>
        </aside>

        <main className="cmp-main">
          {proteinEntry ? (
            <Comparison
              protein={protein}
              cell={activeCell}
              cells={cells}
              onCell={setCell}
              dataset={dataset}
              armRuns={armRuns}
            />
          ) : null}

          <OverallBest experiments={data?.experiments ?? []} onPick={(name) => {
            const { rbp, cell } = splitDataset(name);
            setProtein(rbp); setCell(cell ?? "");
          }} />
        </main>
      </div>
    </div>
  );
}

function Comparison({ protein, cell, cells, onCell, dataset, armRuns }: {
  protein: string; cell: string; cells: string[]; onCell: (c: string) => void;
  dataset: string; armRuns: Run[];
}) {
  // Index the present arms.
  const arms = useMemo(() => {
    const m = new Map<ArmKey, Run>();
    for (const r of armRuns) if (!m.has(armOf(r))) m.set(armOf(r), r);
    return ARM_ORDER.filter((a) => m.has(a)).map((a) => ({ arm: a, run: m.get(a)! }));
  }, [armRuns]);

  const llm = arms.find((a) => a.arm === "llm")?.run;
  const noprior = arms.find((a) => a.arm === "llm_noprior")?.run;
  const optuna = arms.find((a) => a.arm === "optuna")?.run;
  const baseline = llm ? convergence(llm)[0] ?? null : null; // LLM iter_00 = default params

  const bestArm = arms.reduce<ArmKey | null>(
    (acc, a) => (a.run.best_composite != null &&
      (acc == null || (a.run.best_composite > (arms.find((x) => x.arm === acc)!.run.best_composite ?? -1)))
      ? a.arm : acc), null);

  // Decision-trail arm picker.
  const [trailArm, setTrailArm] = useState<ArmKey | null>(null);
  useEffect(() => { setTrailArm(null); }, [dataset]);
  const trailRun = arms.find((a) => a.arm === trailArm)?.run ?? arms[0]?.run ?? null;

  const delta = (a?: Run, b?: Run) =>
    a?.best_composite != null && b?.best_composite != null ? a.best_composite - b.best_composite : null;
  const h2h = delta(llm, optuna);        // LLM prior vs Optuna
  const abl = delta(llm, noprior);       // prior benefit

  return (
    <section className="cmp-report">
      <div className="cmp-head">
        <div>
          <span className="cmp-title">{protein}</span>
          <span className="cmp-dataset">{dataset}</span>
        </div>
        {cells.length > 1 && (
          <div className="cell-tabs no-print">
            {cells.map((c) => (
              <button key={c} className={`cell-tab${c === cell ? " sel" : ""}`} onClick={() => onCell(c)}>{c}</button>
            ))}
          </div>
        )}
        <button className="btn-pdf no-print" onClick={() => window.print()}>⬇ Export PDF</button>
      </div>

      {/* Head-to-head + ablation deltas — the two numbers the thesis reports. */}
      <div className="delta-strip">
        <DeltaChip label="LLM (prior) vs Optuna" d={h2h} pos="LLM wins" neg="Optuna wins" />
        <DeltaChip label="Prior benefit (LLM vs no-prior)" d={abl} pos="prior helps" neg="prior hurts"
          absent={!noprior ? "no ablation run for this dataset" : undefined} />
      </div>

      {/* Arm summary cards */}
      <div className="arm-cards">
        {arms.map(({ arm, run }) => (
          <ArmCard key={arm} arm={arm} run={run} baseline={baseline} winner={arm === bestArm} />
        ))}
      </div>

      {/* Convergence — best-so-far per method */}
      <div className="cmp-block">
        <h3>Convergence — best composite so far</h3>
        <ConvergenceChart arms={arms} baseline={baseline} />
        <div className="chart-legend">
          {arms.map(({ arm }) => {
            const m = armMeta(arm);
            return (
              <span className="legend-item" key={arm}>
                <span className="legend-swatch" style={{ background: m.color }} /> {m.name} <i>({m.tag})</i>
              </span>
            );
          })}
          {baseline != null && (
            <span className="legend-item"><span className="legend-swatch dashed" /> baseline (default params)</span>
          )}
        </div>
      </div>

      {/* Metric breakdown at each method's best iteration */}
      <div className="cmp-block">
        <h3>Where each method wins — metrics at best iteration</h3>
        <MetricTable arms={arms} bestArm={bestArm} />
      </div>

      {/* Per-arm reasoning / decision trail */}
      <div className="cmp-block">
        <div className="trail-head">
          <h3>Decision trail &amp; reasoning</h3>
          <div className="run-picker no-print">
            {arms.map(({ arm, run }) => {
              const m = armMeta(arm);
              return (
                <button key={arm} className={`run-pill${run === trailRun ? " sel" : ""}`}
                  onClick={() => setTrailArm(arm)} title={run.job_id}>
                  <span className={`badge ${m.badge} sm`}>{m.name} · {m.tag}</span>
                  <span className="run-pill-comp">{fmt(run.best_composite, 3)}</span>
                </button>
              );
            })}
          </div>
        </div>
        {trailRun ? <DecisionTrail run={trailRun} arm={armOf(trailRun)} /> : null}
      </div>

      {/* Biological view — secondary */}
      <details className="cmp-block cmp-details">
        <summary>🧬 Binding landscape (best run)</summary>
        <BindingLandscape dataset={dataset} protein={protein} cellLine={cell === "—" ? null : cell} />
      </details>
    </section>
  );
}

function DeltaChip({ label, d, pos, neg, absent }: {
  label: string; d: number | null; pos: string; neg: string; absent?: string;
}) {
  if (absent) return (
    <div className="delta-chip tie"><div className="delta-label">{label}</div><div className="delta-val">{absent}</div></div>
  );
  if (d == null) return (
    <div className="delta-chip tie"><div className="delta-label">{label}</div><div className="delta-val">—</div></div>
  );
  const cls = Math.abs(d) < 1e-9 ? "tie" : d > 0 ? "pos" : "neg";
  const verdict = cls === "tie" ? "tie" : d > 0 ? pos : neg;
  return (
    <div className={`delta-chip ${cls}`}>
      <div className="delta-label">{label}</div>
      <div className="delta-val">{d > 0 ? "+" : ""}{d.toFixed(3)} <span className="delta-verdict">{verdict}</span></div>
    </div>
  );
}

function ArmCard({ arm, run, baseline, winner }: {
  arm: ArmKey; run: Run; baseline: number | null; winner: boolean;
}) {
  const m = armMeta(arm);
  const best = bestIterOf(run);
  const lift = run.best_composite != null && baseline != null ? run.best_composite - baseline : null;
  const bestIterN = best?.iter ?? null;
  return (
    <div className={`arm-card${winner ? " win" : ""}`} style={{ borderTopColor: m.color }}>
      <div className="arm-card-head">
        <span className={`badge ${m.badge}`}>{m.name} · {m.tag}</span>
        {winner && <span className="crown" title="best composite on this dataset">👑</span>}
      </div>
      <div className="arm-comp" style={{ color: m.color }}>{fmt(run.best_composite, 3)}</div>
      <div className="arm-sub">
        {lift != null && <span className={lift >= 0 ? "up" : "down"}>{lift >= 0 ? "▲" : "▼"} {Math.abs(lift).toFixed(3)} vs baseline</span>}
      </div>
      <div className="arm-metrics">
        <MBar l="reprod" v={best?.reproducibility ?? null} color={m.color} />
        <MBar l="motif" v={best?.motif ?? null} color={m.color} />
        <MBar l="recall" v={best?.recall ?? null} color={m.color} />
      </div>
      <div className="arm-foot">
        {best?.n_sites ?? "—"} sites · converged at iter {bestIterN ?? "—"} / {run.n_iters - 1}
      </div>
    </div>
  );
}

function MBar({ l, v, color }: { l: string; v: number | null; color: string }) {
  const pct = v == null ? 0 : Math.max(0, Math.min(1, v)) * 100;
  return (
    <div className="mbar">
      <span className="mbar-l">{l}</span>
      <span className="mbar-track"><span className="mbar-fill" style={{ width: `${pct}%`, background: color }} /></span>
      <span className="mbar-v">{fmt(v, 2)}</span>
    </div>
  );
}

function MetricTable({ arms, bestArm }: { arms: { arm: ArmKey; run: Run }[]; bestArm: ArmKey | null }) {
  const rows: { key: string; label: string; get: (b: RunIter | null) => number | null; pct?: boolean }[] = [
    { key: "composite", label: "composite", get: (b) => b?.composite ?? null, pct: true },
    { key: "reproducibility", label: "reproducibility", get: (b) => b?.reproducibility ?? null, pct: true },
    { key: "motif", label: "motif hit-rate", get: (b) => b?.motif ?? null, pct: true },
    { key: "recall", label: "known-site recall", get: (b) => b?.recall ?? null, pct: true },
    { key: "n_sites", label: "binding sites", get: (b) => b?.n_sites ?? null },
  ];
  const bests = arms.map(({ arm, run }) => ({ arm, meta: armMeta(arm), it: bestIterOf(run) }));
  return (
    <table className="cmp-table">
      <thead>
        <tr>
          <th></th>
          {bests.map((b) => (
            <th key={b.arm} className={b.arm === bestArm ? "col-win" : ""}>
              <span className={`badge ${b.meta.badge} sm`}>{b.meta.name} · {b.meta.tag}</span>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const vals = bests.map((b) => row.get(b.it));
          const max = Math.max(...vals.filter((v): v is number => v != null), -Infinity);
          return (
            <tr key={row.key}>
              <td className="row-label">{row.label}</td>
              {bests.map((b, i) => {
                const v = vals[i];
                const isMax = v != null && v === max && vals.filter((x) => x === max).length === 1;
                return (
                  <td key={b.arm} className={isMax ? "cell-win" : ""}>
                    {row.pct && v != null ? (
                      <span className="cell-bar">
                        <span className="cell-bar-fill" style={{ width: `${Math.max(0, Math.min(1, v)) * 100}%`, background: b.meta.color }} />
                        <span className="cell-bar-v">{fmt(v, 3)}</span>
                      </span>
                    ) : (
                      <b>{v ?? "—"}</b>
                    )}
                  </td>
                );
              })}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/* Overlaid best-so-far curves, one polyline per arm + baseline. */
function ConvergenceChart({ arms, baseline }: { arms: { arm: ArmKey; run: Run }[]; baseline: number | null }) {
  const series = arms.map(({ arm, run }) => ({ arm, meta: armMeta(arm), pts: convergence(run) }));
  const allVals = series.flatMap((s) => s.pts.filter((v): v is number => v != null));
  if (baseline != null) allVals.push(baseline);
  if (!allVals.length) return <div className="landscape-empty">No scored iterations yet.</div>;
  const maxLen = Math.max(...series.map((s) => s.pts.length), 1);
  const W = 660, H = 200, pad = 30;
  const hi = Math.max(...allVals), lo = Math.min(...allVals, 0);
  const span = hi - lo || 1;
  const x = (i: number) => pad + (maxLen === 1 ? (W - 2 * pad) / 2 : (i / (maxLen - 1)) * (W - 2 * pad));
  const y = (v: number) => H - pad - ((v - lo) / span) * (H - 2 * pad);
  return (
    <svg className="cmp-chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
      {/* y gridlines */}
      {[0, 0.5, 1].map((f) => {
        const v = lo + f * span;
        return (
          <g key={f}>
            <line x1={pad} y1={y(v)} x2={W - pad} y2={y(v)} className="grid" />
            <text x={4} y={y(v) + 3} className="ax-lbl">{v.toFixed(2)}</text>
          </g>
        );
      })}
      {baseline != null && <line x1={pad} y1={y(baseline)} x2={W - pad} y2={y(baseline)} className="baseline-line" />}
      <text x={pad} y={H - 8} className="ax-lbl">iter 0</text>
      <text x={W - pad} y={H - 8} className="ax-lbl" textAnchor="end">iter {maxLen - 1}</text>
      {series.map((s) => {
        const line = s.pts.map((v, i) => (v == null ? null : `${x(i)},${y(v)}`)).filter(Boolean).join(" ");
        return (
          <g key={s.arm}>
            <polyline points={line} className="cmp-line" style={{ stroke: s.meta.color }} />
            {s.pts.map((v, i) => v == null ? null : (
              <circle key={i} cx={x(i)} cy={y(v)} r={2.5} style={{ fill: s.meta.color }} />
            ))}
          </g>
        );
      })}
    </svg>
  );
}

function DecisionTrail({ run, arm }: { run: Run; arm: ArmKey }) {
  const m = armMeta(arm);
  const isOptuna = arm === "optuna";
  return (
    <>
      <div className="trail-meta">
        <span className={`badge ${m.badge}`}>{m.name} · {m.tag}</span>
        <span className="trail-desc">{m.desc}{isOptuna ? "" : " Each step lists the parameters it changed and why."}</span>
      </div>
      {run.iterations.length ? (
        <div className="timeline">
          {run.iterations.map((it, idx) => (
            <div key={it.run_id + idx}
              className={`titem${it.composite != null && it.composite === run.best_composite ? " best" : ""}`}>
              <div className="titem-head">
                <span className="it">iter {it.iter ?? idx}</span>
                <span className="comp">composite {fmt(it.composite)}</span>
                {it.composite != null && it.composite === run.best_composite ? (
                  <span className="badge badge-done sm">best</span>
                ) : null}
              </div>
              <div className="titem-metrics">
                reprod {fmt(it.reproducibility)} · motif {fmt(it.motif)} · recall {fmt(it.recall)} · {it.n_sites ?? "—"} sites
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
                <div className="no-change">starting parameters (baseline)</div>
              )}
              {it.reasoning ? (
                <div className={`reason${isOptuna ? " tpe" : ""}`}>{isOptuna ? "🎲 " : "💬 "}{it.reasoning}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : <div className="landscape-empty">No iterations recorded.</div>}
    </>
  );
}

/* Secondary: cross-dataset overview, collapsed by default. */
function OverallBest({ experiments, onPick }: { experiments: Experiment[]; onPick: (name: string) => void }) {
  const rows = useMemo(() => {
    return [...experiments]
      .filter((e) => e.best_composite != null)
      .sort((a, b) => (b.best_composite ?? -1) - (a.best_composite ?? -1));
  }, [experiments]);
  if (!rows.length) return null;
  return (
    <details className="cmp-details overall-best no-print">
      <summary>All datasets — overall best (secondary)</summary>
      <table className="cmp-table">
        <thead><tr><th>dataset</th><th>best composite</th><th>iters</th></tr></thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.name} className="clickable" onClick={() => onPick(e.name)}>
              <td className="row-label">{e.name}</td>
              <td><b style={{ color: "var(--green)" }}>{fmt(e.best_composite, 3)}</b></td>
              <td>{e.n_iters}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
