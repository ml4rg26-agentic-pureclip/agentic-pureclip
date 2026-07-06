# Scripts

Operational utilities that sit *around* the core package (`src/agentic_pureclip/`).
Run them from the repo root. Grouped by purpose:

## `data/` — acquire & prepare datasets

- **`download_data.sh`**: Download CLIP dataset BAMs and motif databases from Google Drive.
- **`download_genome.sh`**: Download the GRCh38 primary-assembly genome FASTA (`--chr21` for a small test slice).
- **`download_gdrive_batches.py`**: Mirror the newer per-dataset `*.tar.gz` batches from shared Google Drive folders into `data/incoming_gdrive/`.
- **`prepare_new_datasets.sh`**: Extract the downloaded Drive batches into `data/<DATASET>/` and index the canonical `_v1` BAMs.
- **`setup_chr21_bams.sh`**: Download ENCODE eCLIP BAMs + reference and subset them to chr21 — the quick test-data path.
- **`extract_chromosome.sh`**: Subset a dataset's BAMs to a single chromosome (currently hardcoded to PUM1_K562/chr21).
- **`index_pum1_bams.sh`**: One-off `samtools index` of the PUM1_K562 BAMs.
- **`write_dataset_config.py`**: Write a reproducible run config for a dataset registered in `agentic_pureclip.pipeline.datasets`.

## `motifs/` — motif library management

- **`list_motifs.py`**: List available motif databases, RBPs, and loaded PWMs.
- **`reorganize_motifs.py`**: Reorganize extracted motif tarballs into the expected `data/motifs/{database}/{RBP}/[{cell_line}/]` hierarchy.

## `run/` — launch optimization batches

- **`batch_runner.py`**: Run multiple agent runs defined in a manifest (e.g. `config/batch_runs.yaml`).
- **`overnight_batch.py`**: Failure-tolerant batch runner — runs many jobs back-to-back within a wall-clock budget, isolating failures.

## `dashboard/` — live monitoring UI

- **`monitor.py`**: Serves the JSON API (`/api/status`, `/api/runs`, `/api/options`, `POST /api/schedule`) and the built React UI.
- **`start_ui.sh`**: Convenience launcher for `monitor.py` (intended to run inside a persistent tmux session).

## Examples

```bash
bash scripts/data/setup_chr21_bams.sh
python scripts/data/write_dataset_config.py RBFOX2_K562 --out config/datasets/RBFOX2_K562.yaml
python scripts/motifs/list_motifs.py --rbp RBFOX2
uv run python scripts/dashboard/monitor.py --port 8888
```
