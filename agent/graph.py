import copy
import json
import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph

from agent.decisions import build_decision_prompt, parse_decision_response, validated_next_config
from agent.logging_config import setup_logger
from agent.state import AgentState, IterationRecord
from pipeline.configs import (
    DEFAULT_SEARCH_BOUNDS,
    load_config,
    save_config,
    score_report_path,
    tunable_snapshot,
    validate_config,
)
from pipeline.runner import run_scorers as run_scorer_script
from pipeline.runner import run_snakemake


load_dotenv()

logger = setup_logger("agent_graph", "results/logs/agent_graph.log")

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.2)

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config/run_config.yaml")


def _with_iteration_output(config: dict) -> dict:
    """Store every agent iteration in its own result directory."""
    cfg = copy.deepcopy(config)
    output = cfg.setdefault("output", {})
    results_root = str(output.setdefault("results_root", "results/runs")).rstrip("/")
    if output.get("use_run_id_subdir", True):
        output["results_dir"] = f"{results_root}/{cfg['run_id']}"
    return cfg


def run_pipeline(state: AgentState) -> dict:
    logger.info("Running pipeline for iteration %s", state["current_iteration"])
    validate_config(state["current_config"], search_bounds=state["search_bounds"])
    save_config(state["current_config"], CONFIG_PATH)

    run_snakemake(
        CONFIG_PATH,
        jobs=state["current_config"]["resources"]["threads"],
        force_rules=("pureclip", "pureclip_per_replicate", "postprocess"),
    )
    return {}


def run_scorers(state: AgentState) -> dict:
    logger.info("Running scorers")
    run_scorer_script(CONFIG_PATH, score_report_path(state["current_config"]))
    return {}


def agent_decide(state: AgentState) -> dict:
    logger.info("Agent is deciding on next config")
    with open(score_report_path(state["current_config"]), "r", encoding="utf-8") as handle:
        report = json.load(handle)
    objective = report.get(state["objective_metric"]) or 0.0

    results_root = state["current_config"].get("output", {}).get("results_root", "results")
    dataset_name = os.path.splitext(os.path.basename(CONFIG_PATH))[0]
    history_path = os.path.join(results_root, f"{dataset_name}_history.jsonl")
    os.makedirs(results_root, exist_ok=True)
    with open(history_path, "a", encoding="utf-8") as f:
        json.dump({
            "iteration": state["current_iteration"],
            "config": tunable_snapshot(state["current_config"]),
            "scores": report,
            "objective_metric": state["objective_metric"]
        }, f)
        f.write("\n")

    resp = llm.invoke(build_decision_prompt(state, report))
    try:
        decision = parse_decision_response(resp.content)
    except (json.JSONDecodeError, ValueError):
        logger.error("Failed to parse LLM response as JSON. Raw response:\n%s", resp.content)
        raise

    logger.info("Agent decision reasoning: %s", decision["reasoning"])

    try:
        new_config = validated_next_config(state, decision)
    except Exception as e:
        if type(e).__name__ == "ConfigValidationError":
            logger.warning("Agent proposed a duplicate configuration. Terminating early to save progress.")
            return {"termination_reason": f"Duplicate proposal: {e}"}
        raise

    cell_line = state["current_config"].get("cell_line")
    if not cell_line:
        logger.warning("cell_line not found in current_config, using 'UNKNOWN_CELL' for run_id")
        cell_line = "UNKNOWN_CELL"

    new_config["run_id"] = f"{state['priors']['target_protein']}_{cell_line}_iter_{state['current_iteration'] + 1:02d}"
    new_config = _with_iteration_output(new_config)

    improved = objective > state["best_score"] + state["score_improvement_threshold"]
    best_score = objective if improved else state["best_score"]
    best_config = state["current_config"] if improved else state["best_config"]
    streak = 0 if improved else state["no_improvement_streak"] + 1

    record: IterationRecord = {
        "iteration": state["current_iteration"],
        "config": tunable_snapshot(state["current_config"]),
        "scores": report,
        "reasoning": decision["reasoning"],
    }

    return {
        "current_config": new_config,
        "current_iteration": state["current_iteration"] + 1,
        "history": [record],
        "best_score": best_score,
        "best_config": best_config,
        "no_improvement_streak": streak,
    }


