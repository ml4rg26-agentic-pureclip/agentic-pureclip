import os
import json

# ChatOpenAI is constructed at import time; give it a dummy key.
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy_key_for_tests")

import agent.graph as g
from pipeline.datasets import dataset_to_config


def _state():
    cfg = g._with_iteration_output(dataset_to_config("RBFOX2_K562"))
    return {
        "priors": cfg["priors"],
        "objective_metric": "replicate_agreement",
        "search_bounds": g.DEFAULT_SEARCH_BOUNDS,
        "current_config": cfg,
        "current_iteration": 1,
        "history": [],
        "best_score": 0.0,
        "best_config": cfg,
        "max_iterations": 5,
        "score_improvement_threshold": 0.01,
        "no_improvement_streak": 0,
        "patience": 10,
        "termination_reason": None,
    }


class _Resp:
    def __init__(self, content):
        self.content = content


def test_repeat_proposal_retries_then_gives_up(monkeypatch):
    """A repeated parameter set must not crash the run — it should retry and converge."""
    state = _state()
    cur_bw = state["current_config"]["pureclip"]["bandwidth_nt"]

    class FakeLLM:
        calls = 0

        def invoke(self, prompt):
            FakeLLM.calls += 1
            # No-op change reproduces the current (already-tried) parameter set.
            return _Resp(json.dumps({"reasoning": "revert", "changes": {"pureclip": {"bandwidth_nt": cur_bw}}}))

    monkeypatch.setattr(g, "llm", FakeLLM())
    decision, new_config = g._propose_next_config(
        state, {"replicate_agreement": 0.1, "motif_hit_rate": 0.1}, 0.25
    )
    assert new_config is None
    assert decision is not None
    assert FakeLLM.calls == g.MAX_DECISION_RETRIES


def test_valid_proposal_is_accepted(monkeypatch):
    state = _state()
    cur_bw = state["current_config"]["pureclip"]["bandwidth_nt"]
    new_bw = cur_bw + 5 if cur_bw + 5 <= 100 else cur_bw - 5

    class FakeLLM:
        def invoke(self, prompt):
            return _Resp(json.dumps({"reasoning": "widen", "changes": {"pureclip": {"bandwidth_nt": new_bw}}}))

    monkeypatch.setattr(g, "llm", FakeLLM())
    decision, new_config = g._propose_next_config(
        state, {"replicate_agreement": 0.1, "motif_hit_rate": 0.1}, 0.25
    )
    assert new_config is not None
    assert new_config["pureclip"]["bandwidth_nt"] == new_bw
