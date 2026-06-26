# tests/test_workflow.py
import subprocess
import pytest
import shutil
from pathlib import Path

import os
import yaml

def test_snakemake_dry_run(tmp_path):
    """Test that the Snakemake workflow can successfully perform a dry run."""
    if not shutil.which("snakemake"):
        pytest.skip("snakemake not found in PATH")
        
    snakefile_path = Path("workflow/Snakefile")
    assert snakefile_path.exists(), "Snakefile not found at workflow/Snakefile"
    
    # Create dummy source files in tmp_path to satisfy Snakemake's dry run input requirements
    dummy_files = [
        "results/ip_rep1/dedup.bam",
        "results/ip_rep1/dedup.bam.bai",
        "results/ip_rep2/dedup.bam",
        "results/ip_rep2/dedup.bam.bai",
        "results/input_control_rep1/dedup.bam",
        "results/input_control_rep1/dedup.bam.bai",
        "ref/test_chr21.fa",
        "ref/test_chr21.gtf"
    ]
    for df in dummy_files:
        p = tmp_path / df
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()

    # Create a dummy config pointing to these temporary files
    dummy_config = {
        "run_id": "dry_run_iter_00",
        "target_protein": "RBFOX2",
        "samples": {
            "ip": {
                "rep1": {"bam": str(tmp_path / "results/ip_rep1/dedup.bam")},
                "rep2": {"bam": str(tmp_path / "results/ip_rep2/dedup.bam")}
            },
            "input_control": {
                "rep1": {"bam": str(tmp_path / "results/input_control_rep1/dedup.bam")}
            }
        },
        "reference": {
            "genome_fasta": str(tmp_path / "ref/test_chr21.fa"),
            "annotation_gtf": str(tmp_path / "ref/test_chr21.gtf")
        },
        "pureclip": {
            "bandwidth_nt": 50,
            "merge_distance_nt": 8,
            "high_precision_mode": False,
            "use_input_covariate": False,
            "use_cl_motif_covariate": False,
            "cl_motif_file": None
        },
        "postprocessing": {
            "force_width": 9,
            "cluster_gap_width": 8,
            "min_region_length_nt": 3,
            "min_crosslink_events": 3
        },
        "resources": {
            "threads": 1
        },
        "output": {
            "results_dir": str(tmp_path / "workflow_results")
        }
    }
    
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(dummy_config, f)
        
    env = os.environ.copy()
    env["CONFIG_PATH"] = str(config_file)

    # Run snakemake dry-run
    # -s specifies the Snakefile
    # -n is dry-run
    # -q is quiet (less output, but still returns non-zero on failure)
    result = subprocess.run(
        ["snakemake", "-s", str(snakefile_path), "-n", "-q"],
        capture_output=True,
        text=True,
        env=env
    )
    
    assert result.returncode == 0, f"Snakemake dry run failed:\n{result.stderr}\n{result.stdout}"
