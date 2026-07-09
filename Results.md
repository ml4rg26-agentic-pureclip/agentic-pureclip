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

## TODO 1 — Smoke-test on the VM before the real batch  [blocking the launch]
- `--dry-run` the manifest on the VM; confirm all 34 jobs show `data=OK`
  (locally they read MISSING — BAMs live on the VM).
- 1-iter smoke run: confirm the **no-priors prompt** withholds motif/protein, and
  that `results/overnight/iterations.jsonl` now captures **LLM** iters (Change 4).
- Confirm the Optuna early-stop callback fires only after its 10 startup trials.
- `uv run python -m pytest tests/ -q` green on the VM.

## TODO 2 — Launch logistics  [decision needed]
34 jobs ≈ **1.5–2 days sequential** (QKI/PUM1 ~50 min/job, but RBFOX2 ~3–4 h/job),
so it will NOT fit one overnight. Options to decide:
- (a) one weekend launch in tmux with `--hours 48 --no-repeat`; or
- (b) split into two launches — K562 manifest first, then HepG2.

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
