# scorers/run_scorers.py
import sys
import json
import yaml
import subprocess
import re
import pandas as pd
from agent.logging_config import setup_logger

logger = setup_logger("scorer", "results/logs/scorer.log")


def load_bed(path):
    """Load a BED file, taking only the first 6 standard columns.
    PureCLIP output has an extra annotation column (e.g. [score_CL=...]) at
    the end. We read all columns, then keep only the first 6 by POSITION
    to avoid pandas' usecols/names misalignment.
    """
    try:
        df = pd.read_csv(path, sep="\t", header=None)
        # Pad with missing columns if the BED is malformed
        for i in range(len(df.columns), 6):
            df[i] = "."
        df = df.iloc[:, :6]
        df.columns = ["chrom", "start", "end", "name", "score", "strand"]
        df["start"] = df["start"].astype(int)
        df["end"] = df["end"].astype(int)
        
        # Filter out invalid intervals (e.g., start >= end) which bedtools would drop
        df = df[df["start"] < df["end"]]
        
        df["score"] = pd.to_numeric(df["score"], errors="coerce")
        logger.info("Loaded %d sites from %s (strand sample: %s)",
                    len(df), path, df["strand"].unique()[:3])
        return df
    except (pd.errors.EmptyDataError, FileNotFoundError) as e:
        logger.warning("Empty or missing bed: %s (%s)", path, e)
        return pd.DataFrame(columns=["chrom", "start", "end", "name", "score", "strand"])


def replicate_agreement(sites_bed, rep_region_files):
    """
    Fraction of final reproducible binding sites that overlap with PureCLIP regions
    from ALL replicates.
    """
    if len(rep_region_files) < 2:
        logger.warning("Fewer than 2 replicate files; agreement undefined")
        return None

    try:
        # Check if sites_bed is empty
        sites_df = load_bed(sites_bed)
        total_sites = len(sites_df)
        if total_sites == 0:
            return 0.0

        # Write the filtered dataframe to a temporary file so bedtools and pandas
        # are using the exact same baseline (solving the numerator/denominator mismatch)
        tmp_sites = "results/_tmp_valid_sites.bed"
        sites_df[["chrom", "start", "end", "name", "score", "strand"]].to_csv(
            tmp_sites, sep="\t", header=False, index=False)

        # Build the bedtools intersect command
        cmd = ["bedtools", "intersect", "-a", tmp_sites, "-b", rep_region_files[0], "-u"]
        
        # Run first intersect
        p = subprocess.run(cmd, capture_output=True, text=True, check=True)
        out = p.stdout
        
        # Pipe through remaining replicates
        for rep_file in rep_region_files[1:]:
            p = subprocess.run(["bedtools", "intersect", "-a", "-", "-b", rep_file, "-u"],
                               input=out, capture_output=True, text=True, check=True)
            out = p.stdout
            
        out = out.strip()
        hits = len(out.split('\n')) if out else 0
        agreement = round(hits / total_sites, 4) if total_sites > 0 else 0.0
        logger.info("Reproducible agreement: %d/%d = %.4f", hits, total_sites, agreement)
        return agreement
    except subprocess.CalledProcessError as e:
        logger.error("bedtools intersect failed: %s", e.stderr.strip())
        return 0.0





def _iupac_to_regex(motif):
    iupac = {"U": "T", "R": "[AG]", "Y": "[CT]", "N": "[ACGT]",
             "W": "[AT]", "S": "[GC]", "K": "[GT]", "M": "[AC]",
             "B": "[CGT]", "D": "[AGT]", "H": "[ACT]", "V": "[ACG]"}
    return "".join(iupac.get(b, b) for b in motif.upper())


def motif_hit_rate(sites_bed, genome_fasta, motif_pattern, flank_nt=15):
    """Fraction of binding sites with the target motif WITHIN a window
    around the site. The crosslink site itself often sits a few nt away
    from the recognition motif (UV crosslinks at U, motif is elsewhere),
    so we search a +/- flank_nt window rather than just the site itself.
    """
    sites = load_bed(sites_bed)
    if len(sites) == 0:
        return 0.0

    # Expand each site by flank_nt on both sides (clamp start at 0)
    expanded = sites.copy()
    expanded["start"] = (expanded["start"] - flank_nt).clip(lower=0)
    expanded["end"] = expanded["end"] + flank_nt

    tmp_bed = "results/_tmp_motif_window.bed"
    expanded[["chrom", "start", "end", "name", "score", "strand"]].to_csv(
        tmp_bed, sep="\t", header=False, index=False)

    result = subprocess.run(
        ["bedtools", "getfasta", "-s", "-fi", genome_fasta,
         "-bed", tmp_bed, "-tab"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        logger.error("bedtools getfasta failed: %s", result.stderr.strip())
        return None

    seqs = [line.split("\t")[1].upper()
            for line in result.stdout.strip().split("\n") if line]
    if not seqs:
        return 0.0

    rx = re.compile(_iupac_to_regex(motif_pattern))
    hits = sum(1 for s in seqs if rx.search(s))
    rate = round(hits / len(seqs), 4)
    logger.info("Motif hit rate (window +/-%d nt): %d/%d = %.4f",
                flank_nt, hits, len(seqs), rate)
    return rate


def main(config_path, out_path):
    logger.info(f"Running scorers with config {config_path}")
    cfg = yaml.safe_load(open(config_path))
    priors = json.load(open("config/priors.json"))

    sites_bed = "results/binding_sites.reproducible.bed"
    genome = cfg["reference"]["genome_fasta"]

    ip_reps = list(cfg["samples"]["ip"].keys())
    rep_region_files = [f"results/ip_{rep}/pureclip_regions.bed" for rep in ip_reps]

    target_motif = next(
        (m["pattern"] for m in priors["known_motifs"] if m["type"] == "target"),
        None
    )


    report = {
        "run_id": cfg["run_id"],
        "n_binding_sites": int(len(load_bed(sites_bed))),
        "replicate_agreement": replicate_agreement(sites_bed, rep_region_files),
        "motif_hit_rate": (motif_hit_rate(sites_bed, genome, target_motif, flank_nt=15)
                           if target_motif else None)
    }

    json.dump(report, open(out_path, "w"), indent=2)
    logger.info(f"Wrote score report to {out_path}")
    logger.info(f"Report: {json.dumps(report)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
