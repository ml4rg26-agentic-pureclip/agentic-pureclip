# New Dataset Batches — Investigation & Integration Plan

_Date: 2026-07-06 · Runner: `agenticpureclipvm-751a3` (32 cores, 251 GB RAM)_
_Downloaded to: `data/incoming_gdrive/` (37.60 GiB, 36 files, all size-verified, no failures)_

## TL;DR

- The three Drive folders are **more of the same kind of data** we already use:
  each `*.tar.gz` unpacks to a dataset in **our exact layout**
  (`<RBP>_<cell>/bam/{ip_rep1_v1,ip_rep2_v1,smi_v1}/*.bam` + `top_regions/`,
  `top_crosslink_sites/`, `top_genes/`, `biotypes_genetypes/`).
- **Net new: 20 datasets across 12 new RBPs.** The rest are duplicates.
- **They are worth using** — they roughly 5× our benchmark and, importantly, add a
  *different class* of RBP (splicing factors), which stress-tests the pipeline beyond
  the clean sequence-specific motifs it was tuned on.
- **Main cost is PureCLIP compute**, not download/prep. Budget ≈ **2–3 machine-days**
  for one full-genome pass over all 20; much less if the optimizer searches on
  restricted regions and only confirms full-genome.

## What was downloaded

| Local subdir | Drive folder | Files | Size | Content |
|---|---|---|---|---|
| `new_batch_1__1Su44OGW` | 1Su44…JRr | 14 | 16.35 GiB | **14 new datasets** (8 new RBPs) |
| `new_batch_2__1jykCsPe` | 1jyk…rizV | 17 | 15.81 GiB | 6 new datasets + 8 dups + 3 tiny `RBFOX2_partners` |
| `new_batch_3__1xX8-pJ2` | 1xX8…AQ5u | 5 | 5.44 GiB | **exact re-package of the preliminary 5** (same ENCODE accessions) |

Notes:
- Batches were kept **separate on purpose**: dataset names collide *across* folders and
  even *within* batch 2 (two distinct `RBFOX2_partners.tar.gz` objects). Downloading by
  Drive file-ID (not name) guarantees nothing was silently overwritten; within-folder
  collisions get a `.dup-<id8>` suffix.
- `RBFOX2_partners.tar.gz` (×3, 126 B each) are valid but ~empty tarballs (~10 KB
  uncompressed) — likely partner/annotation lists, **not** BAM datasets.
- Every tarball contains BAMs but **no `.bai` index** → indexes must be regenerated.

## What is genuinely new (dedup vs. preliminary batch)

Preliminary batch already in `data/`: PUM1_K562, QKI_{K562,HepG2}, RBFOX2_{K562,HepG2}.

**20 new datasets, 12 new RBPs** (K562 and/or HepG2):

| RBP | Cells | Biological role | Motif situation |
|---|---|---|---|
| HNRNPK | K562, HepG2 | hnRNP, splicing/translation | C-rich, degenerate |
| HNRNPM | K562, HepG2 | hnRNP, splicing | GU-rich, degenerate |
| PCBP1 | K562, HepG2 | poly-C binding | C-rich |
| PTBP1 | HepG2 | splicing repressor | CU-rich (pyrimidine) |
| PUM2 | K562 | Pumilio family | UGUANAUA (crisp, like PUM1) |
| RBM22 | K562, HepG2 | spliceosome (Prp19 complex) | weak/structural |
| SF3B1 | K562 | U2 snRNP, branch point | positional, not a k-mer |
| SF3B4 | K562, HepG2 | U2 snRNP | positional |
| SFPQ | HepG2 | paraspeckle, splicing | degenerate |
| SRSF1 | K562, HepG2 | SR protein, ESE | GA-rich (GGAGGA-ish) |
| U2AF1 | K562, HepG2 | 3′ splice site (AG) | positional |
| U2AF2 | K562, HepG2 | polypyrimidine tract | poly-Y, positional |

**Redundant / not new:** batch 3 (5) = preliminary; batch 2 duplicates of
HNRNPK_{K562,HepG2}, U2AF2_HepG2, QKI_{K562,HepG2}, PUM1_K562, RBFOX2_{K562,HepG2}.

## What they add (why use them)

