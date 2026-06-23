# Scorers Module

This directory contains the evaluation logic used to score the output of the PureCLIP pipeline at each iteration. It translates raw genomic coordinate files into quantitative metrics that the Agent uses to judge performance.

## Files

- **`run_scorers.py`**: A Python script executed by the Agent after the pipeline finishes. It calculates various metrics, saves them to `results/score_report.json`, and feeds them back to the LLM.

---

## Detailed Scoring Metrics

The script calculates several metrics. Below is an explanation of how they are calculated, their biological meaning, and how they guide the Agent's decision-making process.

### 1. Replicate Agreement (`replicate_agreement`)
* **How it is calculated**: It uses `bedtools intersect` to compare the final filtered peaks (`binding_sites.reproducible.bed`, generated from merged data) against the called regions from *each individual biological replicate* (`pureclip_regions.bed`). The score is the fraction (0.0 to 1.0) of final peaks that are supported by binding regions in **all** individual replicates.
* **Biological Significance**: A RNA-protein interaction should be reproducible across independent biological experiments. Conversely, sequencing artifacts, PCR duplicates, or non-specific interactions usually only appear in a single replicate. High agreement means the identified peaks represent biological binding events.
* **How it affects the Agent**: This is typically set as the **primary `objective_metric`** for the Agent to maximize.
  * If the Agent sets the tuning parameters (like `bandwidth_nt` or `min_crosslink_events`) too *loosely*, the pipeline will call false-positive noise peaks, causing the `replicate_agreement` score to drop.
  * If the Agent sets the parameters too *strictly*, the pipeline might only call a handful of strong peaks. While agreement might be 100%, the total number of peaks (`n_binding_sites`) drops to a low number. 
  * Therefore, the Agent learns to use this score to find a balance between sensitivity and specificity.

### 2. Number of Binding Sites (`n_binding_sites`)
* **How it is calculated**: Simply counts the total number of peaks in the final `binding_sites.reproducible.bed`.
* **Biological Significance**: Indicates the overall yield or sensitivity of the peak calling. A typical eCLIP experiment for a major RBP yields many binding sites, though the exact number depends heavily on the protein, cell line, and stringency of filtering (e.g., minimum crosslink events, cross-replicate reproducibility).
* **How it affects the Agent**: The Agent uses this as a secondary constraint. If `replicate_agreement` is high but `n_binding_sites` is 10, the Agent knows the parameters are too stringent and the pipeline is discarding too much biological signal.

### 3. Motif Hit Rate (`motif_hit_rate`)
* **How it is calculated**: If a known target motif (e.g., `UGCAUG` for RBFOX2) is provided in `config/priors.json`, the script scans the reference genome sequence within a narrow window (e.g., ±15nt) around the center of every final binding site. It returns the percentage of sites containing this exact motif.
* **Biological Significance**: RNA-binding proteins usually bind to specific RNA sequence patterns. A peak caller should identify crosslink sites centered on these motifs. If the `motif_hit_rate` is low, the peaks might be shifted from the binding pocket (due to KDE bandwidth) or they might be noise.
* **How it is used**: The Agent currently does *not* see this metric during its parameter search. It should be add to help the agent decision making in the future.
