"""
Data collectors for the agentic PureCLIP monitoring dashboard.

These functions read the live pipeline state off the filesystem and running
processes — the active run's dataset, current iteration and pipeline stage, the
tunable parameters in flight, the live optimisation metrics (replicate
agreement, motif hit-rate, motif enrichment, composite objective) and the
agent's latest reasoning, plus the full per-dataset iteration trajectory.

They are pure Python (no web framework); `dashboard.api.main` exposes them over
HTTP as the FastAPI `/api/*` endpoints. All paths are relative to the repo root,
so the API must be launched with the repo root as the working directory.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

from agentic_pureclip.pipeline.configs import DEFAULT_SEARCH_BOUNDS
from agentic_pureclip.pipeline.datasets import list_datasets

# Keep the dashboard's composite in lock-step with the agent's objective.
try:
    from agentic_pureclip.scoring.objective import DEFAULT_OBJECTIVE_WEIGHTS, composite_objective
except Exception:  # pragma: no cover - fallback if agent package not importable
    DEFAULT_OBJECTIVE_WEIGHTS = {"reproducibility": 0.5, "motif": 0.25, "recall": 0.25}

    def composite_objective(report: dict, weights=None) -> float:
        weights = weights or {"reproducibility": 0.5, "motif": 0.25, "recall": 0.25}
        terms = {}
        rep = report.get("reproducibility_score")
        if rep is None:
            rep = report.get("replicate_agreement")
        if rep is not None:
            terms["reproducibility"] = float(rep)
        if report.get("motif_hit_rate") is not None:
            terms["motif"] = float(report["motif_hit_rate"])
        if report.get("benchmark_region_recall") is not None:
            terms["recall"] = float(report["benchmark_region_recall"])
        total = sum(weights.get(k, 0.0) for k in terms)
        if not terms or total <= 0:
            return 0.0
        return float(sum(weights.get(k, 0.0) * v for k, v in terms.items()) / total)


RESULT_ROOTS = [Path("results/runs"), Path("results/batch")]
LOGS_DIR = Path("results/logs")
RUN_CONFIG = Path("config/run_config.yaml")
UI_RUNS_DIR = Path("config/ui_runs")

# Where the pureclip2 binary lives (prepended to PATH for scheduled runs).
PURECLIP_DIR = os.environ.get("MONITOR_PURECLIP_DIR", "/vol/storage1/johannes/projects")
HEAVY_PROC_KEYS = ("agentic_pureclip.loop.graph", "agentic_pureclip.loop.optuna_runner", "pureclip2", "overnight_batch.py")

# Ordered pipeline stages of a single optimisation iteration.
STAGES = ["PureCLIP", "Postprocess", "Score", "LLM decide"]

ITER_RE = re.compile(r"_iter_(\d+)")


# ── data collection ─────────────────────────────────────────────────────────

def _read_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}


def get_processes() -> list[dict]:
    """Relevant pipeline/agent processes with wall-clock elapsed time."""
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid,pcpu,pmem,etime,args", "--no-headers"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    keys = ("pureclip2", "snakemake", "batch_runner", "overnight_batch.py",
            "agentic_pureclip.loop.graph", "agentic_pureclip.loop.graph", "agentic_pureclip.loop.optuna_runner",
            "agentic_pureclip.scoring.run_scorers", "agentic_pureclip.postprocess.postprocess")
    procs = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        pid, pcpu, pmem, etime, args = parts
        if "dashboard.api" in args or " grep " in args:
            continue
        if not any(k in args for k in keys):
            continue
        if "pureclip2" in args:
            label = "PureCLIP"
            m = re.search(r"ip_(rep\d+)", args)
            if m:
                label += f" · {m.group(1)}"
            elif "/PureCLIP." in args or "merged" in args:
                label += " · merged"
        elif "snakemake" in args:
            label = "snakemake"
        elif "agentic_pureclip.scoring.run_scorers" in args:
            label = "scorer"
        elif "agentic_pureclip.postprocess.postprocess" in args:
            label = "postprocess"
        elif "agentic_pureclip.loop.optuna_runner" in args:
            label = "optuna"
        elif "overnight_batch.py" in args:
            label = "orchestrator"
        elif "batch_runner" in args:
            label = "batch_runner"
        else:
            label = "agent"
        procs.append({
            "label": label, "cpu": pcpu, "mem": pmem,
            "etime": etime, "args": args,
        })
    return procs


def get_active_run(procs: list[dict], cfg: dict) -> dict:
    joined = " ".join(p["args"] for p in procs)
    is_active = bool(procs)

    # Which optimizer is driving the loop?
    if "agentic_pureclip.loop.optuna_runner" in joined:
        optimizer = "optuna"
    elif any(k in joined for k in ("agentic_pureclip.loop.graph", "agentic_pureclip.loop.graph")):
        optimizer = "llm"
    else:
        optimizer = None
    decide_label = "TPE suggest" if optimizer == "optuna" else "LLM decide"

    if "pureclip2" in joined:
        stage, idx = "PureCLIP", 0
        m = re.search(r"ip_(rep\d+)", joined)
        substage = m.group(1) if m else "merged"
    elif "agentic_pureclip.postprocess.postprocess" in joined:
        stage, idx, substage = "Postprocess", 1, None
    elif "agentic_pureclip.scoring.run_scorers" in joined:
        stage, idx, substage = "Score", 2, None
    elif "snakemake" in joined:
        stage, idx, substage = "PureCLIP", 0, None
    elif any(k in joined for k in ("agentic_pureclip.loop.graph", "agentic_pureclip.loop.graph", "agentic_pureclip.loop.optuna_runner", "batch_runner")):
        stage, idx, substage = decide_label, 3, None
    else:
        stage, idx, substage = "Idle", -1, None

    run_id = cfg.get("run_id")
    dataset = cfg.get("dataset_id")
    # Prefer the freshest identity parsed from the running command line.
    m = re.search(r"/([A-Za-z0-9]+_[A-Za-z0-9]+_iter_\d+)/", joined) or \
        re.search(r"/([A-Za-z0-9]+_iter_\d+)/", joined)
    if m:
        run_id = m.group(1)
    md = re.search(r"data/([A-Za-z0-9_]+)/bam", joined)
    if md:
        dataset = md.group(1)

    # The overnight orchestrator runs each job under results/overnight/<job_id>/.
    job_id = None
    mj = re.search(r"results/overnight/([^/ ]+)/", joined)
    if mj:
        job_id = mj.group(1)

    it = None
    if run_id:
        mi = ITER_RE.search(run_id)
        if mi:
            it = int(mi.group(1))

    elapsed = next(
        (p["etime"] for p in procs
         if any(k in p["args"] for k in
                ("agentic_pureclip.loop.graph", "agentic_pureclip.loop.graph", "agentic_pureclip.loop.optuna_runner", "batch_runner"))),
        None,
    )

    # Prefer the active job's own config (the orchestrator writes one per job).
    active_cfg = cfg
    if job_id:
        job_cfg = _read_yaml(Path(f"results/overnight/{job_id}/run_config.yaml"))
        if job_cfg:
            active_cfg = job_cfg
    pc = active_cfg.get("pureclip", {})
    post = active_cfg.get("postprocessing", {})
    params = {
        "bandwidth_nt": pc.get("bandwidth_nt"),
        "merge_distance_nt": pc.get("merge_distance_nt"),
        "high_precision_mode": pc.get("high_precision_mode"),
        "learn_on_chr21": pc.get("learn_on_chr21"),
        "min_crosslink_events": post.get("min_crosslink_events"),
        "force_width": post.get("force_width"),
    }

    return {
        "is_active": is_active,
        "optimizer": optimizer,
        "decide_label": decide_label,
        "job_id": job_id,
        "stage": stage,
        "stage_index": idx,
        "substage": substage,
        "dataset": dataset,
        "target_protein": cfg.get("target_protein") or cfg.get("priors", {}).get("target_protein"),
        "cell_line": cfg.get("cell_line"),
        "run_id": run_id,
        "iteration": it,
        "elapsed": elapsed,
        "params": params,
    }


def _iter_index(run_id: str) -> int | None:
    m = ITER_RE.search(run_id or "")
    return int(m.group(1)) if m else None


def _strip_iter(run_id: str) -> str:
    return ITER_RE.sub("", run_id or "").rstrip("_") or run_id


def _result_roots() -> list[Path]:
    """Result roots to scan: score_report.json files live one level below each.

    Live runs sit directly under ``results/runs/<iter>/``. Batch and overnight
    jobs add a job level (``results/{batch,overnight}/<job>/<iter>/``), so we
    expand those into their per-job dirs — otherwise a plain
    ``results/batch/*/score_report.json`` glob misses every batch iteration.
    """
    roots: list[Path] = [Path("results/runs")]
    for parent in (Path("results/batch"), Path("results/overnight")):
        if parent.exists():
            roots += [d for d in parent.iterdir() if d.is_dir()]
    return roots


def _source_label(root: Path) -> str:
    parts = root.parts
    if "overnight" in parts:
        return "overnight"
    if "batch" in parts:
        return "batch"
    return "live"


def _overnight_optimizers() -> dict[str, str]:
    """Map overnight job_id -> optimizer ('llm'|'optuna') from the batch DB."""
    mapping: dict[str, str] = {}
    jobs_db = Path("results/overnight/jobs.jsonl")
    if not jobs_db.exists():
        return mapping
    try:
        for line in jobs_db.read_text().splitlines():
            rec = json.loads(line)
            if rec.get("type") == "job" and rec.get("job_id"):
                mapping[rec["job_id"]] = rec.get("optimizer", "llm")
    except Exception:
        pass
    return mapping


def collect_experiments() -> list[dict]:
    """Group every score_report.json by dataset into iteration trajectories."""
    rows = []
    optimizer_map = _overnight_optimizers()
    for root in _result_roots():
        if not root.exists():
            continue
        source = _source_label(root)
        # For overnight roots, root.name is the job_id -> look up its optimizer.
        optimizer = optimizer_map.get(root.name, "llm") if source == "overnight" else "llm"
        for report in root.glob("*/score_report.json"):
            try:
                d = json.loads(report.read_text())
            except Exception:
                continue
            run_id = d.get("run_id") or report.parent.name
            dataset = d.get("dataset_id") or _strip_iter(run_id)
            comp = composite_objective(d)
            rows.append({
                "dataset": dataset,
                "run_id": run_id,
                "optimizer": optimizer,
                "iter": _iter_index(run_id),
                "n_sites": d.get("n_binding_sites"),
                "agreement": d.get("replicate_agreement"),
                "reproducibility": d.get("reproducibility_score"),
                "repro_enrichment": d.get("reproducibility_enrichment"),
                "motif": d.get("motif_hit_rate"),
                "enrichment": d.get("motif_enrichment"),
                "recall": d.get("benchmark_region_recall"),
                "composite": round(comp, 4) if comp is not None else None,
                "source": source,
                "mtime": report.stat().st_mtime,
            })

    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["dataset"], []).append(r)

    experiments = []
    for dataset, items in groups.items():
        items.sort(key=lambda x: x["mtime"])
        comps = [i["composite"] for i in items if i["composite"] is not None]
        best = max(comps) if comps else None
        best_idx = comps.index(best) if best is not None else None
        # Map best back to its position among the (filtered) items.
        best_run = None
        if best is not None:
            for i in items:
                if i["composite"] == best:
                    best_run = i["run_id"]
                    break
        experiments.append({
            "name": dataset,
            "best_composite": best,
            "best_run": best_run,
            "n_iters": len(items),
            "iterations": items,
            "last_mtime": items[-1]["mtime"],
        })
    experiments.sort(key=lambda g: g["last_mtime"], reverse=True)
    return experiments


