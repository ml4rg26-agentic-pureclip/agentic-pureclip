# Final-Results — open TODOs

Fairness principle for all final numbers: **multi-parameter LLM moves + an equal
search budget + a shared early-stop rule must be in effect for every presented run**
— no mixing old single-change / unequal-budget runs into the final figures.

**Done (branch `final-results-repo-changes`, one commit each, tests green):**
Change 1 (multi-param — already satisfied by the prompt, no code), Change 2
(no-priors ablation), Change 3 (budget 16 + shared early-stop), Change 4 (LLM
iteration-aggregation fix), arm-tagging, and the batch manifest
`config/final_results_jobs.yaml` (34 jobs). Everything below is still open.

---

## Results (fill in as runs land)

Best **composite** per arm + the two deltas the thesis reports. Read each cell off
the dashboard **Runs** page (per-arm best) or `results/overnight/summary.csv`.
**H2H Δ** = LLM(prior) − Optuna (positive → LLM wins). **Prior Δ** = LLM(prior) −
LLM(no-prior) (positive → the prior helps; expected to grow with difficulty).
**Baseline** = the LLM run's `iter_00` (default params). Leave `—` where an arm
wasn't run for that dataset.

### K562 — difficulty axis (all three arms where run)

| Dataset      | Tier       | Baseline | LLM (prior) | LLM (no-prior) | Optuna  | H2H Δ  | Prior Δ |
|--------------|------------|----------|-------------|----------------|---------|--------|---------|
| RBFOX2_K562  | crisp      | —        | —           | —              | —       | —      | —       |
| QKI_K562     | crisp      | ⏳       | ⏳          | —              | ⏳      |        | —       |
| PUM1_K562    | crisp      | ⏳       | ⏳          | —              | ⏳      |        | —       |
| PUM2_K562    | crisp      | 0.2595   | 0.3520      | 0.3834         | 0.3709  | −0.019 | −0.031  |
| HNRNPK_K562  | degenerate | 0.2420   | 0.3294      | 0.2420         | 0.3750  | −0.046 | +0.087  |
| SRSF1_K562   | degenerate | ⏳       | ⏳          | ⏳             | ⏳      |        |         |
| U2AF2_K562   | positional | 0.4229   | 0.4229      | 0.4603         | 0.4883† | −0.065 | −0.037  |
| SF3B4_K562   | positional | ⏳       | ⏳          | ⏳             | ⏳      |        |         |

⏳ = in the running batch (`config/batch_kaxis_remainder.yaml`, launched 2026-07-10
~20:00, 11 h cap — see **Batch status** below). RBFOX2_K562 (`—`) is deferred to a
dedicated run (~10–12 h for its 3 arms alone).

† **U2AF2 Optuna timed out at 2 iterations** (per-job 300-min cap): 0.4883 came at
its 1st TPE trial and is *not* a fair/converged number — re-run before entering the
final figure. Also note both LLM-prior runs on the positional/degenerate-control
side got stuck at `iter_00` (U2AF2 LLM 0.4229, HNRNPK no-prior 0.2420 never moved).

