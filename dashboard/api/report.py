"""Standalone HTML analysis report for a dataset's optimisation run.

Produces a self-contained, print-friendly report (in the spirit of the original
agent/report.py from PR #6) built from the live per-iteration score_report.json
files — best iteration, final scores, optimal config, a convergence chart, and
the full per-iteration history with changed-parameter highlighting.

No weasyprint / LLM dependencies: the HTML is downloadable as-is and prints to
PDF from the browser. jinja2 + matplotlib are already project dependencies.
"""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt  # noqa: E402
from jinja2 import Template  # noqa: E402

from . import collectors

# Metrics surfaced as "Final Scores" cards, in display order, with labels.
SCORE_FIELDS = [
    ("composite", "composite", True),
    ("reproducibility_score", "reproducibility", False),
    ("replicate_agreement", "replicate agreement", False),
    ("motif_hit_rate", "motif hit-rate", False),
    ("motif_enrichment", "motif enrichment (×)", False),
    ("benchmark_region_recall", "known-site recall", False),
    ("n_binding_sites", "binding sites", False),
]

OBJECTIVE_METRIC = "composite"


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}" if abs(v) < 100 else f"{v:,.0f}"
    return str(v)


def format_config(cfg: dict, prev: dict | None = None, collapsible: bool = True) -> str:
    """Render a nested params dict as HTML; highlight values changed vs ``prev``."""
    all_lines: list[str] = []
    changed_lines: list[str] = []

    def _mark(text, changed):
        return f"<span class='chg'>{text}</span>" if changed else str(text)

    for k, v in cfg.items():
        if isinstance(v, dict):
            all_lines.append(f"<b>{k}</b>:")
            prev_sub = (prev or {}).get(k, {}) if prev else {}
            for sk, sv in v.items():
                changed = prev is not None and prev_sub.get(sk) != sv
                all_lines.append(f"&nbsp;&nbsp;{_mark(sk, changed)}: {_mark(sv, changed)}")
                if changed:
                    changed_lines.append(f"<b>{k}.{sk}</b>: {sv}")
        else:
            changed = prev is not None and prev.get(k) != v
            all_lines.append(f"<b>{k}</b>: {_mark(v, changed)}")
            if changed:
                changed_lines.append(f"<b>{k}</b>: {v}")

    full = "<br>".join(all_lines)
    if not collapsible:
        return full
    if prev is None:
        summary = "<span class='muted'>Baseline (click to expand)</span>"
    elif not changed_lines:
        summary = "<span class='muted'>No changes</span>"
    else:
        summary = "<br>".join(changed_lines)
    return (
        f"<details><summary>{summary}</summary>"
        f"<div class='cfg-full'>{full}</div></details>"
    )


def _convergence_chart(history: list[dict]) -> str | None:
    """Base64 PNG of objective + site count over iterations (needs >= 3 points)."""
    if len(history) < 3:
        return None
    iters = [r["iteration"] for r in history]
    objs = [r["scores"].get(OBJECTIVE_METRIC) or 0.0 for r in history]
    sites = [r["scores"].get("n_binding_sites") or 0 for r in history]
    best_i = max(range(len(history)), key=lambda i: objs[i])

    fig, ax1 = plt.subplots(figsize=(8, 3.6))
    ax1.set_xlabel("Iteration")
    ax1.set_ylabel(OBJECTIVE_METRIC, color="#2b6cb0")
    ax1.plot(iters, objs, "-o", color="#2b6cb0", label=OBJECTIVE_METRIC)
    ax1.plot(iters[best_i], objs[best_i], "*", color="#d69e2e", markersize=16, label="best")
    ax1.tick_params(axis="y", labelcolor="#2b6cb0")
    ax2 = ax1.twinx()
    ax2.set_ylabel("binding sites", color="#718096")
    ax2.plot(iters, sites, "--", color="#a0aec0", label="sites")
    ax2.tick_params(axis="y", labelcolor="#718096")
    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def build_history(dataset: str) -> tuple[dict, list[dict]]:
    """Assemble (meta, history) for a dataset from its score_report.json files.

    history: [{iteration, run_id, mtime, scores{...+composite}, config{params}}]
    sorted by mtime — mirrors how the dashboard groups a dataset's trajectory.
    """
    rows: list[dict] = []
    for root in collectors._result_roots():
        if not root.exists():
            continue
        for report_path in root.glob("*/score_report.json"):
            try:
                d = json.loads(report_path.read_text())
            except Exception:
                continue
            ds = d.get("dataset_id") or collectors._strip_iter(
                d.get("run_id") or report_path.parent.name
            )
            if ds != dataset:
                continue
            run_id = d.get("run_id") or report_path.parent.name
            scores = {k: v for k, v in d.items() if k not in ("params", "run_id", "dataset_id")}
            scores["composite"] = round(collectors.composite_objective(d), 4)
            rows.append({
                "run_id": run_id,
                "mtime": report_path.stat().st_mtime,
                "scores": scores,
                "config": d.get("params") or {},
            })

    rows.sort(key=lambda r: r["mtime"])
    for seq, r in enumerate(rows, start=1):
        r["iteration"] = collectors._iter_index(r["run_id"])
        if r["iteration"] is None:
            r["iteration"] = seq

    protein, _, cell = dataset.partition("_")
    meta = {
        "dataset": dataset,
        "target_protein": protein or dataset,
        "cell_line": cell or "—",
        "target_motif": _target_motif(dataset),
    }
    return meta, rows


