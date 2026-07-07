from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from agentic_pureclip.pipeline.configs import load_config, sample_bams, score_report_path, validate_config


# The Snakefile lives alongside postprocess.py inside the package; resolve it
# from here so snakemake can be invoked from any working directory.
SNAKEFILE = str(Path(__file__).resolve().parent.parent / "postprocess" / "Snakefile")


def ensure_bam_indexes(config: dict, *, samtools: str = "samtools") -> None:
    missing = [bam for bam in sample_bams(config) if not Path(f"{bam}.bai").exists()]
    if not missing:
        return

    executable = shutil.which(samtools)
    if not executable:
        raise RuntimeError("samtools is required to index BAM inputs, but it was not found in PATH")

    for bam in missing:
        subprocess.run([executable, "index", bam], check=True)


def run_snakemake(
    config_path: str | Path,
    *,
    jobs: int | None = None,
    force_rules: Iterable[str] | None = None,
    ensure_indexes: bool = True,
    dry_run: bool = False,
) -> subprocess.CompletedProcess:
    config = load_config(config_path)
    validate_config(config, require_files=not dry_run, require_bai=False)
    if ensure_indexes and not dry_run:
        ensure_bam_indexes(config)

    job_count = str(jobs or config.get("resources", {}).get("threads") or 1)
    cmd = [
        "snakemake",
        "-s",
        SNAKEFILE,
        "-j",
        job_count,
        "--configfile",
        str(config_path),
        "--rerun-incomplete",
    ]
    if force_rules:
        cmd.extend(["-R", *force_rules])
    if dry_run:
        cmd.append("-n")

    return subprocess.run(cmd, check=True)


def run_scorers(config_path: str | Path, report_path: str | Path | None = None) -> subprocess.CompletedProcess:
    config = load_config(config_path)
    validate_config(config, require_files=False)
    out = str(report_path or score_report_path(config))
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    return subprocess.run(
        [sys.executable, "-m", "agentic_pureclip.scoring.run_scorers", str(config_path), out],
        check=True,
    )
