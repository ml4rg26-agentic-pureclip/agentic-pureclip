# Configuration Module

This directory stores all YAML and JSON configurations that define both the biological prior knowledge and the tunable parameters for the pipeline.

## Files

- **`run_config.yaml`** / **`run_config.test.yaml`**: The primary configuration for the Snakemake workflow. It contains dataset paths (BAMs), reference genome details, and the tunable sections (`pureclip`, `postprocessing`) that the Agent actively modifies.
- **`priors.json`**: Biological prior knowledge (e.g., target protein name, known motifs like "UGCAUG"). This is provided to the LLM as context for decision-making.
- **`best_config.yaml`**: An artifact generated automatically at the end of the Agent loop, storing the best parameter set discovered during the run.

---

## `run_config.yaml` Data Fields Explained

This YAML file dictates how the Snakemake workflow processes the data. Here are the key sections and their meanings:

### 1. `samples` & `reference` (Inputs)
* **`samples`**: Defines the experimental design. Contains paths to the `dedup.bam` files for the `ip` (Immunoprecipitation, usually multiple biological replicates) and `input_control` (size-matched input used as a covariate background model in PureCLIP).
* **`reference`**: Paths to the `genome_fasta` (reference genome sequence) and `annotation_gtf` (gene models).

### 2. `pureclip` & `postprocessing` (Tunable Parameters)
These are the core fields that dictate peak calling and filtering. The **Agent actively modifies** a subset of these (defined in its `search_bounds`) to optimize the pipeline.
* **`pureclip.bandwidth_nt`**: Kernel Density Estimation (KDE) bandwidth. A smaller number makes the caller sensitive to sharp spikes; a larger number smooths the signal.
* **`pureclip.merge_distance_nt`**: Maximum allowed gap between crosslink sites to merge them into a single continuous binding region.
* **`pureclip.use_input_covariate`** / **`pureclip.high_precision_mode`**: Boolean flags passed directly to PureCLIP.
* **`postprocessing.min_region_length_nt`**: Drops regions where the genomic distance is too short.
* **`postprocessing.min_crosslink_events`**: The cutoff for the minimum number of crosslink events required to keep a merged region (filters out noise).
* **`postprocessing.force_width`**: Standardizes the final width of the binding footprint (e.g., forcing a 9nt window centered on the peak).

---

## `priors.json` Fields Explained

The `priors.json` file contains **Biological Prior Knowledge**. It gives the Agent (LLM) biological context to make parameter decisions.

### Fields
* **`target_protein`**: The name of the RNA-binding protein being analyzed (e.g., `"RBFOX2"`). This helps the LLM retrieve its internal knowledge about the protein's general characteristics.
* **`known_motifs`**: A list of motif objects associated with the protein.
  * **`pattern`**: The RNA sequence motif (e.g., `"UGCAUG"` for RBFOX2).
  * **`type`**: Indicates the role of the motif, typically `"target"` (the main binding sequence).

### Where do these priors come from?
1. **Databases**: [**ATtRACT**](https://attract.cnic.es/) or [**mCrossBase**](https://zhanglab.c2b2.columbia.edu/mCrossBase/rbp.php?id=K562.RBFOX2)
