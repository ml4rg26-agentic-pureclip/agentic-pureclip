# Agentic PureCLIP — project context for AI agents

LLM-driven (and Optuna-driven) parameter optimization for **eCLIP** peak calling
with **PureCLIP**. An optimizer proposes PureCLIP + post-processing parameters;
for each set the pipeline runs PureCLIP, scores the result against biological
quality signals, and iterates to maximize a composite quality score.

This file is the orientation doc — biology first, then how the system is built
and run. Keep it accurate when behaviour changes.

---

## 1. Biological background (read this first)

### eCLIP — what the data is
**eCLIP** (enhanced UV-CrossLinking and ImmunoPrecipitation, Van Nostrand et al.
2016) maps where an **RNA-binding protein (RBP)** contacts RNA in living cells:
UV crosslinks protein to RNA, the RBP is immunoprecipitated with a specific
antibody, RNA is fragmented, and sequencing reads are generated. Reverse
transcription tends to **truncate at the crosslink site**, so the 5′ end of the
read marks the protein–RNA contact at near-nucleotide resolution.

Each dataset has:
- **IP replicates** (usually 2) — the antibody pulldown for the target RBP.
- **SMInput** (size-matched input control) — the background; what you'd pull
  down without specific enrichment. Used to subtract non-specific signal.

We work from **pre-aligned, deduplicated BAM files** (ENCODE), not raw reads.

