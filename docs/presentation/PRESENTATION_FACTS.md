# Presentation Working Notes — Fact-Check Against Implementation

Working reference for the deck in `docs/presentation/` (`index.html`). Every claim
below has been checked against the actual repo code. Use this as the source of
truth while editing slides. Last verified: 2026-07-09 against branch
`presentation-report-revisions`.

Legend: ✅ verified in code · ⚠️ true but needs a caveat · 🔵 placeholder/illustrative (not a real result) · 🟡 team annotation, not derivable from code

---

## 1. Verified facts (safe to state)

### The pipeline & loop
- ✅ **One shared evaluation, two interchangeable optimizers.** Both the LLM agent
  (`loop/graph.py`) and Optuna (`loop/optuna_runner.py`) call the same
  `evaluate_config` (`loop/evaluation.py`) and the same `composite_objective`
  (`scoring/objective.py`) over the same `DEFAULT_SEARCH_BOUNDS`. Only the
  proposal strategy differs. This backs the "comparison isolates only how they
  propose" claim.
- ✅ **Pipeline stages** (Snakemake, `postprocess/Snakefile`): merge IP replicates
  (`samtools merge`) → PureCLIP on merged BAM + per-replicate → postprocess →
  score. The slide-4 diagram order (Merge → PureCLIP → Post-process → Scoring →
  Composite) is correct.
- ✅ **Merge uses samtools** (`samtools merge -f` in the `merge_ip` rule).
- ✅ **PureCLIP binary is `pureclip2`**, an HMM-based crosslink-site caller.

### What we tune — 7 parameters ✅
Exactly 7 tunable parameters in `DEFAULT_SEARCH_BOUNDS` (`pipeline/configs.py`):

| Section | Parameter | Bounds | Plain-English meaning |
|---|---|---|---|
| pureclip | `bandwidth_nt` | [20, 100] | how much to smooth the signal |
| pureclip | `merge_distance_nt` | [4, 16] | how far apart two peaks still count as one site |
| pureclip | `high_precision_mode` | [0, 1] | stricter calling (the `-ld` flag) |
| pureclip | `use_input_covariate` | [0, 1] | use the input control as a covariate |
| postprocessing | `min_crosslink_events` | [2, 6] | how much evidence a site needs |
| postprocessing | `force_width` | [3, 15] | how wide to make each site |
| postprocessing | `cluster_gap_width` | [4, 16] | how aggressively to stitch fragments together |

> Slide 5 describes 4 of these in plain terms (bandwidth, merge distance,
> evidence, width). That is a fair simplification — just don't say "we tune 4";
> the count is **7**.

### The data ✅
- ✅ **26 dataset configs**, **15 unique proteins**, both cell lines **K562 & HepG2**
  (`config/datasets/*.yaml`).
  - Proteins: RBFOX2, QKI, PUM1, PUM2, HNRNPK, HNRNPM, PCBP1, PTBP1, RBM22,
    SF3B1, SF3B4, SFPQ, SRSF1, U2AF1, U2AF2.
  - The 26th config is `ENCORE_RBFOX2_K562` (a second RBFOX2_K562 from a
    different source/processing).
- ✅ **Every dataset = 2 IP replicates (rep1, rep2) + 1 input control.** Confirmed
  across all 26 configs.
- ✅ **chr21 "fast mode"** (`learn_on_chr21: true`) restricts PureCLIP to chr21 via
  `-iv chr21 -chr chr21`; minutes/iteration vs hours for full-genome. README
  confirms "minutes/iter" vs "hours/pass".

### Scoring ✅
- ✅ **Composite formula** (`scoring/objective.py`):
  `composite = (0.5·reproducibility + 0.25·motif + 0.25·recall) × min(1, n_sites/10)`
  Weights are renormalised over whichever terms are present. Overridable per-run
  via `priors.objective_weights`.
