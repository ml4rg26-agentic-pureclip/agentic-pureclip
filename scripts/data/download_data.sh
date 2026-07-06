#!/usr/bin/env bash
# scripts/data/download_data.sh
# Download CLIP datasets and motif databases from Google Drive.
#
# Usage:
#   bash scripts/data/download_data.sh                  # download everything
#   bash scripts/data/download_data.sh --clip-only       # only CLIP BAMs
#   bash scripts/data/download_data.sh --motifs-only     # only motif databases
#   bash scripts/data/download_data.sh --dry-run         # show what would be downloaded
#
# Requires: gdown (pip install gdown)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Google Drive folder IDs ────────────────────────────────────────────────
# CLIP data: BAM files + benchmark summaries for 5 datasets
CLIP_FOLDER_ID="1BD8duAD2TAwvV_8LWAn6bNPK07cUjfb_"
# Motif databases: TRANSFAC PWMs organized by database/RBP
MOTIF_FOLDER_ID="1CzeD8n6wlcg8XPkYkHzhkcXwgkXW-srD"

# ── Flags ──────────────────────────────────────────────────────────────────
CLIP_ONLY=false
MOTIFS_ONLY=false
DRY_RUN=false

for arg in "$@"; do
    case "$arg" in
        --clip-only)    CLIP_ONLY=true ;;
        --motifs-only)  MOTIFS_ONLY=true ;;
        --dry-run)      DRY_RUN=true ;;
        -h|--help)
            echo "Usage: bash scripts/data/download_data.sh [--clip-only] [--motifs-only] [--dry-run]"
            exit 0
            ;;
    esac
done

# ── Resolve gdown via uv ───────────────────────────────────────────────────
GDLINK="https://drive.google.com/drive/folders"

_gdown() {
    cd "$REPO_ROOT" && uv run gdown "$@"
}

# ── Download CLIP data ─────────────────────────────────────────────────────
download_clip() {
    echo "=================================================="
    echo " Downloading CLIP datasets → data/"
    echo " Folder ID: $CLIP_FOLDER_ID"
    echo "=================================================="

    cd "$REPO_ROOT"
    mkdir -p data

    if $DRY_RUN; then
        echo "[DRY RUN] gdown --folder $GDLINK/$CLIP_FOLDER_ID -O data/"
        return
    fi

    _gdown --folder "$GDLINK/$CLIP_FOLDER_ID" -O data/ || {
        echo "WARNING: gdown exited with errors. Some files may already exist or be access-restricted."
        echo "Check the output above for details. Already-downloaded files are fine."
    }

    echo ""
    echo "CLIP data download complete."
    echo "Contents of data/:"
    find data/ -type f 2>/dev/null | head -40 | while read f; do echo "  $f"; done
    echo "  ... (use 'find data/ -type f | wc -l' for full count)"
}

# ── Download motif databases ───────────────────────────────────────────────
download_motifs() {
    echo "=================================================="
    echo " Downloading motif databases → data/motifs/"
    echo " Folder ID: $MOTIF_FOLDER_ID"
    echo "=================================================="

    cd "$REPO_ROOT"
    mkdir -p data/motifs

    if $DRY_RUN; then
        echo "[DRY RUN] gdown --folder $GDLINK/$MOTIF_FOLDER_ID -O data/motifs/"
        return
    fi

    _gdown --folder "$GDLINK/$MOTIF_FOLDER_ID" -O data/motifs/ || {
        echo "WARNING: gdown exited with errors. Some files may already exist or be access-restricted."
        echo "Check the output above for details."
    }

    echo ""
    echo "Motif database download complete."
    echo "Contents of data/motifs/:"
    find data/motifs/ -type f | while read f; do echo "  $f"; done

    echo ""
    echo "Checking motif structure..."
    uv run python scripts/motifs/list_motifs.py || true
}

# ── Main ───────────────────────────────────────────────────────────────────
echo "══════════════════════════════════════════════════"
echo " Agentic PureCLIP — Data Download"
echo "══════════════════════════════════════════════════"
echo ""
echo "CLIP folder:   $GDLINK/$CLIP_FOLDER_ID"
echo "Motif folder:  $GDLINK/$MOTIF_FOLDER_ID"
echo "Target dir:    $REPO_ROOT/data/"
echo ""

if $DRY_RUN; then
    echo ">>> DRY RUN MODE — no files will be downloaded <<<"
    echo ""
fi

if ! $MOTIFS_ONLY; then
    download_clip
fi

if ! $CLIP_ONLY; then
    download_motifs
fi

echo ""
echo "══════════════════════════════════════════════════"
echo " Download finished."
echo ""
echo "Next steps:"
echo "  1. Verify: python scripts/motifs/list_motifs.py"
echo "  2. Index BAMs: find data/ -name '*.bam' | while read b; do samtools index \"\$b\"; done"
echo "  3. Run a dataset: snakemake -s src/agentic_pureclip/postprocess/Snakefile -j 8 --configfile config/datasets/RBFOX2_K562.yaml"
echo "  4. Start the agent: env CONFIG_PATH=config/run_config.yaml MAX_ITER=10 python -m agent.graph"
echo "══════════════════════════════════════════════════"
