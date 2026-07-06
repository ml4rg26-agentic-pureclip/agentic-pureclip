#!/usr/bin/env bash
# Start the monitor/dashboard UI server (serves ui/build/client + /api/*).
# Run inside tmux session "mon" so it persists:  tmux new-session -d -s mon 'bash scripts/start_ui.sh'
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="/vol/storage1/johannes/projects:$HOME/.local/bin:$PATH"
export PYTHONPATH=.
PORT="${1:-8888}"
mkdir -p results/logs
exec uv run python scripts/monitor.py --port "$PORT" 2>&1 | tee results/logs/monitor.log
