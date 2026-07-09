import {
  useStatus,
  fmt,
  fmtx,
  humanDur,
  clockIn,
  armMeta,
  ARM_ORDER,
  type ArmKey,
  type ActiveRun,
  type Experiment,
  type IterationRow,
  type Plan,
  type Proc,
  type Status,
} from "../lib/api";

/** Arm of an iteration/job — distinguishes the no-priors LLM from the priors LLM. */
function armFrom(optimizer?: string, jobId?: string): ArmKey {
  if ((optimizer || "").toLowerCase() === "optuna") return "optuna";
  if (jobId && /no[_-]?prior/i.test(jobId)) return "llm_noprior";
  return "llm";
}

function ArmBadge({ arm, sm }: { arm?: string; sm?: boolean }) {
  const m = armMeta(arm);
  return <span className={`badge ${m.badge}${sm ? " sm" : ""}`}>{m.name} · {m.tag}</span>;
}

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

      <Kpis data={data} />
      {data.active.is_active ? <ActiveCard active={data.active} stages={data.stages} /> : null}
      <PlanCard plan={data.plan} />
      <Leaderboard experiments={data.experiments} />
      <Details experiments={data.experiments} active={data.active} />
      <ProcsCard procs={data.processes} />
    </>
  );
}

/* ── Overview ─────────────────────────────────────────────────── */

function bestOverall(experiments: Experiment[]) {
  let best: { name: string; v: number } | null = null;
  for (const e of experiments) {
    if (e.best_composite != null && (!best || e.best_composite > best.v))
      best = { name: e.name, v: e.best_composite };
  }
  return best;
}

function Kpis({ data }: { data: Status }) {
  const a = data.active;
  const plan = data.plan;
  const totalIters = data.experiments.reduce((s, e) => s + e.n_iters, 0);
  const best = bestOverall(data.experiments);
  return (
    <div className="kpis">
      <div className="kpi">
        <div className="v">
          {a.is_active ? (
            <><span className="dot run" />Running</>
          ) : (
            <><span className="dot idle" />Idle</>
          )}
        </div>
        <div className="l">Status</div>
        {a.is_active ? (
          <div className="sub">
            {a.dataset} · {(() => { const m = armMeta(a.arm ?? a.optimizer); return `${m.name} (${m.tag})`; })()} · {a.stage}
          </div>
        ) : null}
      </div>

      <div className="kpi">
        <div className="v" style={{ color: "var(--green)" }}>{fmt(best?.v)}</div>
        <div className="l">Best composite</div>
        {best ? <div className="sub">{best.name}</div> : null}
      </div>

      <div className="kpi">
        <div className="v">{data.experiments.length}</div>
        <div className="l">Datasets</div>
        <div className="sub">{totalIters} iterations scored</div>
      </div>

      {plan ? (
        <div className="kpi">
          <div className="v">
            {plan.counts.done}<span style={{ color: "var(--muted)", fontSize: 14 }}>/{plan.jobs.length}</span>
          </div>
          <div className="l">Batch jobs done</div>
          <div className="sub">
            {plan.counts.running} running · {plan.counts.queued} queued
          </div>
        </div>
      ) : null}

      {plan ? (
        <div className="kpi">
          <div className="v" style={{ color: plan.eta_remaining_s > 0 ? "var(--blue)" : "var(--green)" }}>
            {plan.eta_remaining_s > 0 ? `~${humanDur(plan.eta_remaining_s)}` : "done"}
          </div>
          <div className="l">Batch ETA</div>
          {plan.eta_remaining_s > 0 ? <div className="sub">finish ~{clockIn(plan.eta_remaining_s)}</div> : null}
        </div>
      ) : null}
    </div>
  );
}

/* ── Active run ───────────────────────────────────────────────── */

