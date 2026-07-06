#!/usr/bin/env python3
"""
Batch runner: executes multiple agent runs defined in config/batch_runs.yaml.

Usage:
    uv run python scripts/batch_runner.py                    # run all
    uv run python scripts/batch_runner.py --ids quick_*      # run matching IDs
    uv run python scripts/batch_runner.py --dry-run          # show what would run
    uv run python scripts/batch_runner.py --parallel 2       # run 2 at a time

Each run:
  1. Creates a dedicated config YAML for the dataset + settings
  2. Runs the agent with MAX_ITER
  3. Saves results to results/batch/<run_id>/
  4. Appends a summary line to results/batch/_summary.tsv
"""

import argparse
import fnmatch
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import yaml

from pipeline.datasets import dataset_to_config


def load_manifest(path: str = "config/batch_runs.yaml") -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f)
    return data["runs"]


DEFAULT_MANIFEST = "config/batch_runs.yaml"


def write_run_config(run: dict, out_path: str) -> None:
    """Generate a run_config.yaml for a specific dataset + settings."""
    dataset = run["dataset"]
    cfg = dataset_to_config(dataset, results_root="results/batch")
    cfg["run_id"] = run["id"]
    cfg["output"]["results_dir"] = f"results/batch/{run['id']}/iter_00"
    cfg["output"]["results_root"] = "results/batch"
    cfg["output"]["use_run_id_subdir"] = True
    cfg["resources"]["threads"] = run.get("threads", 32)

    if run.get("chr21_only"):
        cfg["pureclip"]["learn_on_chr21"] = True

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        yaml.safe_dump(cfg, f)


def execute_run(run: dict) -> dict:
    """Run a single agent optimization. Returns summary dict."""
    run_id = run["id"]
    max_iter = run.get("max_iter", 5)
    config_path = f"config/batch/{run_id}.yaml"

    write_run_config(run, config_path)

    t0 = time.time()
    env = os.environ.copy()
    env["CONFIG_PATH"] = config_path
    env["MAX_ITER"] = str(max_iter)
    env["PYTHONPATH"] = "."

    result = subprocess.run(
        [sys.executable, "-m", "agent.graph"],
        env=env,
        capture_output=True,
        text=True,
    )

    elapsed = time.time() - t0

    # Parse best score from output
    best_score = None
    termination = "unknown"
    for line in result.stdout.split("\n") + result.stderr.split("\n"):
        if "Best replicate_agreement" in line:
            try:
                best_score = float(line.split("=")[-1].strip())
            except ValueError:
                pass
        if "Hard stop" in line:
            termination = "hard_stop"
        elif "Converged" in line:
            termination = "converged"
        elif "ERROR" in line or "Error" in line:
            termination = "error"

    return {
        "run_id": run_id,
        "dataset": run["dataset"],
        "max_iter": max_iter,
        "termination": termination,
        "best_score": best_score,
        "elapsed_s": round(elapsed, 0),
        "exit_code": result.returncode,
        "stderr_tail": "\n".join(result.stderr.split("\n")[-5:]),
    }


def main():
    parser = argparse.ArgumentParser(description="Batch runner for agentic PureCLIP")
    parser.add_argument("--ids", nargs="*", help="Run only matching IDs (glob patterns)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run")
    parser.add_argument("--parallel", type=int, default=1, help="Number of parallel runs")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, help="Path to run manifest YAML")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    os.makedirs("config/batch", exist_ok=True)

    # Filter by --ids
    if args.ids:
        runs = [
            r for r in manifest
            if any(fnmatch.fnmatch(r["id"], pat) for pat in args.ids)
        ]
    else:
        runs = manifest

    if not runs:
        print("No runs matched.")
        return

    print("=" * 70)
    print(f"BATCH RUNNER — {len(runs)} run(s)")
    print("=" * 70)
    for r in runs:
        ch = "chr21" if r.get("chr21_only") else "full"
        print(f"  {r['id']:30s} {r['dataset']:20s} {ch:6s} x{r['max_iter']} iter  {r.get('threads', 32)}t")
    print()

    if args.dry_run:
        print("[DRY RUN] No runs executed.")
        return

    # Summary file
    summary_path = "results/batch/_summary.tsv"
    os.makedirs("results/batch", exist_ok=True)
    if not os.path.exists(summary_path):
        with open(summary_path, "w") as f:
            f.write("timestamp\trun_id\tdataset\tmax_iter\ttermination\tbest_score\telapsed_s\texit_code\n")

    results = []

    if args.parallel > 1:
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            futures = {pool.submit(execute_run, r): r for r in runs}
            for future in as_completed(futures):
                r = futures[future]
                res = future.result()
                results.append(res)
                _print_result(res)
                _append_summary(summary_path, res)
    else:
        for r in runs:
            print(f"\n{'─' * 60}")
            print(f"  Running: {r['id']}  ({r['dataset']}, {r['max_iter']} iter)")
            print(f"{'─' * 60}")
            res = execute_run(r)
            results.append(res)
            _print_result(res)
            _append_summary(summary_path, res)

    print(f"\n{'=' * 70}")
    print("ALL RUNS COMPLETE")
    print(f"Summary: {summary_path}")
    _print_summary_table(results)


def _print_result(res: dict) -> None:
    score = f"{res['best_score']:.4f}" if res['best_score'] else "N/A"
    mins = res["elapsed_s"] / 60
    status = "✅" if res["exit_code"] == 0 else "❌"
    print(f"  {status} {res['run_id']:30s} score={score:8s}  {mins:.0f}min  {res['termination']}")
    if res["exit_code"] != 0:
        print(f"     stderr: {res['stderr_tail'][:200]}")


def _append_summary(path: str, res: dict) -> None:
    with open(path, "a") as f:
        f.write(
            f"{datetime.now().isoformat()}\t{res['run_id']}\t{res['dataset']}\t"
            f"{res['max_iter']}\t{res['termination']}\t{res['best_score']}\t"
            f"{res['elapsed_s']}\t{res['exit_code']}\n"
        )


def _print_summary_table(results: list[dict]) -> None:
    print(f"\n{'Run ID':<30s} {'Dataset':<20s} {'Score':>8s} {'Time':>6s} {'Status'}")
    print("-" * 75)
    for r in sorted(results, key=lambda x: x["run_id"]):
        score = f"{r['best_score']:.4f}" if r['best_score'] else "N/A"
        mins = f"{r['elapsed_s']/60:.0f}m"
        status = "OK" if r["exit_code"] == 0 else "ERR"
        print(f"{r['run_id']:<30s} {r['dataset']:<20s} {score:>8s} {mins:>6s} {status}")


if __name__ == "__main__":
    main()
