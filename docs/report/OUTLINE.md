# Report Outline

Target: **10 pages** incl. title + references (~7.5 pp body). Page budget per
section in brackets. Maps onto `sections/*.tex`.

## Abstract  [0.5 pp, part of titlepage]
- One paragraph (~150 words): problem (eCLIP peak-calling parameters), approach
  (two optimizer strategies on one shared evaluation), key result (LLM vs Optuna
  vs default-parameter baseline), takeaway.

## 1. Introduction  [1.0 pp]  → `1_introduction.tex`
- eCLIP produces **transcriptome-wide** RBP binding maps, but peak-calling
  quality depends heavily on a small set of tool parameters.
- eCLIP yields per-nucleotide crosslink counts, not discrete sites — **peak
  calling is the post-processing step** that turns noisy read density into a
  discrete, interpretable binding-site set; its quality gates everything
  downstream.
- No universal optimal parameter set exists — optimal values vary by RBP, cell
  line, and **experiment quality (antibody efficiency, sequencing depth, …)**.
- Manual tuning is impractical: hours per run, subjective evaluation, ENCODE
  scale → demands a reproducible automated solution.
- **Contribution:** we compare two automated optimizer strategies (LLM reasoning
  vs. Bayesian search) on identical evaluation infrastructure, against a
  default-parameter baseline.

## 2. Theory  [1.5 pp — COMPRESS, bloat risk]  → `2_theory.tex`
- eCLIP biology: RBP function, UV crosslinking, 5′-truncation signal, three RBPs
  (RBFOX2/QKI/PUM1) and their canonical RNA motifs.
- PureCLIP as peak caller: HMM over read density; what bandwidth and merge
  distance control; why "wrong" parameters over-/under-call sites.
- What makes a binding-site set biologically good: reproducibility across
  replicates, motif enrichment, recovery of ENCODE reference sites.
- Two optimizer paradigms: **LLMs as reasoning-based optimizers** (domain priors
  + iterative feedback; cite the LLM-as-optimizer / OPRO line of work) vs.
  **Bayesian optimization / TPE** (data-driven surrogate, no prior knowledge).

## 3. Architecture & Methods  [1.5 pp]  → `3_method.tex`
- 5 ENCODE eCLIP datasets (RBFOX2×2, QKI×2, PUM1×1); chr21 fast mode for
  feasible iteration times.
- 7 tunable parameters with justified bounds; shared Snakemake pipeline
  producing a `score_report.json` per trial.
- **Shared objective (evaluation, not strategy):**
  `composite = (0.5·repro + 0.25·motif + 0.25·recall) × min(1, n/10)`,
  collapse guard prevents degenerate few-site solutions. **Both optimizers are
  scored by this identical objective — that is what makes the comparison
  apples-to-apples.** (Define the formula ONCE, here.)
- **The two strategies differ only in how they propose parameters** (answers
  Wen): Optuna (TPE) fits a surrogate on the composite *scalar*, no domain
  knowledge; the LLM agent (DeepSeek, T=0.2) receives the *decomposed* metrics +
  biological priors + score deltas and proposes one reasoned change per step.
- **Reproducibility & compute:** Snakemake configs, total #evaluations and
  wall-clock budget, code availability (one short paragraph).

## 4. Results  [2.0 pp]  → `4_results.tex`
- **Baseline vs LLM vs Optuna** head-to-head table — default/ENCODE-published
  parameters as the reference row (do either optimizer beat defaults?), plus
  convergence trajectories (who reaches higher composite, and how fast).
  *(Figures: convergence curve + head-to-head table.)*
- Biological quality of optimized sites: per-dataset reproducibility, motif
  enrichment (canonical match?), ENCODE recall.
- Dataset-specific findings: do optimal parameters differ between cell lines for
  the same RBP; does the LLM's reasoning trace reveal interpretable biological
  decisions?
- Collapse guard: site-count distributions confirm both optimizers keep healthy
  yield.

## 5. Discussion / Limitations  [0.75 pp]  → `5_discussion.tex`
- **Fixed objective weights:** the 0.5/0.25/0.25 blend is hardcoded and treats
  replicates as equal quality — no way to down-weight a known-weaker replicate
  or adapt weights per dataset. Kept as-is for time; extension = quality-aware /
  learned weighting. *(Wen + Lambert's point.)*
- Generality: chr21 fast mode + 5 datasets — how far conclusions extend to
  full-genome / other RBPs.
- LLM-specific caveats: cost, latency, non-determinism, dependence on prior
  quality vs. Optuna's reproducibility.

## 6. Conclusion  [0.25 pp]  → `6_conclusion.tex`
- 3–4 sentences: which strategy wins, when, and why; one-line outlook.

## References  [0.75 pp]  → `master.bib`
- eCLIP/ENCODE, PureCLIP, Optuna/TPE, LLM-as-optimizer (OPRO), motif/PWM
  references.

---

### 10-minute presentation (≈10–11 slides, ~50s each)
1. Title / team
2. Problem: eCLIP → why peak calling → why parameters matter
3. Idea: two optimizer strategies, one shared evaluation (fairness)
4. System diagram: loop → pipeline → scoring → objective
5. Objective + collapse guard (Wen distinction: shared metric, different proposal)
6. **Baseline vs LLM vs Optuna** head-to-head table
7. Convergence trajectories
8. Biological quality + one interpretable LLM reasoning-trace example
9. Limitations (fixed weights, chr21, cost)
10. Conclusion / takeaway

Cut from the talk: deep biology + PureCLIP HMM internals (one motivation slide,
not three). Spend the minutes on slides 6–8.
