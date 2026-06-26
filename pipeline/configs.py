from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import yaml


DEFAULT_SEARCH_BOUNDS = {
    "pureclip": {
        "merge_distance_nt": [4, 16],
        "bandwidth_nt": [20, 100],
    },
    "postprocessing": {
        "min_crosslink_events": [2, 6],
    },
}


class ConfigValidationError(ValueError):
    """Raised when a run config or LLM decision is not safe to execute."""


def load_config(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    return cfg


def save_config(config: dict[str, Any], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)


def results_dir(config: dict[str, Any]) -> str:
    output = config.get("output") or {}
    return str(output.get("results_dir") or "results").replace("\\", "/").rstrip("/")


def score_report_path(config: dict[str, Any]) -> str:
    output = config.get("output") or {}
    return str(output.get("score_report") or f"{results_dir(config)}/score_report.json").replace("\\", "/")


def workflow_paths(config: dict[str, Any]) -> dict[str, Any]:
    out = results_dir(config)
    reps = list(config["samples"]["ip"].keys())
    return {
        "results_dir": out,
        "merged_bam": f"{out}/merged_ip.bam",
        "merged_bai": f"{out}/merged_ip.bam.bai",
        "merged_sites": f"{out}/PureCLIP.crosslink_sites.bed",
        "merged_regions": f"{out}/PureCLIP.binding_regions.bed",
        "binding_sites": f"{out}/binding_sites.reproducible.bed",
        "score_report": score_report_path(config),
        "replicate_regions": [f"{out}/ip_{rep}/pureclip_regions.bed" for rep in reps],
        "replicate_sites": [f"{out}/ip_{rep}/pureclip_sites.bed" for rep in reps],
    }


def sample_bams(config: dict[str, Any], include_input_control: bool = True) -> list[str]:
    bams: list[str] = []
    for rep in config.get("samples", {}).get("ip", {}).values():
        bam = rep.get("bam")
        if bam:
            bams.append(str(bam))
    if include_input_control:
        for rep in config.get("samples", {}).get("input_control", {}).values():
            bam = rep.get("bam")
            if bam:
                bams.append(str(bam))
    return bams


def _require_mapping(config: dict[str, Any], key: str) -> dict[str, Any]:
    value = config.get(key)
    if not isinstance(value, dict):
        raise ConfigValidationError(f"Missing or invalid mapping section: {key}")
    return value


def _require_int(section: dict[str, Any], section_name: str, key: str, minimum: int | None = None) -> int:
    value = section.get(key)
    if not isinstance(value, int):
        raise ConfigValidationError(f"{section_name}.{key} must be an integer")
    if minimum is not None and value < minimum:
        raise ConfigValidationError(f"{section_name}.{key} must be >= {minimum}")
    return value


def validate_config(
    config: dict[str, Any],
    *,
    search_bounds: dict[str, dict[str, list[int]]] | None = None,
    require_files: bool = False,
    require_bai: bool = False,
) -> None:
    if not isinstance(config.get("run_id"), str) or not config["run_id"]:
        raise ConfigValidationError("run_id must be a non-empty string")
    if not isinstance(config.get("target_protein"), str) or not config["target_protein"]:
        raise ConfigValidationError("target_protein must be a non-empty string")

    samples = _require_mapping(config, "samples")
    ip = samples.get("ip")
    if not isinstance(ip, dict) or len(ip) < 2:
        raise ConfigValidationError("samples.ip must define at least two IP replicates")
    for rep, spec in ip.items():
        if not isinstance(spec, dict) or not spec.get("bam"):
            raise ConfigValidationError(f"samples.ip.{rep}.bam is required")

    input_control = samples.get("input_control")
    if not isinstance(input_control, dict) or not input_control:
        raise ConfigValidationError("samples.input_control must define at least one control replicate")
    for rep, spec in input_control.items():
        if not isinstance(spec, dict) or not spec.get("bam"):
            raise ConfigValidationError(f"samples.input_control.{rep}.bam is required")

    reference = _require_mapping(config, "reference")
    if not reference.get("genome_fasta"):
        raise ConfigValidationError("reference.genome_fasta is required")

    pureclip = _require_mapping(config, "pureclip")
    post = _require_mapping(config, "postprocessing")
    resources = _require_mapping(config, "resources")

    _require_int(pureclip, "pureclip", "bandwidth_nt", 1)
    _require_int(pureclip, "pureclip", "merge_distance_nt", 0)
    for key in ("high_precision_mode", "use_input_covariate"):
        if not isinstance(pureclip.get(key), bool):
            raise ConfigValidationError(f"pureclip.{key} must be a boolean")

    _require_int(post, "postprocessing", "force_width", 1)
    _require_int(post, "postprocessing", "min_region_length_nt", 0)
    _require_int(post, "postprocessing", "min_crosslink_events", 0)
    _require_int(resources, "resources", "threads", 1)

    if search_bounds:
        _validate_values_within_bounds(config, search_bounds)

    if require_files:
        paths = [reference["genome_fasta"], *sample_bams(config)]
        annotation = reference.get("annotation_gtf")
        if annotation:
            paths.append(annotation)
        benchmark = config.get("benchmark") or {}
        for key in (
            "top_regions_bed",
            "top_crosslinks_bed",
            "top_genes",
            "biotypes_tsv",
            "genotypes_tsv",
        ):
            if benchmark.get(key):
                paths.append(benchmark[key])
        for path in paths:
            if not Path(path).exists():
                raise ConfigValidationError(f"Required input does not exist: {path}")
        if require_bai:
            for bam in sample_bams(config):
                bai = f"{bam}.bai"
                if not Path(bai).exists():
                    raise ConfigValidationError(f"Missing BAM index: {bai}")


def _validate_values_within_bounds(config: dict[str, Any], bounds: dict[str, dict[str, list[int]]]) -> None:
    for section, params in bounds.items():
        values = config.get(section, {})
        for key, (low, high) in params.items():
            value = values.get(key)
            if value is None:
                raise ConfigValidationError(f"{section}.{key} is missing")
            if not low <= value <= high:
                raise ConfigValidationError(f"{section}.{key}={value} outside bounds [{low}, {high}]")


def tunable_snapshot(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "pureclip": {
            "bandwidth_nt": config["pureclip"]["bandwidth_nt"],
            "merge_distance_nt": config["pureclip"]["merge_distance_nt"],
            "high_precision_mode": config["pureclip"]["high_precision_mode"],
            "use_input_covariate": config["pureclip"]["use_input_covariate"],
        },
        "postprocessing": {
            "force_width": config["postprocessing"]["force_width"],
            "min_region_length_nt": config["postprocessing"]["min_region_length_nt"],
            "min_crosslink_events": config["postprocessing"]["min_crosslink_events"],
        },
    }


def tunable_signature(config: dict[str, Any]) -> str:
    return json.dumps(tunable_snapshot(config), sort_keys=True)


def tried_signatures(history: list[dict[str, Any]]) -> set[str]:
    signatures = set()
    for record in history:
        cfg = record.get("config", {})
        if "pureclip" in cfg and "postprocessing" in cfg:
            signatures.add(json.dumps(cfg, sort_keys=True))
    return signatures


def apply_decision_changes(
    current_config: dict[str, Any],
    changes: dict[str, Any],
    *,
    search_bounds: dict[str, dict[str, list[int]]] | None = None,
    previous_signatures: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(changes, dict):
        raise ConfigValidationError("LLM decision changes must be a mapping")

    bounds = search_bounds or DEFAULT_SEARCH_BOUNDS
    allowed_sections = set(bounds)
    new_config = copy.deepcopy(current_config)

    for section, section_changes in changes.items():
        if section not in allowed_sections:
            raise ConfigValidationError(f"LLM attempted to change unsupported section: {section}")
        if not isinstance(section_changes, dict):
            raise ConfigValidationError(f"LLM changes for {section} must be a mapping")
        for key, value in section_changes.items():
            if key not in bounds[section]:
                raise ConfigValidationError(f"LLM attempted to change unsupported parameter: {section}.{key}")
            low, high = bounds[section][key]
            if not isinstance(value, int):
                raise ConfigValidationError(f"LLM value for {section}.{key} must be an integer")
            if not low <= value <= high:
                raise ConfigValidationError(f"LLM value for {section}.{key}={value} outside bounds [{low}, {high}]")
            new_config[section][key] = value

    validate_config(new_config, search_bounds=bounds)

    if previous_signatures and tunable_signature(new_config) in previous_signatures:
        raise ConfigValidationError("LLM proposed a parameter set that was already tried")
    return new_config
