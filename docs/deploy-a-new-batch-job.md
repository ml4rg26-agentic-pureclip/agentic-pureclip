# Deploy a new batch job on the VM

Short runbook for launching an `overnight_batch.py` job on the de.NBI GPU VM.

## Connect

The de.NBI SSH gateway (`194.94.4.28:30121`) only admits registered project
users, so we reach the VM over **Tailscale** instead (bypasses the gateway).

- VM is on the tailnet as `agenticpureclipvm-751a3` (`tailscale ip -4` → `100.87.34.54`).
- Local Mac: `sudo brew services start tailscale` then `tailscale up` (same account).
- `ssh -i ~/.ssh/id_ed25519 ubuntu@100.87.34.54`

(One-time: the client's public key must be in the VM's `~/.ssh/authorized_keys`.)

## Repo, data, results

- Repo: `/vol/storage1/johannes/projects/agentic-pureclip` (NOT a git checkout —
  sync with rsync). Everything lives on `/vol/storage1` (~500G free); the root
  disk is nearly full, keep off it.
- `data/` holds all ENCODE datasets (BAM + `.bai` + benchmark regions).
- `.env` (VM-only, never synced) holds `DEEPSEEK_API_KEY`.
- `.venv` present; run via `uv`.

## 1. Sync code from your Mac

From the local repo root (excludes keep data/results/.env/.venv on the VM intact):

```bash
rsync -av --exclude .git --exclude .venv --exclude data --exclude results \
  --exclude .env --exclude '__pycache__' --exclude '*.pyc' \
  -e "ssh -i ~/.ssh/id_ed25519" ./ ubuntu@100.87.34.54:/vol/storage1/johannes/projects/agentic-pureclip/
```

## 2. Archive previous results (optional, before a fresh batch)

`mv` is instant (same filesystem). The batch writes to `results/overnight/`:

```bash
cd /vol/storage1/johannes/projects/agentic-pureclip
ts=pre_final_$(date +%Y%m%d); mkdir -p results/archive/$ts
mv results/overnight results/batch results/runs results/archive/$ts/ 2>/dev/null
```

## 3. Pre-launch checks

```bash
cd /vol/storage1/johannes/projects/agentic-pureclip
uv run python -m pytest tests/ -q
PYTHONPATH=. uv run python scripts/run/overnight_batch.py \
  --manifest config/<manifest>.yaml --dry-run     # every job should show data=OK
```

## 4. Launch (in tmux so it survives disconnects)

```bash
tmux new -s batch
export PATH=/vol/storage1/johannes/projects:$HOME/.local/bin:$PATH
PYTHONPATH=. uv run python scripts/run/overnight_batch.py \
  --manifest config/<manifest>.yaml --hours <N> --no-repeat \
  --pureclip-dir /vol/storage1/johannes/projects
# detach: Ctrl-b d   |   reattach: tmux attach -t batch
```

Manifests: `config/smoke_final_jobs.yaml` (2 datasets, ~4h) validates the pipeline;
`config/final_results_jobs.yaml` is the full 34-job batch (~1.5–2 days, use `--hours 48`).

## 5. Monitor

- `results/overnight/summary.csv` — one row per job (status, best_composite).
- `results/overnight/jobs.jsonl`, `iterations.jsonl` — aggregate DB (tagged with
  `arm` = llm / optuna / llm_noprior).
- Per job: `results/overnight/<job_id>/run.log`, `decisions.jsonl`.
- Dashboard runs read-only via Docker Compose (see memory: bio dashboard deployment).