### PureCLIP — what turns reads into "binding sites"
[PureCLIP](https://github.com/skrakau/PureCLIP) is an HMM that models the
crosslink-truncation signal (optionally using the input as a covariate) to call
**crosslink sites** and **binding regions**. Its calls are sensitive to a few
parameters (bandwidth, merge distance, precision mode), and the right values are
**dataset-dependent** — which is the whole reason this project exists.

We use the `pureclip2` fork (johan-stph). On the compute VM the binary lives at
`/vol/storage1/johannes/projects/pureclip2`.

### The RBPs and their RNA motifs
A genuine binding site should sit on/near the RBP's known sequence motif. The
datasets and their canonical motifs (DNA alphabet; RNA U→T):

| RBP | Motif (consensus) | Biology |
|-----|-------------------|---------|
| **RBFOX2** | `UGCAUG` (GCAUG core) | Splicing regulator; binds the canonical (U)GCAUG element in introns / 3′UTRs. |
| **QKI** (Quaking) | `ACUAAY` (+ UAAY half-site) | STAR-family; bipartite QKI response element (QRE); splicing, mRNA stability/export. |
| **PUM1** (Pumilio 1) | `UGUANAUA` (PRE, UGUAHAUA) | Pumilio response element; represses translation / destabilizes target mRNAs. |

Motifs are scored with **position weight matrices (PWMs)** from motif databases
(mCrossBase, ATtRACT, CISBP-RNA, RBPDB, RBPmap, oRNAment) under `data/motifs/`,
with the consensus strings above as IUPAC fallback.

The benchmark has since grown to **~26 datasets** (see `pipeline/datasets.py`).
The 20 added in 2026-07 are dominated by **splicing factors** (HNRNPK/M, SF3B1/4,
SRSF1, SFPQ, U2AF1/2, RBM22, PCBP1, PUM2, PTBP1) — a harder class than the crisp
preliminary trio above. ⚠️ For **positional binders** (U2AF1/2, SF3B1/4, RBM22)
the auto-resolved "target motif" is a weak proxy (binding is defined by position
at splice sites / branch point, not a k-mer); motif-aware scoring for them should
be down-weighted or use a positional prior, else the motif term misleads. PUM2 is
a near-free positive control (same UGUANAUA family as PUM1).

### Cell lines
- **K562** — human chronic myelogenous leukemia (ENCODE tier-1).
- **HepG2** — human hepatocellular carcinoma / liver (ENCODE tier-1).

The same RBP in different cell lines (e.g. RBFOX2_K562 vs RBFOX2_HepG2) can give
different binding landscapes, so they are separate datasets.

### What makes a binding-site set "good" (the science behind scoring)
1. **Reproducible** across IP replicates — real binding recurs; noise does not.
2. **Motif-bearing** — sites contain the RBP's expected RNA motif more than chance.
3. **Recovers known sites** — overlaps a curated ENCODE reference of strong
   regions (precision/recall against ground-ish truth).
4. **Adequate yield** — collapsing to a handful of "perfect" sites is *not* a
   good result; reproducibility and motif rate trivially saturate at tiny counts.

`expected_footprint_width_nt ≈ 9` for these RBPs — post-processing normalizes
each site to ~that footprint.

---

## 2. The optimization problem

**Tunable parameters** (`pipeline/configs.py::DEFAULT_SEARCH_BOUNDS`):
- PureCLIP: `bandwidth_nt` [20–100], `merge_distance_nt` [4–16],
  `high_precision_mode` {0,1}, `use_input_covariate` {0,1}
- Post-processing: `min_crosslink_events` [2–6], `force_width` [3–15],
  `cluster_gap_width` [4–16]

**Objective** (`agent/decisions.py::composite_objective`), all terms in [0,1]:

```
composite = ( 0.5·reproducibility + 0.25·motif + 0.25·recall )   # weights renormalised over present terms
            × min(1, n_binding_sites / 10)                        # collapse guard
```

- **reproducibility** = chance-corrected replicate agreement
  `(observed − expected)/(1 − expected)`, expected from shuffled sites. Not
  gameable by keeping a few broad intervals.
- **motif** = fraction of site windows with a log-odds PWM hit, reported for the
  **most enriched** motif (enrichment = rate ÷ shuffled background).
- **recall** = fraction of known-strong ENCODE reference regions recovered,
  **restricted to the analyzed chromosome(s)** (under chr21 mode the genome-wide
  reference would cap recall at ~4.5%).
- **collapse guard** = ramps the score to ~0 below ~10 sites. Added after a 12h
  run showed Optuna collapsing QKI to 1 site for a fake composite of 0.78.

Weights are configurable per run via `priors.objective_weights`; the site floor
is `DEFAULT_MIN_SITES` (10).

---

## 3. Repo map

- `agent/` — optimizers. `graph.py` = LangGraph LLM loop (DeepSeek);
  `optuna_runner.py` = Optuna/TPE alternative; `evaluation.py` = shared
  `evaluate_config` (run PureCLIP + score → report); `decisions.py` = objective,
  prompt, decision validation/retry.
- `pipeline/` — `configs.py` (search bounds, validation), `datasets.py` (dataset
  registry + motif auto-resolution; table-driven `_standard_spec()` helper),
  `motifs.py` (TRANSFAC/PWM log-odds), `runner.py`.
- `workflow/` — `Snakefile` (merge IP → pureclip2 → per-replicate → postprocess →
  score) and `postprocess.py` (footprint standardization).
- `scorers/run_scorers.py` — reproducibility, motif hit-rate + enrichment,
  benchmark recall; writes `score_report.json` (now self-describing: includes the
  params that produced it).
- `scripts/` — `overnight_batch.py` (failure-tolerant, wall-clock-budgeted batch
  runner), `batch_runner.py` (simpler manifest runner: `--manifest`/`--parallel`,
  one `agent.graph` subprocess per run, appends `results/batch/_summary.tsv`),
  data download helpers.
- `dashboard/api/` — FastAPI backend (uvicorn) serving the `/api/*` JSON data.
- `dashboard/ui/` — React Router SPA (Dashboard, Runs, Plan run, Variables);
  calls the `dashboard/api` backend over `/api/*`.
- `config/` — `run_config.yaml`, dataset configs, batch manifests, `priors.json`.
- `tests/` — pytest suite (objective, PWM scoring, agent resilience, Optuna).

`data/` and `results/` are gitignored (large BAMs, run outputs, the analysis DB).

---

## 4. How to run

Toolchain is **uv** (not conda) and the LLM is **DeepSeek** (`DEEPSEEK_API_KEY`
in `.env`); the README still references Gemini/conda and is out of date.

```bash
uv sync                                   # install deps
uv run python -m pytest tests/ -q         # tests (set DEEPSEEK_API_KEY=dummy)

# single LLM optimization run
CONFIG_PATH=config/run_config.yaml MAX_ITER=8 PYTHONPATH=. uv run python agent/graph.py

# single Optuna run (same eval + objective, no API key needed)
CONFIG_PATH=config/run_config.yaml MAX_ITER=12 PYTHONPATH=. uv run python agent/optuna_runner.py

# failure-tolerant batch (CLI; also what the UI "Plan run" page generates)
PYTHONPATH=. uv run python scripts/run/overnight_batch.py \
    --manifest config/bigrun2_jobs.yaml --hours 12 --no-repeat \
    --pureclip-dir /vol/storage1/johannes/projects

# simple manifest batch (per-dataset preliminary runs; results/batch/_summary.tsv)
PYTHONPATH=. uv run python scripts/run/batch_runner.py \
    --manifest config/new_batch_runs.yaml --parallel 4

# dashboard data API (FastAPI; run from the repo root)
uv run uvicorn dashboard.api.main:app --host 0.0.0.0 --port 8888
```

`learn_on_chr21: true` restricts PureCLIP to chr21 — "fast mode", ~minutes/iter
instead of hours; used for all batch experiments.

### UI (dashboard/ui/)
```bash
cd dashboard/ui && npm install && npm run dev   # http://localhost:5173 (proxies /api → backend)
npm run build                                    # SPA → build/client/
```
Pages: **Dashboard** (active run + stepper, queue/ETA, results leaderboard with
LLM-vs-Optuna head-to-head), **Runs** (per-iteration decision trail: params
changed + reasoning, from `decisions.jsonl`), **Plan run** (pick dataset, params
& ranges, schedule via `POST /api/schedule`), **Variables** (plain-English guide).

---

## 5. Compute VM & dashboard ops (`ssh bio`)

- Host alias `bio` → VM `agenticpureclipvm-751a3` (32 cores, 251 GB RAM). Project
  at `/vol/storage1/johannes/projects/agentic-pureclip`.
- The runner copy is **not a git checkout** (git commands fail there) — it's
  deployed by copying files in. To ship a local fix, `scp` the file(s) directly,
  e.g. `scp pipeline/motifs.py bio:/vol/storage1/johannes/projects/agentic-pureclip/pipeline/`.
- **Non-interactive SSH does not source the interactive PATH.** A bare
  `ssh bio '… uv run …'` fails with `uv: command not found`, then
  `ModuleNotFoundError: pipeline`, then `pureclip2: command not found`. To launch
  anything over SSH, export all three:

  ```bash
  ssh bio 'cd /vol/storage1/johannes/projects/agentic-pureclip; \
    export PATH=/vol/storage1/johannes/projects:$HOME/.local/bin:$PATH; \
    PYTHONPATH=. nohup uv run python scripts/run/batch_runner.py \
      --manifest config/rerun_hnrnpk.yaml --parallel 2 \
      > logs/rerun_hnrnpk.log 2>&1 &'
  ```

  `/vol/storage1/johannes/projects` → `pureclip2` (symlink to `pureclip` 2.0.4,
  johan-stph fork); `$HOME/.local/bin` → `uv`; `PYTHONPATH=.` → the `pipeline`/
  `agent` packages. Prefer **tmux** for anything long-lived (a bare `&` over a
  non-detached SSH channel can hang it); `nohup … &` with a redirect works for
  fire-and-forget.
- View the dashboard locally: tunnel the API with
  `ssh -f -N -L 8888:localhost:8888 bio`, then run the UI locally
  (`cd dashboard/ui && npm run dev` → http://localhost:5173, proxies `/api` →
  the tunnel). If data is stale, the tunnel often died — kill and re-establish
  it. `uv run uvicorn dashboard.api.main:app --port 8888` is the backend.
- Result stores (all gitignored, runner-only): `results/batch/` (from
  `batch_runner.py`: per-run `<id>_<ts>/` dirs with `decisions.jsonl` +
  per-iteration `score_report.json`, plus `_summary.tsv`) and `results/overnight/`
  (`iterations.jsonl`, `jobs.jsonl`, `summary.csv`, `<job_id>/decisions.jsonl`).

---

## 6. Conventions & gotchas

- The optimizers are **interchangeable** — same `evaluate_config` and
  `composite_objective`, same bounds. Only the *search strategy* differs, so
  LLM-vs-Optuna comparisons are apples-to-apples.
- `composite_objective` is the **single source of truth** for scoring; the
  monitor imports it so the dashboard never disagrees with the optimizer.
- The composite is computed **live** from `score_report.json`, so changing the
  objective re-scores all historical runs on the dashboard automatically.
- Runs must be **failure-tolerant**: `overnight_batch` isolates each job, never
  aborts the batch on one failure, and records partials.
- The LLM loop recovers from repeated/invalid proposals (re-prompt, then converge)
  rather than crashing.
- `score_report.json` and the decision trail are the durable per-run records;
  the shared agent log is not a reliable per-run source.
- **PWM loading assumes frequency/count matrices, but some databases ship
  log-odds.** RBPmap `*_PSSM` matrices contain *negative* cells; normalizing them
  by their row sum yields negative pseudo-frequencies, and
  `MotifPWM.log_odds` would raise `math domain error` on `log2(≤0)`. It now clamps
  each cell to ≥0 first (no-op for real frequency matrices; disfavored PSSM bases
  map to ~0 → strongly negative log-odds). This is what crashed HNRNPK scoring in
  the 2026-07 batch. When adding motif sources, watch for negative-valued matrices.
- `batch_runner.py` reads a run's score by grepping the agent output for
  `Best composite score=` (what `agent.graph` logs on `DONE`). If that log line
  changes, `_summary.tsv` silently records `best_score=None` even though the real
  score is in each run's `decisions.jsonl`.

## 7. Current focus / open threads

- **RBFOX2_K562** is the hardest dataset (reproducibility ~0.10); wider bandwidth
  helped. Improving it is the main scientific goal.
- LLM vs Optuna: with the collapse guard, results are honest — LLM resists
  collapse (it has the prior); Optuna needs the guard to avoid degenerate wins.
- Possible next steps: tune objective weights, raise Optuna trial budget for a
  fairer comparison, dinucleotide-shuffled motif background, IDR-based
  reproducibility, central/positional motif enrichment.
