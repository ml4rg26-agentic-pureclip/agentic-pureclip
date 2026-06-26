import json
import random
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

from agent.logging_config import setup_logger
from pipeline.configs import workflow_paths
from pipeline.motifs import (
    MotifPWM,
    iupac_to_regex,
    load_all_motifs,
    scan_sequence_with_pwm,
)


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


def _genome_sizes(genome_fasta, tmp_dir):
    """Write a bedtools genome file (chrom\\tsize) from the FASTA .fai index."""
    fai = f"{genome_fasta}.fai"
    if not Path(fai).exists():
        logger.warning("No .fai index for %s; cannot build chance background", genome_fasta)
        return None
    Path(tmp_dir).mkdir(parents=True, exist_ok=True)
    sizes = str(Path(tmp_dir) / "genome.sizes")
    with open(fai) as handle, open(sizes, "w") as out:
        for line in handle:
            parts = line.split("\t")
            if len(parts) >= 2:
                out.write(f"{parts[0]}\t{parts[1]}\n")
    return sizes


def _shuffle_bed(valid_sites_bed, genome_sizes, tmp_dir, seed):
    """Randomly reposition intervals, each kept on its own chromosome (-chrom)."""
    out = str(Path(tmp_dir) / f"shuffled_{seed}.bed")
    result = subprocess.run(
        ["bedtools", "shuffle", "-i", valid_sites_bed, "-g", genome_sizes,
         "-chrom", "-seed", str(seed)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        logger.error("bedtools shuffle failed: %s", result.stderr.strip())
        return None
    Path(out).write_text(result.stdout)
    return out


def replicate_reproducibility(sites_bed, rep_region_files, genome_sizes, tmp_dir,
                              observed, n_shuffles=3):
    """Chance-correct replicate agreement.

    The raw agreement (fraction of sites overlapping every replicate's regions)
    is inflated when sites are few and broad, because broad intervals overlap by
    chance. We estimate that chance level by shuffling the sites (each kept on its
    own chromosome) and re-measuring agreement, then report:

      * expected   — mean agreement of shuffled sites
      * enrichment — observed / expected
      * score      — (observed - expected) / (1 - expected), clamped to [0, 1]

    ``score`` is a chance-corrected, [0, 1]-bounded reproducibility that does not
    reward collapsing to a handful of broad, trivially-overlapping sites.
    """
    if observed is None or genome_sizes is None:
        return None
    valid_sites, n = _write_valid_bed(sites_bed, "repro", tmp_dir)
    if n == 0:
        return {"observed": observed, "expected": None, "enrichment": None, "score": None}

    expectations = []
    for seed in range(1, n_shuffles + 1):
        shuffled = _shuffle_bed(valid_sites, genome_sizes, tmp_dir, seed)
        if shuffled is None:
            continue
        expectations.append(replicate_agreement(shuffled, rep_region_files, tmp_dir) or 0.0)
    if not expectations:
        return {"observed": observed, "expected": None, "enrichment": None, "score": None}

    expected = round(sum(expectations) / len(expectations), 4)
    enrichment = round(observed / expected, 4) if expected > 0 else None
    score = (observed - expected) / (1 - expected) if expected < 1 else 0.0
    score = round(max(0.0, min(1.0, score)), 4)
    logger.info(
        "Reproducibility: observed=%.4f expected=%.4f enrichment=%s score=%.4f",
        observed, expected, enrichment, score,
    )
    return {"observed": observed, "expected": expected, "enrichment": enrichment, "score": score}


def _analyzed_chroms(cfg):
    """Chromosomes the pipeline actually called sites on (for fair benchmarking)."""
    if cfg.get("pureclip", {}).get("learn_on_chr21"):
        return ["chr21"]
    return None


def _restrict_bed_to_chroms(bed_path, chroms, tmp_dir, tag):
    """Subset a BED to the given chromosomes; return original path if no restriction."""
    if not chroms:
        return bed_path
    chromset = set(chroms)
    Path(tmp_dir).mkdir(parents=True, exist_ok=True)
    out = str(Path(tmp_dir) / f"ref_{tag}.bed")
    with open(bed_path) as handle, open(out, "w") as target:
        for line in handle:
            if line.split("\t", 1)[0] in chromset:
                target.write(line)
    return out


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


def _extract_flanking_sequences(sites_bed, genome_fasta, flank_nt=15, tmp_dir=None):
    """Extract flanking sequences around binding sites using bedtools getfasta.

    Returns list of uppercase DNA sequences.
    """
    sites = load_bed(sites_bed)
    if len(sites) == 0:
        return []

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
        return []

    seqs = [line.split("\t")[1].upper() for line in result.stdout.strip().split("\n") if line]
    return seqs


def motif_hit_rate(sites_bed, genome_fasta, motif_pattern, flank_nt=15, tmp_dir=None):
    """Calculate motif hit rate using IUPAC regex (legacy method).

    For PWM-based scoring, use motif_hit_rate_pwm() instead.
    """
    seqs = _extract_flanking_sequences(sites_bed, genome_fasta, flank_nt, tmp_dir)
    if not seqs:
        return 0.0

    rx = re.compile(iupac_to_regex(motif_pattern))
    hits = sum(1 for seq in seqs if rx.search(seq))
    rate = round(hits / len(seqs), 4)
    logger.info("Motif hit rate (IUPAC, window +/-%d nt): %d/%d = %.4f", flank_nt, hits, len(seqs), rate)
    return rate


def _pwm_hit_rate(seqs: list[str], pwm: MotifPWM, threshold: float) -> float:
    """Fraction of sequences with at least one PWM log-odds hit >= threshold."""
    if not seqs:
        return 0.0
    hits = sum(1 for seq in seqs if scan_sequence_with_pwm(seq, pwm, threshold))
    return round(hits / len(seqs), 4)


def _shuffled_sequences(seqs: list[str], seed: int = 0) -> list[str]:
    """Per-sequence character shuffle, preserving each window's base composition.

    Provides a background that controls for the local nucleotide content of the
    binding-site windows, so a motif hit rate can be turned into an enrichment.
    """
    rng = random.Random(seed)
    shuffled = []
    for seq in seqs:
        chars = list(seq)
        rng.shuffle(chars)
        shuffled.append("".join(chars))
    return shuffled


def motif_hit_rate_pwm(
    sites_bed,
    genome_fasta,
    pwms: list[MotifPWM],
    flank_nt=15,
    tmp_dir=None,
    threshold_pct=0.80,
) -> dict[str, float]:
    """Calculate motif hit rate using PWM log-odds scoring.

    For each PWM, extracts flanking sequences around binding sites and
    reports the fraction of sites containing a motif hit above threshold.

    Returns dict of motif_id -> hit_rate.
    """
    seqs = _extract_flanking_sequences(sites_bed, genome_fasta, flank_nt, tmp_dir)
    if not seqs:
        return {}

    results: dict[str, float] = {}
    for pwm in pwms:
        threshold = pwm.match_threshold(threshold_pct)
        rate = _pwm_hit_rate(seqs, pwm, threshold)
        motif_label = pwm.motif_id or pwm.consensus
        logger.info(
            "Motif hit rate (PWM %s, window +/-%d nt, thresh_pct=%.2f): %.4f",
            motif_label, flank_nt, threshold_pct, rate,
        )
        results[motif_label] = rate

    return results


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

    target_protein = cfg.get("target_protein", priors.get("target_protein", ""))
    cell_line = cfg.get("cell_line")

    # ── Motif scoring ─────────────────────────────────────────────────
    known_motifs = priors.get("known_motifs", [])
    target_motifs = [m for m in known_motifs if m.get("type") == "target"]

    # Extract binding-site windows once and build a composition-matched
    # background so hit rates can be reported as enrichment over chance.
    seqs = _extract_flanking_sequences(sites_bed, genome, flank_nt=15, tmp_dir=tmp_dir)
    bg_seqs = _shuffled_sequences(seqs)

    motif_hit_rates: dict[str, float] = {}
    motif_enrichments: dict[str, float] = {}

    # Try PWM log-odds scoring via motif databases
    all_pwm_motifs = load_all_motifs(target_protein, cell_line)
    if all_pwm_motifs and seqs:
        run_logger.info(
            "Found motif databases for %s: %s",
            target_protein,
            list(all_pwm_motifs.keys()),
        )
        for db, entries in all_pwm_motifs.items():
            for entry in entries:
                pwm = entry.pwm
                if pwm is None:
                    continue
                label = pwm.motif_id or pwm.consensus
                threshold = pwm.match_threshold(0.80)
                fg = _pwm_hit_rate(seqs, pwm, threshold)
                bg = _pwm_hit_rate(bg_seqs, pwm, threshold)
                motif_hit_rates[label] = fg
                motif_enrichments[label] = round(fg / bg, 4) if bg > 0 else None
                run_logger.info(
                    "Motif %s (%s): hit_rate=%.4f background=%.4f enrichment=%s",
                    label, db, fg, bg, motif_enrichments[label],
                )

    # Fallback to IUPAC regex if no PWMs are available
    if not motif_hit_rates:
        for motif in target_motifs:
            pattern = motif.get("pattern")
            if pattern:
                rate = motif_hit_rate(
                    sites_bed, genome, pattern, flank_nt=15, tmp_dir=tmp_dir,
                )
                motif_hit_rates[pattern] = rate

    # Aggregate signals for the agent: report the most enriched motif's rate so a
    # single common-but-uninformative motif cannot dominate the headline number.
    if motif_enrichments and any(v is not None for v in motif_enrichments.values()):
        best_label = max(
            (k for k, v in motif_enrichments.items() if v is not None),
            key=lambda k: motif_enrichments[k],
        )
        best_motif_rate = motif_hit_rates[best_label]
        best_enrichment = motif_enrichments[best_label]
    else:
        best_motif_rate = max(motif_hit_rates.values()) if motif_hit_rates else None
        best_enrichment = None

    # ── Reproducibility (chance-corrected) ───────────────────────────
    genome_sizes = _genome_sizes(genome, tmp_dir)
    observed_agreement = replicate_agreement(sites_bed, rep_region_files, tmp_dir)
    repro = replicate_reproducibility(
        sites_bed, rep_region_files, genome_sizes, tmp_dir, observed_agreement
    )

    report = {
        "run_id": cfg["run_id"],
        "dataset_id": cfg.get("dataset_id"),
        "n_binding_sites": int(len(load_bed(sites_bed))),
        "replicate_agreement": observed_agreement,
        "replicate_agreement_expected": repro["expected"] if repro else None,
        "reproducibility_enrichment": repro["enrichment"] if repro else None,
        "reproducibility_score": repro["score"] if repro else None,
        "motif_hit_rate": best_motif_rate,
        "motif_enrichment": best_enrichment,
        "motif_hit_rates_detail": motif_hit_rates if motif_hit_rates else None,
        "motif_enrichments_detail": motif_enrichments if motif_enrichments else None,
    }

    # ── Benchmark vs ENCODE reference, restricted to analyzed chromosomes ──
    # Under chr21 fast mode the genome-wide reference would cap recall at the
    # fraction of reference regions on chr21 (~4.5%), making it meaningless.
    benchmark = cfg.get("benchmark") or {}
    chroms = _analyzed_chroms(cfg)
    if benchmark.get("top_regions_bed"):
        ref = _restrict_bed_to_chroms(benchmark["top_regions_bed"], chroms, tmp_dir, "regions")
        report["benchmark_region_overlap"] = overlap_fraction(sites_bed, ref, tmp_dir)
        report["benchmark_region_recall"] = overlap_fraction(ref, sites_bed, tmp_dir)
    if benchmark.get("top_crosslinks_bed"):
        refx = _restrict_bed_to_chroms(benchmark["top_crosslinks_bed"], chroms, tmp_dir, "xlinks")
        report["benchmark_crosslink_overlap"] = overlap_fraction(sites_bed, refx, tmp_dir)
        report["benchmark_crosslink_recall"] = overlap_fraction(refx, sites_bed, tmp_dir)

    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    run_logger.info("Wrote score report to %s", out_path)
    run_logger.info("Report: %s", json.dumps(report))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
