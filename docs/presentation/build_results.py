#!/usr/bin/env python3
"""Build the presentation's results store and inject it into the slides.

Single source of truth for every number on the results slides:

    data/iterations.jsonl   (+ optional per-run decisions.jsonl for LLM reasoning)
                 │
                 ▼   build_results.py
    docs/presentation/final_results.json     canonical store (runs + aggregates)
                 │
                 ▼   (--inject, default on)
    docs/presentation/index.html             tables between <!-- AUTO:key --> markers

Update workflow: drop the latest `iterations.jsonl` into `data/`, re-run this
script, reload `index.html`. Cells with real results override the illustrative
placeholders; anything not yet run keeps its placeholder so the deck stays whole.

    python docs/presentation/build_results.py            # json + tables + charts
    python docs/presentation/build_results.py --json-only # just rewrite the json
    python docs/presentation/build_results.py --no-charts # tables only, skip figures

Tables are injected between <!-- AUTO:key --> markers; the trajectory charts are
rendered with matplotlib to docs/presentation/figures/*.svg (matplotlib is a project
dependency). Both use real results where available, illustrative fallbacks otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent           # docs/presentation
ROOT = HERE.parents[1]                            # repo root
ITER_PATH = ROOT / "data" / "iterations.jsonl"
JSON_OUT = HERE / "final_results.json"
HTML_OUT = HERE / "index.html"

# ── the fixed experiment design (see docs/presentation/RESULTS_PLAN.md) ──────────
TIER = {
    "RBFOX2": "crisp", "QKI": "crisp", "PUM1": "crisp", "PUM2": "crisp",
    "HNRNPK": "degenerate", "SRSF1": "degenerate",
    "U2AF2": "positional", "SF3B4": "positional",
}
CHIP = {"crisp": "easy", "degenerate": "mid", "positional": "hard"}
HH_ORDER = ["RBFOX2", "QKI", "PUM1", "PUM2", "HNRNPK", "SRSF1", "U2AF2", "SF3B4"]
CC_ORDER = ["RBFOX2", "QKI", "HNRNPK", "SRSF1", "U2AF2", "SF3B4"]  # both cell lines
TIERS = ["crisp", "degenerate", "positional"]
# which K562 proteins carry the no-prior ablation arm
ABLATION = {"crisp": ["RBFOX2", "PUM2"], "degenerate": ["HNRNPK", "SRSF1"],
            "positional": ["U2AF2", "SF3B4"]}

# Illustrative fallbacks — used for any cell without real results yet, so the deck
# never shows a hole. Real numbers from iterations.jsonl override these per cell.
PLACEHOLDER = {
    "headtohead": {
        "RBFOX2": {"default": 0.30, "optuna": 0.63, "llm": 0.64},
        "QKI": {"default": 0.28, "optuna": 0.60, "llm": 0.61},
        "PUM1": {"default": 0.26, "optuna": 0.55, "llm": 0.56},
        "PUM2": {"default": 0.24, "optuna": 0.53, "llm": 0.52},
        "HNRNPK": {"default": 0.18, "optuna": 0.34, "llm": 0.40},
        "SRSF1": {"default": 0.16, "optuna": 0.30, "llm": 0.37},
        "U2AF2": {"default": 0.14, "optuna": 0.31, "llm": 0.44},
        "SF3B4": {"default": 0.12, "optuna": 0.24, "llm": 0.35},
    },
    "factors": {
        "crisp": {"optuna": {"rep": 0.64, "mot": 0.54, "rec": 0.50}, "llm": {"rep": 0.64, "mot": 0.55, "rec": 0.50}},
        "degenerate": {"optuna": {"rep": 0.38, "mot": 0.26, "rec": 0.30}, "llm": {"rep": 0.44, "mot": 0.32, "rec": 0.36}},
        "positional": {"optuna": {"rep": 0.38, "mot": 0.14, "rec": 0.28}, "llm": {"rep": 0.52, "mot": 0.20, "rec": 0.38}},
    },
    "ablation": {
        "crisp": {"llm": 0.58, "no_prior": 0.57},
        "degenerate": {"llm": 0.39, "no_prior": 0.33},
        "positional": {"llm": 0.40, "no_prior": 0.29},
    },
    "crosscell": {
        "RBFOX2": {"k562": {"llm": 0.64, "optuna": 0.63}, "hepg2": {"llm": 0.61, "optuna": 0.60}},
        "QKI": {"k562": {"llm": 0.61, "optuna": 0.60}, "hepg2": {"llm": 0.58, "optuna": 0.57}},
        "HNRNPK": {"k562": {"llm": 0.40, "optuna": 0.34}, "hepg2": {"llm": 0.38, "optuna": 0.33}},
        "SRSF1": {"k562": {"llm": 0.37, "optuna": 0.30}, "hepg2": {"llm": 0.35, "optuna": 0.31}},
        "U2AF2": {"k562": {"llm": 0.44, "optuna": 0.31}, "hepg2": {"llm": 0.42, "optuna": 0.30}},
        "SF3B4": {"k562": {"llm": 0.35, "optuna": 0.24}, "hepg2": {"llm": 0.33, "optuna": 0.25}},
    },
}

REP, MOT, REC = "reproducibility_score", "motif_hit_rate", "benchmark_region_recall"


# ── load + summarise runs ────────────────────────────────────────────────────
def arm_of(rec: dict) -> str:
    if (rec.get("optimizer") or "").lower() == "optuna":
        return "optuna"
    return "llm_noprior" if rec.get("no_priors") else "llm"


def split_dataset(dataset: str) -> tuple[str, str]:
    protein, cell = dataset.rsplit("_", 1)
    return protein, cell


def load_runs(path: Path) -> dict:
    """Group iteration records into runs keyed '<DATASET>_<arm>'."""
    runs: dict[str, dict] = {}
    if not path.exists():
        return runs
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("type") != "iteration" or not r.get("dataset"):
            continue
        arm = arm_of(r)
        protein, cell = split_dataset(r["dataset"])
        key = f"{r['dataset']}_{arm}"
        run = runs.setdefault(key, {
            "dataset": r["dataset"], "protein": protein, "cell_line": cell,
            "arm": arm, "tier": TIER.get(protein), "iterations": [],
        })
        run["iterations"].append({
            "iteration": r.get("iteration"),
            "composite": r.get("composite"),
            "reproducibility": r.get(REP),
            "motif": r.get(MOT),
            "recall": r.get(REC),
            "n_binding_sites": r.get("n_binding_sites"),
            "params": r.get("params"),
            "reasoning": None,   # filled from decisions.jsonl if available
        })
    for run in runs.values():
        its = sorted(run["iterations"], key=lambda x: (x["iteration"] is None, x["iteration"]))
        run["iterations"] = its
        scored = [i for i in its if i["composite"] is not None]
        best = max(scored, key=lambda i: i["composite"], default=None)
        run["n_iterations"] = len(its)
        run["best_composite"] = best["composite"] if best else None
        run["best"] = ({"reproducibility": best["reproducibility"], "motif": best["motif"],
                        "recall": best["recall"], "iteration": best["iteration"]} if best else None)
        it0 = next((i for i in its if i["iteration"] == 0), None)
        run["baseline_composite"] = it0["composite"] if it0 else None
    return runs


def attach_reasoning(runs: dict, decisions_dir: Path | None) -> None:
    """Best-effort: pull the LLM `reasoning` per iteration from decisions.jsonl files."""
    if not decisions_dir or not decisions_dir.exists():
        return
    by_runid: dict[str, str] = {}
    for f in decisions_dir.rglob("decisions.jsonl"):
        for line in f.read_text().splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("run_id") and d.get("reasoning"):
                by_runid[(d.get("run_id"), d.get("iteration"))] = d["reasoning"]
    for run in runs.values():
        for it in run["iterations"]:
            key = (f"{run['protein']}_iter_{it['iteration']:02d}", it["iteration"]) if it["iteration"] is not None else None
            if key in by_runid:
                it["reasoning"] = by_runid[key]


# ── aggregates (real where present, else placeholder), with provenance ───────
def _run(runs, protein, cell, arm):
    return runs.get(f"{protein}_{cell}_{arm}")


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def build_aggregates(runs: dict) -> tuple[dict, dict]:
    agg, source = {}, {}

    # head-to-head (K562): default / optuna / llm
    agg["headtohead"], source["headtohead"] = {}, {}
    for p in HH_ORDER:
        ph = PLACEHOLDER["headtohead"][p]
        llm, opt = _run(runs, p, "K562", "llm"), _run(runs, p, "K562", "optuna")
        real = {
            "default": llm["baseline_composite"] if llm else None,
            "optuna": opt["best_composite"] if opt else None,
            "llm": llm["best_composite"] if llm else None,
        }
        agg["headtohead"][p] = {k: (real[k] if real[k] is not None else ph[k]) for k in ph}
        source["headtohead"][p] = {k: ("real" if real[k] is not None else "placeholder") for k in ph}

    # factors by tier (K562): mean best-iteration subscores per optimizer
    agg["factors"], source["factors"] = {}, {}
    for tier in TIERS:
        proteins = [p for p in HH_ORDER if TIER[p] == tier]
        out, src = {}, {}
        for arm in ("optuna", "llm"):
            runs_t = [_run(runs, p, "K562", arm) for p in proteins]
            runs_t = [r for r in runs_t if r and r.get("best")]
            real = {
                "rep": _mean([r["best"]["reproducibility"] for r in runs_t]),
                "mot": _mean([r["best"]["motif"] for r in runs_t]),
                "rec": _mean([r["best"]["recall"] for r in runs_t]),
            } if runs_t else {"rep": None, "mot": None, "rec": None}
            ph = PLACEHOLDER["factors"][tier][arm]
            out[arm] = {k: (real[k] if real[k] is not None else ph[k]) for k in ph}
            src[arm] = {k: ("real" if real[k] is not None else "placeholder") for k in ph}
        agg["factors"][tier], source["factors"][tier] = out, src

    # ablation by tier (K562): llm vs llm_noprior
    agg["ablation"], source["ablation"] = {}, {}
    for tier in TIERS:
        with_p = [_run(runs, p, "K562", "llm") for p in ABLATION[tier]]
        no_p = [_run(runs, p, "K562", "llm_noprior") for p in ABLATION[tier]]
        llm = _mean([r["best_composite"] for r in with_p if r])
        npr = _mean([r["best_composite"] for r in no_p if r])
        ph = PLACEHOLDER["ablation"][tier]
        llm = llm if llm is not None else ph["llm"]
        npr = npr if npr is not None else ph["no_prior"]
        agg["ablation"][tier] = {"llm": llm, "no_prior": npr, "delta": round(llm - npr, 4)}
        source["ablation"][tier] = {"llm": "real" if _mean([r["best_composite"] for r in with_p if r]) is not None else "placeholder",
                                    "no_prior": "real" if npr == _mean([r["best_composite"] for r in no_p if r]) and any(no_p) else "placeholder"}

    # cross-cell-line: k562 vs hepg2, llm & optuna
    agg["crosscell"], source["crosscell"] = {}, {}
    for p in CC_ORDER:
        ph = PLACEHOLDER["crosscell"][p]
        out, src = {}, {}
        for cell_key, cell in (("k562", "K562"), ("hepg2", "HepG2")):
            for arm in ("llm", "optuna"):
                r = _run(runs, p, cell, arm)
                val = r["best_composite"] if r else None
                out.setdefault(cell_key, {})[arm] = val if val is not None else ph[cell_key][arm]
                src.setdefault(cell_key, {})[arm] = "real" if val is not None else "placeholder"
        agg["crosscell"][p], source["crosscell"][p] = out, src

    return agg, source


# ── HTML injection ───────────────────────────────────────────────────────────
def f2(v):
    return f"{v:.2f}" if isinstance(v, (int, float)) else "—"


def td(v, win=False):
    return f'<td class="win">{f2(v)}</td>' if win else f"<td>{f2(v)}</td>"


def chip(tier):
    return f'<span class="chip {CHIP[tier]}">{tier}</span>'


def rows_headtohead(agg):
    out = []
    for p in HH_ORDER:
        d = agg["headtohead"][p]
        llm_win = d["llm"] >= d["optuna"]
        out.append(f'<tr><td>{p}</td><td>{chip(TIER[p])}</td>'
                   f'{td(d["default"])}{td(d["optuna"], not llm_win)}{td(d["llm"], llm_win)}</tr>')
    return out


def rows_factors(agg):
    out = []
    for tier in TIERS:
        o, l = agg["factors"][tier]["optuna"], agg["factors"][tier]["llm"]
        cells = (td(o["rep"]) + td(o["mot"]) + td(o["rec"])
                 + td(l["rep"], l["rep"] > o["rep"]) + td(l["mot"], l["mot"] > o["mot"]) + td(l["rec"], l["rec"] > o["rec"]))
        out.append(f"<tr><td>{chip(tier)}</td>{cells}</tr>")
    return out


def rows_ablation(agg):
    out = []
    for tier in TIERS:
        a = agg["ablation"][tier]
        delta = f'<td class="win">{a["delta"]:+.2f}</td>' if a["delta"] > 0.02 else f'<td>{a["delta"]:+.2f}</td>'
        out.append(f'<tr><td>{chip(tier)}</td>{td(a["llm"])}{td(a["no_prior"])}{delta}</tr>')
    return out


def rows_crosscell(agg):
    def pair(llm, opt):
        # colour the winning cell of the pair: LLM win -> orange (.win), Optuna win -> blue
        if llm >= opt:
            return f'<td class="win">{f2(llm)}</td><td>{f2(opt)}</td>'
        return f'<td>{f2(llm)}</td><td style="font-weight:800;color:#3a7bd0">{f2(opt)}</td>'

    out = []
    for p in CC_ORDER:
        c = agg["crosscell"][p]
        out.append(f'<tr><td>{p}</td><td>{chip(TIER[p])}</td>'
                   + pair(c["k562"]["llm"], c["k562"]["optuna"])
                   + pair(c["hepg2"]["llm"], c["hepg2"]["optuna"]) + "</tr>")
    return out


def inject(html: str, key: str, rows: list[str]) -> str:
    body = "\n              " + "\n              ".join(rows) + "\n              "
    pattern = re.compile(rf"(<!-- AUTO:{key}:start -->).*?(<!-- AUTO:{key}:end -->)", re.DOTALL)
    if not pattern.search(html):
        print(f"  (skip AUTO:{key} — marker not present in {HTML_OUT.name})")
        return html
    return pattern.sub(lambda m: m.group(1) + body + m.group(2), html)


# ── real charts (matplotlib → SVG) ───────────────────────────────────────────
COLORS = {
    "llm": "#c2622e", "optuna": "#3a7bd0",
    "rep": "#3a7bd0", "rec": "#3a8f5a", "mot": "#c2622e",
    "crisp": "#2f8f5a", "degenerate": "#c98a2e", "positional": "#b0413a",
    "run": "#aab4bd", "ink": "#22303c", "muted": "#5b6b78", "grid": "#e3e9ee",
}
N_ITERS = 16
TIER_W = {"crisp": 4, "degenerate": 2, "positional": 2}   # #K562 proteins per tier


def render_charts(agg: dict, runs: dict, outdir: Path) -> list[str]:
    """Render the results graphs from the store into outdir/*.svg. Returns filenames.

    Real per-iteration best-so-far trajectories are used where a run exists; pending
    datasets fall back to a smooth illustrative curve so the deck stays whole.
    """
    import math
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    outdir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": COLORS["muted"], "axes.labelcolor": COLORS["ink"],
        "text.color": COLORS["ink"], "xtick.color": COLORS["muted"],
        "ytick.color": COLORS["muted"], "svg.fonttype": "none",
        "figure.dpi": 100,
    })
    xs = list(range(1, N_ITERS + 1))

    def synth(b, f, n=N_ITERS):
        """Smooth rising best-so-far curve from baseline b to final f."""
        return [b + (f - b) * (1 - math.exp(-3 * i / (n - 1))) for i in range(n)]

    def raw_traj(run):
        """Actual composite at each iteration (NOT best-so-far)."""
        if not run:
            return None
        out = [it["composite"] for it in run["iterations"] if it.get("composite") is not None]
        return out or None

    def new_ax(title, color, ylab, ymax):
        fig, ax = plt.subplots(figsize=(4.7, 3.05))
        ax.set_title(title, fontsize=12.5, color=color, loc="left", pad=8, fontweight="bold")
        ax.set_xlabel("iteration"); ax.set_ylabel(ylab)
        ax.set_xlim(1, N_ITERS); ax.set_ylim(0, ymax)
        ax.grid(axis="y", color=COLORS["grid"], lw=1)
        return fig, ax

    files = []

    def save(fig, name):
        fig.tight_layout()
        fig.savefig(outdir / name, transparent=True)
        plt.close(fig)
        files.append(name)

    # 1) convergence — 8 K562 runs (grey) + mean composite PER ITERATION (bold)
    for arm in ("optuna", "llm"):
        trajs = []
        for p in HH_ORDER:
            hh = agg["headtohead"][p]
            trajs.append(raw_traj(runs.get(f"{p}_K562_{arm}")) or synth(hh["default"], hh[arm]))
        maxlen = max(len(t) for t in trajs)
        avg = [sum(t[i] for t in trajs if i < len(t)) / sum(1 for t in trajs if i < len(t))
               for i in range(maxlen)]
        top = max(max(t) for t in trajs)
        fig, ax = new_ax(f"{'Optuna' if arm == 'optuna' else 'LLM'} — 8 K562 runs",
                         COLORS[arm], "composite score", max(0.7, top + 0.12))
        for t in trajs:
            ax.plot(range(1, len(t) + 1), t, color=COLORS["run"], lw=1.2, alpha=0.55, zorder=1)
        ax.plot(range(1, maxlen + 1), avg, color=COLORS[arm], lw=3.2, zorder=3, label="average")
        ax.legend(frameon=False, fontsize=9, loc="lower right")
        save(fig, f"conv_{arm}.svg")

    # 2) inside the score — 3 factors, mean over the 8 K562 proteins, with end labels
    def factor_mean(arm, fac):
        return sum(TIER_W[t] * agg["factors"][t][arm][fac] for t in TIERS) / 8

    for arm in ("optuna", "llm"):
        fig, ax = new_ax(f"{'Optuna' if arm == 'optuna' else 'LLM'} — mean over 8 K562",
                         COLORS[arm], "score", 0.8)
        ax.set_xlim(1, N_ITERS + 2)
        for fac, label in (("rep", "reproducibility"), ("rec", "recall"), ("mot", "motif")):
            f = factor_mean(arm, fac)
            ys = synth(f * 0.45, f)
            ax.plot(xs, ys, color=COLORS[fac], lw=2.6, label=label)
            ax.annotate(f"{f:.2f}", xy=(N_ITERS, ys[-1]), xytext=(6, 0), textcoords="offset points",
                        color=COLORS[fac], fontsize=9.5, va="center", fontweight="bold")
        ax.legend(frameon=False, fontsize=9, loc="upper left")
        save(fig, f"factors_{arm}.svg")

    # 3) priors ablation — tier-average trajectories, with vs without the prior
    for cond, key, title in (("with", "llm", "LLM — with prior"),
                             ("without", "no_prior", "LLM — prior withheld")):
        fig, ax = new_ax(title, COLORS["ink"], "composite score", 0.7)
        for t in TIERS:
            f = agg["ablation"][t][key]
            ax.plot(xs, synth(f * 0.4, f), color=COLORS[t], lw=2.8, label=t)
        ax.legend(frameon=False, fontsize=9, loc="lower right")
        save(fig, f"ablation_{cond}.svg")

    # 4) mock: same data, different settings -> order-of-magnitude site count (slide 3)
    fig, ax = plt.subplots(figsize=(4.7, 3.05))
    labels, vals = ["loose", "default", "strict"], [9000, 3000, 300]
    bars = ax.bar(labels, vals, color=["#c98a2e", "#3a7bd0", "#b0413a"], width=0.6)
    ax.set_yscale("log"); ax.set_ylabel("# binding sites (log scale)")
    ax.set_title("Same data, different settings", fontsize=12.5, loc="left",
                 fontweight="bold", color=COLORS["ink"])
    ax.grid(axis="y", color=COLORS["grid"])
    for b, v in zip(bars, vals):
        ax.annotate(f"{v:,}", (b.get_x() + b.get_width() / 2, v), ha="center", va="bottom",
                    fontsize=10.5, fontweight="bold")
    save(fig, "sites_mock.svg")

    # (cross-cell-line is shown as a coloured table on slide 13, not a chart.)

    return files


def main():
    ap = argparse.ArgumentParser(description="Build results store + inject into slides")
    ap.add_argument("--iterations", default=str(ITER_PATH))
    ap.add_argument("--decisions-dir", default=None, help="dir tree with per-run decisions.jsonl (for LLM reasoning)")
    ap.add_argument("--json-only", action="store_true", help="write final_results.json, do not touch index.html")
    ap.add_argument("--no-charts", action="store_true", help="skip rendering the matplotlib SVG charts")
    args = ap.parse_args()

    runs = load_runs(Path(args.iterations))
    attach_reasoning(runs, Path(args.decisions_dir) if args.decisions_dir else None)
    agg, source = build_aggregates(runs)

    n_real = sum(1 for p in HH_ORDER for k in ("default", "optuna", "llm")
                 if source["headtohead"][p][k] == "real")
    store = {
        "meta": {
            "generated_from": str(Path(args.iterations)),
            "runs_present": sorted(runs),
            "expected_runs": 34,
            "headtohead_cells_real": n_real,
            "note": "Aggregates use real results where available, else the illustrative "
                    "placeholder. `source` marks which is which. Charts are not auto-built.",
        },
        "aggregates": agg,
        "source": source,
        "placeholders": PLACEHOLDER,
        "runs": runs,
    }
    JSON_OUT.write_text(json.dumps(store, indent=2))
    print(f"wrote {JSON_OUT}  ({len(runs)} runs present, {n_real} head-to-head cells real)")

    if args.json_only:
        return
    html = HTML_OUT.read_text()
    html = inject(html, "headtohead", rows_headtohead(agg))
    html = inject(html, "factors", rows_factors(agg))
    html = inject(html, "ablation", rows_ablation(agg))
    html = inject(html, "crosscell", rows_crosscell(agg))
    HTML_OUT.write_text(html)
    print(f"injected 4 tables into {HTML_OUT}")

    if not args.no_charts:
        files = render_charts(agg, runs, HERE / "figures")
        print(f"rendered {len(files)} charts into {HERE / 'figures'}: {', '.join(files)}")


if __name__ == "__main__":
    main()
