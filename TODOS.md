# TODOs & session handoff

Snapshot of where the project is and what to do next, so a new session can pick
up cold. (Biology/architecture context: [CLAUDE.md](CLAUDE.md).)

_Last updated: 2026-06-29._

---

## Where we are

- **Branch** `data-integration-rbp-motifs`, open as draft **PR #4**
  (`ml4rg26-agentic-pureclip/agentic-pureclip` → `develop`). All work is committed/pushed.
- **Two optimizers** wired and interchangeable: LLM agent (`agent/graph.py`) and
  Optuna/TPE (`agent/optuna_runner.py`), sharing `evaluate_config` + `composite_objective`.
- **Objective hardened**: chance-corrected reproducibility, motif log-odds +
  enrichment, chr21-restricted ENCODE recall, and a **collapse guard**
  (`× min(1, n_sites/10)`) that stops 1-site degenerate wins.
- **React UI** (`ui/`) served by `monitor.py`: Dashboard, Runs (decision trail),
  Plan run (schedule from the browser → writes a manifest → runs the CLI runner),
  Variables. Runs can also be launched/queued from the CLI.
- **Data**: two completed 12h batches in `results/overnight/` (all 5 datasets ×
  LLM + Optuna, ~250+ scored iterations) + per-run `decisions.jsonl`.

### Currently running (check before launching anything!)
- **Full-genome validation of RBFOX2_K562** in tmux `fullgenome`
  (`config/fullgenome_rbfox2_k562.yaml`): the best chr21 config
  (`bw=100 dm=14 ic=1 xl=2 fw=9`) run on the **whole genome**, 1 pass, ~hours.
  Job id `rbfox2_k562_fullgenome`. Monitor in tmux `mon`.
- Resume status: `ssh bio 'tail -f .../results/logs/fullgenome.log'` or the dashboard.

## Key findings so far

- **Collapse guard works.** Before it, Optuna gamed QKI to **1 site for composite 0.78**;
  after, the same dataset gives a real ~0.33 (7+ sites). Every leading result now
  has a healthy site count.
- **LLM vs Optuna (honest, guarded):** roughly even. LLM wins PUM1_K562
  (0.46, 18 sites); Optuna edges QKI_HepG2 (0.40, 127 sites) and RBFOX2_K562
  (0.22 vs 0.16) with 15 trials. The LLM resists collapse via its prior; Optuna
  needs the guard. At 12 trials Optuna was under-sold — give it budget.
- **RBFOX2_K562 is the hard case** and noisy across runs (~0.16–0.24);
  reproducibility (~0.11–0.14) is the bottleneck. This is the main science target.
- **QKI on chr21 genuinely has very few sites** (7–14) — a data property, not a bug.

## Next steps (roughly prioritized)

1. **Finish + read the full-genome RBFOX2_K562 result.** Compare
   `reproducibility_score` and `motif_hit_rate` (scale-invariant) vs chr21; check
   genome-wide recall (now over all 440 reference regions) and absolute n_sites.
   Question: is the low reproducibility a chr21 sampling artifact or genuinely hard?
2. **If it holds up, run the same full-genome validation for RBFOX2_HepG2**
   (best performer, config `bw=23 hp=1 xl=2 fw=15`). Copy
   `config/fullgenome_rbfox2_k562.yaml`, swap dataset + pinned params.
3. **Attack RBFOX2_K562 reproducibility** specifically: try an IDR-style
   reproducibility metric, push bandwidth even wider, or reweight the objective.
4. **Tighter LLM-vs-Optuna conclusion**: bump Optuna to ~25 trials on the cheap
   datasets (PUM1, QKI) where iterations are fast.
5. **Objective refinements** (research): dinucleotide-shuffled motif background,
   central/positional motif enrichment, per-dataset `min_sites`.
6. **Housekeeping**: mark PR #4 ready for review when satisfied; consider trimming
   `results_mock/` and stale `config/ui_runs/` manifests.

## How to resume

```bash
# tunnel + dashboard
ssh -f -N -L 8888:localhost:8888 bio      # http://localhost:8888  (kill+redo if stale → 000)

# on the VM
ssh bio
cd /vol/storage1/johannes/projects/agentic-pureclip
tmux ls                                    # mon (dashboard), fullgenome (run)
export PATH=/vol/storage1/johannes/projects:$HOME/.local/bin:$PATH   # so pureclip2 resolves

# analyze the database (local or VM)
python -c "import pandas as pd; print(pd.read_json('results/overnight/iterations.jsonl', lines=True).groupby('dataset').composite.max())"
```

## Gotchas

- `pureclip2` is **not on the default PATH** — prepend `/vol/storage1/johannes/projects`
  (or pass `--pureclip-dir`).
- Launch long jobs in **tmux**, never a bare `&` over SSH (hangs the channel);
  the dashboard tunnel dies silently — re-establish if the page is stale.
- Stored composites in old `iterations.jsonl` rows reflect the objective **at the
  time they ran** (pre-guard run-1 QKI shows 0.77); the dashboard recomputes live,
  so trust the dashboard / re-score, not raw old values.
- Don't start a new heavy run while one is active (CPU oversubscription) — check
  `pgrep -f "overnight_batch|optuna_runner|agent/graph.py|pureclip2"` first.
- UI is a build artifact: after changing `ui/`, `npm run build` then rsync
  `ui/build/client/` to the VM and restart the `mon` tmux session.
