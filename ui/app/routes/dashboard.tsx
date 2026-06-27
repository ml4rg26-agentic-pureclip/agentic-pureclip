import {
  useStatus,
  fmt,
  fmtx,
  humanDur,
  clockIn,
  type ActiveRun,
  type Experiment,
  type IterationRow,
  type Plan,
  type Proc,
} from "../lib/api";

export function meta() {
  return [{ title: "Dashboard · Agentic PureCLIP" }];
}

export default function Dashboard() {
  const { data, error, updatedAt } = useStatus(6000);

  if (!data) {
    return (
      <>
        <div className="page-title">Dashboard</div>
        <div className="page-sub">
          {error ? (
            <span className="conn bad">Cannot reach monitor API ({error}) — is the SSH tunnel up?</span>
          ) : (
            "Connecting to monitor…"
          )}
        </div>
      </>
    );
  }

  return (
    <>
      <div className="page-title">Dashboard</div>
      <div className="page-sub">
        {data.host} · {data.cpus} CPUs · {data.mem} RAM
        {error ? <span className="conn bad"> · reconnecting…</span> : null}
        {updatedAt ? <span> · updated {updatedAt.toLocaleTimeString()}</span> : null}
      </div>

      <ActiveCard active={data.active} stages={data.stages} />
      <PlanCard plan={data.plan} />
      <TrajectoriesCard experiments={data.experiments} />
      <ProcsCard procs={data.processes} />
    </>
  );
}

function ActiveCard({ active: a, stages }: { active: ActiveRun; stages: string[] }) {
  if (!a || !a.is_active) {
    return (
      <section className="section">
        <h2>⚡ Active Run</h2>
        <div className="empty">No run is currently active. Latest results below.</div>
      </section>
    );
  }
  const proteinLine = [a.target_protein, a.cell_line].filter(Boolean).join(" · ");
  const m = a.latest ?? ({} as IterationRow);
  const repro = m.reproducibility ?? m.agreement;
  const optBadge =
    a.optimizer === "optuna" ? (
      <span className="badge badge-optuna">OPTUNA · TPE</span>
    ) : a.optimizer === "llm" ? (
      <span className="badge badge-llm">LLM</span>
    ) : null;

  return (
    <section className="section">
      <h2>⚡ Active Run</h2>
      <div className="active-head">
        <span className="badge badge-running">RUNNING</span>
        {optBadge}
        <span className="ds-pill">{a.dataset ?? "—"}</span>
        <span className="ds-sub">{proteinLine}</span>
        <span className="ds-sub">
          • {a.run_id}
          {a.iteration !== null ? ` · iteration ${a.iteration}` : ""}
        </span>
        {a.elapsed ? <span className="ds-sub">• elapsed {a.elapsed}</span> : null}
      </div>

      <div className="stepper">
        {stages.map((s, i) => {
          const cls = a.stage_index > i ? "done" : a.stage_index === i ? "active" : "";
          const sub = a.stage_index === i && a.substage ? ` (${a.substage})` : "";
          return (
            <div className={`step ${cls}`} key={s}>
              <div className="n">step {i + 1}</div>
              <div className="s">{s}{sub}</div>
            </div>
          );
        })}
      </div>

      <div className="metrics">
        <Metric primary value={fmt(m.composite)} label="composite" />
        <Metric
          value={fmt(repro)}
          label={`reproducibility${m.repro_enrichment != null ? ` (${fmtx(m.repro_enrichment)})` : ""}`}
        />
        <Metric value={fmt(m.motif)} label={`motif hit-rate (${fmtx(m.enrichment)})`} />
        <Metric value={fmt(m.recall)} label="known-site recall" />
        <Metric value={m.n_sites ?? "—"} label="binding sites" />
      </div>

      <div className="params">
        <Chip k="bandwidth" v={a.params.bandwidth_nt} />
        <Chip k="merge_dist" v={a.params.merge_distance_nt} />
        <Chip k="min_xl_events" v={a.params.min_crosslink_events} />
        <Chip k="force_width" v={a.params.force_width} />
        <Chip k="high_precision" v={a.params.high_precision_mode} />
        <Chip k="chr21_fast" v={a.params.learn_on_chr21} />
      </div>

      {a.optimizer === "llm" && a.reasoning ? (
        <div className="reasoning">
          <span className="lbl">latest agent reasoning</span>
          {a.reasoning}
        </div>
      ) : a.optimizer === "optuna" ? (
        <div className="reasoning">
          <span className="lbl">strategy</span>
          Optuna TPE (Bayesian) — proposes the next parameter set by modelling past trials; no
          natural-language reasoning.
        </div>
      ) : null}
    </section>
  );
}

