import copy
import json
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from agent.decisions import (
    DEFAULT_OBJECTIVE_WEIGHTS,
    build_decision_prompt,
    composite_objective,
    parse_decision_response,
    validated_next_config,
)
from agent.evaluation import FORCE_RULES
from agent.logging_config import setup_logger
from agent.state import AgentState, IterationRecord
from pipeline.configs import (
    DEFAULT_SEARCH_BOUNDS,
    ConfigValidationError,
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

llm = ChatOpenAI(
    model="deepseek-chat",
    temperature=0.2,
    base_url="https://api.deepseek.com/v1",
    api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
)

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config/run_config.yaml")

# How many times to re-prompt the LLM when it proposes a repeated/out-of-bounds
# parameter set before giving up and converging gracefully.
MAX_DECISION_RETRIES = 3


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
        force_rules=FORCE_RULES,
    )
    return {}


def run_scorers(state: AgentState) -> dict:
    logger.info("Running scorers")
    run_scorer_script(CONFIG_PATH, score_report_path(state["current_config"]))
    return {}


def _propose_next_config(state: AgentState, report: dict, weights: dict):
    """Ask the LLM for a novel, valid next config.

    The search space is small and the LLM may repeat a tried parameter set or
    stray out of bounds. Rather than crashing the whole run, retry with the
    rejection reason fed back into the prompt. Returns ``(decision, new_config)``;
    ``new_config`` is ``None`` if no novel valid set was found.
    """
    feedback = None
    decision = None
    for attempt in range(1, MAX_DECISION_RETRIES + 1):
        resp = llm.invoke(build_decision_prompt(state, report, weights, feedback))
        try:
            decision = parse_decision_response(resp.content)
        except (json.JSONDecodeError, ValueError) as exc:
            feedback = f"The response was not valid JSON ({exc}). Respond with ONLY the JSON object."
            logger.warning("Decision parse failed (attempt %d/%d): %s", attempt, MAX_DECISION_RETRIES, exc)
            continue
        try:
            return decision, validated_next_config(state, decision)
        except ConfigValidationError as exc:
            feedback = (
                f"{exc}. The new parameter set must differ from every set already tried "
                "and stay within the search bounds. Change a different parameter, "
                "or change it by a different amount."
            )
            logger.warning("Decision rejected (attempt %d/%d): %s", attempt, MAX_DECISION_RETRIES, exc)
    return decision, None


def agent_decide(state: AgentState) -> dict:
    logger.info("Agent is deciding on next config")
    with open(score_report_path(state["current_config"]), "r", encoding="utf-8") as handle:
        report = json.load(handle)
    weights = state["priors"].get("objective_weights") or DEFAULT_OBJECTIVE_WEIGHTS
    objective = composite_objective(report, weights)
    logger.info(
        "Scores: reproducibility=%s motif=%s recall=%s composite=%.4f (best so far=%.4f)",
        report.get("reproducibility_score", report.get("replicate_agreement")),
        report.get("motif_hit_rate"),
        report.get("benchmark_region_recall"),
        objective,
        state["best_score"],
    )

    improved = objective > state["best_score"] + state["score_improvement_threshold"]
    best_score = objective if improved else state["best_score"]
    best_config = state["current_config"] if improved else state["best_config"]

    decision, new_config = _propose_next_config(state, report, weights)

    record: IterationRecord = {
        "iteration": state["current_iteration"],
        "config": tunable_snapshot(state["current_config"]),
        "scores": report,
        "reasoning": decision["reasoning"] if decision else "No valid novel parameter set could be proposed.",
    }

    if new_config is None:
        # Search exhausted: stop gracefully instead of crashing the run.
        logger.warning(
            "No novel valid parameter set after %d attempts; converging.", MAX_DECISION_RETRIES
        )
        return {
            "current_config": state["current_config"],
            "current_iteration": state["current_iteration"] + 1,
            "history": [record],
            "best_score": best_score,
            "best_config": best_config,
            "no_improvement_streak": state["patience"],  # trip the convergence stop
        }

    logger.info("Agent decision reasoning: %s", decision["reasoning"])
    new_config["run_id"] = f"{state['priors']['target_protein']}_iter_{state['current_iteration'] + 1:02d}"
    new_config = _with_iteration_output(new_config)
    streak = 0 if improved else state["no_improvement_streak"] + 1

    return {
        "current_config": new_config,
        "current_iteration": state["current_iteration"] + 1,
        "history": [record],
        "best_score": best_score,
        "best_config": best_config,
        "no_improvement_streak": streak,
    }


def should_continue(state: AgentState) -> str:
    if state["current_iteration"] >= state["max_iterations"]:
        logger.info("Hard stop reached")
        return "stop"
    if state["no_improvement_streak"] >= state["patience"]:
        logger.info("Convergence reached")
        return "stop"
    return "continue"


def finalize(state: AgentState) -> dict:
    reason = (
        "Hard stop: reached max_iterations"
        if state["current_iteration"] >= state["max_iterations"]
        else "Converged: no improvement"
    )
    save_config(state["best_config"], "config/best_config.yaml")
    logger.info("DONE. %s. Best composite score=%.4f", reason, state["best_score"])
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
    base_config = _with_iteration_output(load_config(CONFIG_PATH))
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