def get_latest_reasoning() -> str | None:
    if not LOGS_DIR.exists():
        return None
    logs = sorted(LOGS_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for log in logs:
        try:
            text = log.read_text(errors="ignore")
        except Exception:
            continue
        idx = text.rfind("Agent decision reasoning:")
        if idx == -1:
            continue
        tail = text[idx + len("Agent decision reasoning:"):]
        # Reasoning is one log record; stop at the next timestamped line.
        out_lines = []
        for line in tail.splitlines():
            if out_lines and re.match(r"^\d{4}-\d{2}-\d{2} ", line):
                break
            out_lines.append(line)
        reasoning = " ".join(l.strip() for l in out_lines).strip()
        if reasoning:
            return reasoning
    return None


def get_host_info() -> dict:
    def run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=4).stdout.strip()
        except Exception:
            return "?"
    host = run(["hostname"])
    cpus = run(["nproc"])
    mem = "?"
    free = run(["free", "-h"])
    if free and free != "?":
        try:
            mem = free.splitlines()[1].split()[1]
        except Exception:
            pass
    return {"host": host, "cpus": cpus, "mem": mem}


def _etime_to_seconds(etime: str | None) -> int | None:
    """Parse ps etime ('MM:SS', 'HH:MM:SS', 'D-HH:MM:SS') to seconds."""
    if not etime:
        return None
    try:
        days = 0
        if "-" in etime:
            d, etime = etime.split("-", 1)
            days = int(d)
        parts = [int(x) for x in etime.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0)
        h, m, s = parts
        return days * 86400 + h * 3600 + m * 60 + s
    except Exception:
        return None


