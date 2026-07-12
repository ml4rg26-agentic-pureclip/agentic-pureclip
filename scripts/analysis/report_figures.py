"""Generate the figures used in docs/report from an iterations.jsonl snapshot.

Reads the aggregated per-iteration record written by scripts/run/overnight_batch.py
(results/overnight/iterations.jsonl on the runner) and writes publication figures into
docs/report/images:

  convergence_ablation.png  best-so-far composite vs. iteration for the three
                            K562 ablation-gradient datasets (PUM2 / HNRNPK /
                            U2AF2), one panel each, LLM-prior vs. LLM-no-prior
                            vs. Optuna, with the default-parameter baseline.
  deltas_by_tier.png        prior-benefit (LLM_prior - LLM_noprior) and
                            head-to-head (LLM_prior - Optuna) deltas by motif
                            difficulty tier.
  pipeline_overview.png     overview of the shared evaluation loop.

Usage:
    uv run python scripts/analysis/report_figures.py \
        [--input results/overnight/iterations.jsonl] \
        [--outdir docs/report/images]

The committed default input is the snapshot shipped alongside this script so the
figures rebuild without the (gitignored) runner results tree.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent
DEFAULT_INPUT = HERE / "iterations_snapshot.jsonl"

# job_id -> plotting arm; only the fair-comparison K562 runs are shown.
ABLATION = {
    "PUM2 (crisp)": {
        "llm": "final_pum2_k562_llm",
        "llm_noprior": "final_pum2_k562_llm_noprior",
        "optuna": "final_pum2_k562_optuna",
    },
    "HNRNPK (degenerate)": {
        "llm": "final_hnrnpk_k562_llm",
        "llm_noprior": "final_hnrnpk_k562_llm_noprior",
        "optuna": "final_hnrnpk_k562_optuna",
    },
    "U2AF2 (positional)": {
        "llm": "final_u2af2_k562_llm",
        "llm_noprior": "final_u2af2_k562_llm_noprior",
        "optuna": "final_u2af2_k562_optuna",
    },
}

ARM_STYLE = {
    "llm": ("LLM with prior", "#176B87", "-", "o"),
    "llm_noprior": ("LLM without prior", "#D97706", "--", "s"),
    "optuna": ("Optuna (TPE)", "#5B6470", ":", "^"),
}


def load(path: Path):
    by_job = defaultdict(list)
    with open(path) as fh:
        for line in fh:
            rec = json.loads(line)
            if rec.get("type") == "iteration":
                by_job[rec["job_id"]].append(rec)
    for job in by_job:
        by_job[job].sort(key=lambda r: r["iteration"])
    return by_job


def running_best(comps):
    best, out = float("-inf"), []
    for c in comps:
        best = max(best, c)
        out.append(best)
    return out


def fig_convergence(by_job, outdir: Path):
    plt.rcParams.update({"font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9})
    fig, axes = plt.subplots(1, 3, figsize=(10.6, 3.25), sharey=True)
    for ax, (title, arms) in zip(axes, ABLATION.items()):
        baseline = None
        for arm, job in arms.items():
            rows = by_job.get(job)
            if not rows:
                continue
            iters = [r["iteration"] for r in rows]
            best = running_best([r["composite"] for r in rows])
            if baseline is None:
                baseline = rows[0]["composite"]
            label, color, ls, marker = ARM_STYLE[arm]
            ax.plot(iters, best, ls, color=color, marker=marker, ms=4, lw=1.8, label=label)
        if baseline is not None:
            ax.axhline(baseline, color="black", lw=0.8, alpha=0.5)
            ax.text(0.02, baseline + 0.004, "default", fontsize=7,
                    transform=ax.get_yaxis_transform(), va="bottom", alpha=0.7)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Evaluation")
        ax.grid(alpha=0.25)
    axes[0].set_ylabel("Best composite score")
    axes[0].legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    out = outdir / "convergence_ablation.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out


def fig_deltas(by_job, outdir: Path):
    tiers, prior_d, h2h_d = [], [], []
    for title, arms in ABLATION.items():
        def best(job):
            rows = by_job.get(job)
            return max(r["composite"] for r in rows) if rows else None
        llm, npr, opt = best(arms["llm"]), best(arms["llm_noprior"]), best(arms["optuna"])
        tiers.append(title.split(" (")[0])
        prior_d.append(llm - npr)
        h2h_d.append(llm - opt)

    x = range(len(tiers))
    w = 0.38
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.bar([i - w / 2 for i in x], prior_d, w, label="prior benefit (LLM$-$no-prior)", color="#1b6ca8")
    ax.bar([i + w / 2 for i in x], h2h_d, w, label="head-to-head (LLM$-$Optuna)", color="#c1666b")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(tiers)
    ax.set_ylabel(r"$\Delta$ composite")
    ax.set_title("Effect of the biological prior by motif difficulty (K562)")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    out = outdir / "deltas_by_tier.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out


def fig_pipeline(outdir: Path):
    """Draw the matched optimizer/evaluation design used in the study."""
    fig, ax = plt.subplots(figsize=(10.6, 2.7))
    ax.set_xlim(0, 10.6)
    ax.set_ylim(0, 3.0)
    ax.axis("off")

    boxes = [
        (0.15, 1.15, 1.75, 0.9, "Optimizer", "LLM or Optuna", "#E8F1F5", "#176B87"),
        (2.35, 1.15, 1.75, 0.9, "Parameters", "7 bounded variables", "#F4F1E8", "#8A6D1D"),
        (4.55, 1.15, 1.75, 0.9, "PureCLIP pipeline", "merged + replicate calls", "#EDF3EA", "#477A3A"),
        (6.75, 1.15, 1.75, 0.9, "Biological scoring", "reproducibility | motif | recall", "#F5EBF1", "#8B3E68"),
        (8.95, 1.15, 1.5, 0.9, "Objective", "composite + yield guard", "#EFEFF2", "#4B5563"),
    ]
    for x, y, w, h, heading, detail, fill, edge in boxes:
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.06",
            facecolor=fill, edgecolor=edge, linewidth=1.2,
        ))
        ax.text(x + w / 2, y + 0.59, heading, ha="center", va="center",
                fontsize=9, weight="bold", color="#20252B")
        ax.text(x + w / 2, y + 0.29, detail, ha="center", va="center",
                fontsize=7.5, color="#38414A")

    for left, right in zip(boxes, boxes[1:]):
        start = (left[0] + left[2] + 0.05, 1.60)
        end = (right[0] - 0.05, 1.60)
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=10,
                                     linewidth=1.1, color="#4B5563"))

    ax.add_patch(FancyArrowPatch(
        (9.70, 1.08), (1.0, 1.08), connectionstyle="arc3,rad=-0.20",
        arrowstyle="-|>", mutation_scale=11, linewidth=1.1, color="#176B87",
    ))
    ax.text(5.35, 0.34, "Decomposed scores and the best-so-far trajectory are returned to the optimizer",
            ha="center", va="center", fontsize=8, color="#176B87",
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.5})
    ax.text(5.3, 2.65, "Shared evaluation; only the parameter-proposal strategy changes",
            ha="center", va="center", fontsize=10, weight="bold", color="#20252B")

    out = outdir / "pipeline_overview.png"
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--outdir", type=Path,
                    default=HERE.parents[1] / "docs" / "report" / "images")
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    by_job = load(args.input)
    print("wrote", fig_convergence(by_job, args.outdir))
    print("wrote", fig_deltas(by_job, args.outdir))
    print("wrote", fig_pipeline(args.outdir))


if __name__ == "__main__":
    main()