def _target_motif(dataset: str) -> str | None:
    """Best-effort lookup of the RBP's known target motif from the registry."""
    try:
        from agentic_pureclip.pipeline.datasets import dataset_to_config

        cfg = dataset_to_config(dataset)
        motifs = (cfg.get("priors") or {}).get("known_motifs") or []
        target = next((m for m in motifs if m.get("type") == "target"), None) or (motifs[0] if motifs else None)
        return target.get("pattern") if target else None
    except Exception:
        return None


_TEMPLATE = Template(r"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>{{ meta.target_protein }} {{ meta.cell_line }} — Optimisation Report</title>
<style>
  :root { --ink:#1a202c; --muted:#718096; --line:#e2e8f0; --accent:#2b6cb0; --chg:#c05621; }
  * { box-sizing: border-box; }
  body { font-family: 'Inter',system-ui,-apple-system,sans-serif; color:#2d3748; margin:0;
         padding:40px; background:#f8f9fa; line-height:1.6; }
  .container { max-width:960px; margin:0 auto; background:#fff; border-radius:12px;
               box-shadow:0 10px 25px -12px rgba(0,0,0,.15); padding:40px; }
  h1 { font-size:28px; margin:.2rem 0; color:var(--ink); }
  h2 { font-size:14px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted);
       margin:32px 0 12px; border-bottom:1px solid var(--line); padding-bottom:6px; }
  .eyebrow { font-size:12px; text-transform:uppercase; letter-spacing:.08em; color:var(--accent); font-weight:600; }
  .header { display:flex; justify-content:space-between; align-items:flex-end;
            border-bottom:1px solid var(--line); padding-bottom:22px; }
  .meta { display:flex; gap:26px; margin-top:10px; font-size:13px; }
  .meta .t { font-size:11px; text-transform:uppercase; color:var(--muted); letter-spacing:.04em; }
  .mono { font-family:ui-monospace,Menlo,monospace; }
  .best { text-align:right; }
  .best .lbl { font-size:12px; color:var(--muted); }
  .best .val { font-size:34px; font-weight:800; color:#2f855a; line-height:1.1; }
  .best .met { font-size:12px; color:var(--muted); }
  .cards { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }
  .card { border:1px solid var(--line); border-radius:10px; padding:12px 14px; background:#fbfcfd; }
  .card.primary { border-color:#9ae6b4; background:#f0fff4; }
  .card .v { font-size:20px; font-weight:700; font-variant-numeric:tabular-nums; }
  .card.primary .v { color:#2f855a; }
  .card .l { font-size:10.5px; text-transform:uppercase; letter-spacing:.03em; color:var(--muted); margin-top:3px; }
  .cfg { font-size:12.5px; font-family:ui-monospace,Menlo,monospace; background:#f7fafc;
         border:1px solid var(--line); border-radius:10px; padding:12px 14px; }
  .chg { color:var(--chg); font-weight:700; }
  .muted { color:var(--muted); font-style:italic; }
  details summary { cursor:pointer; }
  .cfg-full { margin-top:8px; padding-top:8px; border-top:1px dashed #cbd5e0; }
  .bio { background:#f0fff4; border:1px solid #c6f6d5; border-radius:10px; padding:14px 16px; color:#276749; }
  .bio .disc { margin-top:12px; font-size:11.5px; color:var(--muted); font-style:italic;
               border-top:1px solid #c6f6d5; padding-top:8px; }
  img { max-width:100%; border:1px solid var(--line); border-radius:10px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
  th { font-size:11px; text-transform:uppercase; color:var(--muted); }
  tr.best-row { background:#f0fff4; }
  .num { font-variant-numeric:tabular-nums; }
  @media print { body { background:#fff; padding:0; } .container { box-shadow:none; border-radius:0; padding:0; max-width:none; } }
</style></head><body><div class="container">

  <div class="header">
    <div>
      <div class="eyebrow">Agentic PureCLIP Optimisation</div>
      <h1>{{ meta.target_protein }} <span style="color:#cbd5e0">/</span> {{ meta.cell_line }}</h1>
      <div class="meta">
        <div><div class="t">Iterations</div><div>{{ history|length }}</div></div>
        <div><div class="t">Best run</div><div class="mono">{{ best.run_id }}</div></div>
        {% if meta.target_motif %}<div><div class="t">Target motif</div><div class="mono">{{ meta.target_motif }}</div></div>{% endif %}
      </div>
    </div>
    <div class="best">
      <div class="lbl">Best iteration #{{ best.iteration }}</div>
      <div class="val">{{ '%.3f'|format(best.scores.get('composite') or 0) }}</div>
      <div class="met">composite objective</div>
    </div>
  </div>

  <h2>Final scores</h2>
  <div class="cards">
    {% for f in score_cards %}
    <div class="card {{ 'primary' if f.primary }}"><div class="v">{{ f.value }}</div><div class="l">{{ f.label }}</div></div>
    {% endfor %}
  </div>

  <h2>Optimal config</h2>
  <div class="cfg">{{ best_config_html }}</div>

  <h2>Experiment summary</h2>
  <div class="bio">
    {{ summary }}
    <div class="disc">Auto-generated from the run's score reports — for preliminary reference. Verify biological significance with a domain expert.</div>
  </div>

  <h2>Convergence trend</h2>
  {% if chart %}<img src="data:image/png;base64,{{ chart }}"/>
  {% else %}<div class="muted">Not enough iterations to plot a trend (needs ≥ 3).</div>{% endif %}

  <h2>Per-iteration history</h2>
  <table>
    <thead><tr><th style="width:60px">Iter</th><th>Config</th><th style="width:110px">composite</th><th style="width:70px">sites</th></tr></thead>
    <tbody>
      {% for row in rows %}
      <tr class="{{ 'best-row' if row.iteration == best.iteration }}">
        <td><strong>#{{ row.iteration }}</strong></td>
        <td class="cfg" style="background:transparent;border:none;padding:0">{{ row.config_html }}</td>
        <td class="num">{{ '%.3f'|format(row.scores.get('composite') or 0) }}</td>
        <td class="num">{{ row.scores.get('n_binding_sites', '—') }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

</div></body></html>""")


def render_html(dataset: str) -> tuple[str, str] | None:
    """Return (filename, html) for the dataset's report, or None if no data."""
    meta, history = build_history(dataset)
    if not history:
        return None

    best = max(history, key=lambda r: r["scores"].get(OBJECTIVE_METRIC) or 0.0)

    score_cards = []
    for key, label, primary in SCORE_FIELDS:
        if key in best["scores"]:
            score_cards.append({"label": label, "value": _fmt(best["scores"][key]), "primary": primary})

    # Per-iteration config with changes highlighted against the previous iteration.
    prev = None
    for r in history:
        r["config_html"] = format_config(r["config"], prev, collapsible=True)
        prev = r["config"]

    motif_rate = best["scores"].get("motif_hit_rate")
    motif_txt = f"{motif_rate:.0%}" if isinstance(motif_rate, (int, float)) else "an unknown fraction"
    summary = (
        f"The best iteration (#{best['iteration']}) reached a composite objective of "
        f"{best['scores'].get('composite') or 0:.3f} with {best['scores'].get('n_binding_sites', '—')} binding sites. "
        f"The target motif ({meta['target_motif'] or 'n/a'}) was found in {motif_txt} of site windows, "
        f"indicating alignment with the known {meta['target_protein']} footprint."
    )

    html = _TEMPLATE.render(
        meta=meta,
        history=history,
        rows=history,
        best=best,
        score_cards=score_cards,
        best_config_html=format_config(best["config"], collapsible=False),
        summary=summary,
        chart=_convergence_chart(history),
    )
    return f"{dataset}_report.html", html