- ✅ **Reproducibility is weighted highest (0.5)** = strongest evidence.
- ✅ **Reproducibility is chance-corrected**: `score = (observed − expected)/(1 − expected)`,
  where `expected` is agreement of shuffled sites (`bedtools shuffle`, sites kept
  on-chromosome, mean of 3 shuffles). Clamped to [0,1]. This is what stops
  "keep a few broad sites that trivially overlap" from winning.
- ✅ **Motif** = fraction of sites carrying the RBP's RNA motif, scored with a PWM
  log-odds scan (threshold 80% of max score) over a ±15 nt window, reported as the
  **most-enriched** motif's hit rate (enrichment vs a per-window shuffled
  background). Falls back to IUPAC regex if no PWM available.
- ✅ **Recall** = fraction of known-strong ENCODE reference regions recovered
  (`benchmark_region_recall`), restricted to analyzed chromosomes (chr21 in fast
  mode, so the genome-wide reference doesn't cap recall at ~4.5%).
- ✅ **Collapse guard** `min(1, n_sites/10)`: below 10 sites the composite ramps
  toward zero. A handful of "perfect" sites cannot win.

### The optimizers ✅
- ✅ **LLM = DeepSeek** (`deepseek-chat`, temperature 0.2, via `langchain_openai`
  ChatOpenAI pointed at `api.deepseek.com/v1`), driven by a **LangGraph** state
  machine.
- ✅ **LLM sees priors + full score history** and returns JSON `{reasoning, changes}`.
  It is instructed to **change ONE parameter at a time** (prompt decision rule #2)
  and not repeat a tried set.
- ✅ **LLM leaves a readable reasoning trail** — `reasoning` string per iteration,
  logged to `decisions.jsonl`. This is a genuine, code-backed interpretability
  claim (slide 10 footnote).
- ✅ **Optuna = TPE sampler** (`TPESampler`, `direction="maximize"`, seed 42),
  "black-box search," no API key. Decision trail records a generic
  "TPE proposal" string (no natural-language reasoning).
- ✅ **Stopping**: hard stop at `MAX_ITER`; convergence when no improvement for
  `patience=10`; `score_improvement_threshold=0.01`. Best config saved to
  `config/best_config.yaml`.

### Biology (motifs backed by code)
- ✅ **RBFOX2 → `UGCAUG`** (`priors.json` and `pipeline/datasets.py`).
- ✅ QKI → `ACUAAY`, PUM1 → `UGUANAUA` (`pipeline/datasets.py`).

---

## 2. Caveats — true but state carefully

- ⚠️ **"Fair comparison" has one real asymmetry.** The LLM changes **one parameter
  per iteration**; Optuna **samples all 7 parameters every trial** (`suggest_int`
  for each in `optuna_runner.py`). Same eval/objective/bounds, but the *move size*
  differs. This is exactly why "equal-budget" is (correctly) listed as future work
  on the Limitations/Conclusion slides. Don't overclaim perfect parity.
- ⚠️ **"26 datasets" lives as YAML configs, not the Python registry.** Only **7**
  `DatasetSpec` entries are hardcoded in `pipeline/datasets.py`; the other configs
  were generated via `scripts/data/write_dataset_config.py`. The 26 count is
  correct (config files exist) — just know where it comes from if asked.
- ⚠️ **Default `MAX_ITER` differs by entry point**: graph defaults to 5, Optuna to
  12. Actual runs set it explicitly (batch manifests). Don't quote a fixed
  iteration budget without checking the manifest used.
- ⚠️ **Motif hit rate reported = most-enriched motif**, not a fixed single motif.
  For proteins with multiple known motifs this picks the best-enriched one. Fine
  to say "does the site contain the protein's preferred RNA word," but the
  headline number is enrichment-selected.

---

## 3. Placeholder / illustrative content (NOT real results)

- 🔵 **Slide 7 head-to-head table** (RBFOX2 0.31/0.62/0.64, etc.) — explicitly
  badged ILLUSTRATIVE. Placeholder numbers, real batch pending.
- 🔵 **Slide 8 convergence chart** — placeholder shape.
- 🔵 **Slide 9 "inside the composite" table** — placeholder numbers.
- ➡️ **Action:** these must be replaced with real numbers from `results/overnight/`
  (`summary.csv`, `iterations.jsonl`) before any non-draft showing. Keep the
  ILLUSTRATIVE badges until then.

---

## 4. Team annotations (not derivable from code — label as ours)

- 🟡 **Motif-difficulty tiers** (crisp / degenerate / positional):
  - crisp — clear RNA word (RBFOX2 `UGCAUG`) ✅ motif is real
  - degenerate — fuzzy preference (HNRNPK C-rich)
  - positional — defined by location, not sequence (U2AF2, SF3B4 at splice sites)

  The `UGCAUG` motif is code-backed; the **difficulty grouping and the
  C-rich/splice-site characterizations are the team's biological annotation**, not
  something the pipeline computes. The slide already flags this ("our own
  annotation") — keep that framing. Note this content was **moved to Discussion**
  as an untested hypothesis (per commit `6effc00`), correctly presented as future
  work, not a finding.
- 🟡 **"LLM starts higher / climbs faster thanks to priors"** — a hypothesis about
  expected shape, not a measured result. Keep it hedged.

---

## 5. Known doc drift (don't trust these blindly)

- `docs/architecture-overview.md` is **out of date**: it uses old directory names
  (`agent/`, `workflow/`, `scorers/`, `decisions.py`) and wrongly says the backend
  is stdlib `http.server`. The real layout is
  `src/agentic_pureclip/{loop,scoring,postprocess,pipeline}/` and the dashboard
  backend is **FastAPI**. Trust the top-level `README.md` and this file instead.

---

## 6. Quick file map (where to verify each claim)

| Claim area | Source of truth |
|---|---|
| Composite formula & weights | `src/agentic_pureclip/scoring/objective.py` |
| The 3 scores (repro/motif/recall) | `src/agentic_pureclip/scoring/run_scorers.py` |
| 7 tunable params & bounds | `src/agentic_pureclip/pipeline/configs.py` (`DEFAULT_SEARCH_BOUNDS`) |
| Pipeline stages | `src/agentic_pureclip/postprocess/Snakefile` |
| Post-processing (filter/merge/width) | `src/agentic_pureclip/postprocess/postprocess.py` |
| LLM loop, prompt, one-change rule | `loop/graph.py` + `scoring/objective.py` (`build_decision_prompt`) |
| Optuna TPE, all-params-per-trial | `loop/optuna_runner.py` |
| Datasets (26 configs) | `config/datasets/*.yaml` |
| Dataset registry (7 specs) | `src/agentic_pureclip/pipeline/datasets.py` |
| Priors / motifs | `config/priors.json`, `pipeline/datasets.py` |
| Real results (when ready) | `results/overnight/iterations.jsonl`, per-run `decisions.jsonl` (on VM) |

---

## 7. Meeting feedback (revision TODO) — untangled

Captured from meeting notes where the deck was presented. Grouped by slide.
Status: 🆕 to do · ❓ needs decision · 🔧 needs code.

> **UPDATE 2026-07-09 — the deck (`index.html`) has been rebuilt with placeholders
> matched to the final run structure.** Done: slide 6 formulas + why + collapse
> guard; slide 7 head-to-head (8 K562 proteins by tier); slide 8 convergence +
> priors-ablation curve; slide 9 per-factor-over-iterations + decomposition; NEW
> reasoning slide (LLM vs Optuna + dashboard placeholder); motif-difficulty is now
> a RESULTS slide (was "idea we didn't test"); NEW cross-cell-line slide; slides
> 1/2/3 illustration placeholders; slide 5 scope reframed; slide 11 "scope&budget"
> reframed as deliberate; slide 12 what's-next (multiple/other RBPs). **Still open:**
> real art for the 3 illustration placeholders + dashboard screenshot; swap
> placeholder numbers for real results once the batch lands; verify no slide
> overflows 720 px in a browser. NOTE: the deck now presents motif-difficulty as a
> *result*, which diverges from the report (`docs/report`, commit 6effc00) that
> moved it to discussion as an *untested hypothesis* — intentional per this feedback,
> but the deck's result depends on the batch actually showing the gradient.

### Slide 1 — Title
- 🆕 Add a screenshot/figure from the **eCLIP paper**.

### Slide 2 — The problem
- 🆕 Add an illustration showing **the data PureCLIP receives and generates, and
  its biological meaning** (input eCLIP read pile-up → output binding sites).
  ("dlise" in the raw notes = "slide".)

### Slide 3 — Why it's hard
- 🆕 Show concretely that **parameter change → output change** (before/after site
  lists, or one knob swinging the site count).

### Slide 6 — How we score (the big one)
- 🆕 Add **why we chose this score** (motivation) and **why multiple metrics** vs one.
- 🆕 Surface the **collapse guard** ("punishment for too few sites") prominently.
- 🆕 **Write out the formulas for all three metrics** (not just the composite):
  - **reproducibility** = `(observed − expected)/(1 − expected)`, clamped [0,1];
    `observed` = fraction of final sites overlapping *every* replicate's PureCLIP
    regions; `expected` = same measured on shuffled sites (mean of 3
    `bedtools shuffle`, on-chromosome). Source: `run_scorers.py::replicate_reproducibility`.
  - **motif hit rate** = fraction of ±15 nt site windows with a PWM log-odds hit
    ≥ 80% of the score range; reported for the **most-enriched** motif
    (enrichment = fg hit rate / shuffled-background hit rate). Source:
    `run_scorers.py::motif_hit_rate_pwm` + `motifs.py`.
  - **recall** = fraction of ENCODE reference regions recovered =
    `overlap_fraction(reference, sites)`, restricted to analyzed chromosomes.
    Source: `run_scorers.py` (`benchmark_region_recall`).

### Slide 8 — Convergence
- 🆕 Reframe to **focus on the reasoning**: Optuna (samples all params from a
  surrogate model, no rationale) vs LLM (one readable justification per move).
- 🆕 Add an **ablation: LLM with vs. without prior knowledge** (isolates whether
  the biological priors are what give the LLM its edge). Needs a priors-stripped
  LLM run — likely a new experiment.

### Slide 9 — Inside the score
- 🆕 Add **per-factor graphs over iterations** (reproducibility / motif / recall
  each plotted across iterations), not just final-value tables. Data is available
  per iteration in `iterations.jsonl` / `decisions.jsonl`.

### NEW slide — LLM vs Optuna reasoning (point 4)
- 🆕 Dedicated slide contrasting how each optimizer *reasons*. Recommendation:
  side-by-side. LLM = real `reasoning` string from `decisions.jsonl` (cites the
  metric deltas, names the parameter and direction, is aware of the collapse
  guard) + a **dashboard Runs-page screenshot**. Optuna = its generic
  "TPE proposal — sampled from the model of previous trials" (no per-move
  rationale). Real example pulled from `ins_u2af2_k562_llm`:
  > "…increase merge_distance_nt from 8 to 12 to merge nearby crosslink events
  > into broader, more reproducible peaks … without collapsing sites too much, as
  > the collapse guard requires at least 10 sites."
  This is the interpretability story made concrete.

### Cross-cutting
- 🔧 **Multiple-parameter change for the LLM (point 2):** currently the prompt
  forces one change at a time (`build_decision_prompt` decision rule #2). Enabling
  multi-parameter moves is a **code change** to that rule + validation. Affects the
  fairness framing (Optuna already moves all 7/trial). Track as an implementation
  task.
- 🆕 **Motif difficulty → into Results (point 3):** see §8 below for the data
  investigation and what it needs.

### Slide 11 — Limitations
- 🆕 **Reframe "Scope & Budget"** from a limitation to a deliberate scoping choice
  ("chr21 fast-mode freed us to look more carefully at other things").

### Slide 12 — Conclusion / What's next
- 🆕 Add: **optimize multiple RBPs simultaneously**.
- 🆕 Add: **test on other RBPs** ("auf anderen RBPs testen").

### Global
- 🆕 **More content on the slides** generally — they're currently sparse.

---

## 8. Motif-difficulty analysis — data investigation (point 3)

**Question:** use all runs to test whether quality depends on motif difficulty.
How is motif clearness present in the data, and do we need code changes?

### How motif clearness is present in the data ✅
Every reference motif is a TRANSFAC PWM under
`data/motifs/{database}/{RBP}/{cell_line}/*.transfac` (databases: mCrossBase,
ATtRACT, RBPDB, RBPmap_1.2, oRNAment; **mCrossBase is preferred** and is the
eCLIP-derived one). Each file ships a per-position **information-content (`IC`)
line, 0–2 bits** — a direct, quantitative measure of motif sharpness. Examples
(mCrossBase, K562):
- **RBFOX2 (crisp):** IC core `… 2.000 1.503 1.444 1.792 1.688 …` — a sharp
  `UGCAUG` block. High peak IC.
- **HNRNPK (degenerate):** IC `… 1.593 1.527 1.512 0.817 1.009 …` — informative
  but flatter, C-rich, no 2.0-bit position.
- **U2AF2 (positional):** IC `… 1.839 1.218 0.539 1.033 1.196 1.717 …` —
  moderately informative point-motif, **even though U2AF2 is a positional
  (polypyrimidine-tract) binder**. ⚠️ This is the key caveat: total IC alone does
  NOT cleanly separate "positional" binders — their mCross point-motif can look
  informative. So an IC metric and the biological 3-tier annotation can disagree.

Candidate per-protein difficulty metrics computable straight from these files, no
new data: **total IC**, **peak per-position IC**, number of ≥1.5-bit positions, or
the mCross `Score` field in the `DE` header.

### Do we need code changes?
- **Pipeline / scoring: NO.** The per-run reports already record everything needed:
  `motif_hit_rate`, `motif_enrichment`, `reproducibility_score`,
  `benchmark_region_recall`, `composite`, `n_binding_sites`, and `params`
  (confirmed in `iterations.jsonl` and per-run `decisions.jsonl`).
- **New analysis-only script: YES (small).** It should (1) compute an IC-based
  difficulty per protein from `data/motifs/`, and (2) join it against achieved
  per-run motif/composite scores, then plot/quantify whether the LLM-vs-Optuna gap
  or the motif score varies with difficulty. This touches neither the pipeline nor
  scoring.

### Data availability & one caveat ⚠️
- The clean **paired LLM-vs-Optuna set spanning the difficulty spectrum** is the
  `ins_*` runs: **HNRNPK, PUM2, SF3B4, SRSF1, U2AF2** (K562), plus RBFOX2/QKI/PUM1
  from the `prelim0708_*` and earlier runs. Good spread from crisp → positional.
- ⚠️ **The `ins_*_llm` iterations are NOT in the aggregate `iterations.jsonl`**
  (only the `_optuna` ones are). The LLM data for those does exist, in each run's
  `results/overnight/ins_*_llm/*/decisions.jsonl`. The analysis script must read
  both `iterations.jsonl` and the per-run `decisions.jsonl` to get complete
  LLM coverage — otherwise the LLM side of the difficulty comparison is missing.

### Recommendation for the slide
Keep the biological 3-tier annotation (crisp/degenerate/positional) as the
**x-axis grouping** and plot achieved motif enrichment / composite (LLM vs Optuna)
per group. Optionally overlay the IC metric, but state the caveat that a positional
binder's point-motif can have deceptively high IC — that nuance is itself an
honest, interesting discussion point.

### VM data access (read-only)
`ssh -p 30121 ubuntu@194.94.4.28` — repo at
`/vol/storage1/johannes/projects/agentic-pureclip`. Results in
`results/overnight/` (`iterations.jsonl`, `jobs.jsonl`, per-job subdirs each with
`decisions.jsonl` + score reports). Motifs in `data/motifs/`.
