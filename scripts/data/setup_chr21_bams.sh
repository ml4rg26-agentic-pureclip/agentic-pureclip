#!/bin/bash
set -e

# Common wget options: force progress bar, resume, timeout, retries
WGET_OPTS="--progress=bar:force -c --timeout=30 --tries=3"

echo "=== Preparing chr21 reference files (if not present) ==="
mkdir -p ref

if [ ! -f "ref/test_chr21.fa" ]; then
    echo "Downloading chr21 FASTA from UCSC..."
    wget $WGET_OPTS -O ref/test_chr21.fa.gz https://hgdownload.soe.ucsc.edu/goldenPath/hg38/chromosomes/chr21.fa.gz
    gunzip ref/test_chr21.fa.gz
fi
if [ ! -f "ref/test_chr21.fa.fai" ]; then
    echo "Indexing chr21 FASTA..."
    samtools faidx ref/test_chr21.fa
fi

if [ ! -f "ref/test_chr21.gtf" ]; then
    echo "Downloading GENCODE GTF and extracting chr21 (this may take a minute)..."
    wget $WGET_OPTS -O ref/gencode.v44.annotation.gtf.gz https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_44/gencode.v44.annotation.gtf.gz
    zcat ref/gencode.v44.annotation.gtf.gz | awk '$1 == "chr21"' > ref/test_chr21.gtf
    rm ref/gencode.v44.annotation.gtf.gz
fi


# Ensure data/raw exists
mkdir -p data/raw

echo "=== Downloading RBFOX2 BAM files from ENCODE (if not present) ==="
if [ ! -f "data/raw/ip_rep1_full.bam" ]; then
    echo "Downloading IP Rep 1..."
    wget $WGET_OPTS -O data/raw/ip_rep1_full.bam "https://www.encodeproject.org/files/ENCFF239CML/@@download/ENCFF239CML.bam"
fi
if [ ! -f "data/raw/ip_rep1_full.bam.bai" ]; then
    echo "Indexing IP Rep 1..."
    samtools index data/raw/ip_rep1_full.bam
fi

if [ ! -f "data/raw/ip_rep2_full.bam" ]; then
    echo "Downloading IP Rep 2..."
    wget $WGET_OPTS -O data/raw/ip_rep2_full.bam "https://www.encodeproject.org/files/ENCFF170YQV/@@download/ENCFF170YQV.bam"
fi
if [ ! -f "data/raw/ip_rep2_full.bam.bai" ]; then
    echo "Indexing IP Rep 2..."
    samtools index data/raw/ip_rep2_full.bam
fi

if [ ! -f "data/raw/input_rep1_full.bam" ]; then
    echo "Downloading Input Control..."
    wget $WGET_OPTS -O data/raw/input_rep1_full.bam "https://www.encodeproject.org/files/ENCFF515BTB/@@download/ENCFF515BTB.bam"
fi
if [ ! -f "data/raw/input_rep1_full.bam.bai" ]; then
    echo "Indexing Input Control..."
    samtools index data/raw/input_rep1_full.bam
fi

echo "=== Extracting chr21 directly from full BAMs as ready-to-use dedup.bam ==="

# Ensure directories exist
mkdir -p results/ip_rep1/logs
mkdir -p results/ip_rep2/logs
mkdir -p results/input_control_rep1/logs

# Process IP Rep 1
echo "Processing ip_rep1..."
samtools view -b data/raw/ip_rep1_full.bam chr21 > results/ip_rep1/dedup.bam
samtools index results/ip_rep1/dedup.bam
echo "ip_rep1 chr21 reads: $(samtools view -c results/ip_rep1/dedup.bam)"

# Process IP Rep 2
echo "Processing ip_rep2..."
samtools view -b data/raw/ip_rep2_full.bam chr21 > results/ip_rep2/dedup.bam
samtools index results/ip_rep2/dedup.bam
echo "ip_rep2 chr21 reads: $(samtools view -c results/ip_rep2/dedup.bam)"

# Process Input Control
echo "Processing input_control_rep1..."
samtools view -b data/raw/input_rep1_full.bam chr21 > results/input_control_rep1/dedup.bam
samtools index results/input_control_rep1/dedup.bam
echo "input_control chr21 reads: $(samtools view -c results/input_control_rep1/dedup.bam)"

echo "=== Done. Directly extracted BAMs are ready in results/ ==="