"""Optuna (TPE / Bayesian) optimizer — a drop-in alternative to the LLM agent.

Runs the SAME evaluation (``agentic_pureclip.loop.evaluation.evaluate_config``) and the SAME
objective (``agentic_pureclip.scoring.objective.composite_objective``) as the LLM agent, over the
SAME search bounds — only the search strategy differs. Each trial writes its own
``score_report.json`` (run_id ``<protein>_iter_<trial>``), so the overnight
database and dashboard pick up Optuna runs exactly like LLM runs.

Entry point mirrors ``agent/graph.py``:
    CONFIG_PATH=<cfg> MAX_ITER=<n_trials> python agent/optuna_runner.py
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import optuna

from agentic_pureclip.scoring.objective import DEFAULT_OBJECTIVE_WEIGHTS, composite_objective
from agentic_pureclip.loop.evaluation import evaluate_config
from agentic_pureclip.pipeline.logging_config import setup_logger
from agentic_pureclip.pipeline.configs import DEFAULT_SEARCH_BOUNDS, load_config, save_config

load_dotenv()
optuna.logging.set_verbosity(optuna.logging.WARNING)

logger = setup_logger("optuna_runner", "results/logs/optuna_runner.log")

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config/run_config.yaml")

# Tunables that are booleans in the config (suggested as 0/1, applied as bool).
BOOL_PARAMS = {("pureclip", "high_precision_mode"), ("pureclip", "use_input_covariate")}

# Shared early-stop rule (Change 3): stop when the best composite hasn't improved by
# >= threshold for `patience` consecutive trials. To keep it FAIR vs the LLM (which
# has no random phase), stagnation is only counted AFTER Optuna's random startup
# trials — before that, "no improvement" is sampling noise, not convergence.
# STARTUP_TRIALS mirrors TPESampler's default n_startup_trials (10).
STARTUP_TRIALS = 10
PATIENCE = int(os.environ.get("PATIENCE", "4"))
SCORE_IMPROVEMENT_THRESHOLD = float(os.environ.get("SCORE_IMPROVEMENT_THRESHOLD", "0.01"))


def _make_early_stop_callback(patience: int, threshold: float, startup: int):
    """Optuna callback that stops the study on a shared stagnation rule.

    Counting only begins once ``startup`` trials have completed, so the random
    warm-up phase can't trip an early stop. ``study.stop()`` lets the current trial
    finish, then halts — mirroring the LLM's patience-based convergence.
    """
    tracker = {"best": float("-inf"), "streak": 0}

    def callback(study: optuna.Study, trial: optuna.trial.FrozenTrial) -> None:
        value = trial.value
        if value is None:  # failed trial — don't let it count as (non-)improvement
            return
        if value > tracker["best"] + threshold:
            tracker["best"] = value
            tracker["streak"] = 0
            return
        tracker["best"] = max(tracker["best"], value)
        if trial.number < startup:
            return  # still in the random warm-up; noise, not convergence
        tracker["streak"] += 1
        if tracker["streak"] >= patience:
            logger.info(
                "Optuna early-stop: no improvement > %.3f for %d trials past startup (trial %d)",
                threshold, patience, trial.number,
            )
            study.stop()

    return callback


def _with_iteration_output(config: dict) -> dict:
    """Store every trial in its own result directory (mirrors agent/graph.py)."""
    cfg = copy.deepcopy(config)
    output = cfg.setdefault("output", {})
    results_root = str(output.setdefault("results_root", "results/runs")).rstrip("/")
    if output.get("use_run_id_subdir", True):
        output["results_dir"] = f"{results_root}/{cfg['run_id']}"
    return cfg


def _apply_params(config: dict, params: dict[tuple[str, str], int]) -> dict:
    cfg = copy.deepcopy(config)
    for (section, key), value in params.items():
        cfg[section][key] = bool(value) if (section, key) in BOOL_PARAMS else int(value)
    return cfg


def _record_decision(base_config: dict, trial_no: int, run_id: str, report: dict, score: float) -> None:
    """Append a trial's params/scores to the run's decision trail (no NL reasoning)."""
    results_root = (base_config.get("output") or {}).get("results_root")
    if not results_root:
        return
    pc = report.get("params", {}).get("pureclip", {})
    po = report.get("params", {}).get("postprocessing", {})
    entry = {
        "iteration": trial_no,
        "optimizer": "optuna",
        "run_id": run_id,
        "params": {"pureclip": pc, "postprocessing": po},
        "scores": {
            k: report.get(k)
            for k in ("reproducibility_score", "replicate_agreement", "motif_hit_rate",
                      "benchmark_region_recall", "n_binding_sites")
        },
        "composite": round(score, 4),
        "reasoning": "TPE proposal — sampled from the model of previous trials.",
        "changes": None,
    }
    try:
        path = Path(results_root) / "decisions.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        logger.warning("Could not write decision trail to %s", results_root)


def run_optuna(
    base_config: dict[str, Any],
    max_iter: int,
    weights: dict[str, float],
    search_bounds: dict = DEFAULT_SEARCH_BOUNDS,
    seed: int = 42,
    patience: int = PATIENCE,
    improvement_threshold: float = SCORE_IMPROVEMENT_THRESHOLD,
    startup_trials: int = STARTUP_TRIALS,
) -> optuna.Study:
    """Run a TPE study for up to ``max_iter`` trials, maximising the composite objective.

    Stops early on the shared stagnation rule (see ``_make_early_stop_callback``);
    ``patience <= 0`` disables early stopping.
    """
    priors = base_config.get("priors") or {}
    target = priors.get("target_protein", "RBP")
    best = {"score": float("-inf"), "config": None}

    def objective(trial: optuna.Trial) -> float:
        suggested = {
            (section, key): trial.suggest_int(f"{section}.{key}", low, high)
            for section, params in search_bounds.items()
            for key, (low, high) in params.items()
        }
        cfg = _apply_params(base_config, suggested)
        cfg["run_id"] = f"{target}_iter_{trial.number:02d}"
        cfg = _with_iteration_output(cfg)
        try:
            report = evaluate_config(cfg, CONFIG_PATH, search_bounds=search_bounds)
        except Exception:
            logger.exception("Trial %d evaluation failed", trial.number)
            return float("-inf")
        score = composite_objective(report, weights)
        logger.info(
            "Trial %d: composite=%.4f reproducibility=%s motif=%s recall=%s params=%s",
            trial.number, score,
            report.get("reproducibility_score", report.get("replicate_agreement")),
            report.get("motif_hit_rate"), report.get("benchmark_region_recall"),
            {f"{s}.{k}": v for (s, k), v in suggested.items()},
        )
        _record_decision(base_config, trial.number, cfg["run_id"], report, score)
        if score > best["score"]:
            best["score"], best["config"] = score, cfg
        return score

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    callbacks = []
    if patience and patience > 0:
        callbacks.append(_make_early_stop_callback(patience, improvement_threshold, startup_trials))
    logger.info(
        "Starting Optuna study: up to %d trials, target=%s (early-stop patience=%d after %d startup)",
        max_iter, target, patience, startup_trials,
    )
    study.optimize(objective, n_trials=max_iter, callbacks=callbacks)

    if best["config"] is not None:
        save_config(best["config"], "config/best_config.yaml")
    logger.info(
        "Optuna DONE. Best composite=%.4f params=%s",
        study.best_value, study.best_params,
    )
    return study


if __name__ == "__main__":
    base_config = _with_iteration_output(load_config(CONFIG_PATH))
    priors = base_config.get("priors") or json.load(open("config/priors.json", encoding="utf-8"))
    weights = priors.get("objective_weights") or DEFAULT_OBJECTIVE_WEIGHTS
    n_trials = int(os.environ.get("MAX_ITER", "12"))
    search_bounds = base_config.get("search_bounds") or DEFAULT_SEARCH_BOUNDS
    run_optuna(base_config, n_trials, weights, search_bounds=search_bounds)
