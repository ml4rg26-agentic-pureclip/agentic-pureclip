"""Validate a run request and build a standard overnight-batch manifest.

Kept free of any I/O or web/CLI concerns so both the dashboard API and the
``agentic-pureclip-run`` CLI can share the exact same validation and manifest
shape. The caller writes the manifest and launches ``overnight_batch.py``.
"""

from __future__ import annotations

import time

from agentic_pureclip.pipeline.configs import DEFAULT_SEARCH_BOUNDS
from agentic_pureclip.pipeline.datasets import list_datasets

try:
    from agentic_pureclip.scoring.objective import DEFAULT_OBJECTIVE_WEIGHTS
except Exception:  # pragma: no cover - fallback if scoring package not importable
    DEFAULT_OBJECTIVE_WEIGHTS = {"reproducibility": 0.5, "motif": 0.25, "recall": 0.25}

WEIGHT_KEYS = ("reproducibility", "motif", "recall")


class ScheduleError(ValueError):
    """A run request that failed validation; ``status_code`` mirrors the HTTP code."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def build_manifest(spec: dict) -> tuple[str, dict, dict]:
    """Validate ``spec`` and return ``(job_id, manifest, meta)``.

    ``spec`` matches the Plan-page form: ``dataset``, ``optimizer`` (llm|optuna),
    ``max_iter``, ``hours``, ``threads``, ``learn_on_chr21``, ``weights`` and
    nested ``bounds`` (``{section: {key: [lo, hi]}}``). Unknown/out-of-range
    values are dropped or clamped to ``DEFAULT_SEARCH_BOUNDS``. Raises
    ``ScheduleError`` on anything that can't be made valid.

    ``meta`` carries the fields the launcher needs beyond the manifest itself
    (``hours``, ``optimizer``, ``dataset``, ``max_iter``, ``n_params``).
    """
    dataset = spec.get("dataset")
    if dataset not in set(list_datasets()):
        raise ScheduleError(f"unknown dataset {dataset!r}")

    optimizer = str(spec.get("optimizer") or "llm").lower()
    if optimizer not in ("llm", "optuna"):
        raise ScheduleError("optimizer must be 'llm' or 'optuna'")

    try:
        max_iter = max(1, min(50, int(spec.get("max_iter", 8))))
        hours = max(0.1, min(24.0, float(spec.get("hours", 4))))
        threads = max(1, min(64, int(spec.get("threads", 32))))
    except (TypeError, ValueError):
        raise ScheduleError("invalid numeric field")
    learn_on_chr21 = bool(spec.get("learn_on_chr21", True))

    weights: dict[str, float] = {}
    raw_w = spec.get("weights") or {}
    for k in WEIGHT_KEYS:
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
        raise ScheduleError("select at least one parameter to optimize")

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
    meta = {
        "hours": hours,
        "optimizer": optimizer,
        "dataset": dataset,
        "max_iter": max_iter,
        "n_params": sum(len(p) for p in bounds.values()),
    }
    return job_id, manifest, meta
