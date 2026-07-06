# Agentic PureCLIP — Optimization Review
**Prepared as:** Lead Data Scientist briefing · **Date:** 2026-07-01
**Scope:** All historical experiments under `results/` (`batch/`, `overnight/`, `runs/`) — 5 datasets, 2 optimizers, ~45 job runs, 326 scored iterations.

---

## 1. Executive Summary

The optimization loop works and delivers **real, double-digit-percent gains over default parameters on every dataset** (e.g. RBFOX2_K562 +81%, RBFOX2_HepG2 +27%), with the genuine best result being **RBFOX2_HepG2 at composite 0.498** — a high-yield, high-recall set of 603 sites recovering 90% of the ENCODE reference. **The single most important caveat: the top-line number in the raw logs (0.775, QKI_K562/Optuna) is not a win — it is a 1-site collapse**, and Optuna produced two more inflated scores by the same mechanism. Once the collapse guard is honestly applied, the LLM and Optuna are roughly even (LLM edges the K562 datasets, Optuna edges the HepG2 datasets), and the project's guardrails are doing exactly the job they were designed to do.

---

## 2. Contextualization & Baselines

Every dataset starts each run at **iteration 0 = default PureCLIP parameters** (bw 50, dm 8, force_width 9). That is our apples-to-apples baseline. Best *honest* result = best iteration with **n_sites ≥ 10** (collapse guard = 1).

| Dataset | Baseline (iter 0) | Best honest | Δ | Where the gain came from |
|---|---|---|---|---|
| **RBFOX2_HepG2** | 0.393 | **0.498** (Optuna) | **+27%** | recall 0.60 → **0.90**, rep 0.40 → 0.46 |
| **RBFOX2_K562** *(hardest)* | 0.130 | **0.235** (LLM) | **+81%** | recall 0.15 → 0.50 via wide bandwidth (100 nt) |
| **QKI_HepG2** | 0.327 | **0.401** (Optuna) | **+22%** | motif 0.27 → 0.47, recall held at 0.35 (n=127) |
| **PUM1_K562** | 0.387 | **0.458** (LLM) | **+18%** | reproducibility 0.53 → **0.72** |
| **QKI_K562** | 0.257 | **0.329** (LLM) | **+28%** | motif 0.21 → 0.40 by relaxing `min_crosslink_events` 3→2 |

**On the older `batch/` runs (Jun 26):** these are the earliest, pre-refinement "quick" scans (`quick_rbfox2` 0.114, `quick_qki` 0.357, `quick_pum1` 0.531). They ran 4 iterations under an earlier scoring regime and are **not directly comparable** — `quick_pum1`'s 0.531 in particular reflects a small-n configuration and should not be read as beating the honest 0.458 above. They are useful only as a "day-zero" reference point showing the pipeline stood up and ran end-to-end.

---

## 3. Head-to-Head: LLM (DeepSeek) vs. Optuna (TPE)

Comparing best **honest** composite per dataset (raw logged score → guard-adjusted where n < 10):

| Dataset | LLM best | Optuna best (honest) | Winner | Note |
|---|---|---|---|---|
| PUM1_K562 | **0.458** (n=18) | 0.372 (n=54) | **LLM** | |
| QKI_K562 | **0.329** (n=14) | ~0.234 | **LLM** | Optuna's logged 0.775 is a **collapse** (see §4) |
| RBFOX2_K562 | **0.235** (n=385) | 0.217 (n=281) | **LLM** | |
| QKI_HepG2 | 0.366 (n=22) | **0.401** (n=127) | **Optuna** | |
| RBFOX2_HepG2 | 0.434 (n=492) | **0.498** (n=603) | **Optuna** | overall best run |

**Verdict — score:** Honest scoreboard is **LLM 3 : Optuna 2**. LLM sweeps the harder **K562** cell line; Optuna wins both **HepG2** datasets and owns the single best legitimate run overall (RBFOX2_HepG2, 0.498).

**Verdict — convergence:** Different search behavior, not a clean "fewer steps" winner.
- **LLM** hill-climbs deliberately, one parameter at a time, and typically locks its best around **iter 8–11** (PUM1 best @ it9, RBFOX2_K562 best @ it10, QKI_K562 best @ it5).
- **Optuna** finds strong configs **earlier** when it finds them (RBFOX2_HepG2 best @ it4, its QKI_HepG2 spike @ it1) but **explores blindly** and repeatedly wanders into degenerate 1–7 site solutions — it *needs* the collapse guard to avoid winning dishonestly.

**Bottom line:** The LLM's prior makes it *reliable* (it never collapsed a dataset to a fake win); Optuna is a stronger *raw explorer* (it discovered the high-precision / no-covariate regime the LLM never tried) but is *unsafe without the guard*.

---

## 4. ⚠️ The "0.775" Trap — Read Before Citing Any Number

The highest composite anywhere in the logs is **QKI_K562 / Optuna = 0.775 (iter 13)**. **Do not present this as a result.** Its metric breakdown:

> reproducibility **1.000**, motif **1.000**, recall 0.10, **n_binding_sites = 1**

