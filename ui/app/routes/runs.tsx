import { useEffect, useMemo, useState } from "react";
import { fmt } from "../lib/api";

export function meta() {
  return [{ title: "Runs · Agentic PureCLIP" }];
}

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

interface Change { key: string; from: unknown; to: unknown }
interface RunIter {
  iter: number | null;
  run_id: string;
  params: Record<string, Record<string, unknown>>;
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

export default function Runs() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string>("");

  useEffect(() => {
    let alive = true;
    async function tick() {
      try {
        const res = await fetch(`${API_BASE}/api/runs`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (alive) setRuns(data.runs ?? []);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      }
    }
    tick();
    const t = setInterval(tick, 10000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  // Default to the most recent run once loaded.
  useEffect(() => {
    if (runs && runs.length && !runs.some((r) => r.job_id === selected)) {
      setSelected(runs[0].job_id);
    }
  }, [runs, selected]);

  const run = useMemo(() => runs?.find((r) => r.job_id === selected) ?? null, [runs, selected]);
  const bestComp = run?.best_composite ?? null;

  if (error && !runs) {
    return (
      <>
        <div className="page-title">Runs</div>
        <div className="banner err">Cannot reach monitor API ({error}). Is the SSH tunnel up?</div>
      </>
    );
  }
  if (!runs) {
    return (<><div className="page-title">Runs</div><div className="page-sub">Loading…</div></>);
  }
  if (!runs.length) {
    return (
      <>
        <div className="page-title">Runs</div>
        <div className="page-sub">No runs recorded yet. Decision trails are written for runs launched from now on.</div>
      </>
    );
  }

  return (
    <>
      <div className="page-title">Runs</div>
      <div className="page-sub">
        Iteration-by-iteration trail: what each step scored, which parameters changed, and the decision behind it.
      </div>

      <section className="section">
        <h2>Select a run</h2>
        <div className="form-row">
          <div className="field" style={{ minWidth: 360 }}>
            <label>Run</label>
            <select value={selected} onChange={(e) => setSelected(e.target.value)}>
              {runs.map((r) => (
                <option key={r.job_id} value={r.job_id}>
                  {r.dataset} · {r.optimizer} · {r.job_id} (best {fmt(r.best_composite)}, {r.n_iters} it)
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>

      {run ? (
        <section className="section">
          <div className="exp-head">
            <span className="name">{run.dataset}</span>
            <span className={`badge ${run.optimizer === "optuna" ? "badge-optuna" : "badge-llm"} sm`}>
              {run.optimizer}
            </span>
            <span className="ds-sub">
              {run.job_id} · {run.n_iters} iterations · best{" "}
              <b style={{ color: "var(--green)" }}>{fmt(run.best_composite)}</b>
            </span>
          </div>

          <div className="timeline">
            {run.iterations.map((it, idx) => (
              <div
                key={it.run_id + idx}
                className={`titem${it.composite != null && it.composite === bestComp ? " best" : ""}`}
              >
                <div className="titem-head">
                  <span className="it">iter {it.iter ?? idx}</span>
                  <span className="comp">composite {fmt(it.composite)}</span>
                  {it.composite != null && it.composite === bestComp ? (
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
                  <div className={`reason${run.optimizer === "optuna" ? " tpe" : ""}`}>
                    {run.optimizer === "optuna" ? "🎲 " : "💬 "}
                    {it.reasoning}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}
