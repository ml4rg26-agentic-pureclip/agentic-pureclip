#!/usr/bin/env python3
"""
Live monitoring dashboard for agentic PureCLIP batch runs.

Start on the remote server:
    PYTHONPATH=. uv run python scripts/monitor.py --port 8080

Then open in browser:  http://194.94.4.28:30121
(or tunnel: ssh -L 8080:localhost:8080 bio  then open http://localhost:8080)
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

RESULTS_DIR = Path("results/batch")
SUMMARY_PATH = RESULTS_DIR / "_summary.tsv"

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agentic PureCLIP — Run Monitor</title>
<style>
  :root { --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9;
          --green: #3fb950; --yellow: #d2991d; --red: #f85149; --blue: #58a6ff;
          --accent: #1f6feb; --muted: #8b949e; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         padding:24px; max-width:1200px; margin:0 auto; }
  h1 { font-size:20px; margin-bottom:4px; }
  h1 span { color:var(--blue); }
  .subtitle { color:var(--muted); font-size:13px; margin-bottom:24px; }
  .section { background:var(--card); border:1px solid var(--border); border-radius:8px;
             padding:20px; margin-bottom:20px; }
  .section h2 { font-size:14px; color:var(--muted); text-transform:uppercase; letter-spacing:0.5px;
                margin-bottom:14px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { text-align:left; color:var(--muted); font-weight:500; padding:8px 12px;
       border-bottom:1px solid var(--border); }
  td { padding:8px 12px; border-bottom:1px solid var(--border); font-variant-numeric:tabular-nums; }
  tr:hover { background:rgba(255,255,255,0.03); }
  .status-ok { color:var(--green); }
  .status-err { color:var(--red); }
  .status-running { color:var(--yellow); }
  .badge { display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:600; }
  .badge-running { background:rgba(210,153,29,0.15); color:var(--yellow); }
  .badge-done { background:rgba(63,185,80,0.15); color:var(--green); }
  .badge-error { background:rgba(248,81,73,0.15); color:var(--red); }
  .badge-queued { background:rgba(139,148,158,0.15); color:var(--muted); }
  .progress-bar { width:100%; height:6px; background:var(--border); border-radius:3px; overflow:hidden; margin-top:4px; }
  .progress-fill { height:100%; background:var(--accent); border-radius:3px; transition:width 0.3s; }
  .progress-fill.done { background:var(--green); }
  .progress-fill.running { background:var(--yellow); animation:pulse 1.5s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.6} }
  .sparkline { display:flex; gap:2px; align-items:flex-end; height:20px; }
  .sparkline div { width:4px; background:var(--accent); border-radius:1px; min-height:2px; }
  .refresh { color:var(--muted); font-size:11px; text-align:right; margin-top:12px; }
  .empty { color:var(--muted); font-style:italic; padding:12px; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
  @media(max-width:700px){.grid{grid-template-columns:1fr}}
  .metric { font-size:28px; font-weight:700; }
  .metric-label { font-size:11px; color:var(--muted); text-transform:uppercase; }
  .metric-card { text-align:center; padding:16px; }
  a { color:var(--blue); }
</style>
</head>
<body>
<h1>🧬 Agentic PureCLIP <span>Monitor</span></h1>
<div class="subtitle" id="hostInfo">loading...</div>

<div class="grid">
  <div class="section metric-card">
    <div class="metric" id="totalRuns">—</div>
    <div class="metric-label">Total Runs</div>
  </div>
  <div class="section metric-card">
    <div class="metric" id="activeCount">—</div>
    <div class="metric-label">Active Processes</div>
  </div>
</div>

<div class="section">
  <h2>⚡ Running Now</h2>
  <div id="runningTable"><div class="empty">No active runs</div></div>
</div>

<div class="section">
  <h2>📊 Completed Runs</h2>
  <div id="completedTable"><div class="empty">No completed runs yet</div></div>
</div>

<div class="refresh">Auto-refresh every 8s · <span id="lastUpdate"></span></div>

<script>
async function fetchData() {
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();
    render(data);
    document.getElementById('lastUpdate').textContent =
      'Last update: ' + new Date().toLocaleTimeString();
  } catch(e) { console.error(e); }
}

function render(data) {
  document.getElementById('hostInfo').textContent =
    data.host + ' · ' + data.cpus + ' CPUs · ' + data.mem;
  document.getElementById('totalRuns').textContent = data.summary.total;
  document.getElementById('activeCount').textContent = data.running.length;

  // Running table
  let rhtml = '';
  if (data.running.length === 0) rhtml = '<div class="empty">No active runs</div>';
  for (const p of data.running) {
    rhtml += `<tr>
      <td><span class="badge badge-running">RUNNING</span></td>
      <td>${p.name}</td>
      <td>${p.cpu}% CPU</td>
      <td>${p.mem}</td>
      <td>${p.time}</td>
    </tr>`;
  }
  document.getElementById('runningTable').innerHTML =
    rhtml ? `<table><tr><th></th><th>Process</th><th>CPU</th><th>RAM</th><th>Time</th></tr>${rhtml}</table>` : rhtml;

  // Completed table
  let chtml = '';
  if (data.completed.length === 0) chtml = '<div class="empty">No completed runs yet</div>';
  for (const r of data.completed) {
    const score = r.best_score ? r.best_score.toFixed(4) : '—';
    const mins = r.elapsed_s ? Math.round(r.elapsed_s/60) + 'm' : '—';
    const badge = r.exit_code === 0
      ? '<span class="badge badge-done">DONE</span>'
      : '<span class="badge badge-error">ERROR</span>';
    chtml += `<tr>
      <td>${badge}</td>
      <td>${r.run_id}</td>
      <td>${r.dataset}</td>
      <td>${score}</td>
      <td>${r.max_iter}</td>
      <td>${mins}</td>
      <td>${r.termination || '—'}</td>
    </tr>`;
  }
  document.getElementById('completedTable').innerHTML =
    chtml ? `<table><tr><th></th><th>Run</th><th>Dataset</th><th>Best Score</th><th>Iter</th><th>Time</th><th>Stop</th></tr>${chtml}</table>` : chtml;

  // Progress bars for queued runs
  if (data.queued && data.queued.length > 0) {
    let qhtml = '';
    for (const q of data.queued) {
      qhtml += `<div style="margin-top:8px;font-size:12px;">
        <span class="badge badge-queued">QUEUED</span> ${q}
      </div>`;
    }
  }
}

fetchData();
setInterval(fetchData, 8000);
</script>
</body>
</html>"""


