from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.motifs import (
    MotifEntry,
    available_databases,
    get_best_motif,
    load_all_motifs,
)


GENOME_FASTA = "data/GRCh38.primary_assembly.genome.fa/GRCh38.primary_assembly.genome.fa"

# Hardcoded fallback motifs when no PWM database is available
FALLBACK_MOTIFS: dict[str, list[dict[str, str]]] = {
    "RBFOX2": [{"pattern": "UGCAUG", "type": "target"}],
    "QKI": [{"pattern": "ACUAAY", "type": "target"}],
    "PUM1": [{"pattern": "UGUANAUA", "type": "target"}],
}

# Alias for backward compatibility
KNOWN_MOTIFS = FALLBACK_MOTIFS


@dataclass
class DatasetSpec:
    name: str
    target_protein: str
    cell_line: str
    ip_rep1_bam: str
    ip_rep2_bam: str
    input_bam: str
    top_regions_bed: str | None = None
    top_crosslinks_bed: str | None = None
    top_genes: str | None = None
    biotypes_tsv: str | None = None
    genotypes_tsv: str | None = None
    # Motif database preferences
    motif_databases: list[str] = field(default_factory=lambda: ["mCrossBase", "ATtRACT", "CISBP-RNA"])


DATASETS: dict[str, DatasetSpec] = {
    "RBFOX2_K562": DatasetSpec(
        name="RBFOX2_K562",
        target_protein="RBFOX2",
        cell_line="K562",
        ip_rep1_bam="data/RBFOX2_K562/bam/ip_rep1_v1/ENCFF537RYR.bam",
        ip_rep2_bam="data/RBFOX2_K562/bam/ip_rep2_v1/ENCFF296GDR.bam",
        input_bam="data/RBFOX2_K562/bam/smi_v1/ENCFF212IIR.bam",
        top_regions_bed="data/RBFOX2_K562/top_regions/regions.bed6",
        top_crosslinks_bed="data/RBFOX2_K562/top_crosslink_sites/crosslinks.bed6",
        top_genes="data/RBFOX2_K562/top_genes/list.txt",
        biotypes_tsv="data/RBFOX2_K562/biotypes_genetypes/biotypes_proportions.tsv",
        genotypes_tsv="data/RBFOX2_K562/biotypes_genetypes/genetypes_proportions.tsv",
    ),
    "RBFOX2_HepG2": DatasetSpec(
        name="RBFOX2_HepG2",
        target_protein="RBFOX2",
        cell_line="HepG2",
        ip_rep1_bam="data/RBFOX2_HepG2/bam/ip_rep1_v1/ENCFF239CML.bam",
        ip_rep2_bam="data/RBFOX2_HepG2/bam/ip_rep2_v1/ENCFF170YQV.bam",
        input_bam="data/RBFOX2_HepG2/bam/smi_v1/ENCFF515BTB.bam",
        top_regions_bed="data/RBFOX2_HepG2/top_regions/regions.bed6",
        top_crosslinks_bed="data/RBFOX2_HepG2/top_crosslink_sites/crosslinks.bed6",
        top_genes="data/RBFOX2_HepG2/top_genes/list.txt",
        biotypes_tsv="data/RBFOX2_HepG2/biotypes_genetypes/biotypes_proportions.tsv",
        genotypes_tsv="data/RBFOX2_HepG2/biotypes_genetypes/genetypes_proportions.tsv",
    ),
    "QKI_K562": DatasetSpec(
        name="QKI_K562",
        target_protein="QKI",
        cell_line="K562",
        ip_rep1_bam="data/QKI_K562/bam/ip_rep1_v1/ENCFF698BKX.bam",
        ip_rep2_bam="data/QKI_K562/bam/ip_rep2_v1/ENCFF012WMS.bam",
        input_bam="data/QKI_K562/bam/smi_v1/ENCFF070RME.bam",
        top_regions_bed="data/QKI_K562/top_regions/regions.bed6",
        top_crosslinks_bed="data/QKI_K562/top_crosslink_sites/crosslinks.bed6",
        top_genes="data/QKI_K562/top_genes/list.txt",
        biotypes_tsv="data/QKI_K562/biotypes_genetypes/biotypes_proportions.tsv",
        genotypes_tsv="data/QKI_K562/biotypes_genetypes/genetypes_proportions.tsv",
    ),
    "QKI_HepG2": DatasetSpec(
        name="QKI_HepG2",
        target_protein="QKI",
        cell_line="HepG2",
        ip_rep1_bam="data/QKI_HepG2/bam/ip_rep1_v1/ENCFF567ADV.bam",
        ip_rep2_bam="data/QKI_HepG2/bam/ip_rep2_v1/ENCFF862YVK.bam",
        input_bam="data/QKI_HepG2/bam/smi_v1/ENCFF015GLL.bam",
        top_regions_bed="data/QKI_HepG2/top_regions/regions.bed6",
        top_crosslinks_bed="data/QKI_HepG2/top_crosslink_sites/crosslinks.bed6",
        top_genes="data/QKI_HepG2/top_genes/list.txt",
        biotypes_tsv="data/QKI_HepG2/biotypes_genetypes/biotypes_proportions.tsv",
        genotypes_tsv="data/QKI_HepG2/biotypes_genetypes/genetypes_proportions.tsv",
    ),
    "PUM1_K562": DatasetSpec(
        name="PUM1_K562",
        target_protein="PUM1",
        cell_line="K562",
        ip_rep1_bam="data/PUM1_K562/bam/ip_rep1_v1/ENCFF064COB.bam",
        ip_rep2_bam="data/PUM1_K562/bam/ip_rep2_v1/ENCFF583QFB.bam",
        input_bam="data/PUM1_K562/bam/smi_v1/ENCFF222HEX.bam",
        top_regions_bed="data/PUM1_K562/top_regions/regions.bed6",
        top_crosslinks_bed="data/PUM1_K562/top_crosslink_sites/crosslinks.bed6",
        top_genes="data/PUM1_K562/top_genes/list.txt",
        biotypes_tsv="data/PUM1_K562/biotypes_genetypes/biotypes_proportions.tsv",
        genotypes_tsv="data/PUM1_K562/biotypes_genetypes/genetypes_proportions.tsv",
    ),
    "ENCORE_RBFOX2_K562": DatasetSpec(
        name="ENCORE_RBFOX2_K562",
        target_protein="RBFOX2",
        cell_line="K562",
        ip_rep1_bam="data/ENCORE_RBFOX2_K562/bam_eclip_rep1_1/ENCFF537RYR.bam",
        ip_rep2_bam="data/ENCORE_RBFOX2_K562/bam_eclip_rep2_1/ENCFF296GDR.bam",
        input_bam="data/ENCORE_RBFOX2_K562/bam_smi_rep1_1/ENCFF212IIR.bam",
    ),
}


