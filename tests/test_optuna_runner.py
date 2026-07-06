import agentic_pureclip.loop.optuna_runner as orr
from agentic_pureclip.scoring.objective import DEFAULT_OBJECTIVE_WEIGHTS
from agentic_pureclip.pipeline.configs import DEFAULT_SEARCH_BOUNDS
from agentic_pureclip.pipeline.datasets import dataset_to_config


def test_optuna_runs_budget_and_respects_bounds(monkeypatch):
    """Optuna should run exactly n_trials evaluations, all within the search bounds."""
    cfg = orr._with_iteration_output(dataset_to_config("RBFOX2_K562"))
    seen = []

    def fake_eval(config, config_path, search_bounds=None):
        # A toy objective peaking at bandwidth_nt=60 so TPE has a gradient to follow.
        bw = config["pureclip"]["bandwidth_nt"]
        seen.append(config["pureclip"]["bandwidth_nt"])
        return {
            "replicate_agreement": max(0.0, 1 - abs(bw - 60) / 100),
            "reproducibility_score": max(0.0, 1 - abs(bw - 60) / 100),
            "motif_hit_rate": 0.2,
            "benchmark_region_recall": 0.1,
        }

    monkeypatch.setattr(orr, "evaluate_config", fake_eval)
    monkeypatch.setattr(orr, "save_config", lambda *a, **k: None)  # don't touch disk

    study = orr.run_optuna(cfg, max_iter=8, weights=DEFAULT_OBJECTIVE_WEIGHTS, seed=1)

    assert len(study.trials) == 8
    assert len(seen) == 8
    for bw in seen:
        low, high = DEFAULT_SEARCH_BOUNDS["pureclip"]["bandwidth_nt"]
        assert low <= bw <= high
    # Best trial must be a real (finite) objective value.
    assert study.best_value > 0


def test_optuna_applies_bool_params(monkeypatch):
    """high_precision_mode / use_input_covariate are applied as booleans, not ints."""
    cfg = orr._with_iteration_output(dataset_to_config("RBFOX2_K562"))
    captured = {}

    def fake_eval(config, config_path, search_bounds=None):
        captured["hp"] = config["pureclip"]["high_precision_mode"]
        captured["ic"] = config["pureclip"]["use_input_covariate"]
        return {"reproducibility_score": 0.1, "motif_hit_rate": 0.1, "benchmark_region_recall": 0.1}

    monkeypatch.setattr(orr, "evaluate_config", fake_eval)
    monkeypatch.setattr(orr, "save_config", lambda *a, **k: None)

    orr.run_optuna(cfg, max_iter=1, weights=DEFAULT_OBJECTIVE_WEIGHTS, seed=1)
    assert isinstance(captured["hp"], bool)
    assert isinstance(captured["ic"], bool)