**Reads so far (ablation gradient, `config/batch_ablation_gradient.yaml`, done):**
the prior's benefit tracks difficulty as hypothesised — **Prior Δ = +0.087 on the
degenerate HNRNPK** (no-prior LLM never left baseline) vs **negative on the crisp
PUM2 control** (−0.031, where the prior isn't needed). Optuna edges the head-to-head
on all three here (−0.02 to −0.07), so the crisp/degenerate LLM-vs-Optuna gap still
needs the full 16-iter budget on more datasets before it's conclusive.

### HepG2 — cross-cell-line (head-to-head only)

| Dataset       | Tier       | Baseline | LLM (prior) | Optuna | H2H Δ |
|---------------|------------|----------|-------------|--------|-------|
| RBFOX2_HepG2  | crisp      |          |             |        |       |
| QKI_HepG2     | crisp      |          |             |        |       |
| HNRNPK_HepG2  | degenerate |          |             |        |       |
| SRSF1_HepG2   | degenerate |          |             |        |       |
| U2AF2_HepG2   | positional |          |             |        |       |
| SF3B4_HepG2   | positional |          |             |        |       |

> Provisional smoke numbers exist for QKI_K562 (llm 0.332 / no-prior 0.322 /
> optuna 0.294) and PUM1_K562 (llm 0.364 / optuna 0.325, **optuna truncated** at
> the 90-min smoke cap). **Both are being re-run now** under the final manifest in
> the running batch — replace with those numbers when it lands.

---

## Batch status (2026-07-10)

- **Done — ablation gradient** (`config/batch_ablation_gradient.yaml`, 9 jobs):
  PUM2 / HNRNPK / U2AF2 K562 × {llm, optuna, llm_noprior}. Numbers in the K562
  table above. (final_u2af2_k562_optuna hit the 300-min timeout at 2 iters.)
- **Running — K562 remainder** (`config/batch_kaxis_remainder.yaml`, 10 jobs,
  launched ~20:00, `--hours 11 --no-repeat`, tmux `kaxis`, log
  `logs/kaxis_remainder.log`): QKI + PUM1 (head-to-head) and SRSF1 + SF3B4
  (all 3 arms), cheapest-tier-first so a partial run yields whole datasets.
- **Pending** (not yet scheduled): **RBFOX2_K562** all 3 arms (dedicated run,
  ~10–12 h) and **all HepG2** head-to-head (6 datasets × 2 arms = 12 jobs).

---

## TODO 1 — Smoke-test on the VM before the real batch  [blocking the launch]
- `--dry-run` the manifest on the VM; confirm all 34 jobs show `data=OK`
  (locally they read MISSING — BAMs live on the VM).
- 1-iter smoke run: confirm the **no-priors prompt** withholds motif/protein, and
  that `results/overnight/iterations.jsonl` now captures **LLM** iters (Change 4).
- Confirm the Optuna early-stop callback fires only after its 10 startup trials.
- `uv run python -m pytest tests/ -q` green on the VM.

## TODO 2 — Launch logistics  [DECIDED — option (b), splitting into chunks]
34 jobs ≈ **1.5–2 days sequential** (QKI/PUM1 ~50 min/job, but RBFOX2 ~3–4 h/job),
so it does NOT fit one overnight. **Chosen: split into ~11-h tmux launches**, each a
copy of jobs from `final_results_jobs.yaml`, cheapest-tier-first:
- ✅ Chunk 1 — ablation gradient (PUM2/HNRNPK/U2AF2 K562, 9 jobs) — done.
- ⏳ Chunk 2 — K562 remainder (QKI/PUM1/SRSF1/SF3B4, 10 jobs) — **running now**.
- ☐ Chunk 3 — RBFOX2_K562 (3 arms, dedicated ~10–12 h).
- ☐ Chunk 4 — HepG2 head-to-head (12 jobs).

Do **not** parallelise: each job already uses `threads: 32` and saturates the VM's
32 cores; concurrency would need fewer threads/job and PureCLIP doesn't scale
linearly, so the net speedup is uncertain. Interleaved (dataset-paired) ordering
means a partial run still yields complete paired datasets.

Launch (on the VM, inside tmux):
```bash
export PATH=/vol/storage1/johannes/projects:$HOME/.local/bin:$PATH
PYTHONPATH=. uv run python scripts/run/overnight_batch.py \
    --manifest config/final_results_jobs.yaml --hours 48 --no-repeat \
    --pureclip-dir /vol/storage1/johannes/projects
```

## TODO 3 — Post-run analysis / plotting  [not started; needs the batch results]
Add under `scripts/analysis/` (new):
- `motif_difficulty.py` — per-protein difficulty metric from the PWM `IC` lines in
  `data/motifs/` (total IC / peak IC / #≥1.5-bit positions), joined with best
  achieved motif + composite per run. Read `iterations.jsonl` (+ per-run
  `decisions.jsonl`).
- `plots.py` — head-to-head table (slide 7), convergence curves LLM vs Optuna and
  LLM vs no-priors (slide 8), per-factor final table + over-iteration curves
  (slide 9).
- Reasoning slide needs no script: an existing `decisions.jsonl` reasoning string +
  a dashboard Runs-page screenshot.

Analysis slices cleanly on the new `arm` tag: head-to-head = `arm ∈ {llm, optuna}`;
ablation = `llm` vs `llm_noprior` on the 6 K562 datasets; cross-cell-line = same
protein/arm across `k562` vs `hepg2`. **Always join on `dataset`/`job_id`, never
`run_id`** (`RBFOX2_iter_01` recurs across K562 and HepG2).

---

## Batch reference (context for the TODOs above)

*Dataset* = one (RBP × cell line) eCLIP set. Primary difficulty comparison is in
**K562** (cell line fixed); a 6-protein subset replicates in **HepG2**.

**14 datasets — 8 K562 (difficulty axis) + 6 HepG2 (cross-cell-line):**

| Tier | K562 | HepG2 |
|---|---|---|
| crisp | RBFOX2, QKI, PUM1, PUM2 | RBFOX2, QKI |
| degenerate | HNRNPK, SRSF1 | HNRNPK, SRSF1 |
| positional | U2AF2, SF3B4 | U2AF2, SF3B4 |

(PUM1/PUM2 are K562-only.)

**34 jobs (3 arms):**
- Head-to-head K562: 8 × {llm, optuna} = 16
- Head-to-head HepG2: 6 × {llm, optuna} = 12
- LLM no-priors K562 (ablation gradient): RBFOX2, PUM2, HNRNPK, SRSF1, U2AF2,
  SF3B4 = 6. Crisp + positional together let the ablation show the prior's benefit
  *rising* with difficulty.
- Baseline = each LLM run's `iter_00` (default params), captured automatically.

**Early-stop (both arms):** stop when best composite hasn't improved by ≥0.01 over
4 consecutive iterations; cap 16. Optuna's counter starts only after its 10 startup
trials, so the LLM may stop ~iter 4–5 while Optuna won't before ~iter 14 — report
iterations-used and best-so-far-vs-iteration curves.

**Outputs** (`results/overnight/`): `iterations.jsonl`, `jobs.jsonl`, `summary.csv`
(all now carry the `arm` / `no_priors` tag); per-job `decisions.jsonl` (reasoning
trail), `<iter>/score_report.json`, `run_config.yaml`, `run.log`.
