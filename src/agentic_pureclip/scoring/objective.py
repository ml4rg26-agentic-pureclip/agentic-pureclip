from __future__ import annotations

import json
import re
from typing import Any

from agentic_pureclip.pipeline.configs import apply_decision_changes, tunable_signature, tunable_snapshot, tried_signatures


# Weights for the blended objective. Renormalised over whichever terms a score
# report actually contains. Override per-dataset via priors["objective_weights"].
DEFAULT_OBJECTIVE_WEIGHTS = {"reproducibility": 0.5, "motif": 0.25, "recall": 0.25}

# Backwards-compatible alias (older callers imported this).
DEFAULT_MOTIF_WEIGHT = DEFAULT_OBJECTIVE_WEIGHTS["motif"]

# Collapse guard: with only a handful of binding sites, reproducibility and motif
# rate trivially saturate at 1.0 — a degenerate "win". Below this soft floor the
# composite is ramped down linearly so a 1-site solution scores ~0.
DEFAULT_MIN_SITES = 10


def _objective_terms(report: dict[str, Any]) -> dict[str, float]:
    """Extract the [0, 1] objective terms present in a score report."""
    terms: dict[str, float] = {}
    rep = report.get("reproducibility_score")
    if rep is None:  # fall back to raw agreement for old reports / no genome index
        rep = report.get("replicate_agreement")
    if rep is not None:
        terms["reproducibility"] = float(rep)
    motif = report.get("motif_hit_rate")
    if motif is not None:
        terms["motif"] = float(motif)
    recall = report.get("benchmark_region_recall")
    if recall is not None:
        terms["recall"] = float(recall)
    return terms


def yield_factor(report: dict[str, Any], min_sites: int = DEFAULT_MIN_SITES) -> float:
    """Down-weight scores from too few sites (the collapse failure mode).

    1.0 at/above ``min_sites``, ramping linearly to 0 at zero sites.
    """
    n = report.get("n_binding_sites")
    if n is None or min_sites <= 0:
        return 1.0
    return min(1.0, max(0, n) / min_sites)


def composite_objective(
    report: dict[str, Any],
    weights: dict[str, float] | None = None,
    min_sites: int = DEFAULT_MIN_SITES,
) -> float:
    """Blended quality score the agent climbs (all terms in [0, 1]):

      * reproducibility — chance-corrected replicate agreement (falls back to the
        raw agreement when the chance-corrected score is unavailable)
      * motif           — fraction of sites carrying the expected RNA motif
      * recall          — fraction of known-strong ENCODE reference regions recovered

    Weights are renormalised over whichever terms are present. The result is then
    multiplied by a yield factor so collapsing to a handful of sites (where
    reproducibility/motif trivially hit 1.0) can no longer win.
    """
    weights = weights or DEFAULT_OBJECTIVE_WEIGHTS
    terms = _objective_terms(report)
    if not terms:
        return 0.0
    total_w = sum(weights.get(k, 0.0) for k in terms)
    if total_w <= 0:
        return 0.0
    base = sum(weights.get(k, 0.0) * v for k, v in terms.items()) / total_w
    return float(base * yield_factor(report, min_sites))


def _delta(curr: float | None, prev: float | None) -> str:
    if curr is None or prev is None:
        return "n/a"
    return f"{curr - prev:+.4f}"


def _progress_rows(state: dict[str, Any], weights: dict[str, float]) -> list[dict[str, Any]]:
    """Compact per-iteration trend, with deltas vs the previous attempt."""
    rows = []
    prev = None
    for h in state["history"]:
        scores = h["scores"]
        reproducibility = scores.get("reproducibility_score")
        if reproducibility is None:
            reproducibility = scores.get("replicate_agreement")
        row = {
            "iter": h["iteration"],
            "params": h["config"],
            "reproducibility": reproducibility,
            "agreement_raw": scores.get("replicate_agreement"),
            "motif_hit_rate": scores.get("motif_hit_rate"),
            "known_site_recall": scores.get("benchmark_region_recall"),
            "n_sites": scores.get("n_binding_sites"),
            "composite": round(composite_objective(scores, weights), 4),
        }
        if prev is not None:
            row["d_reproducibility"] = _delta(row["reproducibility"], prev["reproducibility"])
            row["d_recall"] = _delta(row["known_site_recall"], prev["known_site_recall"])
            row["d_composite"] = _delta(row["composite"], prev["composite"])
        rows.append(row)
        prev = row
    return rows


