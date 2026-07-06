#!/usr/bin/env bash
# Extract the new Google-Drive dataset batches into data/<DATASET>/ and index the
# canonical (_v1) BAMs, so the datasets are ready for config generation and runs.
#
# Source tarballs live under data/incoming_gdrive/<batch>/<DATASET>.tar.gz and each
# unpacks to <DATASET>/ in the project's standard layout. Only the canonical v1
# replicate/input BAMs are indexed (some datasets ship extra v2/v3 versions).
#
# Idempotent: re-extracts (overwrites) and re-indexes; safe to re-run.
set -euo pipefail

cd "$(dirname "$0")/.."
INCOMING=data/incoming_gdrive
B1=$INCOMING/new_batch_1__1Su44OGW
B2=$INCOMING/new_batch_2__1jykCsPe

# dataset:batchdir
DATASETS=(
  "HNRNPK_HepG2:$B1" "HNRNPK_K562:$B1" "HNRNPM_HepG2:$B1" "HNRNPM_K562:$B1"
  "SF3B1_K562:$B1" "SF3B4_HepG2:$B1" "SF3B4_K562:$B1" "SFPQ_HepG2:$B1"
  "SRSF1_HepG2:$B1" "SRSF1_K562:$B1" "U2AF1_HepG2:$B1" "U2AF1_K562:$B1"
  "U2AF2_HepG2:$B1" "U2AF2_K562:$B1"
  "RBM22_HepG2:$B2" "RBM22_K562:$B2" "PCBP1_HepG2:$B2" "PCBP1_K562:$B2"
  "PUM2_K562:$B2" "PTBP1_HepG2:$B2"
)

echo "== Extracting $((${#DATASETS[@]})) datasets into data/ =="
for entry in "${DATASETS[@]}"; do
  ds="${entry%%:*}"; dir="${entry#*:}"
  tarball="$dir/$ds.tar.gz"
  [ -f "$tarball" ] || { echo "MISSING tarball: $tarball" >&2; exit 1; }
  echo "  extract $ds"
  tar -xzf "$tarball" -C data/
done

echo "== Indexing canonical v1 BAMs (parallel) =="
idx_jobs=0
for entry in "${DATASETS[@]}"; do
  ds="${entry%%:*}"
  for sub in ip_rep1_v1 ip_rep2_v1 smi_v1; do
    for bam in data/"$ds"/bam/"$sub"/*.bam; do
      [ -f "$bam" ] || continue
      samtools index "$bam" &
      idx_jobs=$((idx_jobs+1))
      # cap concurrency at 16
      if (( idx_jobs % 16 == 0 )); then wait; fi
    done
  done
done
wait

echo "== Verify: each dataset has 3 indexed BAMs =="
missing=0
for entry in "${DATASETS[@]}"; do
  ds="${entry%%:*}"
  n_bam=$(ls data/"$ds"/bam/{ip_rep1_v1,ip_rep2_v1,smi_v1}/*.bam 2>/dev/null | wc -l)
  n_bai=$(ls data/"$ds"/bam/{ip_rep1_v1,ip_rep2_v1,smi_v1}/*.bam.bai 2>/dev/null | wc -l)
  echo "  $ds: $n_bam bam / $n_bai bai"
  [ "$n_bam" -eq 3 ] && [ "$n_bai" -eq 3 ] || missing=1
done
[ "$missing" -eq 0 ] && echo "ALL_DATASETS_READY" || { echo "SOME_DATASETS_INCOMPLETE"; exit 1; }