def _manifest_plan_jobs(manifest_path: str) -> list[dict]:
    """Ordered jobs from a manifest with defaults applied (id, dataset, optimizer, max_iter)."""
    try:
        man = yaml.safe_load(Path(manifest_path).read_text())
    except Exception:
        return []
    defaults = man.get("defaults", {})
    jobs = []
    for job in man.get("jobs", []):
        jobs.append({
            "job_id": job["id"],
            "dataset": job["dataset"],
            "optimizer": (job.get("optimizer") or defaults.get("optimizer") or "llm").lower(),
            "max_iter": int(job.get("max_iter", defaults.get("max_iter", 5))),
        })
    return jobs


def _count_job_iters(job_id: str) -> int:
    d = Path(f"results/overnight/{job_id}")
    return len(list(d.glob("*/score_report.json"))) if d.exists() else 0


def get_batch_plan(active: dict) -> dict | None:
    """Queue + rough ETA for the currently running overnight/comparison batch."""
    db = Path("results/overnight/jobs.jsonl")
    if not db.exists():
        return None
    try:
        records = [json.loads(l) for l in db.read_text().splitlines() if l.strip()]
    except Exception:
        return None

    bs, bs_pos = None, -1
    for i, r in enumerate(records):
        if r.get("type") == "batch_start":
            bs, bs_pos = r, i
    if not bs:
        return None
    plan_jobs = _manifest_plan_jobs(bs.get("manifest", ""))
    if not plan_jobs:
        return None

    completed = {r["job_id"]: r for r in records[bs_pos + 1:] if r.get("type") == "job"}

    # Timing model from ALL historical jobs (better early estimates), per dataset.
    per_ds: dict[str, list[float]] = {}
    samples: list[float] = []
    for r in records:
        if r.get("type") == "job" and r.get("iterations_scored") and r.get("duration_s"):
            pit = r["duration_s"] / r["iterations_scored"]
            per_ds.setdefault(r["dataset"], []).append(pit)
            samples.append(pit)
    global_pit = sum(samples) / len(samples) if samples else 600.0

    def per_iter(ds: str) -> float:
        vals = per_ds.get(ds)
        return sum(vals) / len(vals) if vals else global_pit

    active_job_id = (active or {}).get("job_id")
    out_jobs, remaining_total = [], 0.0
    for j in plan_jobs:
        jid = j["job_id"]
        est_total = j["max_iter"] * per_iter(j["dataset"])
        row = dict(j, per_iter_s=round(per_iter(j["dataset"])))
        if jid in completed:
            r = completed[jid]
            row.update(status=r.get("status", "completed"),
                       best_composite=r.get("best_composite"),
                       duration_s=r.get("duration_s"), eta_remaining_s=0)
        elif jid == active_job_id:
            done = _count_job_iters(jid)
            remaining = max(0.0, (j["max_iter"] - done) * per_iter(j["dataset"]))
            remaining_total += remaining
            row.update(status="running", done_iters=done,
                       elapsed_s=_etime_to_seconds((active or {}).get("elapsed")),
                       eta_remaining_s=round(remaining))
        else:
            remaining_total += est_total
            row.update(status="queued", eta_remaining_s=round(est_total))
        out_jobs.append(row)

    counts = {
        "done": sum(1 for x in out_jobs if x["status"] not in ("running", "queued")),
        "running": sum(1 for x in out_jobs if x["status"] == "running"),
        "queued": sum(1 for x in out_jobs if x["status"] == "queued"),
    }
    return {
        "manifest": bs.get("manifest"),
        "started": bs.get("started"),
        "jobs": out_jobs,
        "eta_remaining_s": round(remaining_total),
        "counts": counts,
    }