def build_decision_prompt(
    state: dict[str, Any],
    report: dict[str, Any],
    weights: dict[str, float] | None = None,
    feedback: str | None = None,
    include_priors: bool = True,
) -> str:
    """Build the LLM decision prompt.

    ``include_priors=False`` runs the no-priors ablation (Change 2): it withholds ALL
    biological prior knowledge from what the LLM sees — the protein identity, motif,
    footprint width and preferred region, plus the biology-grounded framing, rule and
    reasoning instruction. Only the shared "game" (objective weights, search bounds,
    scores) is kept. Scoring is unaffected: the scorer loads priors independently.
    """
    weights = weights or DEFAULT_OBJECTIVE_WEIGHTS
    priors = state["current_config"].get("priors") or state["priors"]
    progress = _progress_rows(state, weights)
    current_composite = round(composite_objective(report, weights), 4)
    weights_str = ", ".join(f"{k}={v}" for k, v in weights.items())
    feedback_block = (
        f"\nIMPORTANT — your previous answer was rejected:\n{feedback}\n"
        "Propose a DIFFERENT change that fixes this.\n"
        if feedback
        else ""
    )

    if include_priors:
        intro = (
            "You are analysing eCLIP data for the RNA-binding protein described in\n"
            "PRIOR KNOWLEDGE below, tuning a two-stage peak-calling pipeline (PureCLIP + post-\n"
            "processing) to recover this protein's true binding sites. Use what is known about\n"
            "its binding biology to guide every parameter choice, and keep the recovered sites\n"
            "biologically plausible."
        )
        prior_block = f"""PRIOR KNOWLEDGE (use this to reason about the biology, not just the statistics):
{json.dumps(priors, indent=2)}

HOW THE BIOLOGY SHOULD INFORM YOUR CHOICES:
  - Relate bandwidth_nt and force_width to the known motif length and to whether
    this protein binds in sharp, point-like sites or in broader regions. A short,
    well-defined motif is poorly served by a very large bandwidth or a very wide
    force_width, which blur a precise site; a protein binding broad regions
    tolerates wider settings. force_width should not be so wide that it dilutes a
    short motif, nor so narrow that it cuts off the binding region.
  - Let the protein's preferred_binding region (e.g. intron, 3'UTR) and its role in
    RNA processing inform how permissive to be, alongside the score deltas.
  - If your reasoning could apply unchanged to any generic signal-processing task
    without mentioning THIS protein, you have NOT used the prior knowledge. Name the
    target protein, its motif and its preferred_binding region explicitly."""
        rule_one = (
            "Ground each choice in this protein's binding biology (motif length, point-like\n"
            "   vs broad binding, preferred_binding region) together with the observed deltas —\n"
            "   not a fixed assumption that relaxing or tightening always helps."
        )
        reasoning_instr = (
            "reflect on this RBP's role and preferred_binding region, name the\n"
            "  trend you saw in the deltas, explain how the biology informs your choice, and why\n"
            "  you chose this direction"
        )
    else:
        intro = (
            "You are tuning a two-stage peak-calling pipeline (PureCLIP + post-processing) to\n"
            "recover the true binding sites in an eCLIP experiment. NO prior knowledge about the\n"
            "target protein, its binding motif, footprint width or preferred region is available\n"
            "— reason purely from the observed scores and how they respond to parameter changes."
        )
        prior_block = (
            "PRIOR KNOWLEDGE: withheld for this run. No protein identity, motif, footprint\n"
            "width or preferred transcript region is provided — optimise from the score deltas\n"
            "alone."
        )
        rule_one = (
            "Ground each choice in the observed deltas and the collapse guard — not a fixed\n"
            "   assumption that relaxing or tightening always helps."
        )
        reasoning_instr = (
            "name the trend you saw in the deltas and explain why you chose this direction"
        )

    return f"""{intro}{feedback_block}

Your goal is to MAXIMISE the COMPOSITE quality score, a weighted blend (weights
renormalised over the terms present; current weights: {weights_str}) of three
metrics, all in [0, 1]:
  * reproducibility    — replicate agreement corrected for chance overlap. Unlike
    raw agreement this CANNOT be inflated by keeping only a few broad sites.
  * motif_hit_rate     — fraction of sites carrying the expected RNA motif
    (biological validity).
  * known_site_recall  — fraction of known-strong ENCODE reference regions your
    sites recover. Collapsing the number of sites LOWERS this term.

Because recall punishes site collapse and reproducibility is chance-corrected,
trimming sites to chase agreement no longer helps — you must find sites that are
reproducible, motif-bearing AND cover the known binding regions.

COLLAPSE GUARD: the composite is multiplied by min(1, n_binding_sites/{DEFAULT_MIN_SITES}).
Below {DEFAULT_MIN_SITES} sites the score is ramped toward zero, so a handful of
"perfect" sites is NOT a win. Keep a healthy number of binding sites.

{prior_block}

SEARCH BOUNDS (hard limits, never exceed these):
{json.dumps(state['search_bounds'], indent=2)}

CURRENT TUNABLE PARAMETERS:
{json.dumps(tunable_snapshot(state['current_config']), indent=2)}

LATEST SCORE (composite={current_composite}):
{json.dumps(report, indent=2)}

PROGRESS (oldest first; d_* are deltas vs the previous attempt):
{json.dumps(progress, indent=2)}

DECISION RULES:
1. {rule_one}
2. Read the deltas: keep moving parameters in directions that raised composite,
   reverse directions that lowered it.
3. Prefer changing ONE parameter at a time so its effect stays interpretable, but
   you MAY change 2-3 together when you have a specific reason to expect them to
   interact — state what you expect each change to do. Avoid changing many at once,
   which makes the result impossible to attribute to any single cause.
4. Do not repeat any previous parameter set, and avoid trivial one-unit changes
   that do not meaningfully explore the space.
5. Stay strictly inside the search bounds.
6. Only change parameters listed in SEARCH BOUNDS.
7. If reproducibility rose but known_site_recall or motif_hit_rate fell, you are
   likely discarding real sites — prefer reverting or trying a different parameter.
8. If n_sites is collapsing and recall is dropping, relax stringency (lower
   min_crosslink_events, raise merge_distance_nt) to recover sensitivity.

Respond ONLY with JSON:
{{"reasoning": "{reasoning_instr}",
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
