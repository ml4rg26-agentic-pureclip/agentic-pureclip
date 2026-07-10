# Final-Results Plan — repo changes → experiment batch → analysis

Plan to (1) make the repo changes required for a fair final comparison, (2) launch
the runs, and (3) produce the figures for the deck. **No code has been changed yet.**
Fairness principle driving this: **the LLM's multi-parameter-change ability and an
equal search budget must be in effect for ALL presented results** — no mixing old
single-change / unequal-budget runs into the final numbers.

Grounded in code as of branch `presentation-report-revisions`. File/line anchors
are given so each change is unambiguous.

---

## Part 1 — Repo changes that MUST land before the batch

These are blocking — the final runs should only start once they are all in.
**Five items total:** Changes 1–4 below, plus the small **arm-tagging** addition
(detailed under *Storage & provenance*). All five appear in the change-summary table
at the end.

### Change 1 — Multi-parameter LLM moves (fairness: applies to all results)
**Why:** Optuna already samples all 7 params every trial; the LLM is currently
forced to change one at a time. To compare fairly (and per the meeting decision),
the LLM must be allowed to change several at once. This must be active for every
LLM run in the final batch.

**What to change — it's smaller than it looks:**
- `src/agentic_pureclip/scoring/objective.py` → `build_decision_prompt`, **decision
  rule #2** currently reads *"Change ONE parameter at a time so the effect is
  interpretable."* Rewrite it to permit (and lightly encourage) changing multiple
  parameters in one step — e.g. *"You may change one or several parameters at once;
  change what the evidence supports, and keep your reasoning tied to the deltas you
  observed."* Also relax the response-format note if it implies a single change.
- **No change needed** to `apply_decision_changes` (`pipeline/configs.py:214`): it
  already loops over every section and key in `changes` and applies them all. The
  one-at-a-time behavior is enforced *only* by the prompt text.
- **No change needed** to dedup: `tunable_signature` hashes the full snapshot, so
  multi-key moves are deduped correctly.

**Risk / note:** interpretability is preserved — the `reasoning` field still
explains the (now possibly multi-param) move. Keep the "explain via the deltas"
instruction so the reasoning slide still works.

**Tests:** check `tests/test_agent.py` / `tests/test_agent_resilience.py` for any
assertion on the "ONE parameter" wording or single-key changes; update accordingly.

---

### Change 2 — No-priors ablation mode (for "does the prior help?")
**Why:** Slide 8 needs an **LLM-with-priors vs LLM-without-priors** comparison.
No such data exists today. This isolates whether the biological prior is what gives
the LLM its edge.

**Critical correctness constraint:** the ablation must change **only what the LLM
sees in its prompt**, NOT what gets scored. The scorer (`scoring/run_scorers.py`)
loads priors independently and uses `target_protein`/`cell_line` to pick the motif
PWMs — that must stay intact so both arms are scored identically. Likewise keep
`objective_weights` and `search_bounds` visible (they are the shared game, not a
biological prior).

**What to change:**
- `scoring/objective.py` → `build_decision_prompt`: add a param
  `include_priors: bool = True`. When `False`, replace the `PRIOR KNOWLEDGE`
  block with a withheld-placeholder line and do not inject `known_motifs`,
  `target_protein`, `expected_footprint_width_nt`, `preferred_transcript_region`,
  `binding_breadth`. Keep the weights line and the `SEARCH BOUNDS` block.
- `loop/graph.py`: read an env flag (e.g. `LLM_NO_PRIORS=1`), pass
  `include_priors=not no_priors` into `build_decision_prompt`. Leave
  `state["priors"]` untouched so run-id naming, weights, and scoring are unchanged.
- `scripts/run/overnight_batch.py` → `run_one_job`: set
  `env["LLM_NO_PRIORS"] = "1"` when the job manifest entry has `no_priors: true`.
  (Env is already copied and augmented there, ~line 248.)

**Tests:** add one asserting the no-priors prompt contains no motif/protein string
while the default prompt does.

---

### Change 3 — Equal budget cap + shared early-stop rule  [DECIDED]
**Why:** current runs gave Optuna 12 and the LLM 8 iterations (see
`config/insight_llm_vs_optuna.yaml`); that confound must go. Fairness rule: the
budget cap AND the early-stop criterion must be identical for both optimizers.