def list_datasets() -> list[str]:
    return sorted(DATASETS)


def get_dataset(name: str) -> DatasetSpec:
    try:
        return DATASETS[name]
    except KeyError as exc:
        available = ", ".join(list_datasets())
        raise KeyError(f"Unknown dataset {name!r}. Available datasets: {available}") from exc


def _resolve_motifs(
    target_protein: str,
    cell_line: str | None = None,
    databases: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Resolve known motifs for a target protein.

    Priority:
    1. Load PWMs from available motif databases (e.g. mCrossBase)
    2. Fall back to hardcoded IUPAC consensus
    """
    db_list = databases or ["mCrossBase", "ATtRACT", "CISBP-RNA"]
    available_dbs = set(available_databases())

    resolved: list[dict[str, Any]] = []

    for db in db_list:
        if db not in available_dbs:
            continue
        all_for_rbp = load_all_motifs(target_protein, cell_line, databases=[db])
        if db in all_for_rbp:
            for entry in all_for_rbp[db]:
                motif_dict: dict[str, Any] = {
                    "pattern": entry.pattern,
                    "type": entry.type,
                    "source_database": db,
                }
                if entry.pwm is not None:
                    motif_dict["motif_id"] = entry.pwm.motif_id
                    motif_dict["consensus"] = entry.pwm.consensus
                resolved.append(motif_dict)
            break  # Use the first database that has data

    if not resolved:
        # Fallback to hardcoded
        fallback = FALLBACK_MOTIFS.get(target_protein, [])
        resolved = [dict(m) for m in fallback]

    return resolved


def dataset_to_config(
    name: str,
    *,
    results_root: str = "results/datasets",
    genome_fasta: str = GENOME_FASTA,
    use_input_covariate: bool = True,
) -> dict[str, Any]:
    spec = get_dataset(name)
    run_id = f"{spec.name}_iter_00"
    benchmark = {
        key: value
        for key, value in {
            "top_regions_bed": spec.top_regions_bed,
            "top_crosslinks_bed": spec.top_crosslinks_bed,
            "top_genes": spec.top_genes,
            "biotypes_tsv": spec.biotypes_tsv,
            "genotypes_tsv": spec.genotypes_tsv,
        }.items()
        if value
    }

    known_motifs = _resolve_motifs(
        spec.target_protein,
        cell_line=spec.cell_line,
        databases=spec.motif_databases,
    )

    return {
        "run_id": run_id,
        "dataset_id": spec.name,
        "target_protein": spec.target_protein,
        "cell_line": spec.cell_line,
        "clip_protocol": "eCLIP",
        "samples": {
            "ip": {
                "rep1": {"bam": spec.ip_rep1_bam},
                "rep2": {"bam": spec.ip_rep2_bam},
            },
            "input_control": {
                "rep1": {"bam": spec.input_bam},
            },
        },
        "reference": {
            "genome_fasta": genome_fasta,
            "annotation_gtf": None,
        },
        "priors": {
            "target_protein": spec.target_protein,
            "clip_protocol": "eCLIP",
            "expected_footprint_width_nt": 9,
            "known_motifs": known_motifs,
            "primary_objective_metric": "replicate_agreement",
        },
        "pureclip": {
            "bandwidth_nt": 50,
            "merge_distance_nt": 8,
            "high_precision_mode": False,
            "use_input_covariate": use_input_covariate,
            "use_cl_motif_covariate": False,
            "cl_motif_file": None,
        },
        "postprocessing": {
            "force_width": 9,
            "cluster_gap_width": 8,
            "min_region_length_nt": 3,
            "min_crosslink_events": 3,
        },
        "reproducibility": {
            "percentile_threshold": 10,
            "min_crosslink_events_floor": 2,
            "min_replicates_passing": 2,
        },
        "benchmark": benchmark,
        "output": {
            "results_dir": str(Path(results_root) / spec.name).replace("\\", "/"),
        },
        "resources": {
            "max_memory_gb": 16,
            "threads": 8,
        },
    }

