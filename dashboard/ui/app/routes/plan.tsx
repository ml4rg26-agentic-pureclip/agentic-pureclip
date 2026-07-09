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

  const [command, setCommand] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

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
    setCommand(null); // any edit invalidates a previously generated command
  }

  // Build the `agentic-pureclip-run` invocation that reproduces this form.
  function buildCommand(): string {
    const parts = [
      "uv run agentic-pureclip-run",
      `--dataset ${dataset}`,
      `--optimizer ${optimizer}`,
      `--max-iter ${maxIter}`,
      `--hours ${hours}`,
      `--threads ${threads}`,
      chr21 ? "--chr21" : "--no-chr21",
    ];
    for (const k of ["reproducibility", "motif", "recall"] as const) {
      parts.push(`--weight ${k}=${weights[k]}`);
    }
    for (const p of Object.values(params)) {
      if (!p.enabled) continue;
      parts.push(`--param ${p.section}.${p.key}=${p.lo}:${p.hi}`);
    }
    return parts.join(" ");
  }

  async function copyCommand() {
    if (!command) return;
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard may be unavailable over plain HTTP — the box is selectable anyway */
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
        Configure a parameter search, then copy the generated command and run it on the runner
        (<code>ssh bio</code>, from the repo root). The dashboard is read-only monitoring — it doesn’t
        launch jobs itself; the <code>agentic-pureclip-run</code> CLI writes the standard manifest and
        starts the same optimizer (<code>scripts/run/overnight_batch.py</code>).
      </div>

      {opts.run_active ? (
        <div className="banner warn">A run is currently active — a new run will only start once the current one finishes.</div>
      ) : null}

      <section className="section">
        <h2>① Run setup</h2>
        <div className="form-row">
          <div className="field">
            <label>Dataset</label>
            <select value={dataset} onChange={(e) => { setDataset(e.target.value); setCommand(null); }}>
              {opts.datasets.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Optimizer</label>
            <select value={optimizer} onChange={(e) => { setOptimizer(e.target.value); setCommand(null); }}>
              <option value="llm">LLM agent (DeepSeek)</option>
              <option value="optuna">Optuna (TPE / Bayesian)</option>
            </select>
          </div>
          <div className="field">
            <label>Iterations / trials</label>
            <input type="number" min={1} max={50} value={maxIter}
              onChange={(e) => { setMaxIter(+e.target.value); setCommand(null); }} />
          </div>
          <div className="field">
            <label>Time budget (h)</label>
            <input type="number" min={0.1} max={24} step={0.5} value={hours}
              onChange={(e) => { setHours(+e.target.value); setCommand(null); }} />
          </div>
          <div className="field">
            <label>Threads</label>
            <input type="number" min={1} max={64} value={threads}
              onChange={(e) => { setThreads(+e.target.value); setCommand(null); }} />
          </div>
          <div className="field">
            <label>chr21 fast mode</label>
            <label style={{ display: "flex", alignItems: "center", gap: 8, height: 32 }}>
              <input type="checkbox" checked={chr21} onChange={(e) => { setChr21(e.target.checked); setCommand(null); }} />
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
                onChange={(e) => { setWeights((w) => ({ ...w, [k]: +e.target.value })); setCommand(null); }} />
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
        <button className="btn" disabled={!dataset || nSelected === 0} onClick={() => setCommand(buildCommand())}>
          ▶ Generate CLI command
        </button>
        <span className="page-sub" style={{ margin: 0 }}>
          {nSelected === 0 ? "Select at least one parameter." : `Builds an ${optimizer.toUpperCase()} run on ${dataset}.`}
        </span>
      </div>

      {command ? (
        <section className="section">
          <h2>④ Run it on the runner</h2>
          <div className="page-sub" style={{ marginTop: -8 }}>
            Copy this and run it from the repo root on <code>bio</code>. It launches the run in the
            background and prints a job id + log path; the Dashboard then tracks it live.
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
            <pre style={{
              flex: 1, margin: 0, padding: "12px 14px", background: "var(--panel, #0d1117)",
              border: "1px solid var(--border, #30363d)", borderRadius: 8, overflowX: "auto",
              whiteSpace: "pre-wrap", wordBreak: "break-all", fontSize: 12.5, lineHeight: 1.5,
            }}>{command}</pre>
            <button className="btn" onClick={copyCommand} style={{ whiteSpace: "nowrap" }}>
              {copied ? "✓ Copied" : "Copy"}
            </button>
          </div>
        </section>
      ) : null}
    </>
  );
}