def should_continue(state: AgentState) -> str:
    if state.get("termination_reason"):
        logger.info("Early termination triggered: %s", state["termination_reason"])
        return "stop"
    if state["current_iteration"] >= state["max_iterations"]:
        logger.info("Hard stop reached")
        return "stop"
    if state["no_improvement_streak"] >= state["patience"]:
        logger.info("Convergence reached")
        return "stop"
    return "continue"


def finalize(state: AgentState) -> dict:
    reason = state.get("termination_reason")
    if not reason:
        reason = (
            "Hard stop: reached max_iterations"
            if state["current_iteration"] >= state["max_iterations"]
            else "Converged: no improvement"
        )
    save_config(state["best_config"], "config/best_config.yaml")
    logger.info("DONE. %s. Best %s=%.4f", reason, state["objective_metric"], state["best_score"])

    # Automatically generate the final report
    import subprocess
    dataset_name = os.path.splitext(os.path.basename(CONFIG_PATH))[0]
    results_root = state["current_config"].get("output", {}).get("results_root", "results")
    pdf_path = os.path.join(results_root, f"{dataset_name}_report.pdf")
    logger.info("Generating final PDF report at %s", pdf_path)
    subprocess.run(["python", "agent/report.py", CONFIG_PATH, pdf_path], check=False)

    return {"termination_reason": reason}


def build_graph():
    graph_builder = StateGraph(AgentState)
    graph_builder.add_node("run_pipeline", run_pipeline)
    graph_builder.add_node("run_scorers", run_scorers)
    graph_builder.add_node("agent_decide", agent_decide)
    graph_builder.add_node("finalize", finalize)

    graph_builder.add_edge(START, "run_pipeline")
    graph_builder.add_edge("run_pipeline", "run_scorers")
    graph_builder.add_edge("run_scorers", "agent_decide")
    graph_builder.add_conditional_edges(
        "agent_decide",
        should_continue,
        {"continue": "run_pipeline", "stop": "finalize"},
    )
    graph_builder.add_edge("finalize", END)
    return graph_builder.compile()


graph = build_graph()


if __name__ == "__main__":
    raw_config = load_config(CONFIG_PATH)

    # Implement Option B: Timestamped run directory
    import datetime
    import re
    session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_name = os.path.splitext(os.path.basename(CONFIG_PATH))[0]

    output = raw_config.setdefault("output", {})
    orig_root = str(output.get("results_root", "results/runs")).rstrip("/")

    if re.search(r"_\d{8}_\d{6}$", orig_root):
        new_root = re.sub(r"_\d{8}_\d{6}$", f"_{session_id}", orig_root)
    else:
        new_root = f"{orig_root}/{dataset_name}_{session_id}"

    output["results_root"] = new_root

    base_config = _with_iteration_output(raw_config)
    priors = base_config.get("priors") or json.load(open("config/priors.json", encoding="utf-8"))
    initial_state: AgentState = {
        "priors": priors,
        "objective_metric": priors.get("primary_objective_metric", "replicate_agreement"),
        "search_bounds": DEFAULT_SEARCH_BOUNDS,
        "current_config": base_config,
        "current_iteration": 0,
        "history": [],
        "best_score": 0.0,
        "best_config": base_config,
        "max_iterations": int(os.environ.get("MAX_ITER", "5")),
        "score_improvement_threshold": 0.01,
        "no_improvement_streak": 0,
        "patience": 10,
        "termination_reason": None,
    }
    logger.info("Starting Agent Graph")
    graph.invoke(initial_state, {"recursion_limit": 50})