**Budget cap = 16 (both).** Optuna's `TPESampler` uses `n_startup_trials=10`
(default, unchanged in code) — its first 10 trials are RANDOM and only then does
the TPE model guide the search. So 12 trials = ~2 model-guided; **16 = ~6
model-guided**, a fair showing of TPE. (Optional lever: lowering `n_startup_trials`
gives more guided trials per budget but changes Optuna's behavior — leave at 10.)

**Shared early-stop rule (both allowed to stop early):**
- Stop when best composite hasn't improved by **≥ δ = 0.01** for **P = 4**
  consecutive iterations. Cap 16.
- **Protect Optuna's startup:** only begin counting stagnation AFTER its 10 random
  startup trials (before that, "no improvement" is noise, not convergence). The LLM
  has no random phase, so it counts from iteration 0.
- Consequence: the LLM may stop ~iter 4–5 on a plateau; Optuna won't stop before
  ~iter 14 (10 startup + 4 stagnation). This asymmetry is honest — report
  iterations-used per run and show best-so-far-vs-iteration curves.

**What to change:**
- Manifest: `max_iter: 16` for every job.
- `loop/graph.py`: LLM early-stop already exists (`patience`/
  `score_improvement_threshold` in `__main__`, ~line 274). Make `patience`
  configurable via env and set **patience=4**, threshold 0.01.
- `loop/optuna_runner.py`: NO early stop exists today. Add a stop-callback that
  calls `study.stop()` when the rule trips, **gated on `trial.number >= 10`**
  (past startup).

**Tests:** optional check that env overrides are read and the Optuna callback fires.

---

### Change 4 — Fix the LLM iteration-aggregation gap
**Why:** the LLM's per-iteration results never reached the aggregate
`results/overnight/iterations.jsonl` — only Optuna's did. Confirmed root cause:

- `loop/graph.py` `__main__` (~line 250-261) inserts a **timestamped session
  subdir**, so LLM score reports land at
  `results/overnight/<job>/run_config_<ts>/<iter>/score_report.json` (two levels
  under the job root).
- Optuna (`optuna_runner.py`) does **not** re-nest, so its reports land at
  `results/overnight/<job>/<iter>/score_report.json` (one level).
- `overnight_batch.py` → `collect_iterations` (~line 187) globs
  `root.glob("*/score_report.json")` — **one level only** → it catches Optuna and
  misses the LLM.

**What to change (pick one):**
- **Recommended:** make `collect_iterations` glob recursively —
  `root.glob("**/score_report.json")` — and de-dup by `run_id` if needed. Least
  surprising, keeps per-run isolation, also back-fills the *existing* LLM runs when
  re-collected.
- Alternative: make `graph.py` skip the timestamped re-nest when `results_root` is
  already provided by the batch (align it with Optuna's behavior).

**Note:** the LLM also names iter 0 `<DATASET>_iter_00` but later iters
`<PROTEIN>_iter_NN` (graph renames `run_id` by `target_protein` after iter 0). The
`_iter_index` regex still parses both; just be aware when joining by run_id.

**Tests:** optionally a small test that a two-level-nested report is collected.

---

## Part 2 — The experiment batch (after Part 1 lands)

Create a new manifest `config/final_results_jobs.yaml` that **supersedes** the
`ins_*`, `prelim*`, and `*_r2` runs for the final numbers.

**Terminology:** a *dataset* = one (RBP × cell line) pair = one eCLIP experiment set
(2 IP replicates + 1 input control, specific ENCODE BAMs). `RBFOX2_K562` and
`RBFOX2_HepG2` are different datasets. The **primary difficulty comparison is run in
K562** (cell line fixed, so difficulty isn't confounded); a **6-protein subset is
replicated in HepG2** as the cross-cell-line arm.

**Exact datasets — 14 (8 K562 + 6 HepG2).** All are in the `datasets.py` registry
(RBFOX2/QKI/PUM1 as original specs; the rest via `_NEW_ENCODE_DATASETS`) and all
have data verified present + indexed on the VM (2 IP + 1 input BAM each, `.bai`
present, benchmark regions present) as of 2026-07-09.

Primary difficulty axis (K562, cell line fixed):

| Dataset ID | Protein | Tier | Motif / rationale |
|---|---|---|---|
| `RBFOX2_K562` | RBFOX2 | crisp | UGCAUG — sharpest motif; crisp control |
| `QKI_K562` | QKI | crisp | ACUAAY; crisp control |
| `PUM1_K562` | PUM1 | crisp | UGUANAUA; crisp control |
| `PUM2_K562` | PUM2 | crisp | Pumilio; positive control (expect LLM ≈ Optuna) |
| `HNRNPK_K562` | HNRNPK | degenerate | C-rich |
| `SRSF1_K562` | SRSF1 | degenerate | GA-rich ESE |
| `U2AF2_K562` | U2AF2 | positional | polypyrimidine tract (splice site) |
| `SF3B4_K562` | SF3B4 | positional | branch point / U2 snRNP |

Cross-cell-line arm (HepG2 — same 6 proteins that have HepG2 data; PUM1/PUM2 are
K562-only): `RBFOX2_HepG2`, `QKI_HepG2`, `HNRNPK_HepG2`, `SRSF1_HepG2`,
`U2AF2_HepG2`, `SF3B4_HepG2`. Purpose: show the LLM-vs-Optuna pattern and the
difficulty gradient **replicate in a second cell line**, and match the deck's
"both cell lines" scope.

**Run configurations — 34 jobs (3 arms):**
- **Head-to-head, K562:** 8 datasets × {LLM, Optuna} → 16 jobs
- **Head-to-head, HepG2:** 6 datasets × {LLM, Optuna} → 12 jobs
- **LLM no-priors (ablation gradient), K562:** 6 datasets spanning crisp→positional
  — RBFOX2, PUM2 (crisp), HNRNPK, SRSF1 (degenerate), U2AF2, SF3B4 (positional) → 6
  jobs. Crisp + positional together let the ablation show the prior's benefit
  *rising* with difficulty (not just "it helps on hard").
- **Baseline** = each LLM run's `iter_00` (default params) — captured automatically.

**The manifest — `config/final_results_jobs.yaml` (write exactly this):**
Ordered **interleaved by dataset**, K562 block then HepG2 block, so a wall-clock
cutoff leaves whole datasets finished (paired) rather than a half-done arm.

```yaml
# Final results batch — fair LLM vs Optuna (+ LLM no-priors ablation) across the
# motif-difficulty axis, in two cell lines. One launch produces all results.
defaults:
  threads: 32
  learn_on_chr21: true
  per_job_timeout_min: 300   # RAISED from 150: a 16-iter RBFOX2 job runs ~3-4 h;
                             # the old 150-min cap would truncate the expensive ones.
  objective_weights: {reproducibility: 0.5, motif: 0.25, recall: 0.25}
  # Early-stop (Change 3): patience=4, delta=0.01; Optuna counts only after its 10
  # startup trials. Wired via env / runner change, not per-job fields here.

jobs:
  # ============================ K562 ============================
  # RBFOX2 — crisp (+ no-priors)
  - {id: final_rbfox2_k562_llm,         dataset: RBFOX2_K562, optimizer: llm,    max_iter: 16}
  - {id: final_rbfox2_k562_optuna,      dataset: RBFOX2_K562, optimizer: optuna, max_iter: 16}
  - {id: final_rbfox2_k562_llm_noprior, dataset: RBFOX2_K562, optimizer: llm,    max_iter: 16, no_priors: true}
  # QKI — crisp
  - {id: final_qki_k562_llm,            dataset: QKI_K562,    optimizer: llm,    max_iter: 16}
  - {id: final_qki_k562_optuna,         dataset: QKI_K562,    optimizer: optuna, max_iter: 16}
  # PUM1 — crisp
  - {id: final_pum1_k562_llm,           dataset: PUM1_K562,   optimizer: llm,    max_iter: 16}
  - {id: final_pum1_k562_optuna,        dataset: PUM1_K562,   optimizer: optuna, max_iter: 16}
  # PUM2 — crisp control (+ no-priors)
  - {id: final_pum2_k562_llm,           dataset: PUM2_K562,   optimizer: llm,    max_iter: 16}
  - {id: final_pum2_k562_optuna,        dataset: PUM2_K562,   optimizer: optuna, max_iter: 16}
  - {id: final_pum2_k562_llm_noprior,   dataset: PUM2_K562,   optimizer: llm,    max_iter: 16, no_priors: true}
  # HNRNPK — degenerate (+ no-priors)
  - {id: final_hnrnpk_k562_llm,         dataset: HNRNPK_K562, optimizer: llm,    max_iter: 16}
  - {id: final_hnrnpk_k562_optuna,      dataset: HNRNPK_K562, optimizer: optuna, max_iter: 16}
  - {id: final_hnrnpk_k562_llm_noprior, dataset: HNRNPK_K562, optimizer: llm,    max_iter: 16, no_priors: true}
  # SRSF1 — degenerate (+ no-priors)
  - {id: final_srsf1_k562_llm,          dataset: SRSF1_K562,  optimizer: llm,    max_iter: 16}
  - {id: final_srsf1_k562_optuna,       dataset: SRSF1_K562,  optimizer: optuna, max_iter: 16}
  - {id: final_srsf1_k562_llm_noprior,  dataset: SRSF1_K562,  optimizer: llm,    max_iter: 16, no_priors: true}
  # U2AF2 — positional (+ no-priors)
  - {id: final_u2af2_k562_llm,          dataset: U2AF2_K562,  optimizer: llm,    max_iter: 16}
  - {id: final_u2af2_k562_optuna,       dataset: U2AF2_K562,  optimizer: optuna, max_iter: 16}
  - {id: final_u2af2_k562_llm_noprior,  dataset: U2AF2_K562,  optimizer: llm,    max_iter: 16, no_priors: true}
  # SF3B4 — positional (+ no-priors)
  - {id: final_sf3b4_k562_llm,          dataset: SF3B4_K562,  optimizer: llm,    max_iter: 16}
  - {id: final_sf3b4_k562_optuna,       dataset: SF3B4_K562,  optimizer: optuna, max_iter: 16}
  - {id: final_sf3b4_k562_llm_noprior,  dataset: SF3B4_K562,  optimizer: llm,    max_iter: 16, no_priors: true}
  # ==================== HepG2 (head-to-head only) ====================
  - {id: final_rbfox2_hepg2_llm,        dataset: RBFOX2_HepG2, optimizer: llm,    max_iter: 16}
  - {id: final_rbfox2_hepg2_optuna,     dataset: RBFOX2_HepG2, optimizer: optuna, max_iter: 16}
  - {id: final_qki_hepg2_llm,           dataset: QKI_HepG2,    optimizer: llm,    max_iter: 16}
  - {id: final_qki_hepg2_optuna,        dataset: QKI_HepG2,    optimizer: optuna, max_iter: 16}
  - {id: final_hnrnpk_hepg2_llm,        dataset: HNRNPK_HepG2, optimizer: llm,    max_iter: 16}
  - {id: final_hnrnpk_hepg2_optuna,     dataset: HNRNPK_HepG2, optimizer: optuna, max_iter: 16}
  - {id: final_srsf1_hepg2_llm,         dataset: SRSF1_HepG2,  optimizer: llm,    max_iter: 16}
  - {id: final_srsf1_hepg2_optuna,      dataset: SRSF1_HepG2,  optimizer: optuna, max_iter: 16}
  - {id: final_u2af2_hepg2_llm,         dataset: U2AF2_HepG2,  optimizer: llm,    max_iter: 16}
  - {id: final_u2af2_hepg2_optuna,      dataset: U2AF2_HepG2,  optimizer: optuna, max_iter: 16}
  - {id: final_sf3b4_hepg2_llm,         dataset: SF3B4_HepG2,  optimizer: llm,    max_iter: 16}
  - {id: final_sf3b4_hepg2_optuna,      dataset: SF3B4_HepG2,  optimizer: optuna, max_iter: 16}
```

**Total: 34 jobs** (22 K562 + 12 HepG2), chr21 fast-mode.

> **Timing — this will NOT fit one overnight.** Measured durations vary hugely by
> dataset: QKI/PUM1 ~2-4 min/iter (~50 min/job at 16), but **RBFOX2 ~10-15 min/iter
> (~3-4 h/job)**. Rough total for 34 jobs ≈ **1.5-2 days of sequential compute**.
> Options: (a) run over a weekend in tmux with `--hours 48`; or (b) split into two
> launches — K562 manifest first, then HepG2. (Parallelising jobs is *discouraged* —
> the VM's cores are already saturated per job; see Part 4 §5.) The interleaved order
> means a partial run still yields complete, paired datasets.

**Launch (on the VM, inside tmux):**
```bash
export PATH=/vol/storage1/johannes/projects:$HOME/.local/bin:$PATH
PYTHONPATH=. uv run python scripts/run/overnight_batch.py \
    --manifest config/final_results_jobs.yaml --hours 48 --no-repeat \
    --pureclip-dir /vol/storage1/johannes/projects
```

**Pre-launch checklist:**
- `--dry-run` the manifest; confirm all 34 jobs show `data=OK`.
- Confirm the no-priors prompt withholds motif/protein (Change 2 test).
- Confirm `iterations.jsonl` now captures LLM iters (Change 4) on a 1-iter smoke run.
- `uv run python -m pytest tests/ -q` green.

### Storage & provenance — one launch, results sorted by purpose

The existing runner already stores everything after **each** job (fail-tolerant: a
job failure never aborts the batch), so a single launch produces the full result
set. Naming makes purpose self-describing:

- **Job id scheme:** `final_<protein>_<cellline>_<arm>`,
  `arm ∈ {llm, optuna, llm_noprior}`. The `final_` prefix separates this batch from
  the old `ins_*`/`prelim*`/`*_r2` runs; `<cellline>` (`k562`/`hepg2`) separates the
  cross-cell-line arm; the arm suffix separates head-to-head from ablation.

**Written after every job (aggregate, under `results/overnight/`):**
- `iterations.jsonl` — one row per scored iteration: dataset, optimizer, iteration,
  the 3 subscores + composite, `n_binding_sites`, params. *(Requires Change 4 so
  the LLM rows actually land here — without it the LLM half is silently dropped.)*
- `jobs.jsonl` — one row per job: status, timing, exit code, `best_composite`,
  optimizer, `max_iter`, failure hint.
- `summary.csv` — one eyeball-able row per job.

**Written per job (under `results/overnight/final_<...>/`):**
- `decisions.jsonl` — **the reasoning trail**: per iteration the params, the 3
  subscores + composite, and the `reasoning` string (LLM natural language; Optuna a
  generic "TPE proposal" line) + `changes`. This is the source for the reasoning
  slide and the per-iteration decision view.
- `<iter>/score_report.json` — full scorer output for each iteration.
- `run_config.yaml`, `run.log` — exact config used + full run log.

**One required addition for clean purpose-sorting (fold into Change 2 / Change 4):**
tag each `jobs.jsonl` and `iterations.jsonl` record with the **arm** (`llm` /
`optuna` / `llm_noprior`) or an explicit `no_priors: bool`. `optimizer` alone
cannot distinguish the priors-on LLM from the no-priors LLM. With this tag, any
analysis slices cleanly: head-to-head = `arm ∈ {llm, optuna}`; ablation = `llm` vs
`llm_noprior` on the 6 K562 datasets; cross-cell-line = same protein/arm across
`k562` vs `hepg2`.

**Note — `run_id` is not unique across cell lines** (the LLM names iterations
`<PROTEIN>_iter_NN`, so `RBFOX2_iter_01` appears for both `RBFOX2_K562` and
`RBFOX2_HepG2`). Always join analyses on `dataset` or `job_id`, never `run_id`
alone. `collect_iterations` already stamps the correct `dataset` per record, so the
aggregate is safe; this only matters for ad-hoc joins.

**Optional (cleaner separation, small code change):** add an `--out` override to
`overnight_batch.py` so this batch writes to `results/overnight/final/` with its own
aggregate files. Not required — the `final_` prefix + the arm tag already make the
batch fully filterable in place.

---

## Part 3 — Post-run analysis / plotting (not blocking the runs)

Needed to turn the batch into slides. Add under `scripts/analysis/` (new):
- `motif_difficulty.py` — compute a per-protein difficulty metric from the PWM `IC`
  lines in `data/motifs/` (total IC / peak IC / #≥1.5-bit positions), join with best
  achieved motif + composite per run. Read **both** `iterations.jsonl` **and** per-run
  `decisions.jsonl` (the latter only needed if Change 4 isn't applied).
- `plots.py` — head-to-head table (slide 7), convergence curves LLM vs Optuna
  (slide 8), LLM vs no-priors curves (slide 8), per-factor final table + per-factor
  over-iteration curves (slide 9).
- Reasoning slide needs no script: use an existing `decisions.jsonl` reasoning string
  + a dashboard Runs-page screenshot.

---

## Decisions — RESOLVED (2026-07-09)

1. **Multi-param scope:** allow **multiple simultaneous changes, no hard cap**;
   prompt guidance = "change one or several parameters; change what the evidence
   supports." (Capping would reintroduce asymmetry vs Optuna's all-7-per-trial.)
2. **Budget:** **16** iterations, both optimizers (Optuna needs ≥10 startup trials
   before TPE engages — 16 gives ~6 guided trials).
3. **Dataset set:** **8 K562** (difficulty axis) **+ 6 HepG2** (cross-cell-line
   robustness + matches the deck's "both cell lines"). HepG2 = the 6 proteins with
   HepG2 data (RBFOX2, QKI, HNRNPK, SRSF1, U2AF2, SF3B4); PUM1/PUM2 K562-only.
4. **Early stop:** **allowed for both**, identical rule — stop when best composite
   hasn't improved by ≥0.01 over 4 consecutive iterations; Optuna's counter only
   starts after its 10 startup trials. See Change 3 for details.
5. **No-priors coverage:** **6** K562 datasets spanning the difficulty gradient —
   RBFOX2, PUM2 (crisp) · HNRNPK, SRSF1 (degenerate) · U2AF2, SF3B4 (positional).
   Crisp points included so the ablation shows the prior's benefit *rising* with
   difficulty.

---

## Change summary (file-by-file)

| Change | Files touched | Blocking runs? |
|---|---|---|
| 1 Multi-param LLM | `scoring/objective.py` (prompt rule #2); tests | Yes |
| 2 No-priors mode | `scoring/objective.py`, `loop/graph.py`, `scripts/run/overnight_batch.py`; tests | Yes |
| 3 Budget 16 + early-stop | `loop/graph.py` (patience env), `loop/optuna_runner.py` (stop-callback, gated after 10) | Yes |
| 4 Aggregation fix | `scripts/run/overnight_batch.py` (`collect_iterations` recursive glob) | Yes (for clean data) |
| Arm-tagging | `scripts/run/overnight_batch.py` (add `arm`/`no_priors` to job + iteration records) | Yes (for purpose-sorting) |
| Batch manifest | `config/final_results_jobs.yaml` (new, 34 jobs) | — |
| Analysis/plots | `scripts/analysis/*` (new) | No (post-run) |

---

## Part 4 — Investigation: do the HepG2 + expanded batch need MORE repo changes?

Checked after adding HepG2 and the crisp no-priors runs. Conclusion: **no new
structural code changes** beyond Changes 1–4 + arm-tagging already listed. The HepG2 datasets are
already registered in `datasets.py` and their BAMs are present + indexed, so they run
through the identical code path. Findings:

1. **HepG2 works with zero code changes.** All 6 HepG2 datasets resolve via
   `dataset_to_config` (registry) and motif resolution uses `spec.cell_line`, so the
   scorer automatically picks the **HepG2** PWMs. Data + `.bai` verified present.
2. **Config-only fix (in the manifest, not code): raise `per_job_timeout_min` to
   300.** A 12-iter RBFOX2 LLM run already measured **183 min > the old 150-min cap**;
   at 16 iters the expensive datasets would be silently truncated (status `timeout`,
   partial iterations). Already set to 300 in the manifest above.
3. **Run logistics, not code: 34 jobs ≈ 1.5–2 days sequential.** Use `--hours 48`
   over a weekend, or split K562 / HepG2 into two launches. Interleaved ordering
   protects partial completion.
4. **`run_id` non-uniqueness across cell lines** — handled by joining on `dataset`;
   `collect_iterations` already stamps `dataset`, so the aggregate is correct. No
   change needed (documented in Storage §).
5. **Concurrency is NOT an easy win here.** VM = **32 cores / 251 GB RAM**, and each
   job already runs `threads: 32` — one job saturates the CPU. RAM is plentiful, so
   the bottleneck is cores, not memory. Running jobs concurrently would therefore
   require *also* cutting per-job threads (e.g. 2 jobs × 16 threads), and PureCLIP
   doesn't necessarily scale linearly with threads, so the net speedup is uncertain
   and could even be negative. **Recommendation: don't parallelise** — just run
   sequentially with `--hours 48` over a weekend, or split into two launches (K562,
   then HepG2). Simpler and predictable.

**Net:** the blocking work is still exactly Changes 1–4 + arm-tagging. HepG2 adds only a manifest
timeout bump (`per_job_timeout_min: 300`) and a longer wall-clock budget
(`--hours 48`, or two launches). No new structural code changes.
