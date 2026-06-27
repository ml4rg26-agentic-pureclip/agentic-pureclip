"""Optuna (TPE / Bayesian) optimizer — a drop-in alternative to the LLM agent.

Runs the SAME evaluation (``agent.evaluation.evaluate_config``) and the SAME
objective (``agent.decisions.composite_objective``) as the LLM agent, over the
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
from typing import Any

from dotenv import load_dotenv
import optuna

from agent.decisions import DEFAULT_OBJECTIVE_WEIGHTS, composite_objective
from agent.evaluation import evaluate_config
from agent.logging_config import setup_logger
from pipeline.configs import DEFAULT_SEARCH_BOUNDS, load_config, save_config

load_dotenv()
optuna.logging.set_verbosity(optuna.logging.WARNING)

logger = setup_logger("optuna_runner", "results/logs/optuna_runner.log")

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config/run_config.yaml")

# Tunables that are booleans in the config (suggested as 0/1, applied as bool).
BOOL_PARAMS = {("pureclip", "high_precision_mode"), ("pureclip", "use_input_covariate")}


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


def run_optuna(
    base_config: dict[str, Any],
    max_iter: int,
    weights: dict[str, float],
    search_bounds: dict = DEFAULT_SEARCH_BOUNDS,
    seed: int = 42,
) -> optuna.Study:
    """Run a TPE study for ``max_iter`` trials, maximising the composite objective."""
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
        if score > best["score"]:
            best["score"], best["config"] = score, cfg
        return score

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    logger.info("Starting Optuna study: %d trials, target=%s", max_iter, target)
    study.optimize(objective, n_trials=max_iter)

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
    run_optuna(base_config, n_trials, weights)
