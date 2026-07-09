"""Tests for the overnight batch runner's result collection (Change 4)."""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run" / "overnight_batch.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("overnight_batch", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_report(path: Path, run_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "run_id": run_id,
        "reproducibility_score": 0.5,
        "motif_hit_rate": 0.4,
        "benchmark_region_recall": 0.3,
        "n_binding_sites": 200,
    }))


def test_collect_iterations_finds_nested_llm_reports(tmp_path, monkeypatch):
    """LLM reports live two levels down (timestamped session subdir); Optuna one."""
    mod = _load_module()
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    results_root = "results/overnight/job1"
    job_dir = tmp_path / results_root

    # Optuna-style: one level under the job root.
    _write_report(job_dir / "RBFOX2_iter_01" / "score_report.json", "RBFOX2_iter_01")
    # LLM-style: nested under a timestamped session subdir (two levels).
    _write_report(job_dir / "RBFOX2_K562_20260709_010101" / "RBFOX2_iter_02" / "score_report.json",
                  "RBFOX2_iter_02")

    recs = mod.collect_iterations(results_root, "job1", "RBFOX2_K562", mod.DEFAULT_OBJECTIVE_WEIGHTS)
    run_ids = {r["run_id"] for r in recs}
    assert run_ids == {"RBFOX2_iter_01", "RBFOX2_iter_02"}, run_ids
    # Iterations parsed and sorted.
    assert [r["iteration"] for r in recs] == [1, 2]
    assert all(r["composite"] is not None for r in recs)


def test_collect_iterations_dedups_by_run_id(tmp_path, monkeypatch):
    """A run_id appearing twice collapses to a single (newest) record."""
    mod = _load_module()
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    results_root = "results/overnight/job2"
    job_dir = tmp_path / results_root
    _write_report(job_dir / "a" / "score_report.json", "QKI_iter_00")
    _write_report(job_dir / "b" / "nested" / "score_report.json", "QKI_iter_00")

    recs = mod.collect_iterations(results_root, "job2", "QKI_K562", mod.DEFAULT_OBJECTIVE_WEIGHTS)
    assert len(recs) == 1
    assert recs[0]["run_id"] == "QKI_iter_00"