def _flat_params(params: dict) -> dict:
    out = {}
    for kv in (params or {}).values():
        for k, v in (kv or {}).items():
            out[k] = v
    return out


def _param_diff(prev: dict | None, curr: dict) -> list[dict]:
    """Which tunables changed from the previous iteration to this one."""
    if not prev:
        return []
    pf, cf = _flat_params(prev), _flat_params(curr)
    return [{"key": k, "from": pf.get(k), "to": v} for k, v in cf.items() if k in pf and pf[k] != v]


def collect_runs() -> list[dict]:
    """Per-run decision trail: each iteration's params, what changed, and the reasoning.

    Covers both overnight jobs and batch jobs — they share the layout
    ``<job>/decisions.jsonl`` + ``<job>/<iter>/score_report.json``.
    """
    job_dirs: list[Path] = []
    for parent in (Path("results/overnight"), Path("results/batch")):
        if parent.exists():
            job_dirs += [x for x in parent.iterdir() if x.is_dir()]
    if not job_dirs:
        return []
    opt_map = _overnight_optimizers()
    runs = []
    for d in job_dirs:
        reports = sorted(d.glob("*/score_report.json"), key=lambda p: p.stat().st_mtime)
        if not reports:
            continue
        decisions: dict = {}
        dj = d / "decisions.jsonl"
        if dj.exists():
            try:
                for line in dj.read_text().splitlines():
                    if line.strip():
                        rec = json.loads(line)
                        decisions[rec.get("iteration")] = rec
            except Exception:
                pass
        iters, prev, dataset = [], None, None
        for rp in reports:
            try:
                rep = json.loads(rp.read_text())
            except Exception:
                continue
            dataset = dataset or rep.get("dataset_id")
            run_id = rep.get("run_id") or rp.parent.name
            it = _iter_index(run_id)
            params = rep.get("params") or {}
            iters.append({
                "iter": it,
                "run_id": run_id,
                "params": params,
                "changed": _param_diff(prev, params),
                "reproducibility": rep.get("reproducibility_score"),
                "motif": rep.get("motif_hit_rate"),
                "recall": rep.get("benchmark_region_recall"),
                "n_sites": rep.get("n_binding_sites"),
                "composite": round(composite_objective(rep), 4),
                "reasoning": (decisions.get(it) or {}).get("reasoning"),
            })
            prev = params
        comps = [i["composite"] for i in iters if i["composite"] is not None]
        runs.append({
            "job_id": d.name,
            "dataset": dataset or _strip_iter(d.name),
            "optimizer": opt_map.get(d.name, "llm"),
            "n_iters": len(iters),
            "best_composite": max(comps) if comps else None,
            "iterations": iters,
            "mtime": reports[-1].stat().st_mtime,
        })
    runs.sort(key=lambda r: r["mtime"], reverse=True)
    return runs


