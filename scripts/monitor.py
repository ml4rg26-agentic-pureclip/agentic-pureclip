#!/usr/bin/env python3
"""
Live monitoring dashboard for agentic PureCLIP optimisation runs.

Start on the remote server:
    PYTHONPATH=. uv run python scripts/monitor.py --port 8888

Then open in browser (tunnel):
    ssh -L 8888:localhost:8888 bio   →   http://localhost:8888

The dashboard is science-oriented: it shows the active run's dataset, current
iteration and pipeline stage, the tunable parameters in flight, the live
optimisation metrics (replicate agreement, motif hit-rate, motif enrichment,
composite objective) and the agent's latest reasoning — plus the full
per-dataset iteration trajectory.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

import yaml

# Keep the dashboard's composite in lock-step with the agent's objective.
try:
    from agent.decisions import composite_objective
except Exception:  # pragma: no cover - fallback if agent package not importable
    def composite_objective(report: dict, weights=None) -> float:
        weights = weights or {"reproducibility": 0.5, "motif": 0.25, "recall": 0.25}
        terms = {}
        rep = report.get("reproducibility_score")
        if rep is None:
            rep = report.get("replicate_agreement")
        if rep is not None:
            terms["reproducibility"] = float(rep)
        if report.get("motif_hit_rate") is not None:
            terms["motif"] = float(report["motif_hit_rate"])
        if report.get("benchmark_region_recall") is not None:
            terms["recall"] = float(report["benchmark_region_recall"])
        total = sum(weights.get(k, 0.0) for k in terms)
        if not terms or total <= 0:
            return 0.0
        return float(sum(weights.get(k, 0.0) * v for k, v in terms.items()) / total)


RESULT_ROOTS = [Path("results/runs"), Path("results/batch")]
LOGS_DIR = Path("results/logs")
RUN_CONFIG = Path("config/run_config.yaml")

# Ordered pipeline stages of a single optimisation iteration.
STAGES = ["PureCLIP", "Postprocess", "Score", "LLM decide"]

ITER_RE = re.compile(r"_iter_(\d+)")


# ── data collection ─────────────────────────────────────────────────────────

def _read_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}


def get_processes() -> list[dict]:
    """Relevant pipeline/agent processes with wall-clock elapsed time."""
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid,pcpu,pmem,etime,args", "--no-headers"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    keys = ("pureclip2", "snakemake", "batch_runner", "agent/graph.py",
            "agent.graph", "run_scorers.py", "postprocess.py")
    procs = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        pid, pcpu, pmem, etime, args = parts
        if "monitor.py" in args or " grep " in args:
            continue
        if not any(k in args for k in keys):
            continue
        if "pureclip2" in args:
            label = "PureCLIP"
            m = re.search(r"ip_(rep\d+)", args)
            if m:
                label += f" · {m.group(1)}"
            elif "/PureCLIP." in args or "merged" in args:
                label += " · merged"
        elif "snakemake" in args:
            label = "snakemake"
        elif "run_scorers.py" in args:
            label = "scorer"
        elif "postprocess.py" in args:
            label = "postprocess"
        elif "batch_runner" in args:
            label = "batch_runner"
        else:
            label = "agent"
        procs.append({
            "label": label, "cpu": pcpu, "mem": pmem,
            "etime": etime, "args": args,
        })
    return procs


def get_active_run(procs: list[dict], cfg: dict) -> dict:
    joined = " ".join(p["args"] for p in procs)
    is_active = bool(procs)

    # Which optimizer is driving the loop?
    if "optuna_runner.py" in joined:
        optimizer = "optuna"
    elif any(k in joined for k in ("agent/graph.py", "agent.graph")):
        optimizer = "llm"
    else:
        optimizer = None
    decide_label = "TPE suggest" if optimizer == "optuna" else "LLM decide"

    if "pureclip2" in joined:
        stage, idx = "PureCLIP", 0
        m = re.search(r"ip_(rep\d+)", joined)
        substage = m.group(1) if m else "merged"
    elif "postprocess.py" in joined:
        stage, idx, substage = "Postprocess", 1, None
    elif "run_scorers.py" in joined:
        stage, idx, substage = "Score", 2, None
    elif "snakemake" in joined:
        stage, idx, substage = "PureCLIP", 0, None
    elif any(k in joined for k in ("agent/graph.py", "agent.graph", "optuna_runner.py", "batch_runner")):
        stage, idx, substage = decide_label, 3, None
    else:
        stage, idx, substage = "Idle", -1, None

    run_id = cfg.get("run_id")
    dataset = cfg.get("dataset_id")
    # Prefer the freshest identity parsed from the running command line.
    m = re.search(r"/([A-Za-z0-9]+_[A-Za-z0-9]+_iter_\d+)/", joined) or \
        re.search(r"/([A-Za-z0-9]+_iter_\d+)/", joined)
    if m:
        run_id = m.group(1)
    md = re.search(r"data/([A-Za-z0-9_]+)/bam", joined)
    if md:
        dataset = md.group(1)

    it = None
    if run_id:
        mi = ITER_RE.search(run_id)
        if mi:
            it = int(mi.group(1))

    elapsed = next(
        (p["etime"] for p in procs
         if any(k in p["args"] for k in
                ("agent/graph.py", "agent.graph", "optuna_runner.py", "batch_runner"))),
        None,
    )

    pc = cfg.get("pureclip", {})
    post = cfg.get("postprocessing", {})
    params = {
        "bandwidth_nt": pc.get("bandwidth_nt"),
        "merge_distance_nt": pc.get("merge_distance_nt"),
        "high_precision_mode": pc.get("high_precision_mode"),
        "learn_on_chr21": pc.get("learn_on_chr21"),
        "min_crosslink_events": post.get("min_crosslink_events"),
        "force_width": post.get("force_width"),
    }

    return {
        "is_active": is_active,
        "optimizer": optimizer,
        "decide_label": decide_label,
        "stage": stage,
        "stage_index": idx,
        "substage": substage,
        "dataset": dataset,
        "target_protein": cfg.get("target_protein") or cfg.get("priors", {}).get("target_protein"),
        "cell_line": cfg.get("cell_line"),
        "run_id": run_id,
        "iteration": it,
        "elapsed": elapsed,
        "params": params,
    }


def _iter_index(run_id: str) -> int | None:
    m = ITER_RE.search(run_id or "")
    return int(m.group(1)) if m else None


def _strip_iter(run_id: str) -> str:
    return ITER_RE.sub("", run_id or "").rstrip("_") or run_id


def _result_roots() -> list[Path]:
    """Result roots to scan: live runs, batch runs, and each overnight job dir."""
    roots = list(RESULT_ROOTS)
    overnight = Path("results/overnight")
    if overnight.exists():
        roots += [d for d in overnight.iterdir() if d.is_dir()]
    return roots


def _source_label(root: Path) -> str:
    parts = root.parts
    if "overnight" in parts:
        return "overnight"
    if root.name == "batch":
        return "batch"
    return "live"


def _overnight_optimizers() -> dict[str, str]:
    """Map overnight job_id -> optimizer ('llm'|'optuna') from the batch DB."""
    mapping: dict[str, str] = {}
    jobs_db = Path("results/overnight/jobs.jsonl")
    if not jobs_db.exists():
        return mapping
    try:
        for line in jobs_db.read_text().splitlines():
            rec = json.loads(line)
            if rec.get("type") == "job" and rec.get("job_id"):
                mapping[rec["job_id"]] = rec.get("optimizer", "llm")
    except Exception:
        pass
    return mapping


def collect_experiments() -> list[dict]:
    """Group every score_report.json by dataset into iteration trajectories."""
    rows = []
    optimizer_map = _overnight_optimizers()
    for root in _result_roots():
        if not root.exists():
            continue
        source = _source_label(root)
        # For overnight roots, root.name is the job_id -> look up its optimizer.
        optimizer = optimizer_map.get(root.name, "llm") if source == "overnight" else "llm"
        for report in root.glob("*/score_report.json"):
            try:
                d = json.loads(report.read_text())
            except Exception:
                continue
            run_id = d.get("run_id") or report.parent.name
            dataset = d.get("dataset_id") or _strip_iter(run_id)
            comp = composite_objective(d)
            rows.append({
                "dataset": dataset,
                "run_id": run_id,
                "optimizer": optimizer,
                "iter": _iter_index(run_id),
                "n_sites": d.get("n_binding_sites"),
                "agreement": d.get("replicate_agreement"),
                "reproducibility": d.get("reproducibility_score"),
                "repro_enrichment": d.get("reproducibility_enrichment"),
                "motif": d.get("motif_hit_rate"),
                "enrichment": d.get("motif_enrichment"),
                "recall": d.get("benchmark_region_recall"),
                "composite": round(comp, 4) if comp is not None else None,
                "source": source,
                "mtime": report.stat().st_mtime,
            })

    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["dataset"], []).append(r)

    experiments = []
    for dataset, items in groups.items():
        items.sort(key=lambda x: x["mtime"])
        comps = [i["composite"] for i in items if i["composite"] is not None]
        best = max(comps) if comps else None
        best_idx = comps.index(best) if best is not None else None
        # Map best back to its position among the (filtered) items.
        best_run = None
        if best is not None:
            for i in items:
                if i["composite"] == best:
                    best_run = i["run_id"]
                    break
        experiments.append({
            "name": dataset,
            "best_composite": best,
            "best_run": best_run,
            "n_iters": len(items),
            "iterations": items,
            "last_mtime": items[-1]["mtime"],
        })
    experiments.sort(key=lambda g: g["last_mtime"], reverse=True)
    return experiments


def get_latest_reasoning() -> str | None:
    if not LOGS_DIR.exists():
        return None
    logs = sorted(LOGS_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for log in logs:
        try:
            text = log.read_text(errors="ignore")
        except Exception:
            continue
        idx = text.rfind("Agent decision reasoning:")
        if idx == -1:
            continue
        tail = text[idx + len("Agent decision reasoning:"):]
        # Reasoning is one log record; stop at the next timestamped line.
        out_lines = []
        for line in tail.splitlines():
            if out_lines and re.match(r"^\d{4}-\d{2}-\d{2} ", line):
                break
            out_lines.append(line)
        reasoning = " ".join(l.strip() for l in out_lines).strip()
        if reasoning:
            return reasoning
    return None


def get_host_info() -> dict:
    def run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=4).stdout.strip()
        except Exception:
            return "?"
    host = run(["hostname"])
    cpus = run(["nproc"])
    mem = "?"
    free = run(["free", "-h"])
    if free and free != "?":
        try:
            mem = free.splitlines()[1].split()[1]
        except Exception:
            pass
    return {"host": host, "cpus": cpus, "mem": mem}


def build_status() -> dict:
    cfg = _read_yaml(RUN_CONFIG)
    procs = get_processes()
    experiments = collect_experiments()
    active = get_active_run(procs, cfg)

    # Attach the latest metric snapshot for the active dataset.
    latest = None
    if active["dataset"]:
        for g in experiments:
            if g["name"] == active["dataset"] or _strip_iter(active["run_id"] or "") == g["name"]:
                latest = g["iterations"][-1]
                break
    active["latest"] = latest
    active["reasoning"] = get_latest_reasoning()

    # The final loop step is optimizer-specific.
    stages = list(STAGES)
    stages[-1] = active.get("decide_label") or STAGES[-1]

    host = get_host_info()
    return {
        "host": host["host"],
        "cpus": host["cpus"],
        "mem": host["mem"],
        "stages": stages,
        "active": active,
        "experiments": experiments,
        "processes": procs,
    }


# ── frontend ────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agentic PureCLIP — Run Monitor</title>
<style>
  :root { --bg:#0d1117; --card:#161b22; --card2:#0f141a; --border:#30363d; --text:#c9d1d9;
          --green:#3fb950; --yellow:#d2991d; --red:#f85149; --blue:#58a6ff;
          --accent:#1f6feb; --muted:#8b949e; --purple:#bc8cff; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:var(--bg); color:var(--text);
         font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         padding:24px; max-width:1180px; margin:0 auto; }
  h1 { font-size:20px; margin-bottom:4px; } h1 span { color:var(--blue); }
  .subtitle { color:var(--muted); font-size:13px; margin-bottom:20px; }
  .section { background:var(--card); border:1px solid var(--border); border-radius:10px;
             padding:18px 20px; margin-bottom:18px; }
  .section h2 { font-size:12px; color:var(--muted); text-transform:uppercase;
                letter-spacing:0.6px; margin-bottom:14px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { text-align:right; color:var(--muted); font-weight:500; padding:6px 10px;
       border-bottom:1px solid var(--border); }
  th:first-child, td:first-child { text-align:left; }
  td { padding:6px 10px; border-bottom:1px solid var(--border); font-variant-numeric:tabular-nums; text-align:right; }
  tr:hover { background:rgba(255,255,255,0.03); }
  .best td { background:rgba(63,185,80,0.10); }
  .best td:first-child { box-shadow:inset 3px 0 0 var(--green); }
  .badge { display:inline-block; padding:2px 9px; border-radius:10px; font-size:11px; font-weight:600; }
  .badge-running { background:rgba(210,153,29,0.16); color:var(--yellow); }
  .badge-idle { background:rgba(139,148,158,0.16); color:var(--muted); }
  .badge-live { background:rgba(63,185,80,0.14); color:var(--green); }
  .badge-batch { background:rgba(188,140,255,0.14); color:var(--purple); }
  .badge-overnight { background:rgba(210,153,29,0.16); color:var(--yellow); }
  .badge-llm { background:rgba(88,166,255,0.16); color:var(--blue); }
  .badge-optuna { background:rgba(210,153,29,0.18); color:var(--yellow); }
  .empty { color:var(--muted); font-style:italic; padding:10px; }

  /* active run card */
  .active-head { display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:16px; }
  .ds-pill { font-size:15px; font-weight:700; }
  .ds-sub { color:var(--muted); font-size:13px; }
  .stepper { display:flex; gap:8px; margin:6px 0 18px; flex-wrap:wrap; }
  .step { flex:1; min-width:120px; padding:10px 12px; border-radius:8px; border:1px solid var(--border);
          background:var(--card2); font-size:12px; position:relative; }
  .step .n { color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:0.5px; }
  .step .s { font-size:13px; font-weight:600; margin-top:2px; }
  .step.done { border-color:rgba(63,185,80,0.4); }
  .step.done .s { color:var(--green); }
  .step.active { border-color:var(--yellow); background:rgba(210,153,29,0.08); animation:pulse 1.6s infinite; }
  .step.active .s { color:var(--yellow); }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.62} }

  .metrics { display:grid; grid-template-columns:repeat(5,1fr); gap:10px; margin-bottom:16px; }
  @media(max-width:760px){ .metrics{grid-template-columns:repeat(2,1fr)} .stepper .step{min-width:45%} }
  .metric-card { background:var(--card2); border:1px solid var(--border); border-radius:8px;
                 padding:12px; text-align:center; }
  .metric-card .v { font-size:22px; font-weight:700; }
  .metric-card .l { font-size:10px; color:var(--muted); text-transform:uppercase; letter-spacing:0.4px; margin-top:2px; }
  .metric-card.primary { border-color:var(--accent); }
  .metric-card.primary .v { color:var(--blue); }

  .params { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px; }
  .chip { background:var(--card2); border:1px solid var(--border); border-radius:6px;
          padding:4px 9px; font-size:12px; }
  .chip b { color:var(--text); } .chip span { color:var(--muted); }

  .reasoning { background:var(--card2); border-left:3px solid var(--purple); border-radius:0 6px 6px 0;
               padding:11px 14px; font-size:13px; line-height:1.5; color:#d8dde3; }
  .reasoning .lbl { color:var(--purple); font-size:11px; text-transform:uppercase; letter-spacing:0.5px;
                    display:block; margin-bottom:5px; }

  .exp-head { display:flex; align-items:baseline; gap:10px; margin-bottom:10px; }
  .exp-head .name { font-size:14px; font-weight:700; }
  .spark { display:inline-flex; gap:2px; align-items:flex-end; height:22px; vertical-align:middle; }
  .spark i { width:5px; background:var(--accent); border-radius:1px; min-height:2px; display:block; }
  .spark i.best { background:var(--green); }
  .refresh { color:var(--muted); font-size:11px; text-align:right; margin-top:8px; }
  .src { font-size:10px; }
</style>
</head>
<body>
<h1>🧬 Agentic PureCLIP <span>Monitor</span></h1>
<div class="subtitle" id="hostInfo">loading…</div>

<div class="section" id="activeSection">
  <h2>⚡ Active Run</h2>
  <div id="active"><div class="empty">Loading…</div></div>
</div>

<div class="section">
  <h2>🔬 Optimisation Trajectories</h2>
  <div id="experiments"><div class="empty">No runs found yet</div></div>
</div>

<div class="section">
  <h2>🖥 Processes</h2>
  <div id="procs"><div class="empty">No active processes</div></div>
</div>

<div class="refresh">Auto-refresh every 6s · <span id="lastUpdate"></span></div>

<script>
const fmt = (v, d=4) => (v===null||v===undefined) ? '—' : Number(v).toFixed(d);
const fmtx = (v) => (v===null||v===undefined) ? '—' : Number(v).toFixed(2)+'×';
const esc = (s) => (s||'').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

async function fetchData(){
  try{
    const data = await (await fetch('/api/status')).json();
    render(data);
    document.getElementById('lastUpdate').textContent = 'Last update: ' + new Date().toLocaleTimeString();
  }catch(e){ console.error(e); }
}

function renderActive(a, stages){
  if(!a || !a.is_active){
    return '<div class="empty">No run is currently active. Latest results below.</div>';
  }
  const proteinLine = [a.target_protein, a.cell_line].filter(Boolean).join(' · ');
  const optBadge = a.optimizer==='optuna'
    ? '<span class="badge badge-optuna">OPTUNA · TPE</span>'
    : (a.optimizer==='llm' ? '<span class="badge badge-llm">LLM</span>' : '');
  let h = `<div class="active-head">
    <span class="badge badge-running">RUNNING</span>
    ${optBadge}
    <span class="ds-pill">${esc(a.dataset||'—')}</span>
    <span class="ds-sub">${esc(proteinLine)}</span>
    <span class="ds-sub">• ${esc(a.run_id||'')}${a.iteration!==null?` · iteration ${a.iteration}`:''}</span>
    ${a.elapsed?`<span class="ds-sub">• elapsed ${esc(a.elapsed)}</span>`:''}
  </div>`;

  h += '<div class="stepper">';
  stages.forEach((s,i)=>{
    let cls = ''; if(a.stage_index>i) cls='done'; else if(a.stage_index===i) cls='active';
    const sub = (a.stage_index===i && a.substage) ? ` (${esc(a.substage)})` : '';
    h += `<div class="step ${cls}"><div class="n">step ${i+1}</div><div class="s">${esc(s)}${sub}</div></div>`;
  });
  h += '</div>';

  const m = a.latest || {};
  const repro = (m.reproducibility!==null&&m.reproducibility!==undefined) ? m.reproducibility : m.agreement;
  h += `<div class="metrics">
    <div class="metric-card primary"><div class="v">${fmt(m.composite)}</div><div class="l">composite</div></div>
    <div class="metric-card"><div class="v">${fmt(repro)}</div><div class="l">reproducibility${m.repro_enrichment!==null&&m.repro_enrichment!==undefined?` (${fmtx(m.repro_enrichment)})`:''}</div></div>
    <div class="metric-card"><div class="v">${fmt(m.motif)}</div><div class="l">motif hit-rate (${fmtx(m.enrichment)})</div></div>
    <div class="metric-card"><div class="v">${fmt(m.recall)}</div><div class="l">known-site recall</div></div>
    <div class="metric-card"><div class="v">${m.n_sites??'—'}</div><div class="l">binding sites</div></div>
  </div>`;

  const p = a.params||{};
  const chip = (k,v)=> v===null||v===undefined ? '' : `<div class="chip"><span>${k}</span> <b>${esc(String(v))}</b></div>`;
  h += `<div class="params">
    ${chip('bandwidth', p.bandwidth_nt)}
    ${chip('merge_dist', p.merge_distance_nt)}
    ${chip('min_xl_events', p.min_crosslink_events)}
    ${chip('force_width', p.force_width)}
    ${chip('high_precision', p.high_precision_mode)}
    ${chip('chr21_fast', p.learn_on_chr21)}
  </div>`;

  if(a.optimizer==='llm' && a.reasoning){
    h += `<div class="reasoning"><span class="lbl">latest agent reasoning</span>${esc(a.reasoning)}</div>`;
  } else if(a.optimizer==='optuna'){
    h += `<div class="reasoning"><span class="lbl">strategy</span>Optuna TPE (Bayesian) — proposes the next parameter set by modelling past trials; no natural-language reasoning.</div>`;
  }
  return h;
}

function sparkline(items){
  const vals = items.map(i=>i.composite).filter(v=>v!==null&&v!==undefined);
  if(!vals.length) return '';
  const max = Math.max(...vals), min = Math.min(...vals);
  const span = (max-min)||1;
  let h = '<span class="spark">';
  for(const i of items){
    const v = i.composite;
    if(v===null||v===undefined){ h+='<i style="height:2px;opacity:.3"></i>'; continue; }
    const ht = 4 + Math.round((v-min)/span*18);
    const best = v===max ? ' best':'';
    h += `<i class="${best.trim()}" style="height:${ht}px"></i>`;
  }
  return h+'</span>';
}

function renderExperiments(exps){
  if(!exps || !exps.length) return '<div class="empty">No runs found yet</div>';
  let html = '';
  const optBadge = (o) => o==='optuna'
    ? '<span class="badge badge-optuna src">optuna</span>'
    : '<span class="badge badge-llm src">llm</span>';
  for(const g of exps){
    // Per-optimizer best, so a head-to-head shows up when a dataset has both.
    const byOpt = {};
    for(const it of g.iterations){
      const o = it.optimizer||'llm';
      if(it.composite!=null && (byOpt[o]===undefined || it.composite>byOpt[o])) byOpt[o]=it.composite;
    }
    let versus = '';
    if(byOpt.llm!==undefined && byOpt.optuna!==undefined){
      const win = byOpt.llm===byOpt.optuna ? 'tie' : (byOpt.llm>byOpt.optuna?'LLM':'Optuna');
      versus = ` · <b style="color:var(--blue)">LLM ${fmt(byOpt.llm)}</b> vs <b style="color:var(--yellow)">Optuna ${fmt(byOpt.optuna)}</b> → ${win}`;
    }
    html += `<div style="margin-bottom:22px">
      <div class="exp-head">
        <span class="name">${esc(g.name)}</span>
        <span class="ds-sub">${g.n_iters} iteration${g.n_iters===1?'':'s'} · best <b style="color:var(--green)">${fmt(g.best_composite)}</b>${versus}</span>
        ${sparkline(g.iterations)}
      </div>`;
    html += `<table><tr>
      <th>run</th><th>opt</th><th>iter</th><th>sites</th><th>reprod.</th>
      <th>motif</th><th>recall</th><th>composite</th><th>src</th></tr>`;
    for(const it of g.iterations){
      const isBest = it.run_id===g.best_run;
      const srcBadge = it.source==='batch'
        ? '<span class="badge badge-batch src">batch</span>'
        : it.source==='overnight'
        ? '<span class="badge badge-overnight src">overnight</span>'
        : '<span class="badge badge-live src">live</span>';
      const repro = (it.reproducibility!==null&&it.reproducibility!==undefined) ? it.reproducibility : it.agreement;
      html += `<tr class="${isBest?'best':''}">
        <td>${esc(it.run_id)}</td>
        <td>${optBadge(it.optimizer)}</td>
        <td>${it.iter===null?'—':it.iter}</td>
        <td>${it.n_sites??'—'}</td>
        <td>${fmt(repro)}</td>
        <td>${fmt(it.motif)}</td>
        <td>${fmt(it.recall)}</td>
        <td><b>${fmt(it.composite)}</b></td>
        <td>${srcBadge}</td>
      </tr>`;
    }
    html += '</table></div>';
  }
  return html;
}

function renderProcs(procs){
  if(!procs || !procs.length) return '<div class="empty">No active processes</div>';
  let h = '<table><tr><th>process</th><th>CPU%</th><th>MEM%</th><th>elapsed</th></tr>';
  for(const p of procs){
    h += `<tr><td>${esc(p.label)}</td><td>${esc(p.cpu)}</td><td>${esc(p.mem)}</td><td>${esc(p.etime)}</td></tr>`;
  }
  return h+'</table>';
}

function render(data){
  document.getElementById('hostInfo').textContent =
    `${data.host} · ${data.cpus} CPUs · ${data.mem} RAM`;
  document.getElementById('active').innerHTML = renderActive(data.active, data.stages);
  document.getElementById('experiments').innerHTML = renderExperiments(data.experiments);
  document.getElementById('procs').innerHTML = renderProcs(data.processes);
}

fetchData();
setInterval(fetchData, 6000);
</script>
</body>
</html>"""


class MonitorHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence default logging
        pass

    def do_GET(self):
        if self.path == "/api/status":
            payload = json.dumps(build_status()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode())
            return
        self.send_response(404)
        self.end_headers()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Science dashboard for agentic PureCLIP runs")
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), MonitorHandler)
    print(f"Monitor running at http://localhost:{args.port}")
    print(f"  Tunnel: ssh -L {args.port}:localhost:{args.port} bio")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
