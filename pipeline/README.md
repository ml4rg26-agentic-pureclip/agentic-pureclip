# Pipeline Helpers

This package contains shared infrastructure that is used by the agent, tests, scripts, and workflow wrappers.

## Files

- **`configs.py`**: Loads, saves, validates, and normalizes run configs. It also enforces hard search bounds on LLM-proposed parameter changes.
- **`datasets.py`**: Registry of local datasets under `data/`, including BAM paths, known motifs, and benchmark files.
- **`runner.py`**: Reproducible wrappers around Snakemake and scorer execution. It calls `workflow/Snakefile` explicitly and can build missing BAM indexes before a real run.

## Why This Exists

The agent prompt still tells the LLM what it may change, but this package is the enforcement layer. Invalid configs, unsupported parameters, out-of-bounds values, and repeated parameter sets are rejected in code before execution.
