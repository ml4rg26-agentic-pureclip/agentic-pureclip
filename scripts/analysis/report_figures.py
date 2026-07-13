"""Generate the figures used in ``docs/report`` from an iteration snapshot.

The runner appends records when jobs are retried.  Loading therefore keeps the
newest record for each ``(job_id, iteration)`` pair before calculating a best
score.  This makes the committed snapshot reproduce the final batch state
without counting superseded attempts twice.

Usage:
    uv run python scripts/analysis/report_figures.py \
        [--input results/overnight/iterations.jsonl] \
        [--outdir docs/report/images]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent
DEFAULT_INPUT = HERE / "iterations_snapshot.jsonl"

BENCHMARKS = {
    "K562": ["QKI", "PUM1", "PUM2", "HNRNPK", "SRSF1", "U2AF2", "SF3B4"],
    "HepG2": ["RBFOX2", "HNRNPK", "SRSF1", "U2AF2", "SF3B4"],
}
PRIOR_ABLATIONS = ["QKI", "PUM2", "HNRNPK", "SRSF1", "U2AF2", "SF3B4"]

COLORS = {
    "llm": "#176B87",
    "optuna": "#6D4C7D",
    "ink": "#263238",
    "line": "#BCC4CA",
}


def load(path: Path):
    """Load final iteration records, deduplicating retried job iterations."""
    newest = {}
    with path.open() as fh:
        for line in fh:
            record = json.loads(line)
            if record.get("type") != "iteration":
                continue
            key = (record["job_id"], record["iteration"])
            previous = newest.get(key)
            if previous is None or record.get("mtime", 0) >= previous.get("mtime", 0):
                newest[key] = record

    by_job = defaultdict(list)
    for record in newest.values():
        by_job[record["job_id"]].append(record)
    for rows in by_job.values():
        rows.sort(key=lambda row: row["iteration"])
    return by_job


def job_id(protein: str, cell_line: str, arm: str) -> str:
    return f"final_{protein.lower()}_{cell_line.lower()}_{arm}"


def best_score(by_job, job: str) -> float:
    rows = by_job.get(job, [])
    if not rows:
        raise KeyError(f"No iteration records found for {job}")
    return max(row["composite"] for row in rows)


def fig_benchmark(by_job, outdir: Path):
    """Plot all final LLM--TPE comparisons as two compact dumbbell panels."""
    plt.rcParams.update({"font.size": 8.5, "axes.titlesize": 10, "axes.labelsize": 9})
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(10.6, 3.85),
        sharex=True,
        gridspec_kw={"width_ratios": [1.08, 0.92]},
    )

    for ax, (cell_line, proteins) in zip(axes, BENCHMARKS.items()):
        y_positions = list(range(len(proteins)))[::-1]
        llm_higher = 0
        tpe_higher = 0
        for y, protein in zip(y_positions, proteins):
            llm_job = job_id(protein, cell_line, "llm")
            tpe_job = job_id(protein, cell_line, "optuna")
            llm = best_score(by_job, llm_job)
            tpe = best_score(by_job, tpe_job)
            llm_higher += llm > tpe
            tpe_higher += tpe > llm

            ax.plot([llm, tpe], [y, y], color=COLORS["line"], lw=1.7, zorder=1)
            for score, arm, marker in (
                (llm, "llm", "o"),
                (tpe, "optuna", "^"),
            ):
                ax.scatter(
                    score,
                    y,
                    s=43,
                    marker=marker,
                    facecolor=COLORS[arm],
                    edgecolor=COLORS[arm],
                    linewidth=0.7,
                    zorder=3,
                )

        ax.set_yticks(y_positions)
        ax.set_yticklabels(proteins)
        ax.set_title(cell_line, loc="left", weight="bold", color=COLORS["ink"])
        ax.set_xlabel("Best composite score")
        ax.set_xlim(0.10, 0.57)
        ax.grid(axis="x", alpha=0.22, lw=0.7)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.text(
            0.99,
            1.015,
            f"Observed higher: LLM {llm_higher}  |  TPE {tpe_higher}",
            transform=ax.transAxes,
            ha="right",
            va="bottom",
            fontsize=7.4,
            color="#56616A",
        )

    handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=COLORS["llm"],
               markeredgecolor=COLORS["llm"], markersize=6, label="LLM with prior"),
        Line2D([0], [0], marker="^", color="none", markerfacecolor=COLORS["optuna"],
               markeredgecolor=COLORS["optuna"], markersize=6, label="Optuna (TPE)"),
    ]
    fig.legend(handles=handles, ncol=2, loc="lower center", frameon=False, bbox_to_anchor=(0.5, -0.01))
    fig.suptitle(
        "Observed optimizer outcomes across completed paired runs",
        x=0.08,
        y=1.03,
        ha="left",
        fontsize=11,
        weight="bold",
        color=COLORS["ink"],
    )
    fig.tight_layout(rect=(0, 0.08, 1, 0.98), w_pad=2.3)
    out = outdir / "benchmark_summary.png"
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def fig_prior_ablation(by_job, outdir: Path):
    """Plot the effect of providing RBP-specific context to the LLM."""
    deltas = []
    for protein in PRIOR_ABLATIONS:
        with_prior = best_score(by_job, job_id(protein, "K562", "llm"))
        without_prior = best_score(by_job, job_id(protein, "K562", "llm_noprior"))
        deltas.append(with_prior - without_prior)

    y_positions = list(range(len(PRIOR_ABLATIONS)))[::-1]
    ordered = sorted(deltas)
    mean_delta = sum(deltas) / len(deltas)
    median_delta = (ordered[2] + ordered[3]) / 2
    fig, ax = plt.subplots(figsize=(7.3, 3.0))
    for y, delta in zip(y_positions, deltas):
        ax.plot([0, delta], [y, y], color=COLORS["line"], lw=2.0, zorder=1)
        ax.scatter(delta, y, s=45, color=COLORS["llm"], zorder=2)
    ax.axvline(0, color=COLORS["ink"], lw=0.9)
    ax.set_yticks(y_positions)
    ax.set_yticklabels(PRIOR_ABLATIONS)
    ax.set_xlabel("Prior effect: best LLM with prior - best LLM without prior")
    ax.set_xlim(-0.05, 0.10)
    ax.grid(axis="x", alpha=0.22, lw=0.7)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    for y, delta in zip(y_positions, deltas):
        offset = 0.0025 if delta >= 0 else -0.0025
        ax.text(
            delta + offset,
            y,
            f"{delta:+.3f}",
            va="center",
            ha="left" if delta >= 0 else "right",
            fontsize=8,
            color=COLORS["ink"],
        )
    ax.text(
        0.99,
        0.94,
        f"Mean {mean_delta:+.3f}  |  median {median_delta:+.3f}",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=8,
        color="#56616A",
    )
    ax.set_title(
        "Prior and no-prior LLM outcomes were similar overall (K562)",
        loc="left",
        fontsize=10.5,
        weight="bold",
        color=COLORS["ink"],
    )
    fig.tight_layout()
    out = outdir / "prior_ablation.png"
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def fig_pipeline(outdir: Path):
    """Draw the optimizer-specific inputs and the shared evaluation path."""
    fig, ax = plt.subplots(figsize=(10.6, 3.25))
    ax.set_xlim(0, 10.6)
    ax.set_ylim(0, 3.25)
    ax.axis("off")

    def box(x, y, w, h, heading, detail, fill, edge):
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.06",
            facecolor=fill, edgecolor=edge, linewidth=1.2,
        ))
        ax.text(x + w / 2, y + h * 0.66, heading, ha="center", va="center",
                fontsize=8.8, weight="bold", color=COLORS["ink"])
        ax.text(x + w / 2, y + h * 0.32, detail, ha="center", va="center",
                multialignment="center", linespacing=1.15, fontsize=7.1, color="#44515A")

    box(0.15, 1.82, 1.85, 0.83, "LLM proposal", "RBP prior + decomposed\nscore trajectory", "#E8F1F5", COLORS["llm"])
    box(0.15, 0.58, 1.85, 0.83, "TPE proposal", "scalar-score history", "#F0EAF3", COLORS["optuna"])
    box(2.55, 1.18, 1.65, 0.90, "Candidate", "7 bounded\nparameters", "#F4F1E8", "#8A6D1D")
    box(4.72, 1.18, 1.85, 0.90, "Shared workflow", "PureCLIP +\npost-processing", "#EDF3EA", "#477A3A")
    box(7.08, 1.18, 1.80, 0.90, "Measurements", "replicates · motif\nreference recall", "#F5EBF1", "#8B3E68")
    box(9.38, 1.18, 1.05, 0.90, "Objective", "weighted score\n+ yield guard", "#EFEFF2", "#4B5563")

    arrow = {"arrowstyle": "-|>", "mutation_scale": 10, "linewidth": 1.1, "color": "#59636B"}
    ax.add_patch(FancyArrowPatch((2.02, 2.22), (2.53, 1.76), **arrow))
    ax.add_patch(FancyArrowPatch((2.02, 1.00), (2.53, 1.49), **arrow))
    for start, end in [((4.22, 1.63), (4.70, 1.63)), ((6.59, 1.63), (7.06, 1.63)), ((8.90, 1.63), (9.36, 1.63))]:
        ax.add_patch(FancyArrowPatch(start, end, **arrow))

    ax.add_patch(FancyArrowPatch(
        (7.85, 2.13), (1.05, 2.69), connectionstyle="arc3,rad=0.08",
        arrowstyle="-|>", mutation_scale=10, linewidth=1.05, color=COLORS["llm"],
    ))
    ax.text(4.55, 2.79, "component feedback", ha="center", va="center",
            fontsize=7.3, color=COLORS["llm"],
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.0})
    ax.add_patch(FancyArrowPatch(
        (9.90, 1.13), (1.05, 0.54), connectionstyle="arc3,rad=-0.08",
        arrowstyle="-|>", mutation_scale=10, linewidth=1.05, color=COLORS["optuna"],
    ))
    ax.text(5.55, 0.31, "scalar feedback", ha="center", va="center",
            fontsize=7.3, color=COLORS["optuna"],
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.0})
    ax.text(5.3, 3.12, "Different proposal loops, matched evaluation",
            ha="center", va="center", fontsize=10.5, weight="bold", color=COLORS["ink"])

    out = outdir / "pipeline_overview.png"
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--outdir",
        type=Path,
        default=HERE.parents[1] / "docs" / "report" / "images",
    )
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    by_job = load(args.input)
    print("wrote", fig_benchmark(by_job, args.outdir))
    print("wrote", fig_prior_ablation(by_job, args.outdir))
    print("wrote", fig_pipeline(args.outdir))


if __name__ == "__main__":
    main()
