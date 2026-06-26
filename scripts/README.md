# Scripts Module

This directory contains utility bash scripts designed to help you set up test environments and prepare data for the Agentic PureCLIP pipeline.

## Files

- **`setup_chr21_bams.sh`**: A script that downloads pre-aligned eCLIP BAM files for the RBFOX2 protein from ENCODE, reference genome files, and subsets them to Chromosome 21. This provides a way to prepare data for Agent testing.
- **`write_dataset_config.py`**: Writes a reproducible config for one of the local full-size datasets registered in `pipeline/datasets.py`.

## Usage

```bash
bash scripts/setup_chr21_bams.sh
```

```bash
python scripts/write_dataset_config.py RBFOX2_K562 --out config/datasets/RBFOX2_K562.yaml
```
