# tests/test_agent.py
import os
import pytest
from unittest.mock import patch

# Save the original API key status to determine if we should skip the real API test later.
# Inject a dummy key if it's missing so that importing agentic_pureclip.loop.graph_mock doesn't
# crash with pydantic_core._pydantic_core.ValidationError during test collection.
_original_api_key = os.environ.get("GOOGLE_API_KEY", "")
if not _original_api_key:
    os.environ["GOOGLE_API_KEY"] = "dummy_key_for_tests"

from agentic_pureclip.loop.graph_mock import build_graph, AgentState, CONFIG_PATH
import agentic_pureclip.loop.graph_mock
import yaml
import json
from pathlib import Path

# Provide a helper to construct a clean initial state for tests
def get_initial_state(max_iterations=5, patience=2):
    base_config = {
        "run_id": "test_iter_00",
        "pureclip": {"bandwidth_nt": 50, "merge_distance_nt": 8,
                     "high_precision_mode": False},
        "postprocessing": {"force_width": 9, "min_crosslink_events": 3},
    }
    return {
        "priors": {"target_protein": "TEST", "known_motifs": []},
        "objective_metric": "replicate_agreement",
        "search_bounds": {
            "pureclip": {"merge_distance_nt": [4, 16], "bandwidth_nt": [20, 100]},
            "postprocessing": {"min_crosslink_events": [2, 6]},
        },
        "current_config": base_config,
        "current_iteration": 0,
        "history": [],
        "best_score": 0.0,
        "best_config": base_config,
        "max_iterations": max_iterations,
        "score_improvement_threshold": 0.01,
        "no_improvement_streak": 0,
        "patience": patience,
        "termination_reason": None,
    }

def test_convergence_plateau():
    """Test that plateau mode halts execution due to convergence."""
    with patch.object(agentic_pureclip.loop.graph_mock, "USE_GEMINI", False), \
         patch.object(agentic_pureclip.loop.graph_mock, "SCORE_MODE", "plateau"):
        
        graph = build_graph()
        initial_state = get_initial_state(max_iterations=10)
        
        final_state = graph.invoke(initial_state, {"recursion_limit": 50})
        
        assert final_state["termination_reason"] == "Converged: no improvement"
        assert final_state["current_iteration"] < final_state["max_iterations"]
        assert final_state["no_improvement_streak"] >= final_state["patience"]

def test_hard_cap_always_up():
    """Test that always_up mode halts execution due to hard cap max iterations."""
    with patch.object(agentic_pureclip.loop.graph_mock, "USE_GEMINI", False), \
         patch.object(agentic_pureclip.loop.graph_mock, "SCORE_MODE", "always_up"):
        
        graph = build_graph()
        initial_state = get_initial_state()
        
        final_state = graph.invoke(initial_state, {"recursion_limit": 50})
        
        assert final_state["termination_reason"] == "Hard stop: reached max_iterations"
        assert final_state["current_iteration"] == final_state["max_iterations"]
        # Score should have kept improving
        assert final_state["no_improvement_streak"] == 0

@pytest.mark.integration
def test_real_gemini_api():
    """
    Test the pipeline using the REAL Gemini API.
    This requires a valid GOOGLE_API_KEY in the .env file.
    To run this specific test, use: pytest tests/test_agent.py -k test_real_gemini_api -s
    """
    # Check if the user has changed the default placeholder or invalid key
    if not _original_api_key:
        pytest.skip("Skipping real API test: valid GOOGLE_API_KEY not found in .env")

    with patch.object(agentic_pureclip.loop.graph_mock, "USE_GEMINI", True), \
         patch.object(agentic_pureclip.loop.graph_mock, "SCORE_MODE", "plateau"):
        
        graph = build_graph()
        # We only run 2 iterations to save API quota and time
        initial_state = get_initial_state(max_iterations=2)
        
        final_state = graph.invoke(initial_state, {"recursion_limit": 50})
        
        assert final_state["current_iteration"] == 2
        assert len(final_state["history"]) > 0