function ActiveCard({ active: a, stages }: { active: ActiveRun; stages: string[] }) {
  const proteinLine = [a.target_protein, a.cell_line].filter(Boolean).join(" · ");
  const m = a.latest ?? ({} as IterationRow);
  const repro = m.reproducibility ?? m.agreement;
  const optBadge = a.optimizer ? <ArmBadge arm={a.arm ?? a.optimizer} /> : null;

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

/* ── Batch queue ──────────────────────────────────────────────── */

function PlanCard({ plan }: { plan: Plan | null }) {
  if (!plan || !plan.jobs.length) return null;
  const c = plan.counts;
  const manifest = (plan.manifest ?? "").split("/").pop();
  const running = c.running > 0;
  return (
    <details className="section" open={running}>
      <summary>
        📋 Batch Queue &amp; ETA
        <span className="count">
          {manifest} · {c.done}/{plan.jobs.length} done
          {running ? ` · ~${humanDur(plan.eta_remaining_s)} left` : " · complete"}
        </span>
      </summary>
      <table>
        <thead>
          <tr>
            <th>#</th><th>job</th><th>opt</th><th>dataset</th><th>status</th>
            <th>progress</th><th>best</th><th>ETA</th>
          </tr>
        </thead>
        <tbody>
          {plan.jobs.map((j, i) => {
            const isRun = j.status === "running";
            const isQ = j.status === "queued";
            const done = j.done_iters ?? 0;
            const frac = Math.min(1, done / (j.max_iter || 1));
            return (
              <tr key={j.job_id} className={isRun ? "best" : ""}>
                <td>{i + 1}</td>
                <td>{j.job_id}</td>
                <td><ArmBadge arm={armFrom(j.optimizer, j.job_id)} sm /></td>
                <td>{j.dataset}</td>
                <td>
                  {isRun ? <span className="badge badge-running">running</span>
                    : isQ ? <span className="badge badge-queued">queued</span>
                    : <span className={`badge ${j.status === "completed" ? "badge-done" : "badge-error"}`}>{j.status}</span>}
                </td>
                <td>
                  {isRun ? (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      {done}/{j.max_iter}
                      <span className="progress-bar" style={{ width: 80 }}>
                        <span className="progress-fill running" style={{ width: `${Math.round(frac * 100)}%`, display: "block" }} />
                      </span>
                    </span>
                  ) : isQ ? `0/${j.max_iter}` : `${j.max_iter}/${j.max_iter}`}
                </td>
                <td><b>{isQ || isRun ? "—" : fmt(j.best_composite)}</b></td>
                <td>{isQ || isRun ? `~${humanDur(j.eta_remaining_s)}` : humanDur(j.duration_s)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </details>
  );
}

/* ── Results: leaderboard + per-dataset detail ────────────────── */

/** Best composite per arm (prior LLM / no-prior LLM / Optuna). */
function bestByArm(it: IterationRow[]): Partial<Record<ArmKey, number>> {
  const by: Partial<Record<ArmKey, number>> = {};
  for (const r of it) {
    const a = (r.arm as ArmKey) ?? armFrom(r.optimizer, r.run_id);
    if (r.composite != null && (by[a] === undefined || r.composite > (by[a] as number))) by[a] = r.composite;
  }
  return by;
}

/** Winning arm among those present (needs ≥2 arms), or "tie". */
function armWinner(by: Partial<Record<ArmKey, number>>): ArmKey | "tie" | null {
  const present = ARM_ORDER.filter((a) => by[a] !== undefined);
  if (present.length < 2) return null;
  const max = Math.max(...present.map((a) => by[a] as number));
  const tops = present.filter((a) => (by[a] as number) === max);
  return tops.length > 1 ? "tie" : tops[0];
}

const CELL_LINES = ["K562", "HepG2"];
function splitDataset(name: string): { rbp: string; cell: string | null } {
  const parts = name.split("_");
  const last = parts[parts.length - 1];
  if (CELL_LINES.some((c) => c.toLowerCase() === last.toLowerCase()))
    return { rbp: parts.slice(0, -1).join("_"), cell: last };
  return { rbp: name, cell: null };
}

function Leaderboard({ experiments }: { experiments: Experiment[] }) {
  if (!experiments.length) {
    return (
      <section className="section">
        <h2>🏆 Results</h2>
        <div className="empty">No runs found yet</div>
      </section>
    );
  }

  // Group datasets by RBP; rank groups (and rows within) by best composite.
  const globalMax = Math.max(0.001, ...experiments.map((e) => e.best_composite ?? 0));
  const byRbp = new Map<string, Experiment[]>();
  for (const e of experiments) {
    const { rbp } = splitDataset(e.name);
    byRbp.set(rbp, [...(byRbp.get(rbp) ?? []), e]);
  }
  const groups = [...byRbp.entries()]
    .map(([rbp, exps]) => ({
      rbp,
      exps: exps.sort((a, b) => (b.best_composite ?? -1) - (a.best_composite ?? -1)),
      best: Math.max(...exps.map((e) => e.best_composite ?? -1)),
    }))
    .sort((a, b) => b.best - a.best);

  return (
    <section className="section">
      <h2>🏆 Results — best per dataset <span className="count">{experiments.length} datasets · ranked by composite</span></h2>
      <div className="lb">
        {groups.map((g) => (
          <div className="lb-group" key={g.rbp}>
            <div className="lb-rbp">
              <span className="lb-rbp-name">{g.rbp}</span>
              <span className="lb-rbp-best">{g.best >= 0 ? fmt(g.best, 3) : "—"}</span>
            </div>
            {g.exps.map((e) => {
              const { cell } = splitDataset(e.name);
              const byArm = bestByArm(e.iterations);
              const winner = armWinner(byArm);
              const comp = e.best_composite ?? 0;
              return (
                <div className="lb-row" key={e.name}>
                  <span className="lb-cell">{cell ?? e.name}</span>
                  <span className="lb-bar-wrap">
                    <span className="lb-bar" style={{ width: `${Math.max(3, (comp / globalMax) * 100)}%` }} />
                    <span className="lb-comp">{fmt(e.best_composite, 3)}</span>
                  </span>
                  <span className="lb-opt">
                    {ARM_ORDER.map((a, i) => {
                      const mm = armMeta(a);
                      return (
                        <span key={a}>
                          {i > 0 && <span className="lb-slash">/</span>}
                          <b style={{ color: byArm[a] !== undefined ? mm.color : "var(--muted)" }}
                            title={`${mm.name} (${mm.tag})`}>
                            {byArm[a] !== undefined ? fmt(byArm[a], 3) : "—"}
                          </b>
                        </span>
                      );
                    })}
                    {winner && (
                      <span className={`win ${winner} xs`}>
                        {winner === "tie" ? "=" : winner === "llm_noprior" ? "LLM np" : armMeta(winner).name}
                      </span>
                    )}
                  </span>
                  <span className="lb-iters">{e.n_iters} it</span>
                  <Sparkline items={e.iterations} />
                </div>
              );
            })}
          </div>
        ))}
      </div>
      <div className="lb-legend">
        <span><i className="lb-swatch llm" /> LLM (prior)</span>
        <span><i className="lb-swatch noprior" /> LLM (no prior)</span>
        <span><i className="lb-swatch optuna" /> Optuna</span>
        <span>trio = best composite per arm · bar = best overall (vs top {fmt(globalMax, 3)})</span>
      </div>
    </section>
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

function Details({ experiments, active }: { experiments: Experiment[]; active: ActiveRun }) {
  if (!experiments.length) return null;
  return (
    <>
      {experiments.map((g) => {
        const openByDefault = active.is_active && active.dataset === g.name;
        return (
          <details className="section" key={g.name} open={openByDefault}>
            <summary>
              {g.name}
              <span className="count">{g.n_iters} iters · best {fmt(g.best_composite)}</span>
            </summary>
            <table>
              <thead>
                <tr>
                  <th>run</th><th>arm</th><th>iter</th><th>sites</th>
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
                      <td><ArmBadge arm={it.arm ?? armFrom(it.optimizer, it.run_id)} sm /></td>
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
          </details>
        );
      })}
    </>
  );
}

function ProcsCard({ procs }: { procs: Proc[] }) {
  if (!procs.length) return null;
  return (
    <details className="section">
      <summary>
        🖥 Processes <span className="count">{procs.length} active</span>
      </summary>
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
    </details>
  );
}