function Metric({ value, label, primary }: { value: React.ReactNode; label: string; primary?: boolean }) {
  return (
    <div className={`metric-card${primary ? " primary" : ""}`}>
      <div className="v">{value}</div>
      <div className="l">{label}</div>
    </div>
  );
}

function Chip({ k, v }: { k: string; v: unknown }) {
  if (v === null || v === undefined) return null;
  return (
    <div className="chip">
      <span>{k}</span> <b>{String(v)}</b>
    </div>
  );
}

function PlanCard({ plan }: { plan: Plan | null }) {
  if (!plan || !plan.jobs.length) return null;
  const c = plan.counts;
  const manifest = (plan.manifest ?? "").split("/").pop();
  return (
    <section className="section">
      <h2>📋 Batch Queue &amp; ETA</h2>
      <div className="ds-sub" style={{ marginBottom: 12 }}>
        {manifest} · <b>{c.done}</b> done · <b style={{ color: "var(--yellow)" }}>{c.running}</b> running ·{" "}
        <b>{c.queued}</b> queued
        {plan.eta_remaining_s > 0 ? (
          <>
            {" "}· <b style={{ color: "var(--blue)" }}>~{humanDur(plan.eta_remaining_s)} left</b> (finish ~
            {clockIn(plan.eta_remaining_s)})
          </>
        ) : (
          <> · <b style={{ color: "var(--green)" }}>complete</b></>
        )}
        <span style={{ opacity: 0.7 }}> · estimates are rough</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>#</th><th>job</th><th>opt</th><th>dataset</th><th>status</th>
            <th>progress</th><th>best</th><th>ETA</th>
          </tr>
        </thead>
        <tbody>
          {plan.jobs.map((j, i) => {
            const running = j.status === "running";
            const queued = j.status === "queued";
            const done = j.done_iters ?? 0;
            const frac = Math.min(1, done / (j.max_iter || 1));
            return (
              <tr key={j.job_id} className={running ? "best" : ""}>
                <td>{i + 1}</td>
                <td>{j.job_id}</td>
                <td><OptBadge o={j.optimizer} /></td>
                <td>{j.dataset}</td>
                <td>
                  {running ? <span className="badge badge-running">running</span>
                    : queued ? <span className="badge badge-queued">queued</span>
                    : <span className={`badge ${j.status === "completed" ? "badge-done" : "badge-error"}`}>{j.status}</span>}
                </td>
                <td>
                  {running ? (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      {done}/{j.max_iter}
                      <span className="progress-bar" style={{ width: 90 }}>
                        <span className="progress-fill running" style={{ width: `${Math.round(frac * 100)}%`, display: "block" }} />
                      </span>
                    </span>
                  ) : queued ? `0/${j.max_iter}` : `${j.max_iter}/${j.max_iter}`}
                </td>
                <td><b>{queued || running ? "—" : fmt(j.best_composite)}</b></td>
                <td>{queued || running ? `~${humanDur(j.eta_remaining_s)}` : humanDur(j.duration_s)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

function OptBadge({ o }: { o?: string }) {
  return o === "optuna" ? (
    <span className="badge badge-optuna sm">optuna</span>
  ) : (
    <span className="badge badge-llm sm">llm</span>
  );
}

function Sparkline({ items }: { items: IterationRow[] }) {
  const vals = items.map((i) => i.composite).filter((v): v is number => v != null);
  if (!vals.length) return null;
  const max = Math.max(...vals);
  const min = Math.min(...vals);
  const span = max - min || 1;
  return (
    <span className="spark">
      {items.map((it, idx) => {
        const v = it.composite;
        if (v == null) return <i key={idx} style={{ height: 2, opacity: 0.3 }} />;
        const h = 4 + Math.round(((v - min) / span) * 18);
        return <i key={idx} className={v === max ? "best" : ""} style={{ height: h }} />;
      })}
    </span>
  );
}

function TrajectoriesCard({ experiments }: { experiments: Experiment[] }) {
  return (
    <section className="section">
      <h2>🔬 Optimisation Trajectories</h2>
      {!experiments.length ? (
        <div className="empty">No runs found yet</div>
      ) : (
        experiments.map((g) => {
          const byOpt: Record<string, number> = {};
          for (const it of g.iterations) {
            const o = it.optimizer || "llm";
            if (it.composite != null && (byOpt[o] === undefined || it.composite > byOpt[o]))
              byOpt[o] = it.composite;
          }
          const versus =
            byOpt.llm !== undefined && byOpt.optuna !== undefined ? (
              <>
                {" "}·{" "}
                <b style={{ color: "var(--blue)" }}>LLM {fmt(byOpt.llm)}</b> vs{" "}
                <b style={{ color: "var(--yellow)" }}>Optuna {fmt(byOpt.optuna)}</b> →{" "}
                {byOpt.llm === byOpt.optuna ? "tie" : byOpt.llm > byOpt.optuna ? "LLM" : "Optuna"}
              </>
            ) : null;
          return (
            <div key={g.name} style={{ marginBottom: 22 }}>
              <div className="exp-head">
                <span className="name">{g.name}</span>
                <span className="ds-sub">
                  {g.n_iters} iteration{g.n_iters === 1 ? "" : "s"} · best{" "}
                  <b style={{ color: "var(--green)" }}>{fmt(g.best_composite)}</b>
                  {versus}
                </span>
                <Sparkline items={g.iterations} />
              </div>
              <table>
                <thead>
                  <tr>
                    <th>run</th><th>opt</th><th>iter</th><th>sites</th>
                    <th>reprod.</th><th>motif</th><th>recall</th><th>composite</th><th>src</th>
                  </tr>
                </thead>
                <tbody>
                  {g.iterations.map((it) => {
                    const repro = it.reproducibility ?? it.agreement;
                    const src =
                      it.source === "batch" ? "badge-batch"
                        : it.source === "overnight" ? "badge-overnight"
                        : "badge-live";
                    return (
                      <tr key={it.run_id} className={it.run_id === g.best_run ? "best" : ""}>
                        <td>{it.run_id}</td>
                        <td><OptBadge o={it.optimizer} /></td>
                        <td>{it.iter ?? "—"}</td>
                        <td>{it.n_sites ?? "—"}</td>
                        <td>{fmt(repro)}</td>
                        <td>{fmt(it.motif)}</td>
                        <td>{fmt(it.recall)}</td>
                        <td><b>{fmt(it.composite)}</b></td>
                        <td><span className={`badge ${src} sm`}>{it.source}</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          );
        })
      )}
    </section>
  );
}

function ProcsCard({ procs }: { procs: Proc[] }) {
  return (
    <section className="section">
      <h2>🖥 Processes</h2>
      {!procs.length ? (
        <div className="empty">No active processes</div>
      ) : (
        <table>
          <thead>
            <tr><th>process</th><th>CPU%</th><th>MEM%</th><th>elapsed</th></tr>
          </thead>
          <tbody>
            {procs.map((p, i) => (
              <tr key={i}>
                <td>{p.label}</td><td>{p.cpu}</td><td>{p.mem}</td><td>{p.etime}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
