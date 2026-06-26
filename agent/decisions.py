from __future__ import annotations

import json
import re
from typing import Any

from pipeline.configs import apply_decision_changes, tunable_signature, tunable_snapshot, tried_signatures


def build_decision_prompt(state: dict[str, Any], report: dict[str, Any]) -> str:
    priors = state["current_config"].get("priors") or state["priors"]
    history = [
        {
            "iter": h["iteration"],
            "params": h["config"],
            "agreement": h["scores"].get("replicate_agreement"),
            "n_sites": h["scores"].get("n_binding_sites"),
            "motif_hit_rate": h["scores"].get("motif_hit_rate"),
        }
        for h in state["history"]
    ]
    return f"""You are optimising PureCLIP parameters for eCLIP data.
Your goal is to MAXIMISE {state['objective_metric']} without collapsing the number of binding sites.

PRIOR KNOWLEDGE:
{json.dumps(priors, indent=2)}

SEARCH BOUNDS (hard limits, never exceed these):
{json.dumps(state['search_bounds'], indent=2)}

CURRENT TUNABLE PARAMETERS:
{json.dumps(tunable_snapshot(state['current_config']), indent=2)}

LATEST SCORE:
{json.dumps(report, indent=2)}

FULL HISTORY OF PREVIOUS ATTEMPTS:
{json.dumps(history, indent=2)}

DECISION RULES:
1. Use observed score trends, not a fixed assumption that relaxing or tightening always helps.
2. Prefer changing one parameter at a time so the effect is interpretable.
3. Do not repeat any previous parameter set.
4. Stay inside the search bounds exactly.
5. Only change parameters listed in SEARCH BOUNDS.

Respond ONLY with JSON:
{{"reasoning": "state the trend you observed and why you chose this direction",
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
