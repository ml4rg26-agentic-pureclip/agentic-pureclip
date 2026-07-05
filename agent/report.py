import sys
import json
import yaml
import os
import matplotlib.pyplot as plt
import base64
from io import BytesIO
from jinja2 import Template



def main():
    if len(sys.argv) != 3:
        print("Usage: python agent/report.py <config_path> <output_pdf>")
        sys.exit(1)
        
    config_path = sys.argv[1]
    output_pdf = sys.argv[2]
    
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
        
    results_root = cfg.get("output", {}).get("results_root", "results")
    target_protein = cfg.get("target_protein", "Unknown")
    cell_line = cfg.get("cell_line", "Unknown")
    run_id = cfg.get("run_id", "Unknown")
    
    priors = cfg.get("priors")
    if not priors:
        try:
            with open("config/priors.json", "r", encoding="utf-8") as f:
                priors = json.load(f)
        except Exception:
            priors = {}
            
    known_motifs = priors.get("known_motifs", [])
    target_motif = next((m["pattern"] for m in known_motifs if m.get("type") == "target"), "Unknown")
    
    dataset_name = os.path.splitext(os.path.basename(config_path))[0]
    history_path = os.path.join(results_root, f"{dataset_name}_history.jsonl")
    history = []
    if os.path.exists(history_path):
        with open(history_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    history.append(json.loads(line))
                    
    total_iterations = len(history)
    
    if total_iterations == 0:
        print(f"No history found at {history_path}")
        sys.exit(1)
        
    objective_metric = history[0].get("objective_metric", "replicate_agreement")
    
    # Find best iteration
    best_record = max(history, key=lambda x: x["scores"].get(objective_metric) or 0.0)
    best_iteration = best_record["iteration"]
    best_scores = best_record["scores"]
    best_config = best_record["config"]
    
    # Render chart if >= 3
    chart_base64 = None
    if total_iterations >= 3:
        iters = [r["iteration"] for r in history]
        objs = [(r["scores"].get(objective_metric) or 0.0) for r in history]
        sites = [(r["scores"].get("n_binding_sites") or 0) for r in history]
        
        fig, ax1 = plt.subplots(figsize=(8, 4))
        ax1.set_xlabel("Iteration")
        ax1.set_ylabel(objective_metric, color="tab:blue")
        ax1.plot(iters, objs, marker="o", color="tab:blue", label=objective_metric)
        ax1.tick_params(axis="y", labelcolor="tab:blue")
        
        ax2 = ax1.twinx()
        ax2.set_ylabel("n_binding_sites", color="tab:red")
        ax2.plot(iters, sites, marker="s", color="tab:red", linestyle="--", alpha=0.7, label="Sites")
        ax2.tick_params(axis="y", labelcolor="tab:red")
        
        best_obj = best_record["scores"].get(objective_metric) or 0.0
        ax1.plot([best_iteration], [best_obj], marker="*", color="gold", markersize=15, label="Best")
        
        fig.tight_layout()
        buf = BytesIO()
        plt.savefig(buf, format="png", dpi=150)
        buf.seek(0)
        chart_base64 = base64.b64encode(buf.read()).decode("utf-8")
        plt.close()
        
    motif_score = best_scores.get("motif_hit_rate")
    motif_text = "N/A" if motif_score is None else f"{motif_score:.4f}"
    static_biology_check = f"The target motif ({target_motif}) was found in {motif_text} of the binding site windows, indicating alignment with the known {target_protein} footprint."
    
    best_obj_val = best_record["scores"].get(objective_metric) or 0.0
    
    experiment_summary = ""
    try:
        from dotenv import load_dotenv
        from langchain_google_genai import ChatGoogleGenerativeAI
        load_dotenv()
        
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.2)
        baseline_scores = history[0]["scores"] if history else {}
        
        prompt = f"""
You are an expert computational biologist analyzing the results of an Agentic PureCLIP optimization run.

Here is the experiment context:
- Target Protein: {target_protein}
- Cell Line: {cell_line}
- Objective Metric: {objective_metric}
- Total Iterations: {total_iterations}

Optimization Results:
- Initial (Baseline) Objective: {baseline_scores.get(objective_metric, 'N/A')}
- Best Objective Achieved: {best_obj_val} (at Iteration {best_iteration})
- Best Iteration Scores: {json.dumps(best_scores)}

Biological Context (CRITICAL):
- The known target motif for {target_protein} is: {target_motif}
- The motif hit rate in the best iteration was: {motif_text}

Instructions:
1. Summarize how the optimization improved the results from the baseline.
2. Interpret the motif hit rate ({target_motif}) objectively.
3. TONE: Strictly neutral, purely descriptive, and academic. Do NOT use exaggerated, strong, or hyped adjectives. Be completely flat and objective.
4. LENGTH: Maximum 100 words. Keep it extremely concise.
5. FORMAT: Return plain text. You may use <b> tags for bolding and <br> for line breaks if needed. Do NOT use markdown (**). Do not include introductory phrases.
"""
        print("Generating LLM experiment summary...")
        response = llm.invoke(prompt)
        experiment_summary = response.content.strip()
    except Exception as e:
        print(f"Warning: Failed to generate LLM summary ({e}). Falling back to static check.")
        experiment_summary = static_biology_check

    score_cards = []
    for k, v in best_scores.items():
        if k in ("run_id", "dataset_id"):
            continue
        val_str = "N/A" if v is None else str(v)
        score_cards.append({
            "key": k,
            "value": val_str
        })

    def format_config(cfg_dict, prev_cfg_dict=None, collapsible=True):
        all_lines = []
        changed_lines = []
        for k, v in cfg_dict.items():
            if isinstance(v, dict):
                all_lines.append(f"<b>{k}</b>:")
                prev_sub_dict = prev_cfg_dict.get(k, {}) if prev_cfg_dict else {}
                for sub_k, sub_v in v.items():
                    changed = False
                    if prev_cfg_dict is not None:
                        changed = prev_sub_dict.get(sub_k) != sub_v
                    
                    val_str = f"<span style='color: #c05621; font-weight: 700;'>{sub_v}</span>" if changed else str(sub_v)
                    key_str = f"<span style='color: #c05621; font-weight: 700;'>{sub_k}</span>" if changed else sub_k
                    all_lines.append(f"&nbsp;&nbsp;{key_str}: {val_str}")
                    
                    if changed:
                        summary_key = f"<b>{k}.{sub_k}</b>"
                        changed_lines.append(f"{summary_key}: {sub_v}")
            else:
                changed = False
                if prev_cfg_dict is not None:
                    changed = prev_cfg_dict.get(k) != v
                val_str = f"<span style='color: #c05621; font-weight: 700;'>{v}</span>" if changed else str(v)
                key_str = f"<span style='color: #c05621; font-weight: 700;'>{k}</span>" if changed else k
                all_lines.append(f"<b>{k}</b>: {val_str}")
                
                if changed:
                    changed_lines.append(f"<b>{k}</b>: {v}")
                    
        full_html = "<br>".join(all_lines)
        
        if not collapsible:
            return full_html
            
        if prev_cfg_dict is None:
            summary_text = "<span style='color: #718096; font-style: italic;'>Baseline (Click to expand)</span>"
        elif not changed_lines:
            summary_text = "<span style='color: #718096; font-style: italic;'>No changes</span>"
        else:
            summary_text = "<br>".join(changed_lines)
            
        return f'''
        <details>
            <summary style="cursor: pointer; outline: none; user-select: none;">
                <div style="display: inline-block; vertical-align: top;">{summary_text}</div>
            </summary>
            <div style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed #cbd5e0;">
                {full_html}
            </div>
        </details>
        '''

    history_table_interactive = []
    history_table_static = []
    prev_config = None
    for r in history:
        current_config = r.get("config", {})
        history_table_interactive.append({
            "iteration": r["iteration"],
            "config_html": format_config(current_config, prev_config, collapsible=True),
            "objective": r["scores"].get(objective_metric, "N/A"),
            "sites": r["scores"].get("n_binding_sites", "N/A")
        })
        history_table_static.append({
            "iteration": r["iteration"],
            "config_html": format_config(current_config, prev_config, collapsible=False),
            "objective": r["scores"].get(objective_metric, "N/A"),
            "sites": r["scores"].get("n_binding_sites", "N/A")
        })
        prev_config = current_config
        
    template_str = """
    <!DOCTYPE html>
    <html>
    <head>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { 
            font-family: 'Inter', system-ui, -apple-system, sans-serif; 
            margin: 0; 
            padding: 40px; 
            background-color: #f8f9fa; 
            color: #2d3748; 
            line-height: 1.6;
        }
        .container {
            max-width: 960px;
            margin: 0 auto;
            background-color: #ffffff;
            border-radius: 12px;
            box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05), 0 4px 6px -2px rgba(0,0,0,0.025);
            padding: 40px;
        }
        
        @page {
            size: A4;
            margin: 1cm;
        }
        
        @media print {
            body {
                background-color: #ffffff;
                padding: 0;
            }
            .container {
                box-shadow: none;
                border-radius: 0;
                padding: 0;
                max-width: none;
                margin: 0;
            }
            table {
                font-size: 0.72rem;
            }
            .config-block {
                font-size: 0.68rem;
            }
        }
        h1, h2, h3 { 
            color: #1a202c; 
            font-weight: 600; 
            margin-top: 2rem;
            margin-bottom: 1rem;
        }
        
        .header { 
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            padding-bottom: 25px;
            border-bottom: 1px solid #e2e8f0;
            margin-bottom: 40px;
        }
        .header-left {
            flex: 1;
            padding-right: 40px;
        }
        .header-left .eyebrow {
            text-transform: uppercase; 
            letter-spacing: 0.1em; 
            font-size: 0.75rem; 
            font-weight: 700; 
            color: #718096; 
            margin-bottom: 8px;
        }
        .header-left h1 { 
            font-size: 2.2rem; 
            font-weight: 700; 
            color: #1a202c; 
            margin-top: 0; 
            margin-bottom: 5px; 
            line-height: 1.2;
        }
        .header-left h1 .in-text {
            font-weight: 300; 
            color: #cbd5e0;
            margin: 0 4px;
        }
        .header-left .meta-grid {
            margin-top: 25px; 
            display: flex; 
            gap: 40px;
        }
        .meta-item-title {
            font-size: 0.75rem; 
            text-transform: uppercase; 
            color: #718096; 
            font-weight: 600; 
            letter-spacing: 0.05em; 
            margin-bottom: 4px;
        }
        .meta-item-value {
            font-size: 1.1rem; 
            font-weight: 600; 
            color: #2d3748;
        }
        .meta-item-value.monospace {
            font-size: 0.9rem; 
            font-family: 'SFMono-Regular', Consolas, monospace; 
            color: #4a5568; 
            margin-top: 2px;
            font-weight: normal;
        }
        
        .header-right {
            text-align: right;
            padding-bottom: 5px;
        }
        .header-right .best-title {
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #4a5568;
            font-weight: 700;
            margin-bottom: 4px;
        }
        .header-right .best-value {
            font-size: 3.5rem; 
            font-weight: 700; 
            color: #2b6cb0; 
            margin: 0;
            line-height: 1;
            letter-spacing: -0.02em;
        }
        .header-right .best-metric {
            font-size: 0.85rem; 
            font-weight: 600; 
            color: #718096;
            margin-top: 8px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .config-block { 
            font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; 
            font-size: 0.85rem; 
            background-color: #f7fafc; 
            padding: 18px; 
            border-radius: 12px; 
            border: 1px solid #e2e8f0;
            line-height: 1.6;
            box-sizing: border-box;
            word-wrap: break-word;
        }

        .card-container { 
            display: flex; 
            flex-wrap: wrap; 
            margin: -10px;
        }
        .card { 
            width: calc(50% - 20px);
            margin: 10px;
            border: 1px solid #e2e8f0; 
            border-radius: 12px; 
            padding: 20px; 
            background-color: #ffffff; 
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
            box-sizing: border-box;
        }
        .card .title { font-weight: 600; color: #4a5568; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; word-wrap: break-word; overflow-wrap: break-word; }
        .card .value { font-size: 1.8rem; font-weight: 700; color: #2b6cb0; margin-top: 10px; }

        .layout-row {
            display: flex;
            justify-content: space-between;
            margin-bottom: 40px;
        }
        .layout-col-main {
            width: 64%;
            display: flex;
            flex-direction: column;
        }
        .layout-col-side {
            width: 32%;
            display: flex;
            flex-direction: column;
        }

        .bio-check { 
            display: flex;
            align-items: flex-start;
            padding: 20px 25px; 
            background-color: #f0fff4; 
            border: 1px solid #c6f6d5;
            border-radius: 12px; 
            margin-bottom: 40px; 
            color: #276749;
            box-shadow: 0 2px 4px rgba(72, 187, 120, 0.1);
        }
        .bio-check-icon {
            font-size: 2rem;
            margin-right: 20px;
            margin-top: -5px;
        }

        table { 
            width: 100%; 
            max-width: 100%;
            table-layout: fixed;
            box-sizing: border-box;
            border-collapse: separate; 
            border-spacing: 0;
            margin-bottom: 40px; 
            font-size: 0.85rem; 
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid #e2e8f0;
        }
        th, td { 
            padding: 10px 12px; 
            text-align: left; 
            vertical-align: top;
            border-bottom: 1px solid #e2e8f0;
            word-break: break-word;
            overflow-wrap: anywhere;
        }
        th { 
            background-color: #f7fafc; 
            font-weight: 600; 
            color: #4a5568; 
            text-transform: uppercase; 
            font-size: 0.8rem;
            letter-spacing: 0.05em;
        }
        tr:last-child td { border-bottom: none; }
        .best-row { 
            background-color: #ebf8ff; 
        }
        .best-row td {
            font-weight: 500;
        }
        
        .chart-container { 
            text-align: center; 
            margin: 40px 0; 
            padding: 20px;
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
        }
        .chart-container img { max-width: 100%; height: auto; }
        .fallback-text {
            color: #718096;
            font-style: italic;
            text-align: center;
            padding: 30px;
            background: #f7fafc;
            border-radius: 12px;
            border: 1px dashed #cbd5e0;
        }
        .glossary-box {
            background-color: #f7fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 15px 20px;
            margin-bottom: 30px;
            font-size: 0.8rem;
            color: #4a5568;
        }
        .glossary-box ul {
            margin: 8px 0 0 0;
            padding-left: 20px;
        }
        .glossary-box li {
            margin-bottom: 4px;
        }
    </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="header-left">
                    <div class="eyebrow">Agentic PureCLIP Optimisation</div>
                    <h1>
                        {{ target_protein }} <span class="in-text">/</span> {{ cell_line }}
                    </h1>
                    
                    <div class="meta-grid">
                        <div>
                            <div class="meta-item-title">Total Iterations</div>
                            <div class="meta-item-value">{{ total_iterations }}</div>
                        </div>
                        <div>
                            <div class="meta-item-title">Run ID</div>
                            <div class="meta-item-value monospace">{{ run_id }}</div>
                        </div>
                    </div>
                </div>
                <div class="header-right">
                    <div class="best-title">Best Iteration (#{{ best_iteration }})</div>
                    <div class="best-value">{{ best_objective_val }}</div>
                    <div class="best-metric">{{ objective_metric }}</div>
                </div>
            </div>
            
            <div class="glossary-box">
                <strong style="font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: #718096;">Glossary</strong>
                <ul>
                    <li><strong>Iteration:</strong> One complete cycle of the pipeline where the AI proposes a new set of PureCLIP peak-calling and post-processing parameters, followed by pipeline execution and scoring.</li>
                    <li><strong>Run ID:</strong> A unique identifier for the specific pipeline execution, typically formatted as <code>[TargetProtein]_[CellLine]_iter_[Number]</code> (e.g., <code>RBFOX2_K562_iter_01</code>).</li>
                    <li><strong>motif_hit_rate:</strong> The percentage of final binding sites that contain the exact target motif sequence within a ±15nt window flanking the boundaries of the binding region.</li>
                </ul>
            </div>
            
            <div class="layout-row">
                <div class="layout-col-main">
                    <h2 style="margin-top: 0;">Final Scores</h2>
                    <div class="card-container">
                        {% for card in score_cards %}
                        <div class="card">
                            <div class="title">{{ card.key }}</div>
                            <div class="value">{{ card.value }}</div>
                        </div>
                        {% endfor %}
                    </div>
                </div>
                <div class="layout-col-side">
                    <h2 style="margin-top: 0;">Optimal Config</h2>
                    <div class="config-block">
                        {{ best_config_html }}
                    </div>
                </div>
            </div>

            <h2>Experiment Summary</h2>
            <div class="bio-check" style="flex-direction: column; align-items: flex-start;">
                <div style="display: flex; align-items: flex-start; margin-bottom: 20px;">
                    <div style="font-size: 1.05rem; line-height: 1.7; color: #276749;">
                        {{ experiment_summary }}
                    </div>
                </div>
                <div style="margin-top: 15px; font-size: 0.8rem; color: #718096; font-style: italic; border-top: 1px solid #c6f6d5; padding-top: 10px; width: 100%;">
                    Disclaimer: This experiment summary is automatically generated by AI and is intended for preliminary reference only. Please verify biological significance with a domain expert.
                </div>
            </div>
            
            <h2>Convergence Trend</h2>
            {% if chart_base64 %}
            <div class="chart-container">
                <img src="data:image/png;base64,{{ chart_base64 }}" />
            </div>
            {% else %}
            <div class="fallback-text">Not enough iterations to generate a trend chart (requires at least 3). Showing table fallback.</div>
            {% endif %}
            
            <h2>Per-Iteration History</h2>
            <table>
                <thead>
                    <tr>
                        <th style="width: 70px;">Iteration</th>
                        <th style="width: 380px;">Config</th>
                        <th style="width: 130px;">{{ objective_metric }}</th>
                        <th style="width: 70px;">Sites</th>
                    </tr>
                </thead>
                <tbody>
                    {% for row in history_table %}
                    <tr class="{% if row.iteration == best_iteration %}best-row{% endif %}">
                        <td><strong>#{{ row.iteration }}</strong></td>
                        <td><div class="config-block" style="background: transparent; border: none; padding: 0;">{{ row.config_html }}</div></td>
                        <td>{{ row.objective }}</td>
                        <td>{{ row.sites }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    
    best_obj_val = best_record["scores"].get(objective_metric) or 0.0

    template = Template(template_str)
    
    def render_report(table_data):
        return template.render(
            target_protein=target_protein,
            cell_line=cell_line,
            run_id=run_id,
            objective_metric=objective_metric,
            total_iterations=total_iterations,
            best_objective_val=best_obj_val,
            best_iteration=best_iteration,
            best_config_html=format_config(best_config, collapsible=False),
            experiment_summary=experiment_summary,
            score_cards=score_cards,
            chart_base64=chart_base64,
            history_table=table_data
        )

    html_out_interactive = render_report(history_table_interactive)
    html_out_static = render_report(history_table_static)
    
    html_path = output_pdf.replace(".pdf", ".html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_out_interactive)
    print(f"Report saved to {html_path}")
    
    try:
        from weasyprint import HTML
        HTML(string=html_out_static).write_pdf(output_pdf)
        print(f"PDF report generated at {output_pdf}")
    except ImportError as e:
        print(f"Weasyprint is not installed ({e}). PDF generation skipped.")

if __name__ == "__main__":
    main()
