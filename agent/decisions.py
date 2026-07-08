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
    return f"""You are analysing eCLIP data for the RNA-binding protein described in
PRIOR KNOWLEDGE below. You are tuning a two-stage peak-calling pipeline to recover
this protein's true binding sites. Use what is known about this protein's binding
biology to guide every parameter decision.

Your goal is to MAXIMISE {state['objective_metric']} without collapsing the number
of binding sites, while keeping the recovered sites biologically plausible.

THE PIPELINE HAS TWO STAGES, and the parameters you control belong to each:

  Stage 1 - PureCLIP (peak calling):
    Runs an HMM on the BAM data to detect crosslink sites and merge them into
    raw binding regions. Parameters under "pureclip" change how these raw
    regions are called:
      - bandwidth_nt: KDE smoothing. Smaller = sensitive to sharp local spikes
        (narrower peaks); larger = smoother signal, merges adjacent peaks,
        reduces background but can blur closely spaced sites.
      - merge_distance_nt: max gap between crosslink sites that still get merged
        into one continuous region. Higher = broader regions; lower = more
        fragmented regions.

  Stage 2 - Postprocessing (filtering and reshaping PureCLIP's output):
    Takes the raw regions from Stage 1 and turns them into final binding sites.
    Parameters under "postprocessing" act ONLY on Stage 1's output:
      - min_crosslink_events: drop regions with fewer than this many crosslink
        events (noise filter; higher = stricter, fewer final sites).
      - min_region_length_nt: drop regions shorter than this.
      - force_width: re-centre each surviving region on its MIDPOINT
        (the geometric centre between start and end, NOT a signal summit)
        and force it to this fixed width.

PRIOR KNOWLEDGE (use this to reason about the biology, not just the statistics):
{json.dumps(priors, indent=2)}

HOW THE BIOLOGY SHOULD INFORM YOUR CHOICES:
  - Relate bandwidth_nt and force_width to the known motif length and to whether
    this protein binds in sharp, point-like sites or in broad regions. A protein
    with a short, well-defined motif that binds point-like sites is poorly served
    by a very large bandwidth or a very wide force_width, which blur a precise
    site; a protein binding broad regions tolerates wider settings.
  - force_width should not be so wide that it dilutes a short motif, nor so narrow
    that it cuts off the binding region.
  - If your reasoning could apply unchanged to any generic signal-processing task
    without mentioning THIS protein's biology, you have NOT used the prior
    knowledge. Name the target protein, its motif, its binding_preference and its
    role in RNA processing explicitly.
    
SEARCH BOUNDS (hard limits, never exceed these):
{json.dumps(state['search_bounds'], indent=2)}

CURRENT TUNABLE PARAMETERS:
{json.dumps(tunable_snapshot(state['current_config']), indent=2)}

LATEST SCORE:
{json.dumps(report, indent=2)}

FULL HISTORY OF PREVIOUS ATTEMPTS:
{json.dumps(history, indent=2)}

DECISION RULES:
1. Ground each parameter choice in this protein's binding biology (motif length,
   point-like vs broad binding) AND in the observed score trends. Do not rely on
   a fixed assumption that relaxing or tightening always helps.
2. Consider motif_hit_rate and n_binding_sites alongside the primary objective,
   not the objective in isolation.
3. You may change multiple parameters at once when you have a reason to expect
   them to interact, but keep the number of simultaneous changes small (at most
   2-3). For every parameter you change, state in your reasoning what you expect
   it to do and why, referencing the biology where relevant. Changing many
   parameters blindly makes the result impossible to attribute to any single cause.
4. Do not repeat any previous parameter set, and avoid trivial one-unit changes
   that do not meaningfully explore the space.
5. Stay inside the search bounds exactly.
6. Only change parameters listed in SEARCH BOUNDS.

Respond ONLY with JSON:
{{"reasoning": "reflect on this RBP's role and binding_preference, state the trend
  you observed, how the biology and known target genes inform your choice, and why
  you chose this direction",
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