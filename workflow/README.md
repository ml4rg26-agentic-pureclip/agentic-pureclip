# Workflow Module

This directory contains the Snakemake bioinformatics pipeline responsible for processing the raw eCLIP data into reproducible binding sites.

## Files

- **`Snakefile`**: The core Snakemake pipeline. It handles PureCLIP execution and post-processing. The pipeline is designed to start directly from pre-processed, deduplicated BAM files, enabling iterative tuning by the Agent.
- **`postprocess.py`**: A script called by Snakemake to filter and format the raw PureCLIP output. It enforces minimum crosslink events, minimum region lengths, and forces a specific footprint width (e.g., 9nt) as defined in the configuration.

---

## Detailed Pipeline Steps (Snakefile)

The `Snakefile` defines a Directed Acyclic Graph (DAG) of bioinformatics jobs focused on Peak Calling and Postprocessing. The pipeline is forced to rerun in every Agent loop to evaluate new parameter combinations.

### Peak Calling (Runs Every Iteration)
1. **`merge_ip`**: Merges the deduplicated BAM files from multiple biological replicates into a single "meta-replicate".
   * *Purpose*: Increases the statistical power and signal-to-noise ratio for the peak caller to find true binding sites.
2. **`pureclip` (Merged)**: Runs the PureCLIP Hidden Markov Model on the merged BAM file to detect crosslink sites and binding regions based on the current Agent-tuned parameters (`bandwidth_nt`, `merge_distance_nt`).
3. **`pureclip_per_replicate`**: Runs PureCLIP independently on each individual biological replicate.
   * *Purpose*: The outputs from individual replicates are used later by `run_scorers.py` to calculate `replicate_agreement` (reproducibility).
4. **`postprocess`**: Executes `postprocess.py` to filter and format the merged PureCLIP regions into the final `binding_sites.reproducible.bed`.

---

## Postprocessing Logic (`postprocess.py`)

PureCLIP outputs crosslink sites and merged regions. `postprocess.py` refines these raw regions into standard binding footprints.

### 1. `min_crosslink_events` Filter
* **What it does**: Parses the `name` column of `PureCLIP.binding_regions.bed` (which contains semicolon-separated crosslink sites) and drops any region that contains fewer than `X` crosslink events.
* **Biological Significance**: A true RNA-Binding Protein (RBP) interaction site should capture multiple crosslinking events. Regions with only 1 or 2 crosslink events are often stochastic noise, random sequencing artifacts, or weak transient interactions. Filtering these out improves the precision of the dataset.

### 2. `min_region_length_nt` Filter
* **What it does**: Drops regions where the genomic distance between the start and end is too short.
* **Biological Significance**: Ensures the identified regions represent continuous binding footprints rather than isolated single-nucleotide anomalies.

### 3. `force_width` Centering
* **What it does**: Calculates the center (summit) of each surviving region and artificially expands/contracts it to a perfectly symmetrical, fixed width (e.g., 9nt).
* **Biological Significance**: Many biological motifs are 4-8nt long (e.g., the RBFOX2 motif `UGCAUG` is 6nt). Standardizing peak widths around the crosslink summit by extracting a fixed 9nt window ensures that the core motif and minimal necessary flanking context are captured consistently. This standardization aids downstream **Motif Discovery**, as motif algorithms struggle with alignment if peaks have variable lengths.
