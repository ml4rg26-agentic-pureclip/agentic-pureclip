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


def test_optuna_early_stop_after_startup(monkeypatch):
    """A flat objective should trip the shared early-stop, but only past startup."""
    cfg = orr._with_iteration_output(dataset_to_config("RBFOX2_K562"))

    def flat_eval(config, config_path, search_bounds=None):
        return {"reproducibility_score": 0.3, "motif_hit_rate": 0.3, "benchmark_region_recall": 0.3}

    monkeypatch.setattr(orr, "evaluate_config", flat_eval)
    monkeypatch.setattr(orr, "save_config", lambda *a, **k: None)

    study = orr.run_optuna(
        cfg, max_iter=30, weights=DEFAULT_OBJECTIVE_WEIGHTS, seed=1,
        patience=4, improvement_threshold=0.01, startup_trials=10,
    )
    # Must stop early (well under the 30 cap) but never before startup + patience.
    n = len(study.trials)
    assert n < 30, "early-stop never fired on a flat objective"
    assert n >= 10 + 4, f"stopped during/too soon after startup ({n} trials)"


def test_optuna_no_early_stop_when_improving(monkeypatch):
    """A strictly improving objective must run the full budget (no early stop)."""
    cfg = orr._with_iteration_output(dataset_to_config("RBFOX2_K562"))
    n_calls = {"i": 0}

    def rising_eval(config, config_path, search_bounds=None):
        n_calls["i"] += 1
        v = min(0.9, 0.01 * n_calls["i"])  # monotonic climb
        return {"reproducibility_score": v, "motif_hit_rate": v, "benchmark_region_recall": v}

    monkeypatch.setattr(orr, "evaluate_config", rising_eval)
    monkeypatch.setattr(orr, "save_config", lambda *a, **k: None)

    study = orr.run_optuna(
        cfg, max_iter=20, weights=DEFAULT_OBJECTIVE_WEIGHTS, seed=1,
        patience=4, improvement_threshold=0.005, startup_trials=10,
    )
    assert len(study.trials) == 20


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