def _read_bed_sites(bed: Path, cap: int = 4000) -> list[dict]:
    """Parse a BED file into [{chrom,start,end}] (first ``cap`` intervals)."""
    sites: list[dict] = []
    try:
        for line in bed.read_text().splitlines():
            if not line or line.startswith(("#", "track", "browser")):
                continue
            f = line.split("\t") if "\t" in line else line.split()
            if len(f) < 3:
                continue
            try:
                start, end = int(f[1]), int(f[2])
            except ValueError:
                continue
            sites.append({"chrom": f[0], "start": start, "end": end})
            if len(sites) >= cap:
                break
    except Exception:
        return []
    return sites


def collect_run_sites(dataset: str) -> dict:
    """Binding-site coordinates for a dataset's best-scoring iteration.

    Reads the ``binding_sites.reproducible.bed`` that sits next to each
    ``score_report.json``; picks the iteration with the highest composite so the
    "where did the RBP dock" view reflects the best result we found. Positions
    are real; ``motif_bearing`` is an approximation (we flag round(hit_rate·N)
    sites — per-site motif calls are not persisted) purely for illustration.
    """
    best = None  # (composite, report_path, report_dict)
    for root in _result_roots():
        if not root.exists():
            continue
        for report in root.glob("*/score_report.json"):
            try:
                d = json.loads(report.read_text())
            except Exception:
                continue
            ds = d.get("dataset_id") or _strip_iter(report.parent.name)
            if ds != dataset:
                continue
            comp = composite_objective(d)
            key = comp if comp is not None else -1.0
            if best is None or key > best[0]:
                best = (key, report, d)
    if best is None:
        return {"dataset": dataset, "found": False, "sites": []}

    _, report, d = best
    bed = report.parent / "binding_sites.reproducible.bed"
    sites = _read_bed_sites(bed) if bed.exists() else []
    coords = [s["start"] for s in sites] + [s["end"] for s in sites]
    lo, hi = (min(coords), max(coords)) if coords else (0, 0)
    chrom = sites[0]["chrom"] if sites else (
        "chr21" if (d.get("params") or {}) and "chr21" in str(report) else "genome")

    # Approximate motif-bearing flag: spread hit_rate·N hits deterministically.
    hit_rate = d.get("motif_hit_rate") or 0.0
    n_hits = int(round(hit_rate * len(sites)))
    if sites and n_hits:
        step = max(1, len(sites) // n_hits)
        for i, s in enumerate(sites):
            s["motif"] = (i % step == 0) and (sum(1 for x in sites[:i] if x.get("motif")) < n_hits)
    for s in sites:
        s.setdefault("motif", False)

    return {
        "dataset": dataset,
        "found": True,
        "run_id": d.get("run_id") or report.parent.name,
        "source": _source_label(report.parents[1] if report.parents[1] != Path(".") else report.parent),
        "chrom": chrom,
        "extent": {"start": lo, "end": hi},
        "n_sites": d.get("n_binding_sites") if d.get("n_binding_sites") is not None else len(sites),
        "composite": round(best[0], 4) if best[0] >= 0 else None,
        "reproducibility": d.get("reproducibility_score"),
        "motif_hit_rate": hit_rate,
        "motif_enrichment": d.get("motif_enrichment"),
        "recall": d.get("benchmark_region_recall"),
        "params": d.get("params") or {},
        "sites": sites,
    }


def build_status() -> dict:
    cfg = _read_yaml(RUN_CONFIG)
    procs = get_processes()
    experiments = collect_experiments()
    active = get_active_run(procs, cfg)

    # Attach the latest metric snapshot for the active dataset.
    latest = None
    if active["dataset"]:
        for g in experiments:
            if g["name"] == active["dataset"] or _strip_iter(active["run_id"] or "") == g["name"]:
                latest = g["iterations"][-1]
                break
    active["latest"] = latest
    active["reasoning"] = get_latest_reasoning()

    # The final loop step is optimizer-specific.
    stages = list(STAGES)
    stages[-1] = active.get("decide_label") or STAGES[-1]

    host = get_host_info()
    return {
        "host": host["host"],
        "cpus": host["cpus"],
        "mem": host["mem"],
        "stages": stages,
        "active": active,
        "plan": get_batch_plan(active),
        "experiments": experiments,
        "processes": procs,
    }


def _run_active() -> bool:
    """Is any heavy optimization process already running?"""
    try:
        out = subprocess.run(["ps", "-eo", "args", "--no-headers"],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return False
    for line in out.splitlines():
        if "dashboard.api" in line:
            continue
        if any(k in line for k in HEAVY_PROC_KEYS):
            return True
    return False


def schedule_run(spec: dict) -> tuple[int, dict]:
    """Validate a UI run request, write a manifest, and launch the CLI runner.

    Produces a standard overnight-batch manifest (config/ui_runs/<id>.yaml) and
    launches scripts/run/overnight_batch.py on it — so the same run can be started
    from the CLI, and the UI is just a front-end for that path.
    """
    datasets = set(list_datasets())
    dataset = spec.get("dataset")
    if dataset not in datasets:
        return 400, {"ok": False, "error": f"unknown dataset {dataset!r}"}

    optimizer = str(spec.get("optimizer") or "llm").lower()
    if optimizer not in ("llm", "optuna"):
        return 400, {"ok": False, "error": "optimizer must be 'llm' or 'optuna'"}

    try:
        max_iter = max(1, min(50, int(spec.get("max_iter", 8))))
        hours = max(0.1, min(24.0, float(spec.get("hours", 4))))
        threads = max(1, min(64, int(spec.get("threads", 32))))
    except (TypeError, ValueError):
        return 400, {"ok": False, "error": "invalid numeric field"}
    learn_on_chr21 = bool(spec.get("learn_on_chr21", True))

    weights = {}
    raw_w = spec.get("weights") or {}
    for k in ("reproducibility", "motif", "recall"):
        try:
            weights[k] = max(0.0, float(raw_w.get(k, DEFAULT_OBJECTIVE_WEIGHTS[k])))
        except (TypeError, ValueError):
            weights[k] = DEFAULT_OBJECTIVE_WEIGHTS[k]
    if sum(weights.values()) <= 0:
        weights = dict(DEFAULT_OBJECTIVE_WEIGHTS)

    # Validate the requested parameter ranges against the hard default bounds.
    bounds: dict[str, dict[str, list[int]]] = {}
    for section, params in (spec.get("bounds") or {}).items():
        if section not in DEFAULT_SEARCH_BOUNDS:
            continue
        for key, rng in (params or {}).items():
            if key not in DEFAULT_SEARCH_BOUNDS[section]:
                continue
            try:
                lo, hi = int(rng[0]), int(rng[1])
            except (TypeError, ValueError, IndexError):
                continue
            dlo, dhi = DEFAULT_SEARCH_BOUNDS[section][key]
            lo, hi = max(dlo, min(dhi, lo)), max(dlo, min(dhi, hi))
            if lo > hi:
                lo, hi = hi, lo
            bounds.setdefault(section, {})[key] = [lo, hi]
    if not bounds:
        return 400, {"ok": False, "error": "select at least one parameter to optimize"}

    if _run_active():
        return 409, {"ok": False, "busy": True,
                     "error": "A run is already active — wait for it to finish."}

    ts = time.strftime("%Y%m%d_%H%M%S")
    job_id = f"ui_{dataset.lower()}_{optimizer}_{ts}"
    manifest = {
        "defaults": {
            "max_iter": max_iter,
            "threads": threads,
            "learn_on_chr21": learn_on_chr21,
            "per_job_timeout_min": int(hours * 60),
            "optimizer": optimizer,
            "objective_weights": weights,
            "search_bounds": bounds,
        },
        "jobs": [{"id": job_id, "dataset": dataset}],
    }
    UI_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = UI_RUNS_DIR / f"{job_id}.yaml"
    with open(manifest_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(manifest, handle, sort_keys=False)

    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    env["PATH"] = f"{PURECLIP_DIR}:{env.get('PATH', '')}"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_handle = open(LOGS_DIR / "ui_scheduled.log", "a", encoding="utf-8")
    log_handle.write(f"\n=== {ts} launch {job_id} ({optimizer}, {dataset}) ===\n")
    log_handle.flush()
    subprocess.Popen(
        [sys.executable, "scripts/run/overnight_batch.py", "--manifest", str(manifest_path),
         "--no-repeat", "--hours", str(hours), "--pureclip-dir", PURECLIP_DIR],
        cwd=str(Path.cwd()), env=env, stdout=log_handle, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    n_params = sum(len(p) for p in bounds.values())
    return 200, {
        "ok": True,
        "job_id": job_id,
        "manifest": str(manifest_path),
        "message": f"Scheduled {optimizer.upper()} run on {dataset} "
                   f"({max_iter} iters, optimizing {n_params} parameter(s)).",
    }