def get_processes() -> list[dict]:
    """Get running PureCLIP/snakemake/agent processes."""
    try:
        out = subprocess.run(
            ["ps", "aux", "--no-headers"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    procs = []
    for line in out.split("\n"):
        if not line.strip():
            continue
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        cmd = parts[10]
        # Filter for relevant processes
        if any(k in cmd for k in ["pureclip2", "snakemake", "batch_runner", "agent.graph"]):
            if "grep" in cmd or "ps aux" in cmd:
                continue
            name = cmd.split("/")[-1].split()[0][:30]
            if "pureclip2" in cmd:
                name = "pureclip2 (" + cmd.split("data/")[1].split("/")[0] if "data/" in cmd else name + ")"
            elif "snakemake" in cmd:
                name = "snakemake"
            elif "batch_runner" in cmd:
                name = "batch_runner"
            elif "agent.graph" in cmd:
                name = "agent"
            procs.append({
                "name": name[:40],
                "cpu": parts[2],
                "mem": parts[5],
                "time": parts[9],
            })
    return procs


def get_completed() -> list[dict]:
    """Parse completed runs from TSV."""
    if not SUMMARY_PATH.exists():
        return []
    runs = []
    with open(SUMMARY_PATH) as f:
        header = f.readline().strip().split("\t")
        for line in f:
            if not line.strip():
                continue
            vals = line.strip().split("\t")
            if len(vals) >= 7:
                try:
                    runs.append({
                        "timestamp": vals[0],
                        "run_id": vals[1],
                        "dataset": vals[2],
                        "max_iter": int(vals[3]) if vals[3] else 0,
                        "termination": vals[4],
                        "best_score": float(vals[5]) if vals[5] and vals[5] != "None" else None,
                        "elapsed_s": float(vals[6]) if vals[6] and vals[6] != "None" else None,
                        "exit_code": int(vals[7]) if len(vals) > 7 and vals[7] else 0,
                    })
                except (ValueError, IndexError):
                    pass
    return runs


def get_queued() -> list[str]:
    """Infer queued runs from batch config vs completed."""
    import yaml
    config_path = Path("config/batch_runs.yaml")
    if not config_path.exists():
        return []
    try:
        with open(config_path) as f:
            manifest = yaml.safe_load(f)
    except Exception:
        return []
    completed_ids = {r["run_id"] for r in get_completed()}
    running = {p["name"] for p in get_processes()}
    queued = []
    for r in manifest.get("runs", []):
        rid = r["id"]
        if rid not in completed_ids and not any(rid in p["name"] for p in get_processes()):
            queued.append(f"{rid} ({r['dataset']}, {r.get('max_iter', '?')} iter)")
    return queued


def get_host_info() -> dict:
    try:
        host = subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip()
    except Exception:
        host = "unknown"
    try:
        nproc = subprocess.run(["nproc"], capture_output=True, text=True).stdout.strip()
    except Exception:
        nproc = "?"
    try:
        mem = subprocess.run(
            ["free", "-h"], capture_output=True, text=True
        ).stdout.split("\n")[1].split()[1] if "free" else "?"
    except Exception:
        mem = "?"
    return {"host": host, "cpus": nproc, "mem": mem + " total"}


class MonitorHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/status":
            completed = get_completed()
            running = get_processes()
            queued = get_queued()
            host = get_host_info()
            data = {
                "host": f"{host['host']}",
                "cpus": host["cpus"],
                "mem": host["mem"],
                "summary": {
                    "total": len(completed),
                    "active": len(running),
                },
                "running": running,
                "completed": completed[-20:],  # last 20
                "queued": queued,
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
            return

        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode())
            return

        self.send_response(404)
        self.end_headers()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Monitoring dashboard for batch runs")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), MonitorHandler)
    print(f"📊 Monitor running at http://localhost:{args.port}")
    print(f"   Tunnel: ssh -L {args.port}:localhost:{args.port} bio")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
