from __future__ import annotations

import json
import re
from typing import Any

from pipeline.configs import apply_decision_changes, tunable_signature, tunable_snapshot, tried_signatures


DEFAULT_MOTIF_WEIGHT = 0.25


def composite_objective(report: dict[str, Any], motif_weight: float = DEFAULT_MOTIF_WEIGHT) -> float:
    """Single quality score the agent climbs.

    Blends reproducibility (replicate_agreement) with biological validity
    (motif_hit_rate), both in [0, 1]. This guards against the failure mode
    where agreement rises by enriching reproducible noise: such a change
    raises agreement but drops the motif rate, so the composite barely moves.

    Falls back to pure replicate_agreement when no motif signal is available.
    """
    agreement = report.get("replicate_agreement") or 0.0
    motif = report.get("motif_hit_rate")
    if motif is None or motif_weight <= 0:
        return float(agreement)
    return float((1 - motif_weight) * agreement + motif_weight * motif)


def _delta(curr: float | None, prev: float | None) -> str:
    if curr is None or prev is None:
        return "n/a"
    return f"{curr - prev:+.4f}"


def _progress_rows(state: dict[str, Any], motif_weight: float) -> list[dict[str, Any]]:
    """Compact per-iteration trend, with deltas vs the previous attempt."""
    rows = []
    prev = None
    for h in state["history"]:
        scores = h["scores"]
        row = {
            "iter": h["iteration"],
            "params": h["config"],
            "agreement": scores.get("replicate_agreement"),
            "motif_hit_rate": scores.get("motif_hit_rate"),
            "motif_enrichment": scores.get("motif_enrichment"),
            "n_sites": scores.get("n_binding_sites"),
            "composite": round(composite_objective(scores, motif_weight), 4),
        }
        if prev is not None:
            row["d_agreement"] = _delta(row["agreement"], prev["agreement"])
            row["d_motif"] = _delta(row["motif_hit_rate"], prev["motif_hit_rate"])
            row["d_composite"] = _delta(row["composite"], prev["composite"])
        rows.append(row)
        prev = row
    return rows


def build_decision_prompt(
    state: dict[str, Any],
    report: dict[str, Any],
    motif_weight: float = DEFAULT_MOTIF_WEIGHT,
) -> str:
    priors = state["current_config"].get("priors") or state["priors"]
    progress = _progress_rows(state, motif_weight)
    current_composite = round(composite_objective(report, motif_weight), 4)
    return f"""You are optimising PureCLIP parameters for eCLIP data.

Your goal is to MAXIMISE the COMPOSITE quality score, defined as:
    composite = {1 - motif_weight:.2f} * replicate_agreement + {motif_weight:.2f} * motif_hit_rate
Both terms are in [0, 1]. replicate_agreement measures reproducibility across
replicates; motif_hit_rate measures whether sites contain the expected RNA
motif (biological validity). Do NOT collapse the number of binding sites.

PRIOR KNOWLEDGE:
{json.dumps(priors, indent=2)}

SEARCH BOUNDS (hard limits, never exceed these):
{json.dumps(state['search_bounds'], indent=2)}

CURRENT TUNABLE PARAMETERS:
{json.dumps(tunable_snapshot(state['current_config']), indent=2)}

LATEST SCORE (composite={current_composite}):
{json.dumps(report, indent=2)}

PROGRESS (oldest first; d_* are deltas vs the previous attempt):
{json.dumps(progress, indent=2)}

DECISION RULES:
1. Read the deltas: keep moving parameters in directions that raised composite,
   reverse directions that lowered it. Do not assume relaxing or tightening always helps.
2. Change ONE parameter at a time so the effect is interpretable.
3. Do not repeat any previous parameter set.
4. Stay strictly inside the search bounds.
5. Only change parameters listed in SEARCH BOUNDS.
6. If replicate_agreement rose but motif_hit_rate fell, treat it as enriching
   reproducible noise: prefer reverting or trying a different parameter.
7. If n_sites is collapsing, relax stringency (lower min_crosslink_events,
   raise merge_distance_nt) to recover sensitivity before optimising further.

Respond ONLY with JSON:
{{"reasoning": "name the trend you saw in the deltas and why you chose this direction",
  "changes": {{"pureclip": {{...}}, "postprocessing": {{...}}}}}}"""


def parse_decision_response(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    match = re.search(r"```(?:json)?(.*?)```", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1).strip()
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            cleaned = cleaned[start : end + 1]
    decision = json.loads(cleaned)
    if not isinstance(decision, dict) or "changes" not in decision or "reasoning" not in decision:
        raise ValueError("Decision response must contain reasoning and changes")
    return decision


def validated_next_config(state: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    previous = tried_signatures(state["history"])
    previous.add(tunable_signature(state["current_config"]))
    return apply_decision_changes(
        state["current_config"],
        decision["changes"],
        search_bounds=state["search_bounds"],
        previous_signatures=previous,
    )
