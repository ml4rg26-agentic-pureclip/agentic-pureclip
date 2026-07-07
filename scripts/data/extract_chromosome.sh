#!/usr/bin/env bash
set -euo pipefail   # fail fast: stop on first error, catch unset vars and pipe failures

RBP="PUM1_K562"
SRC="data/${RBP}/bam"
OUT="data/${RBP}/chr21"
CHROM="chr21"

mkdir -p "${OUT}"

# Map each role to its ENCODE accession (from metadata.txt)
declare -A BAMS=(
  ["ip_rep1"]="${SRC}/ip_rep1_v1/ENCFF064COB.bam"
  ["ip_rep2"]="${SRC}/ip_rep2_v1/ENCFF583QFB.bam"
  ["input_rep1"]="${SRC}/smi_v1/ENCFF222HEX.bam"
)

for role in "${!BAMS[@]}"; do
  src="${BAMS[$role]}"
  dst="${OUT}/${role}.${CHROM}.bam"

  echo "=== ${role}: extracting ${CHROM} from ${src} ==="

  # The full BAM needs an index before region extraction; build it if missing
  if [[ ! -f "${src}.bai" ]]; then
    echo "  indexing ${src} ..."
    samtools index "${src}"
  fi

  samtools view -b "${src}" "${CHROM}" > "${dst}"
  samtools index "${dst}"

  echo "  ${role} ${CHROM} reads: $(samtools view -c "${dst}")"
done

echo "=== Done. chr21 BAMs are in ${OUT}/ ==="