1. **Scale:** benchmark grows from 5 → ~25 datasets (5×). More statistical weight for
   comparing optimizers (LLM vs Optuna vs baseline) and for motif-aware scoring claims.
2. **Diversity / harder cases:** the preliminary set is sequence-specific RBPs with crisp
   motifs (RBFOX2 `UGCAUG`, QKI `ACUAAY`, PUM1 `UGUANAUA`). The new set is dominated by
   **splicing factors** whose binding is **positional/degenerate** (U2AF2 poly-Y, U2AF1/SF3B
   at splice sites). This is exactly where PureCLIP tuning and our motif priors are least
   obvious — a strong test of generalization.
3. **Paired cell lines** (K562 + HepG2 for most RBPs) enable cross-cell-line reproducibility
   analysis, not just cross-replicate.
4. **PUM2_K562** is a near-free win: same motif family as PUM1, so existing priors transfer
   directly — good sanity/positive control.

## Caveats before using

- **Motif priors need per-RBP curation.** Our `known_motifs` (e.g. `config/datasets/*.yaml`)
  assume a clean target k-mer. For U2AF1/U2AF2/SF3B1/SF3B4/RBM22 that assumption breaks;
  motif-aware scoring should be down-weighted or switched to a positional prior for them,
  else scores mislead. A motif catalog exists (`data/motifs/{ATtRACT,RBPDB,RBPmap_1.2,
  mCrossBase,oRNAment}`) to source per-RBP motifs.
- **Benchmark files provenance:** each tarball ships its own `top_regions/regions.bed6`,
  `top_crosslink_sites/crosslinks.bed6`, `top_genes/list.txt`, `biotypes_genetypes/*.tsv`.
  Confirm these were generated consistently with the preliminary batch before treating
  scores as comparable.
- **Batch 3 / batch-2 duplicates:** do **not** re-ingest; would double-count in aggregates.

## Integration steps

1. Extract each new tarball into `data/<DATASET>/` (they already carry the right internal
   structure). Skip batch 3 and the batch-2 duplicates.
2. `samtools index` all BAMs (no `.bai` shipped).
3. Generate a `config/datasets/<DATASET>.yaml` per dataset from the existing template
   (bam paths, benchmark paths, `resources`, `pureclip`) and set a sensible `known_motifs`
   / objective per RBP (see caveat above).
4. Register in the run harness and launch.

## Time budget (evidence-based)

Measured on this runner:
- **Full-genome PureCLIP pass:** `results/overnight/summary.csv` →
  RBFOX2_K562 full-genome = **12 456 s ≈ 3.46 h** (Snakemake `-j 32`, one config).
- **Region-restricted dev iteration:** ~4–10 min (e.g. PUM1_K562 overnight iterations).

| Stage | Per dataset | ×20 new datasets |
|---|---|---|
| Download | done | done (~10 min total) |
| Extract `.tar.gz` | ~1–3 min | ~30–45 min (I/O bound) |
| `samtools index` (3 BAMs) | ~2–4 min | ~10–15 min wall (parallel on 32c) |
| Config generation | seconds | minutes |
| **PureCLIP full-genome (1 config)** | **~3.5 h** | **~70 machine-h ≈ 2–3 days** |
| PureCLIP region-restricted (1 iter) | ~5–10 min | ~2–3 h total |

**Recommended strategy:** run the agentic optimizer on **restricted regions** (minutes per
iteration) to search parameters, then a **single full-genome confirmation** per dataset.
That keeps the search cheap and pays the 3.5 h full-genome cost only ~20 times.
- Prep (extract + index + configs): **~1–1.5 h wall.**
- Optimization search (restricted): **~0.5–1 day** depending on iterations/dataset.
- Final full-genome confirmations: **~2–3 days** sequential at `-j 32`, or **~1 day**
  if packed 3–4 datasets concurrently (memory allows; watch core contention).

**Bottom line:** plan for **~3–4 machine-days** end-to-end for the full new batch; a first
useful pass on the 8 most interesting RBPs is achievable within a day.

## Recommendation

Use **batch 1 + the 6 new datasets in batch 2** (20 total). Discard batch 3 and the batch-2
duplicates. Prioritize PUM2 (control) and the splicing factors (highest analytical value),
but first fix per-RBP motif priors so scoring stays meaningful.
