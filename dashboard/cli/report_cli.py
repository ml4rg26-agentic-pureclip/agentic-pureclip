"""``report`` CLI — turn a ``data.json`` into a standalone HTML report.

Unlike the API (which assembles a dataset's trajectory by scanning the live
``results/`` tree), this command reads a single JSON file and renders the same
report next to it, so a report can be produced anywhere the JSON is available.

Usage::

    uv run python -m dashboard.cli data.json          # writes <dataset>_report.html next to it
    uv run python -m dashboard.cli data.json -o out.html

Accepted ``data.json`` shapes
-----------------------------
1. Already assembled (exactly what the renderer consumes)::

     {
       "meta":    {"dataset": "PUM2_K562", "target_protein": "PUM2",
                   "cell_line": "K562", "target_motif": "TGTANATA"},
       "history": [
         {"iteration": 1, "run_id": "PUM2_K562_iter_01",
          "scores": {"composite": 0.51, "n_binding_sites": 1200,
                     "replicate_agreement": 0.72, "motif_hit_rate": 0.42},
          "config": {"pureclip": {"...": "..."}}},
         ...
       ]
     }

2. Raw per-iteration score reports (the shape the pipeline writes as
   ``score_report.json``). Give a dataset id and a list; the CLI fills in the
   composite objective and iteration order::

     {
       "dataset": "PUM2_K562",
       "target_motif": "TGTANATA",
       "reports": [
         {"run_id": "PUM2_K562_iter_01", "n_binding_sites": 1200,
          "replicate_agreement": 0.72, "motif_hit_rate": 0.42, "params": {...}},
         ...
       ]
     }

   (A bare top-level JSON list is also accepted and treated as ``reports``; the
   dataset id is then inferred from the first ``run_id``.)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import typer

from dashboard.api import report as report_mod

app = typer.Typer(add_completion=False, help=__doc__)

_ITER_RE = re.compile(r"_iter_(\d+)")

# Kept in lock-step with the dashboard's fallback objective (see
# dashboard.api.collectors.composite_objective) so the CLI's composite matches.
_OBJECTIVE_WEIGHTS = {"reproducibility": 0.5, "motif": 0.25, "recall": 0.25}


def _iter_index(run_id: str) -> int | None:
    m = _ITER_RE.search(run_id or "")
    return int(m.group(1)) if m else None


def _strip_iter(run_id: str) -> str:
    return _ITER_RE.sub("", run_id or "").rstrip("_") or run_id


def _composite(scores: dict) -> float:
    """Weighted composite objective from a raw report's score fields."""
    terms: dict[str, float] = {}
    rep = scores.get("reproducibility_score")
    if rep is None:
        rep = scores.get("replicate_agreement")
    if rep is not None:
        terms["reproducibility"] = float(rep)
    if scores.get("motif_hit_rate") is not None:
        terms["motif"] = float(scores["motif_hit_rate"])
    if scores.get("benchmark_region_recall") is not None:
        terms["recall"] = float(scores["benchmark_region_recall"])
    total = sum(_OBJECTIVE_WEIGHTS.get(k, 0.0) for k in terms)
    if not terms or total <= 0:
        return 0.0
    return round(sum(_OBJECTIVE_WEIGHTS.get(k, 0.0) * v for k, v in terms.items()) / total, 4)


def _meta_for(dataset: str, target_motif: str | None) -> dict:
    protein, _, cell = dataset.partition("_")
    return {
        "dataset": dataset,
        "target_protein": protein or dataset,
        "cell_line": cell or "—",
        "target_motif": target_motif,
    }


def _assemble_from_reports(dataset: str, reports: list[dict], target_motif: str | None) -> tuple[dict, list[dict]]:
    """Build (meta, history) from raw score-report dicts (shape #2)."""
    rows: list[dict] = []
    for r in reports:
        run_id = r.get("run_id") or dataset
        scores = {k: v for k, v in r.items() if k not in ("params", "run_id", "dataset_id")}
        scores.setdefault("composite", _composite(scores))
        rows.append({"run_id": run_id, "scores": scores, "config": r.get("params") or {}})

    # Order by parsed iteration where available, otherwise keep input order.
    rows.sort(key=lambda r: (_iter_index(r["run_id"]) is None, _iter_index(r["run_id"]) or 0))
    for seq, r in enumerate(rows, start=1):
        r["iteration"] = _iter_index(r["run_id"]) or seq
    return _meta_for(dataset, target_motif), rows


def load_data(path: Path) -> tuple[dict, list[dict]]:
    """Normalise any accepted ``data.json`` shape into (meta, history)."""
    data = json.loads(path.read_text())

    # Shape #1: already assembled.
    if isinstance(data, dict) and "history" in data:
        meta = dict(data.get("meta") or {})
        history = data["history"]
        if not meta.get("dataset"):
            meta.update(_meta_for(meta.get("dataset") or path.stem, meta.get("target_motif")))
        return meta, history

    # Shape #2: raw per-iteration reports.
    if isinstance(data, list):
        reports = data
        dataset = _strip_iter((reports[0].get("run_id") if reports else None) or path.stem)
        target_motif = None
    elif isinstance(data, dict) and ("reports" in data or "iterations" in data):
        reports = data.get("reports") or data.get("iterations") or []
        dataset = data.get("dataset") or _strip_iter(
            (reports[0].get("run_id") if reports else None) or path.stem
        )
        target_motif = data.get("target_motif")
    else:
        raise typer.BadParameter(
            f"{path} is not a recognised report input: expected a 'history', "
            "'reports'/'iterations' key, or a top-level list of score reports."
        )
    return _assemble_from_reports(dataset, reports, target_motif)


@app.command()
def build(
    data: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the data.json describing the run.",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Write the HTML here instead of <dataset>_report.html next to the input.",
    ),
) -> None:
    """Build the HTML optimisation report from DATA and write it next to it."""
    meta, history = load_data(data)
    result = report_mod.render_report(meta, history)
    if result is None:
        raise typer.BadParameter(f"no scored iterations found in {data}")

    filename, html = result
    out_path = output if output is not None else data.parent / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    typer.echo(f"Wrote {out_path}  ({len(history)} iteration(s), dataset {meta['dataset']!r})")


if __name__ == "__main__":  # `python dashboard/cli/report_cli.py ...`
    app()
