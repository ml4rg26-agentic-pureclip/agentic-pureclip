import pytest

from pipeline.configs import (
    ConfigValidationError,
    DEFAULT_SEARCH_BOUNDS,
    apply_decision_changes,
    load_config,
    validate_config,
)
from pipeline.datasets import dataset_to_config, list_datasets


def test_default_config_validates():
    cfg = load_config("config/run_config.yaml")
    validate_config(cfg, search_bounds=DEFAULT_SEARCH_BOUNDS)


def test_dataset_registry_configs_validate_without_file_checks():
    assert "RBFOX2_K562" in list_datasets()
    for name in list_datasets():
        cfg = dataset_to_config(name)
        validate_config(cfg, search_bounds=DEFAULT_SEARCH_BOUNDS)


def test_decision_rejects_out_of_bounds_value():
    cfg = load_config("config/run_config.yaml")
    with pytest.raises(ConfigValidationError):
        apply_decision_changes(
            cfg,
            {"pureclip": {"bandwidth_nt": 1000}},
            search_bounds=DEFAULT_SEARCH_BOUNDS,
        )


def test_decision_rejects_unsupported_section():
    cfg = load_config("config/run_config.yaml")
    with pytest.raises(ConfigValidationError):
        apply_decision_changes(
            cfg,
            {"reference": {"genome_fasta": 1}},
            search_bounds=DEFAULT_SEARCH_BOUNDS,
        )


def test_decision_rejects_non_numeric_value():
    cfg = load_config("config/run_config.yaml")
    with pytest.raises(ConfigValidationError):
        apply_decision_changes(
            cfg,
            {"pureclip": {"bandwidth_nt": "wide"}},
            search_bounds=DEFAULT_SEARCH_BOUNDS,
        )
