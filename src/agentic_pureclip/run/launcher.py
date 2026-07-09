"""Write a run manifest and launch ``overnight_batch.py`` on it.

Shared by the dashboard API and the ``agentic-pureclip-run`` CLI so a run started
from either path is launched exactly the same way. All paths are relative to the
current working directory, which must be the repo root (that is where ``results/``,
``config/`` and ``scripts/`` live).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

UI_RUNS_DIR = Path("config/ui_runs")
LOGS_DIR = Path("results/logs")
OVERNIGHT = "scripts/run/overnight_batch.py"

# Where the pureclip2 binary lives (prepended to PATH for the launched run).
DEFAULT_PURECLIP_DIR = os.environ.get("MONITOR_PURECLIP_DIR", "/vol/storage1/johannes/projects")


def write_manifest(job_id: str, manifest: dict) -> Path:
    """Persist ``manifest`` to ``config/ui_runs/<job_id>.yaml`` and return the path."""
    UI_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = UI_RUNS_DIR / f"{job_id}.yaml"
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(manifest, fh, sort_keys=False)
    return path


def overnight_command(
    manifest_path: str | Path, hours: float, pureclip_dir: str = DEFAULT_PURECLIP_DIR,
    python: str | None = None,
) -> list[str]:
    """The argv that runs a single-shot overnight batch on ``manifest_path``."""
    return [
        python or sys.executable, OVERNIGHT,
        "--manifest", str(manifest_path),
        "--no-repeat", "--hours", str(hours),
        "--pureclip-dir", pureclip_dir,
    ]


def launch_detached(
    job_id: str, manifest_path: str | Path, hours: float,
    pureclip_dir: str = DEFAULT_PURECLIP_DIR, log_name: str = "ui_scheduled.log",
) -> Path:
    """Spawn ``overnight_batch.py`` detached; return the log file it writes to.

    Runs in a new session so it survives the parent (API worker or CLI shell)
    exiting, with ``PYTHONPATH=.`` and the pureclip dir on ``PATH`` — matching how
    the pipeline is invoked from the repo root.
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    env["PATH"] = f"{pureclip_dir}:{env.get('PATH', '')}"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / log_name
    log_handle = open(log_path, "a", encoding="utf-8")
    log_handle.write(f"\n=== {time.strftime('%Y%m%d_%H%M%S')} launch {job_id} ===\n")
    log_handle.flush()
    subprocess.Popen(
        overnight_command(manifest_path, hours, pureclip_dir),
        cwd=str(Path.cwd()), env=env, stdout=log_handle, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return log_path
