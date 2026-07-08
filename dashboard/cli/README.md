# Report CLI

Build the standalone HTML optimisation report from a single `data.json`, without
a running dashboard or the live `results/` tree. It reuses the exact renderer the
API uses (`dashboard.api.report.render_report`), so the output is identical to the
`/api/report` download.

## Run

```bash
# writes <dataset>_report.html next to data.json
uv run python -m dashboard.cli path/to/data.json

# or choose the output path
uv run python -m dashboard.cli path/to/data.json -o report.html
```

See `data.example.json` for the input format. `--help` documents both accepted
shapes.

## `data.json` shapes

**1. Already assembled** — exactly what the renderer consumes:

```json
{
  "meta": { "dataset": "PUM2_K562", "target_protein": "PUM2",
            "cell_line": "K562", "target_motif": "TGTANATA" },
  "history": [
    { "iteration": 1, "run_id": "PUM2_K562_iter_01",
      "scores": { "composite": 0.51, "n_binding_sites": 1200,
                  "replicate_agreement": 0.72, "motif_hit_rate": 0.42 },
      "config": { "pureclip": { "bandwidth": 50 } } }
  ]
}
```

**2. Raw score reports** — the shape the pipeline writes as `score_report.json`.
Give a dataset id and a list of reports; the CLI fills in the composite objective
and iteration order:

```json
{
  "dataset": "PUM2_K562",
  "target_motif": "TGTANATA",
  "reports": [
    { "run_id": "PUM2_K562_iter_01", "n_binding_sites": 1200,
      "replicate_agreement": 0.72, "motif_hit_rate": 0.42,
      "params": { "pureclip": { "bandwidth": 50 } } }
  ]
}
```

A bare top-level JSON list is also accepted and treated as `reports`.
