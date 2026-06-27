import { useEffect, useState } from "react";
import { Link } from "react-router";

export function meta() {
  return [{ title: "Plan run · Agentic PureCLIP" }];
}

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

type Bounds = Record<string, Record<string, [number, number]>>;

interface Options {
  datasets: string[];
  bounds: Bounds;
  weights: Record<string, number>;
  run_active: boolean;
}

// Short explanations shown next to each tunable.
const HELP: Record<string, string> = {
  bandwidth_nt: "PureCLIP smoothing window — larger = broader/more sensitive sites.",
  merge_distance_nt: "How close sites must be to merge into one.",
  high_precision_mode: "Stricter calling (0/1) — fewer, higher-confidence sites.",
  use_input_covariate: "Use input control to correct background (0/1).",
  min_crosslink_events: "Min crosslink events to keep a site — higher = stricter.",
  force_width: "Fixed site width (nt) ≈ protein footprint.",
  cluster_gap_width: "Max gap when clustering sites into regions.",
};

interface ParamState {
  enabled: boolean;
  lo: number;
  hi: number;
  hard: [number, number];
  section: string;
  key: string;
}

interface SubmitResult {
  ok: boolean;
  message?: string;
  error?: string;
  job_id?: string;
  busy?: boolean;
}

export default function Plan() {
  const [opts, setOpts] = useState<Options | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  const [dataset, setDataset] = useState("");
  const [optimizer, setOptimizer] = useState("llm");
  const [maxIter, setMaxIter] = useState(8);
  const [hours, setHours] = useState(4);
  const [threads, setThreads] = useState(32);
  const [chr21, setChr21] = useState(true);
  const [weights, setWeights] = useState({ reproducibility: 0.5, motif: 0.25, recall: 0.25 });
  const [params, setParams] = useState<Record<string, ParamState>>({});

  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<SubmitResult | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/options`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((o: Options) => {
        setOpts(o);
        setDataset(o.datasets[0] ?? "");
        setWeights({
          reproducibility: o.weights.reproducibility ?? 0.5,
          motif: o.weights.motif ?? 0.25,
          recall: o.weights.recall ?? 0.25,
        });
        const ps: Record<string, ParamState> = {};
        for (const [section, keys] of Object.entries(o.bounds)) {
          for (const [key, [lo, hi]] of Object.entries(keys)) {
            ps[`${section}.${key}`] = { enabled: true, lo, hi, hard: [lo, hi], section, key };
          }
        }
        setParams(ps);
      })
      .catch((e) => setLoadErr(e instanceof Error ? e.message : String(e)));
  }, []);

  function setParam(id: string, patch: Partial<ParamState>) {
    setParams((p) => ({ ...p, [id]: { ...p[id], ...patch } }));
  }

  async function submit() {
    setSubmitting(true);
    setResult(null);
    const bounds: Bounds = {};
    for (const p of Object.values(params)) {
      if (!p.enabled) continue;
      (bounds[p.section] ||= {} as Record<string, [number, number]>)[p.key] = [p.lo, p.hi];
    }
    try {
      const res = await fetch(`${API_BASE}/api/schedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dataset, optimizer, max_iter: maxIter, hours, threads,
          learn_on_chr21: chr21, weights, bounds,
        }),
      });
      const data = (await res.json()) as SubmitResult;
      setResult(data);
    } catch (e) {
      setResult({ ok: false, error: e instanceof Error ? e.message : String(e) });
    } finally {
      setSubmitting(false);
    }
  }

  if (loadErr) {
    return (
      <>
        <div className="page-title">Plan run</div>
        <div className="banner err">Cannot reach monitor API ({loadErr}). Is the SSH tunnel up?</div>
      </>
    );
  }
  if (!opts) {
    return (
      <>
        <div className="page-title">Plan run</div>
        <div className="page-sub">Loading options…</div>
      </>
    );
  }

  const nSelected = Object.values(params).filter((p) => p.enabled).length;

  return (
    <>
      <div className="page-title">Plan run</div>
      <div className="page-sub">
        Configure a parameter search and launch it on the server. This writes a standard manifest and
        runs the same CLI optimizer (<code>scripts/overnight_batch.py</code>), so it stays CLI-compatible.
      </div>

      {result?.ok ? (
        <div className="banner ok">
          ✓ {result.message}{" "}
          <Link to="/" style={{ fontWeight: 700 }}>Watch it on the Dashboard →</Link>
        </div>
      ) : result?.busy ? (
        <div className="banner warn">⏳ {result.error}</div>
      ) : result && !result.ok ? (
        <div className="banner err">✕ {result.error}</div>
      ) : opts.run_active ? (
        <div className="banner warn">A run is currently active — you can plan one, but it can only start once the current run finishes.</div>
      ) : null}

      <section className="section">
        <h2>① Run setup</h2>
        <div className="form-row">
          <div className="field">
            <label>Dataset</label>
            <select value={dataset} onChange={(e) => setDataset(e.target.value)}>
              {opts.datasets.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Optimizer</label>
            <select value={optimizer} onChange={(e) => setOptimizer(e.target.value)}>
              <option value="llm">LLM agent (DeepSeek)</option>
              <option value="optuna">Optuna (TPE / Bayesian)</option>
            </select>
          </div>
          <div className="field">
            <label>Iterations / trials</label>
            <input type="number" min={1} max={50} value={maxIter}
              onChange={(e) => setMaxIter(+e.target.value)} />
          </div>
          <div className="field">
            <label>Time budget (h)</label>
            <input type="number" min={0.1} max={24} step={0.5} value={hours}
              onChange={(e) => setHours(+e.target.value)} />
          </div>
          <div className="field">
            <label>Threads</label>
            <input type="number" min={1} max={64} value={threads}
              onChange={(e) => setThreads(+e.target.value)} />
          </div>
          <div className="field">
            <label>chr21 fast mode</label>
            <label style={{ display: "flex", alignItems: "center", gap: 8, height: 32 }}>
              <input type="checkbox" checked={chr21} onChange={(e) => setChr21(e.target.checked)} />
              <span className="phelp">restrict to chr21 (much faster)</span>
            </label>
          </div>
        </div>
      </section>

      <section className="section">
        <h2>② Objective weights</h2>
        <div className="page-sub" style={{ marginTop: -8 }}>
          What the optimizer maximises (auto-normalised). See <Link to="/variables">Variables</Link> for details.
        </div>
        <div className="form-row">
          {(["reproducibility", "motif", "recall"] as const).map((k) => (
            <div className="field" key={k}>
              <label>{k}</label>
              <input type="number" min={0} max={1} step={0.05} value={weights[k]}
                onChange={(e) => setWeights((w) => ({ ...w, [k]: +e.target.value }))} />
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <h2>③ Parameters to optimize <span style={{ color: "var(--muted)", textTransform: "none", letterSpacing: 0 }}>· {nSelected} selected</span></h2>
        <div className="param-row" style={{ color: "var(--muted)", fontSize: 11, textTransform: "uppercase" }}>
          <span></span><span>parameter</span><span>min</span><span>max</span><span>what it does</span>
        </div>
        {Object.entries(params).map(([id, p]) => (
          <div className={`param-row${p.enabled ? "" : " off"}`} key={id}>
            <input type="checkbox" checked={p.enabled} onChange={(e) => setParam(id, { enabled: e.target.checked })} />
            <span>
              <span className="pname">{p.key}</span>
              <div className="hard">allowed {p.hard[0]}–{p.hard[1]}</div>
            </span>
            <input type="number" value={p.lo} min={p.hard[0]} max={p.hard[1]} disabled={!p.enabled}
              onChange={(e) => setParam(id, { lo: +e.target.value })} />
            <input type="number" value={p.hi} min={p.hard[0]} max={p.hard[1]} disabled={!p.enabled}
              onChange={(e) => setParam(id, { hi: +e.target.value })} />
            <span className="phelp">{HELP[p.key] ?? ""}</span>
          </div>
        ))}
        <div style={{ marginTop: 8, fontSize: 12, color: "var(--muted)" }}>
          Unchecked parameters stay fixed at their default; checked ones are searched within your min–max.
        </div>
      </section>

      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <button className="btn" disabled={submitting || !dataset || nSelected === 0} onClick={submit}>
          {submitting ? "Scheduling…" : "▶ Schedule run"}
        </button>
        <span className="page-sub" style={{ margin: 0 }}>
          {nSelected === 0 ? "Select at least one parameter." : `Launches ${optimizer.toUpperCase()} on ${dataset}.`}
        </span>
      </div>
    </>
  );
}
