#!/usr/bin/env python3
"""
Failure-tolerant overnight batch runner for agentic PureCLIP optimisation.

Runs many optimisation jobs back-to-back within a wall-clock budget (~8h) and
NEVER aborts the batch on a single job's failure. Every job — succeeded, failed,
timed out, or skipped for missing data — is recorded, so afterwards you have a
clean database to analyse and to see where the pipeline needs improving.

Outputs (under results/overnight/):
  iterations.jsonl  one row per scored iteration (metrics + params + composite)
  jobs.jsonl        one row per job (status, timing, exit code, failure hint)
  summary.csv       one row per job, best composite + status — easy to eyeball
  <job_id>/...      that job's run_config, per-iteration results, and run log

Launch (on the server, inside tmux so it survives disconnects):
    export PATH=/path/to/pureclip2dir:$HOME/.local/bin:$PATH
    PYTHONPATH=. uv run python scripts/run/overnight_batch.py --hours 8

Dry run (plan only, no compute):
    PYTHONPATH=. uv run python scripts/run/overnight_batch.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import yaml

# scripts/run/overnight_batch.py -> repo root is two levels up
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agentic_pureclip.pipeline.datasets import dataset_to_config  # noqa: E402
from agentic_pureclip.pipeline.configs import sample_bams  # noqa: E402
from agentic_pureclip.scoring.objective import composite_objective, DEFAULT_OBJECTIVE_WEIGHTS  # noqa: E402

OUT = ROOT / "results" / "overnight"
ITER_RE = re.compile(r"_iter_(\d+)")
DEADLINE_BUFFER_S = 300  # stop launching new jobs within 5 min of the deadline

_STOP = False  # set by signal handler to finish the current job then exit cleanly


def _handle_stop(signum, frame):
    global _STOP
    _STOP = True
    print(f"\n[overnight] received signal {signum}; will stop after the current job.", flush=True)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def jsonl_append(path: Path, record: dict) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def _iter_index(run_id: str) -> int | None:
    m = ITER_RE.search(run_id or "")
    return int(m.group(1)) if m else None


# ── job configuration ───────────────────────────────────────────────────────

def build_job_config(job: dict, defaults: dict, pass_idx: int):
    """Materialise a full run config for one job, layering defaults < job."""
    dataset = job["dataset"]
    job_id = job["id"] if pass_idx == 0 else f"{job['id']}_p{pass_idx}"

    cfg = dataset_to_config(dataset)
    cfg["pureclip"] = {
        **cfg["pureclip"],
        **(defaults.get("pureclip") or {}),
        **(job.get("pureclip") or {}),
        "learn_on_chr21": job.get("learn_on_chr21", defaults.get("learn_on_chr21", True)),
    }
    cfg["postprocessing"] = {
        **cfg["postprocessing"],
        **(defaults.get("postprocessing") or {}),
        **(job.get("postprocessing") or {}),
    }
    cfg["resources"]["threads"] = job.get("threads", defaults.get("threads", 8))

    weights = job.get("objective_weights") or defaults.get("objective_weights") or DEFAULT_OBJECTIVE_WEIGHTS
    cfg.setdefault("priors", {})["objective_weights"] = weights

    # Optional custom search bounds — which parameters to optimize and over what
    # range. Stored on the config so graph.py / optuna_runner.py pick them up, and
    # the starting values are clamped inside the bounds so validation passes.
    bounds = job.get("search_bounds") or defaults.get("search_bounds")
    if bounds:
        cfg["search_bounds"] = bounds
        for section, params in bounds.items():
            for key, rng in params.items():
                try:
                    low, high = int(rng[0]), int(rng[1])
                except (TypeError, ValueError, IndexError):
                    continue
                cur = cfg.get(section, {}).get(key)
                if isinstance(cur, bool):
                    cur = int(cur)
                if not isinstance(cur, (int, float)):
                    cur = (low + high) // 2
                clamped = max(low, min(high, int(cur)))
                if key in ("high_precision_mode", "use_input_covariate"):
                    cfg[section][key] = bool(clamped)
                else:
                    cfg[section][key] = clamped

    results_root = f"results/overnight/{job_id}"
    cfg["run_id"] = f"{dataset}_iter_00"
    cfg["output"] = {
        "results_root": results_root,
        "results_dir": f"{results_root}/{dataset}_iter_00",
        "use_run_id_subdir": True,
    }
    max_iter = int(job.get("max_iter", defaults.get("max_iter", 5)))
    optimizer = (job.get("optimizer") or defaults.get("optimizer") or "llm").lower()
    return job_id, cfg, max_iter, results_root, weights, optimizer


# Entry script per optimizer; both read CONFIG_PATH + MAX_ITER and write the
# same per-iteration score reports.
OPTIMIZER_SCRIPTS = {"llm": "agentic_pureclip.loop.graph", "optuna": "agentic_pureclip.loop.optuna_runner"}


def data_present(cfg: dict):
    for bam in sample_bams(cfg):
        if not (ROOT / bam).exists():
            return False, f"missing BAM: {bam}"
    genome = cfg["reference"]["genome_fasta"]
    if not (ROOT / genome).exists():
        return False, f"missing genome: {genome}"
    return True, ""


# ── failure analysis ────────────────────────────────────────────────────────

FAILURE_SIGNATURES = [
    (r"out of memory|memoryerror|\bkilled\b|oom", "out_of_memory"),
    (r"pureclip", "pureclip_error"),
    (r"bedtools", "bedtools_error"),
    (r"samtools", "samtools_error"),
    (r"deepseek|openai|api key|authentication|rate.?limit|connecttimeout|read timed out", "llm_api_error"),
    (r"configvalidationerror", "config_validation"),
    (r"jsondecodeerror|not valid json", "llm_bad_json"),
    (r"filenotfounderror|no such file|does not exist", "missing_file"),
]


def classify_failure(log_text: str) -> str:
    low = log_text.lower()
    for pattern, label in FAILURE_SIGNATURES:
        if re.search(pattern, low):
            return label
    return "unknown"


def _log_tail(path: Path, n_lines: int = 40) -> str:
    try:
        return "\n".join(path.read_text(errors="ignore").splitlines()[-n_lines:])
    except Exception:
        return ""


# ── result collection ───────────────────────────────────────────────────────

def arm_of(optimizer: str, no_priors: bool) -> str:
    """Label a job's experimental arm so analyses slice cleanly.

    `optimizer` alone can't tell the priors-on LLM from the no-priors LLM; the arm
    tag distinguishes head-to-head (llm/optuna) from the ablation (llm_noprior).
    """
    if optimizer == "optuna":
        return "optuna"
    return "llm_noprior" if no_priors else "llm"


def collect_iterations(results_root: str, job_id: str, dataset: str, weights: dict,
                       optimizer: str = "llm", arm: str = "llm", no_priors: bool = False) -> list[dict]:
    root = ROOT / results_root
    if not root.exists():
        return []
    # Recursive glob (Change 4): the LLM re-nests reports under a timestamped session
    # subdir (results_root/<dataset>_<ts>/<iter>/score_report.json, two levels down)
    # while Optuna writes one level down. A one-level glob silently dropped every LLM
    # iteration; "**" catches both. De-dup by run_id, keeping the newest report, in
    # case a run_id ever recurs across re-nested subdirs.
    by_run: dict[str, dict] = {}
    for report_path in root.glob("**/score_report.json"):
        try:
            d = json.loads(report_path.read_text())
        except Exception:
            continue
        comp = composite_objective(d, weights)
        run_id = d.get("run_id")
        mtime = report_path.stat().st_mtime
        rec = {
            "type": "iteration",
            "job_id": job_id,
            "dataset": dataset,
            "optimizer": optimizer,
            "arm": arm,
            "no_priors": no_priors,
            "run_id": run_id,
            "iteration": _iter_index(run_id or ""),
            "n_binding_sites": d.get("n_binding_sites"),
            "replicate_agreement": d.get("replicate_agreement"),
            "reproducibility_score": d.get("reproducibility_score"),
            "reproducibility_enrichment": d.get("reproducibility_enrichment"),
            "motif_hit_rate": d.get("motif_hit_rate"),
            "motif_enrichment": d.get("motif_enrichment"),
            "benchmark_region_recall": d.get("benchmark_region_recall"),
            "benchmark_region_overlap": d.get("benchmark_region_overlap"),
            "composite": round(comp, 4) if comp is not None else None,
            "params": d.get("params"),
            "mtime": mtime,
        }
        key = run_id or str(report_path)
        if key not in by_run or mtime > by_run[key]["mtime"]:
            by_run[key] = rec
    records = list(by_run.values())
    records.sort(key=lambda r: (r["iteration"] if r["iteration"] is not None else 0))
    return records


# ── one job ─────────────────────────────────────────────────────────────────

def run_one_job(job, defaults, pass_idx, job_timeout_s, extra_path):
    """Run a single optimisation job in an isolated subprocess. Never raises."""
    started = time.time()
    job_id, cfg, max_iter, results_root, weights, optimizer = build_job_config(job, defaults, pass_idx)
    script = OPTIMIZER_SCRIPTS.get(optimizer, OPTIMIZER_SCRIPTS["llm"])
    no_priors = bool(job.get("no_priors"))
    arm = arm_of(optimizer, no_priors)
    record = {
        "type": "job",
        "job_id": job_id,
        "dataset": job["dataset"],
        "optimizer": optimizer,
        "arm": arm,
        "no_priors": no_priors,
        "pass": pass_idx,
        "max_iter": max_iter,
        "weights": weights,
        "started": utcnow(),
    }

    ok, reason = data_present(cfg)
    if not ok:
        record.update(status="skipped", failure_hint="missing_data", error=reason,
                      ended=utcnow(), duration_s=0, iterations_scored=0, best_composite=None)
        print(f"[overnight] SKIP {job_id}: {reason}", flush=True)
        return record, []

    job_dir = ROOT / results_root
    job_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = job_dir / "run_config.yaml"
    log_path = job_dir / "run.log"
    with open(cfg_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(cfg, handle, sort_keys=False)

    env = os.environ.copy()
    env["CONFIG_PATH"] = str(cfg_path.relative_to(ROOT))
    env["MAX_ITER"] = str(max_iter)
    env["PYTHONPATH"] = "."
    if job.get("no_priors"):
        # Change 2: no-priors ablation — the LLM prompt withholds biological priors.
        env["LLM_NO_PRIORS"] = "1"
    if extra_path:
        env["PATH"] = f"{extra_path}:{env.get('PATH', '')}"

    print(f"[overnight] START {job_id} ({job['dataset']}, optimizer={optimizer}, "
          f"max_iter={max_iter}, timeout={int(job_timeout_s)}s)", flush=True)

    status, exit_code = "completed", None
    try:
        with open(log_path, "w", encoding="utf-8") as logf:
            proc = subprocess.Popen(
                [sys.executable, "-m", script],
                cwd=str(ROOT), env=env, stdout=logf, stderr=subprocess.STDOUT,
                start_new_session=True,  # own process group so we can kill the whole tree
            )
            try:
                proc.wait(timeout=job_timeout_s)
            except subprocess.TimeoutExpired:
                status = "timeout"
                _terminate_tree(proc)
            exit_code = proc.returncode
        if status != "timeout" and exit_code not in (0, None):
            status = "failed"
    except Exception:
        status = "failed"
        with open(log_path, "a", encoding="utf-8") as logf:
            logf.write("\n[overnight orchestrator exception]\n" + traceback.format_exc())

    # Always try to collect whatever iterations were scored, even on failure.
    try:
        iterations = collect_iterations(results_root, job_id, job["dataset"], weights,
                                         optimizer, arm=arm, no_priors=no_priors)
    except Exception:
        iterations = []

    composites = [it["composite"] for it in iterations if it["composite"] is not None]
    best = max(composites) if composites else None
    failure_hint = None
    error = None
    if status in ("failed", "timeout"):
        tail = _log_tail(log_path)
        failure_hint = "timeout" if status == "timeout" else classify_failure(tail)
        error = tail

    record.update(
        status=status,
        exit_code=exit_code,
        ended=utcnow(),
        duration_s=round(time.time() - started, 1),
        iterations_scored=len(iterations),
        best_composite=best,
        failure_hint=failure_hint,
        error=error,
        results_dir=results_root,
        log_file=str(log_path.relative_to(ROOT)),
    )
    print(f"[overnight] END   {job_id}: status={status} iters={len(iterations)} "
          f"best_composite={best} ({record['duration_s']}s)", flush=True)
    return record, iterations


def _terminate_tree(proc):
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass


# ── driver ──────────────────────────────────────────────────────────────────

def write_summary(jobs_records: list[dict], path: Path) -> None:
    cols = ["job_id", "dataset", "optimizer", "arm", "pass", "status", "failure_hint", "best_composite",
            "iterations_scored", "max_iter", "exit_code", "duration_s"]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for rec in jobs_records:
            writer.writerow(rec)


def main():
    parser = argparse.ArgumentParser(description="Failure-tolerant overnight batch runner")
    parser.add_argument("--manifest", default="config/overnight_jobs.yaml")
    parser.add_argument("--hours", type=float, default=8.0, help="wall-clock budget")
    parser.add_argument("--no-repeat", action="store_true",
                        help="run the job list once instead of cycling until the deadline")
    parser.add_argument("--pureclip-dir", default=None,
                        help="directory to prepend to PATH so 'pureclip2' resolves")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    args = parser.parse_args()

    manifest = yaml.safe_load((ROOT / args.manifest).read_text())
    defaults = manifest.get("defaults", {})
    jobs = manifest.get("jobs", [])
    per_job_cap = float(defaults.get("per_job_timeout_min", 150)) * 60

    OUT.mkdir(parents=True, exist_ok=True)
    iters_path = OUT / "iterations.jsonl"
    jobs_path = OUT / "jobs.jsonl"
    summary_path = OUT / "summary.csv"

    if args.dry_run:
        print(f"Plan: {len(jobs)} jobs, budget {args.hours}h, repeat={not args.no_repeat}\n")
        for job in jobs:
            _id, cfg, max_iter, root, weights, optimizer = build_job_config(job, defaults, 0)
            ok, reason = data_present(cfg)
            print(f"  {_id:24s} {job['dataset']:14s} optimizer={optimizer:6s} max_iter={max_iter} "
                  f"data={'OK' if ok else 'MISSING (' + reason + ')'}")
        return

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    start = time.time()
    deadline = start + args.hours * 3600
    jsonl_append(jobs_path, {
        "type": "batch_start", "started": utcnow(), "hours": args.hours,
        "n_jobs": len(jobs), "repeat": not args.no_repeat, "manifest": args.manifest,
    })

    all_job_records: list[dict] = []
    pass_idx = 0
    while not _STOP:
        for job in jobs:
            if _STOP or time.time() >= deadline - DEADLINE_BUFFER_S:
                break
            remaining = deadline - time.time()
            job_timeout = min(per_job_cap, remaining - 10)
            if job_timeout < 60:
                break
            try:
                job_rec, iter_recs = run_one_job(job, defaults, pass_idx, job_timeout, args.pureclip_dir)
            except Exception:
                # Last-resort guard: the orchestrator must never die on a job.
                job_rec = {
                    "type": "job", "job_id": job.get("id"), "dataset": job.get("dataset"),
                    "pass": pass_idx, "status": "failed", "failure_hint": "orchestrator_exception",
                    "error": traceback.format_exc(), "ended": utcnow(),
                }
                iter_recs = []
            jsonl_append(jobs_path, job_rec)
            for rec in iter_recs:
                jsonl_append(iters_path, rec)
            all_job_records.append(job_rec)
            write_summary(all_job_records, summary_path)

        pass_idx += 1
        if args.no_repeat or _STOP or time.time() >= deadline - DEADLINE_BUFFER_S:
            break

    elapsed_h = (time.time() - start) / 3600
    completed = sum(1 for r in all_job_records if r.get("status") == "completed")
    failed = sum(1 for r in all_job_records if r.get("status") in ("failed", "timeout"))
    skipped = sum(1 for r in all_job_records if r.get("status") == "skipped")
    jsonl_append(jobs_path, {
        "type": "batch_end", "ended": utcnow(), "elapsed_hours": round(elapsed_h, 2),
        "jobs_run": len(all_job_records), "completed": completed,
        "failed": failed, "skipped": skipped, "passes": pass_idx,
    })
    write_summary(all_job_records, summary_path)
    print(f"\n[overnight] DONE in {elapsed_h:.2f}h — {len(all_job_records)} jobs "
          f"({completed} ok, {failed} failed/timeout, {skipped} skipped). "
          f"DB: {iters_path}, {jobs_path}, {summary_path}", flush=True)


if __name__ == "__main__":
    main()
