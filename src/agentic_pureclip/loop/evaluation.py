"""Optimizer-agnostic evaluation of a PureCLIP parameter set.

Both optimizers — the LLM agent (``agent/graph.py``) and the Optuna search
(``agent/optuna_runner.py``) — share this single expensive step: run the
pipeline for a config and return its score report. Keeping it here guarantees
the two optimizers are compared on an identical evaluation and objective.
"""

from __future__ import annotations

import json
from typing import Any

from agentic_pureclip.pipeline.configs import (
    DEFAULT_SEARCH_BOUNDS,
    save_config,
    score_report_path,
    validate_config,
)
from agentic_pureclip.pipeline.runner import run_scorers as _run_scorers
from agentic_pureclip.pipeline.runner import run_snakemake

# Rules re-run on every evaluation so a parameter change actually takes effect.
FORCE_RULES = ("pureclip", "pureclip_per_replicate", "postprocess")


def evaluate_config(
    config: dict[str, Any],
    config_path: str,
    search_bounds: dict | None = DEFAULT_SEARCH_BOUNDS,
) -> dict[str, Any]:
    """Run PureCLIP + scoring for ``config`` and return the score report.

    Validates, persists the config to ``config_path`` (the Snakefile reads it
    from there), forces the PureCLIP/postprocess rules to re-run, scores, and
    returns the parsed ``score_report.json``.
    """
    validate_config(config, search_bounds=search_bounds)
    save_config(config, config_path)
    run_snakemake(
        config_path,
        jobs=config["resources"]["threads"],
        force_rules=FORCE_RULES,
    )
    report_path = score_report_path(config)
    _run_scorers(config_path, report_path)
    with open(report_path, "r", encoding="utf-8") as handle:
        return json.load(handle)
