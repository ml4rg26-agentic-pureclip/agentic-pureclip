# Agentic PureCLIP

Agentic PureCLIP is a research framework for automated parameter optimization in
[PureCLIP](https://github.com/skrakau/PureCLIP) eCLIP peak calling. It provides a
shared experimental test bed for comparing a biology-informed large language
model (LLM) agent with numerical black-box optimization.

The project asks whether automated search can improve eCLIP binding-site calls,
whether an LLM can compete with a Tree-structured Parzen Estimator (TPE), and
whether RBP-specific biological context changes the LLM's search behavior.

## Research motivation

Enhanced crosslinking and immunoprecipitation (eCLIP) measures RNA-binding
protein (RBP) contacts transcriptome-wide, but the assay produces aligned reads
rather than a definitive set of binding sites. PureCLIP infers those sites with a
hidden Markov model whose output depends on signal smoothing, site merging,
covariate, and post-processing parameters. Suitable values may vary across RBPs,
cell lines, and experiments, making manual tuning difficult to standardize.

Agentic PureCLIP turns parameter selection into an iterative optimization
problem. Every candidate configuration is evaluated by the same Snakemake
workflow and biological objective, regardless of which optimizer proposed it.
This isolates the proposal strategy from the downstream peak-calling and scoring
machinery.

## Experimental design

The framework compares three experimental arms:

1. **LLM with biological priors** — DeepSeek receives RBP identity, known motifs,
   decomposed score feedback, and prior iterations.
2. **LLM without biological priors** — the same agent and feedback, with the
   RBP-specific context withheld.
3. **TPE** — Optuna proposes parameters using the same bounds, evaluation
   workflow, and scalar objective.

Each evaluation follows the same path:

```text
two eCLIP IP replicates + SMInput + GRCh38
                    │
                    ▼
       PureCLIP and post-processing
                    │
                    ▼
 reproducibility · motif support · reference recall
                    │
                    ▼
             composite score
                    │
                    └──── feedback to optimizer
```

The optimizer searches seven PureCLIP and post-processing parameters. Runs are
recorded as durable configuration, decision, and score artifacts so that the
comparison remains auditable.

## Evaluation objective

Candidate binding-site sets are assessed using three complementary signals:

- **Replicate reproducibility:** chance-corrected support across the two IP
  replicates.
- **Motif support:** hit rate of the most enriched target-RBP PWM relative to a
  sequence-shuffled background.
- **Reference recall:** recovery of strong ENCODE reference regions.

With the default weights, the objective is

```text
S = (0.50 × reproducibility + 0.25 × motif support + 0.25 × reference recall)
    × min(1, number of sites / 10)
```

The final factor penalizes degenerate solutions containing only a few apparently
perfect sites. Weights are configurable and are renormalized if a component is
unavailable.

## Empirical scope and findings

The software registry contains 26 ENCODE datasets spanning 15 RBPs in K562 and
HepG2 cells. The reported experiment is intentionally narrower: PUM2, HNRNPK,
and U2AF2 in K562 form the principal chromosome-21 prior-ablation study, with QKI
and PUM1 as supplementary pilots.

The current evidence is preliminary:

- automated optimization gains were dataset-dependent;
- biological priors improved the LLM result for HNRNPK, but not for PUM2 or
  U2AF2;
- TPE achieved the highest observed score on the three principal datasets, but
  unequal evaluation counts and an incomplete run prevent a controlled optimizer
  ranking.

The main contribution is therefore methodological: a reproducible framework for
testing optimizer behavior against decomposed biological quality signals. A
conclusive comparison requires replicated, equal-budget, genome-wide runs.

## Research artifacts

| Artifact | Location |
|---|---|
| Thesis source and complete study account | [`docs/report/`](docs/report/) |
| Experimental and run configurations | [`config/`](config/) |
| Architecture and data flow | [`docs/architecture-overview.md`](docs/architecture-overview.md) |
| Dataset registry and configuration reference | [`config/README.md`](config/README.md) |
| Interactive research presentation | [`docs/presentation/index.html`](docs/presentation/index.html) |
| Monitoring dashboard documentation | [`dashboard/README.md`](dashboard/README.md) |

Raw eCLIP data, reference files, and generated results are intentionally excluded
from version control. Configurations and code define the experiment; large inputs
and outputs live under the ignored `data/`, `ref/`, and `results/` directories.

## Reproducing and extending the work

Installation, external bioinformatics dependencies, data preparation, execution
commands, testing, dashboard setup, repository structure, and VM deployment are
documented in the [developer onboarding guide](docs/developer-onboarding.md).
The [report build guide](docs/report/ONBOARDING.md) covers the LaTeX manuscript.
