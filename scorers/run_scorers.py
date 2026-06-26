import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

from agent.logging_config import setup_logger
from pipeline.configs import workflow_paths


logger = setup_logger("scorer")


def load_bed(path):
    """Load a BED-like file, keeping only the first six standard BED columns."""
    try:
        df = pd.read_csv(path, sep="\t", header=None)
        for i in range(len(df.columns), 6):
            df[i] = "."
        df = df.iloc[:, :6]
        df.columns = ["chrom", "start", "end", "name", "score", "strand"]
        df["start"] = df["start"].astype(int)
        df["end"] = df["end"].astype(int)
        df = df[df["start"] < df["end"]]
        df["score"] = pd.to_numeric(df["score"], errors="coerce")
        logger.info(
            "Loaded %d sites from %s (strand sample: %s)",
            len(df),
            path,
            df["strand"].unique()[:3],
        )
        return df
    except (pd.errors.EmptyDataError, FileNotFoundError) as exc:
        logger.warning("Empty or missing bed: %s (%s)", path, exc)
        return pd.DataFrame(columns=["chrom", "start", "end", "name", "score", "strand"])


def _write_valid_bed(path, suffix, tmp_dir):
    df = load_bed(path)
    safe_name = str(path).replace("\\", "_").replace("/", "_").replace(":", "_")
    Path(tmp_dir).mkdir(parents=True, exist_ok=True)
    tmp = str(Path(tmp_dir) / f"{safe_name}.{suffix}.tmp")
    df[["chrom", "start", "end", "name", "score", "strand"]].to_csv(
        tmp,
        sep="\t",
        header=False,
        index=False,
    )
    return tmp, len(df)


def overlap_fraction(query_bed, database_bed, tmp_dir):
    """Fraction of valid query intervals with at least one database overlap."""
    tmp_query, total = _write_valid_bed(query_bed, "valid", tmp_dir)
    if total == 0:
        return 0.0
    result = subprocess.run(
        ["bedtools", "intersect", "-a", tmp_query, "-b", database_bed, "-u"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("bedtools intersect failed: %s", result.stderr.strip())
        return None
    out = result.stdout.strip()
    hits = len(out.split("\n")) if out else 0
    return round(hits / total, 4)


def replicate_agreement(sites_bed, rep_region_files, tmp_dir):
    """Fraction of final binding sites overlapping PureCLIP regions from all replicates."""
    if len(rep_region_files) < 2:
        logger.warning("Fewer than 2 replicate files; agreement undefined")
        return None

    try:
        tmp_sites, total_sites = _write_valid_bed(sites_bed, "agreement", tmp_dir)
        if total_sites == 0:
            return 0.0

        p = subprocess.run(
            ["bedtools", "intersect", "-a", tmp_sites, "-b", rep_region_files[0], "-u"],
            capture_output=True,
            text=True,
            check=True,
        )
        out = p.stdout

        for rep_file in rep_region_files[1:]:
            p = subprocess.run(
                ["bedtools", "intersect", "-a", "-", "-b", rep_file, "-u"],
                input=out,
                capture_output=True,
                text=True,
                check=True,
            )
            out = p.stdout

        out = out.strip()
        hits = len(out.split("\n")) if out else 0
        agreement = round(hits / total_sites, 4)
        logger.info("Reproducible agreement: %d/%d = %.4f", hits, total_sites, agreement)
        return agreement
    except subprocess.CalledProcessError as exc:
        logger.error("bedtools intersect failed: %s", exc.stderr.strip())
        return 0.0


def _iupac_to_regex(motif):
    iupac = {
        "U": "T",
        "R": "[AG]",
        "Y": "[CT]",
        "N": "[ACGT]",
        "W": "[AT]",
        "S": "[GC]",
        "K": "[GT]",
        "M": "[AC]",
        "B": "[CGT]",
        "D": "[AGT]",
        "H": "[ACT]",
        "V": "[ACG]",
    }
    return "".join(iupac.get(base, base) for base in motif.upper())


def motif_hit_rate(sites_bed, genome_fasta, motif_pattern, flank_nt=15, tmp_dir=None):
    sites = load_bed(sites_bed)
    if len(sites) == 0:
        return 0.0

    expanded = sites.copy()
    expanded["start"] = (expanded["start"] - flank_nt).clip(lower=0)
    expanded["end"] = expanded["end"] + flank_nt

    tmp_root = Path(tmp_dir or Path(sites_bed).parent / "tmp")
    tmp_root.mkdir(parents=True, exist_ok=True)
    tmp_bed = str(tmp_root / "motif_window.bed")
    expanded[["chrom", "start", "end", "name", "score", "strand"]].to_csv(
        tmp_bed,
        sep="\t",
        header=False,
        index=False,
    )

    result = subprocess.run(
        ["bedtools", "getfasta", "-s", "-fi", genome_fasta, "-bed", tmp_bed, "-tab"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("bedtools getfasta failed: %s", result.stderr.strip())
        return None

    seqs = [line.split("\t")[1].upper() for line in result.stdout.strip().split("\n") if line]
    if not seqs:
        return 0.0

    rx = re.compile(_iupac_to_regex(motif_pattern))
    hits = sum(1 for seq in seqs if rx.search(seq))
    rate = round(hits / len(seqs), 4)
    logger.info("Motif hit rate (window +/-%d nt): %d/%d = %.4f", flank_nt, hits, len(seqs), rate)
    return rate


def _load_priors(cfg):
    if cfg.get("priors"):
        return cfg["priors"]
    with open("config/priors.json", "r", encoding="utf-8") as handle:
        return json.load(handle)


def main(config_path, out_path):
    cfg = yaml.safe_load(open(config_path))
    run_logger = setup_logger("scorer_run", f"{out_path}.log")
    run_logger.info("Running scorers with config %s", config_path)
    priors = _load_priors(cfg)
    paths = workflow_paths(cfg)
    tmp_dir = str(Path(paths["results_dir"]) / "tmp")

    sites_bed = paths["binding_sites"]
    genome = cfg["reference"]["genome_fasta"]
    ip_reps = list(cfg["samples"]["ip"].keys())
    rep_region_files = [f"{paths['results_dir']}/ip_{rep}/pureclip_regions.bed" for rep in ip_reps]

    target_motif = next(
        (motif["pattern"] for motif in priors.get("known_motifs", []) if motif["type"] == "target"),
        None,
    )

    report = {
        "run_id": cfg["run_id"],
        "dataset_id": cfg.get("dataset_id"),
        "n_binding_sites": int(len(load_bed(sites_bed))),
        "replicate_agreement": replicate_agreement(sites_bed, rep_region_files, tmp_dir),
        "motif_hit_rate": (
            motif_hit_rate(sites_bed, genome, target_motif, flank_nt=15, tmp_dir=tmp_dir)
            if target_motif
            else None
        ),
    }

    benchmark = cfg.get("benchmark") or {}
    if benchmark.get("top_regions_bed"):
        report["benchmark_region_overlap"] = overlap_fraction(
            sites_bed, benchmark["top_regions_bed"], tmp_dir
        )
        report["benchmark_region_recall"] = overlap_fraction(
            benchmark["top_regions_bed"], sites_bed, tmp_dir
        )
    if benchmark.get("top_crosslinks_bed"):
        report["benchmark_crosslink_overlap"] = overlap_fraction(
            sites_bed, benchmark["top_crosslinks_bed"], tmp_dir
        )

    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    run_logger.info("Wrote score report to %s", out_path)
    run_logger.info("Report: %s", json.dumps(report))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
