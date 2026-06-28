export function meta() {
  return [{ title: "Variables · Agentic PureCLIP" }];
}

interface Variable {
  name: string;
  range: string;
  tag: string;
  desc: string;
  effect?: string;
}

// Tunable parameters — mirror pipeline/configs.py DEFAULT_SEARCH_BOUNDS.
const TUNABLES: { group: string; note: string; vars: Variable[] }[] = [
  {
    group: "PureCLIP (peak caller)",
    note: "Control how raw eCLIP read signal is turned into crosslink sites.",
    vars: [
      {
        name: "bandwidth_nt",
        range: "20 – 100",
        tag: "pureclip",
        desc: "Smoothing window PureCLIP uses when scanning read coverage for crosslink sites.",
        effect: "Larger → broader, more sensitive regions (more sites). Smaller → sharper, more precise calls.",
      },
      {
        name: "merge_distance_nt",
        range: "4 – 16",
        tag: "pureclip",
        desc: "How close two crosslink sites must be before they are merged into one.",
        effect: "Larger → nearby signal collapses into single wider sites. Smaller → keeps sites separate.",
      },
      {
        name: "high_precision_mode",
        range: "0 / 1",
        tag: "pureclip · bool",
        desc: "PureCLIP's stricter calling mode (the -ld flag).",
        effect: "On → fewer but higher-confidence sites. Off → more sensitive.",
      },
      {
        name: "use_input_covariate",
        range: "0 / 1",
        tag: "pureclip · bool",
        desc: "Whether to use the size-matched input control to correct background signal.",
        effect: "On → subtracts non-specific background; usually improves specificity.",
      },
    ],
  },
  {
    group: "Post-processing",
    note: "Filter and normalise PureCLIP's sites into the final binding-site set.",
    vars: [
      {
        name: "min_crosslink_events",
        range: "2 – 6",
        tag: "postproc",
        desc: "Minimum number of crosslink read events required to keep a site.",
        effect: "Higher → stricter, fewer sites (can collapse yield). Lower → more sensitive.",
      },
      {
        name: "force_width",
        range: "3 – 15",
        tag: "postproc",
        desc: "Fixed width (nt) each binding site is normalised to — roughly the protein's footprint.",
        effect: "Should match the expected RNA footprint (~9 nt for these RBPs).",
      },
      {
        name: "cluster_gap_width",
        range: "4 – 16",
        tag: "postproc",
        desc: "Maximum gap allowed when clustering adjacent sites into a region.",
        effect: "Larger → merges sparse sites into regions.",
      },
    ],
  },
];

// What the optimizer maximises (agent/decisions.py composite_objective).
const OBJECTIVE: Variable[] = [
  {
    name: "reproducibility  (×0.50)",
    range: "0 – 1",
    tag: "metric",
    desc: "Replicate agreement corrected for chance overlap: (observed − expected) / (1 − expected), where the chance level comes from shuffling the sites.",
    effect: "Cannot be inflated by keeping only a few broad sites — unlike raw agreement.",
  },
  {
    name: "motif  (×0.25)",
    range: "0 – 1",
    tag: "metric",
    desc: "Fraction of binding sites that contain the protein's expected RNA motif, scored with a log-odds PWM.",
    effect: "Measures biological validity. Reported with an enrichment (×) over a shuffled background.",
  },
  {
    name: "recall  (×0.25)",
    range: "0 – 1",
    tag: "metric",
    desc: "Fraction of known-strong ENCODE reference regions (restricted to the analysed chromosome) that our sites recover.",
    effect: "Anchors the score to ground truth — dropping real sites lowers recall, so it penalises collapse.",
  },
];

// Read-only context metrics shown alongside.
const CONTEXT: Variable[] = [
  { name: "composite", range: "0 – 1", tag: "objective", desc: "The single score the optimizer climbs: 0.5·reproducibility + 0.25·motif + 0.25·recall (renormalised over available terms), then multiplied by the collapse guard below." },
  { name: "collapse guard", range: "min(1, n/10)", tag: "guard", desc: "The composite is scaled down below ~10 binding sites. With only a handful of sites, reproducibility and motif trivially hit 1.0 — a degenerate 'win'. This ramp makes a 1-site solution score near zero, so the optimizer can't game the score by collapsing." },
  { name: "n_binding_sites", range: "count", tag: "context", desc: "Number of reproducible binding sites produced — watch for collapse." },
  { name: "motif_enrichment", range: "×", tag: "context", desc: "Motif hit-rate divided by the shuffled-background rate; >1× means real signal." },
];

function VarCard({ v }: { v: Variable }) {
  return (
    <div className="var">
      <div className="var-head">
        <span className="var-name">{v.name}</span>
        <span className="var-range">{v.range}</span>
        <span className="var-tag">{v.tag}</span>
      </div>
      <div className="var-desc">{v.desc}</div>
      {v.effect ? <div className="var-effect"><b>Effect:</b> {v.effect}</div> : null}
    </div>
  );
}

export default function Variables() {
  return (
    <>
      <div className="page-title">Variables</div>
      <div className="page-sub">What the system tunes, what it measures, and what each knob does.</div>

      <div className="intro">
        <b>What is this project?</b> eCLIP experiments find where an RNA-binding protein (RBP) attaches to
        RNA. A tool called <b>PureCLIP</b> turns the raw sequencing reads into "binding sites", but its
        results depend heavily on a handful of parameters. This system <b>automatically tunes those
        parameters</b>: an optimizer proposes a parameter set, the pipeline runs PureCLIP and scores the
        result, and it repeats — searching for the settings that give the most trustworthy binding sites.
        <div className="flow">
          <div className="node">① Optimizer proposes params <span style={{ color: "var(--muted)" }}>(LLM agent or Optuna/TPE)</span></div>
          <span className="arrow">→</span>
          <div className="node">② Run PureCLIP</div>
          <span className="arrow">→</span>
          <div className="node">③ Score (reproducibility · motif · recall)</div>
          <span className="arrow">→</span>
          <div className="node">④ Pick next params</div>
          <span className="arrow">↺</span>
        </div>
      </div>

      {TUNABLES.map((grp) => (
        <section className="section" key={grp.group}>
          <h2>{grp.group}</h2>
          <div className="ds-sub" style={{ marginTop: -8, marginBottom: 12 }}>{grp.note}</div>
          {grp.vars.map((v) => <VarCard key={v.name} v={v} />)}
        </section>
      ))}

      <section className="section">
        <h2>Objective — what the optimizer maximises</h2>
        <div className="ds-sub" style={{ marginTop: -8, marginBottom: 12 }}>
          A weighted blend of three quality signals, all in [0, 1]. Weights are configurable per dataset.
        </div>
        {OBJECTIVE.map((v) => <VarCard key={v.name} v={v} />)}
      </section>

      <section className="section">
        <h2>Other reported values</h2>
        {CONTEXT.map((v) => <VarCard key={v.name} v={v} />)}
      </section>
    </>
  );
}
