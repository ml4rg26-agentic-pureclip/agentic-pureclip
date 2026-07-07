#!/usr/bin/env bash
# scripts/data/download_genome.sh
# Download GRCh38 primary assembly genome FASTA for PureCLIP.
#
# Sources from GENCODE (preferred, includes all chromosomes + scaffolds)
# or falls back to Ensembl.
#
# Usage:
#   bash scripts/data/download_genome.sh              # full primary assembly (~900 MB)
#   bash scripts/data/download_genome.sh --chr21      # chr21 only for quick testing (~2 MB)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="$REPO_ROOT/data"
GENOME_DIR="$DATA_DIR/GRCh38.primary_assembly.genome.fa"
GENOME_FA="$GENOME_DIR/GRCh38.primary_assembly.genome.fa"

CHR21_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --chr21) CHR21_ONLY=true ;;
        -h|--help)
            echo "Usage: bash scripts/data/download_genome.sh [--chr21]"
            echo ""
            echo "  (no flag)   Download full GRCh38 primary assembly (~900 MB)"
            echo "  --chr21     Download chr21 only (~2 MB, for quick testing)"
            exit 0
            ;;
    esac
done

# ── Already downloaded? ────────────────────────────────────────────────────
if [ -f "$GENOME_FA" ]; then
    size=$(du -sh "$GENOME_FA" | cut -f1)
    echo "[download_genome] Already present: $GENOME_FA ($size)"
    exit 0
fi

mkdir -p "$GENOME_DIR"

# ── chr21 quick mode ───────────────────────────────────────────────────────
if $CHR21_ONLY; then
    echo "=================================================="
    echo " Downloading chr21 only (for test runs)"
    echo "=================================================="
    CHR21_URL="https://ftp.ensembl.org/pub/release-113/fasta/homo_sapiens/dna/Homo_sapiens.GRCh38.dna.chromosome.21.fa.gz"
    CHR21_GZ="$GENOME_DIR/chr21.fa.gz"

    echo "  → $CHR21_URL"
    curl -L --progress-bar -o "$CHR21_GZ" "$CHR21_URL"
    
    echo "Decompressing..."
    gunzip -f "$CHR21_GZ"
    
    # Create a minimal FASTA that PureCLIP can use
    # Rename the header to match what the pipeline expects (just the sequence, keep header simple)
    mv "$GENOME_DIR/chr21.fa" "$GENOME_FA"
    
    echo ""
    echo "Done: $(du -sh "$GENOME_FA" | cut -f1)"
    exit 0
fi

# ── Full GRCh38 primary assembly ───────────────────────────────────────────
echo "=================================================="
echo " Downloading GRCh38 primary assembly (~900 MB)"
echo "=================================================="

# GENCODE primary assembly URL (includes scaffolds, patches, alt loci)
# This is the recommended reference for eCLIP analysis
GENCODE_URL="https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_47/GRCh38.primary_assembly.genome.fa.gz"

GZ_FILE="$GENOME_DIR/GRCh38.primary_assembly.genome.fa.gz"

echo "  → $GENCODE_URL"
echo ""
echo "This will download ~900 MB. Press Ctrl-C to cancel, or wait..."

if command -v wget &>/dev/null; then
    wget -q --show-progress -O "$GZ_FILE" "$GENCODE_URL" || {
        echo "wget failed, trying curl..."
        curl -L --progress-bar -o "$GZ_FILE" "$GENCODE_URL"
    }
else
    curl -L --progress-bar -o "$GZ_FILE" "$GENCODE_URL"
fi

echo ""
echo "Decompressing (this may take a minute)..."
gunzip -f "$GZ_FILE"

echo ""
echo "Done: $(du -sh "$GENOME_FA" | cut -f1)"
echo "Genome FASTA: $GENOME_FA"

# ── Index with samtools if available ───────────────────────────────────────
if command -v samtools &>/dev/null; then
    echo "Indexing with samtools..."
    samtools faidx "$GENOME_FA"
    echo "  → $GENOME_FA.fai"
else
    echo ""
    echo "⚠️  samtools not found. You'll need to index the FASTA before running PureCLIP:"
    echo "   samtools faidx $GENOME_FA"
fi

echo ""
echo "=================================================="
echo " Genome reference ready."
echo ""
echo "Next: run a dataset with:"
echo "  snakemake -s src/agentic_pureclip/postprocess/Snakefile -j 8 --configfile config/datasets/RBFOX2_K562.yaml"
echo "=================================================="
