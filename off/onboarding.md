# Runner handover quick reference

This is the operator runbook for the Agentic PureCLIP runner. It assumes you
know Git, SSH, rsync, Docker Compose, and the command line. For background, use
the linked documentation at the end.

## Connect and find the project

```bash
ssh -p 30121 -i ~/.ssh/id_ed25519 ubuntu@194.94.4.28
cd /vol/storage1/johannes/projects/agentic-pureclip
```

The runner is `agenticpureclipvm-751a3`. The project directory is a deployed
copy, not a Git checkout. Its `.env` and `.venv` are already present; do not
overwrite them.

Inspect the input data:

```bash
cd /vol/storage1/johannes/projects/agentic-pureclip/data
pwd
du -sh .
find . -maxdepth 1 -mindepth 1 -type d -printf '%f\n' | sort
cd ..
```

The GRCh38 FASTA, BAM inputs, indexes, motifs, and dataset directories are under
`data/`. The runner currently has no separate `ref/` directory.

## Check the runner

Run these before a deployment or batch launch:

```bash
cd /vol/storage1/johannes/projects/agentic-pureclip
df -h / /vol/storage1
du -sh data results
docker compose ps
tmux ls
ps -eo pid,etime,cmd | grep -E \
  'overnight_batch|agentic_pureclip.loop.(graph|optuna_runner)|pureclip2' | grep -v grep
```

Do not deploy while an optimization is running. Keep all large data and results
under `/vol/storage1`; the root disk is small and nearly full.

## Restart the dashboard containers

Restart without rebuilding images:

```bash
ssh -p 30121 -i ~/.ssh/id_ed25519 ubuntu@194.94.4.28
cd /vol/storage1/johannes/projects/agentic-pureclip
docker compose restart
docker compose ps
```

The expected services are `api`, `ui`, and `proxy`. The API and UI should report
healthy. The proxy publishes port 8080 on the runner.

Open the dashboard locally:

```bash
ssh -N -L 8080:localhost:8080 -p 30121 \
  -i ~/.ssh/id_ed25519 ubuntu@194.94.4.28
```

Then visit `http://localhost:8080`.

## Deploy the latest committed changes

Start from the local repository. Commit the intended changes and update the
local `develop` branch first:

```bash
git status --short
git pull --ff-only origin develop
```

Review the exact content delta without changing the runner:

```bash
git ls-files -z | rsync -rcni --from0 --files-from=- \
  --out-format='%i %n' \
  -e "ssh -p 30121 -i $HOME/.ssh/id_ed25519" ./ \
  ubuntu@194.94.4.28:/vol/storage1/johannes/projects/agentic-pureclip/
```

Deploy only Git-tracked files:

```bash
git ls-files -z | rsync -avrc --from0 --files-from=- \
  -e "ssh -p 30121 -i $HOME/.ssh/id_ed25519" ./ \
  ubuntu@194.94.4.28:/vol/storage1/johannes/projects/agentic-pureclip/
```

This leaves `.env`, `.venv`, `data/`, `results/`, logs, and other runner-only
state untouched. The `-c` option compares file contents, matching the dry run
and ignoring timestamp-only differences. Do not add `--delete` and do not
replace this with an unfiltered sync of the local working directory.

Update the existing environment, test, and rebuild the dashboard:

```bash
ssh -p 30121 -i ~/.ssh/id_ed25519 ubuntu@194.94.4.28
cd /vol/storage1/johannes/projects/agentic-pureclip
~/.local/bin/uv sync --frozen
~/.local/bin/uv run pytest -q
docker compose up -d --build
docker compose ps
```

The dashboard is monitor-only. Deploying or restarting it does not start an
optimization job.

## Run and monitor jobs

Use the [batch-job runbook](../docs/deploy-a-new-batch-job.md) for all run
execution. It distinguishes between a single dataset/optimizer command generated
by the dashboard UI and a multi-job YAML manifest executed by the Python batch
runner. It also contains validation, tmux, log, result, and monitoring commands.

Always launch from the project root. Do not start a second run while another is
active.

## Existing detailed documentation

- [Developer onboarding](../docs/developer-onboarding.md) — installation,
  dependencies, execution, testing, dashboard internals, and VM storage.
- [Dashboard guide](../dashboard/README.md) — services, ports, API endpoints,
  and monitor-only behavior.
- [Architecture overview](../docs/architecture-overview.md) — package and data
  flow.
- [Configuration guide](../config/README.md) — run and dataset configuration.
- [Report build guide](../docs/report/ONBOARDING.md) — build the thesis PDF.
