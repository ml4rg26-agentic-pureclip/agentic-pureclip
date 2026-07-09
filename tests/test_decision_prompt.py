"""Tests for the LLM decision prompt, incl. the no-priors ablation (Change 2)."""

from agentic_pureclip.scoring.objective import build_decision_prompt


def _state():
    config = {
        "run_id": "RBFOX2_iter_01",
        "pureclip": {
            "bandwidth_nt": 50,
            "merge_distance_nt": 8,
            "high_precision_mode": False,
            "use_input_covariate": True,
        },
        "postprocessing": {
            "force_width": 9,
            "cluster_gap_width": 8,
            "min_region_length_nt": 5,
            "min_crosslink_events": 3,
        },
        "priors": {
            "target_protein": "RBFOX2",
            "known_motifs": ["UGCAUG"],
            "preferred_binding": "intron",
            "expected_footprint_width_nt": 9,
        },
    }
    return {
        "current_config": config,
        "priors": config["priors"],
        "history": [],
        "search_bounds": {
            "pureclip": {"bandwidth_nt": [20, 100], "merge_distance_nt": [4, 16]},
            "postprocessing": {"min_crosslink_events": [2, 6]},
        },
    }


def _report():
    return {
        "reproducibility_score": 0.4,
        "motif_hit_rate": 0.3,
        "benchmark_region_recall": 0.2,
        "n_binding_sites": 500,
    }


# Prior-specific strings that MUST leak in the default prompt and MUST be absent
# in the no-priors ablation.
PRIOR_MARKERS = ["RBFOX2", "UGCAUG", "intron", "PRIOR KNOWLEDGE (use this"]


def test_default_prompt_includes_priors():
    prompt = build_decision_prompt(_state(), _report())
    for marker in PRIOR_MARKERS:
        assert marker in prompt, f"expected {marker!r} in the default prompt"


def test_no_priors_prompt_withholds_biology():
    prompt = build_decision_prompt(_state(), _report(), include_priors=False)
    for marker in PRIOR_MARKERS:
        assert marker not in prompt, f"{marker!r} leaked into the no-priors prompt"
    # The shared game must remain visible in both arms.
    assert "SEARCH BOUNDS" in prompt
    assert "COMPOSITE" in prompt
    assert "withheld for this run" in prompt


def test_no_priors_still_valid_json_instruction():
    """Both arms must still ask for the reasoning/changes JSON contract."""
    prompt = build_decision_prompt(_state(), _report(), include_priors=False)
    assert '"reasoning"' in prompt
    assert '"changes"' in prompt