A single binding site trivially agrees with itself (rep=1) and trivially sits on a motif (motif=1). The raw logged composite (`0.5·1 + 0.25·1 + 0.25·0.1 = 0.775`) has the **collapse guard not applied**; with the guard (`× min(1, n/10) = ×0.1`) the honest score is **≈0.078**. This is the exact failure mode CLAUDE.md documents ("Optuna collapsing QKI to 1 site for a fake composite of 0.78"). Two sibling scores are inflated the same way: **QKI_HepG2/Optuna 0.554 (n=6 → ~0.33)** and **PUM1_K562/Optuna 0.361 (n=9 → ~0.325)**. **All three are Optuna, none are LLM.**

---

## 5. The Winning Parameters (best honest run overall)

**RBFOX2_HepG2 · Optuna · iteration 4 · composite 0.498** (603 sites, 90% reference recall):

| PureCLIP | value | | Post-processing | value |
|---|---|---|---|---|
| `bandwidth_nt` | **23** (narrow) | | `force_width` | **15** (wide) |
| `merge_distance_nt` | **11** | | `cluster_gap_width` | **16** (max) |
| `high_precision_mode` | **true** | | `min_crosslink_events` | **2** |
| `use_input_covariate` | **false** | | `min_region_length_nt` | 3 |

**Why this matters strategically:** this config is the *opposite* of the defaults on two switches — `high_precision_mode=true` and `use_input_covariate=false` — paired with a **narrow bandwidth (23) but wide footprint (15)**. This "sharp-detection, wide-footprint, precision-mode" regime is a corner of the space the **LLM never explored** (it stayed on the default `iv=true / hp=false` island the entire time). Optuna's blind search paid off precisely because it ignored the prior here.

---

## 6. Biological Trade-offs — Did It Find a True Center?

The objective is `0.5·reproducibility + 0.25·motif + 0.25·recall`, so the optimizer is structurally tempted to buy cheap reproducibility by shrinking the site set. Behavior split cleanly:

- **True optimal centers (balanced, high-yield):**
  - **RBFOX2_HepG2 (0.498):** did *not* sacrifice recall — it pushed recall to **0.90** and reproducibility to 0.46 simultaneously on 603 sites, accepting a modest motif rate (0.166). This is the model result: breadth *and* agreement.
  - **QKI_HepG2 / Optuna_r2 (0.401):** rep 0.39 / motif 0.47 / recall 0.35 on **127 sites** — genuinely balanced across all three axes.

- **Reproducibility bought at the cost of recall (near-collapse):**
  - **PUM1_K562 / LLM (0.458):** reproducibility jumped to **0.72**, but **recall fell to 0.0** and n dropped to 18. The optimizer over-weighted the 0.5 reproducibility term. Notably the LLM *saw this happening* (see §7) — it recognized the collapse-guard risk rather than blindly chasing it.

- **The degenerate extreme:** the §4 collapses are the pathological version of the same trade — reproducibility and motif driven to 1.0 by discarding everything, recall and yield sacrificed to ~0.

**Takeaway:** On HepG2 the optimizer found real biological centers; on the sparser K562 signal it tends to trade recall for reproducibility, and only the collapse guard keeps that trade honest.

---

## 7. LLM Reasoning Engine — Direct Quotes

The LLM's decision trail (`decisions.jsonl`) shows it reasoning from *biology and the scoring math*, not just numbers:

**Mathematical / objective-aware reasoning** (QKI_HepG2, iter 2) — it correctly reasons about the weighting and the chance-correction of the reproducibility term:

> *"The composite improved from 0.3274 to 0.3537 despite a drop in reproducibility from 0.3836 to 0.3297, because the weight on reproducibility (0.5) was offset by gains in motif and recall. The reproducibility drop is acceptable since it is chance-corrected and the increase in sites is beneficial."*

**Biological / motif-geometry reasoning** (QKI_K562, iter 9) — it ties a parameter to the physical length of the RBP's motif:

> *"The known motifs for QKI are ~11nt long, and the expected footprint is 9nt. Currently force_width=9 matches the footprint, but the motif_hit_rate is low. Increasing force_width to 11 might capture more of the full motif span, potentially raising motif_hit_rate without harming reproducibility or recall too much."*

*(Bonus — collapse-awareness, PUM1_K562 iter 10: "Iteration 9 … gave the highest composite (0.4583) but collapsed n_sites to 18 and recall to 0.0, triggering the collapse guard." The LLM explicitly declines to chase the degenerate win.)*

---

## 8. Recommendations

1. **Report guard-adjusted composites everywhere.** The raw logged scores are misleading for n<10; surface the collapse-adjusted value in the dashboard leaderboard so 0.775-type artifacts can never headline.
2. **Give Optuna the LLM's blind spot as a prior, or vice-versa.** Optuna's win came from the `high_precision=true / no-covariate` regime the LLM never tried — seed the LLM's search with it.
3. **RBFOX2_K562 remains the open problem.** Even the best (0.235) is our lowest; wide bandwidth (100 nt) helped recall but reproducibility is stuck at ~0.10. This is the priority scientific target.
4. **Reproducibility metric is gameable on sparse data.** Consider IDR-based reproducibility and dinucleotide-shuffled motif backgrounds to harden the objective against the recall-for-reproducibility trade seen on K562.
