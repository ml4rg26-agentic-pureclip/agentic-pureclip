# agent/graph_mock.py
# Mock version: replaces run_pipeline / run_scorers with fake outputs so the
# LangGraph loop, Gemini decisions, logging, and stop conditions can be tested
# WITHOUT running STAR / PureCLIP. Run on any machine, finishes in seconds.
import os
import json
import yaml
import copy
import time
import random
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv

# Automatically load environment variables from .env file
load_dotenv()

from langgraph.graph import StateGraph, START, END
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None
from agent.state import AgentState, IterationRecord
from agent.logging_config import setup_logger

log = setup_logger("agent_mock", "results/logs/agent_loop_mock.log")

MOCK_DIR = "results_mock"
os.makedirs(MOCK_DIR, exist_ok=True)

# Toggle: set USE_GEMINI=0 to also mock the LLM (fully offline, no API key needed)
USE_GEMINI = os.environ.get("USE_GEMINI", "1") == "1"

# Controls the fake-score curve. "plateau" = improve then stall (triggers
# convergence stop). "always_up" = keep improving (triggers hard-cap stop).
SCORE_MODE = os.environ.get("MOCK_SCORE_MODE", "plateau")

CONFIG_PATH = "config/run_config.yaml"
REPORT_PATH = "results/score_report.json"

if USE_GEMINI and ChatOpenAI is not None:
    llm = ChatOpenAI(
        model="deepseek-chat",
        temperature=0.2,
        base_url="https://api.deepseek.com/v1",
        api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
    )
else:
    llm = None

# MOCK NODES

def run_pipeline(state: AgentState) -> dict:
    """MOCK: pretend Snakemake ran. Write a fake binding-sites bed."""
    it = state["current_iteration"]
    log.info("───── ITERATION %d | [MOCK] run_pipeline START ─────", it)
    log.info("Tunable params this round: pureclip=%s postprocessing=%s",
             state["current_config"]["pureclip"],
             state["current_config"]["postprocessing"])

    # Simulate a little work so logs have realistic timing
    time.sleep(0.3)

    # Write a fake bed so downstream "looks" real
    fake_n = 1000 + it * 50
    fake_path = os.path.join(MOCK_DIR, "binding_sites.reproducible.bed")
    with open(fake_path, "w") as f:
        for i in range(fake_n):
            f.write(f"chr21\t{1000 + i*10}\t{1009 + i*10}\tsite_{i}\t10\t+\n")
    log.info("[MOCK] wrote %d fake binding sites to %s", fake_n, fake_path)
    log.info("[MOCK] pipeline OK (iter %d)", it)
    return {}

def run_scorers(state: AgentState) -> dict:
    """MOCK: produce a fake score report following SCORE_MODE."""
    it = state["current_iteration"]
    log.info("ITERATION %d | [MOCK] run_scorers START (mode=%s)", it, SCORE_MODE)

    if SCORE_MODE == "plateau":
        # Improves for first 2 iters, then plateaus -> convergence stop expected
        curve = [0.40, 0.55, 0.62, 0.625, 0.626, 0.626]
    else:  # "always_up": keeps improving -> hard-cap (5 iters) stop expected
        curve = [0.40, 0.48, 0.56, 0.64, 0.72, 0.80]

    agreement = curve[min(it, len(curve) - 1)]
    # add tiny noise so it looks real but stays deterministic-ish
    agreement = round(agreement + random.uniform(-0.002, 0.002), 4)

    report = {
        "run_id": state["current_config"]["run_id"],
        "n_binding_sites": 1000 + it * 50,
        "replicate_agreement": agreement,
        "motif_hit_rate": round(0.30 + it * 0.03, 4),
        "mean_sbr": None,
    }
    json.dump(report, open(REPORT_PATH, "w"), indent=2)
    log.info("[MOCK] score report: %s", json.dumps(report))
    return {}

# AGENT DECISION (real or mock LLM)

def _mock_llm_decision(state: AgentState, report: dict) -> dict:
    """Offline stand-in for Gemini: nudges one tunable param within bounds."""
    it = state["current_iteration"]
    bounds = state["search_bounds"]["pureclip"]["merge_distance_nt"]
    cur = state["current_config"]["pureclip"]["merge_distance_nt"]
    # Simple deterministic nudge: shrink merge distance each round, clamp to bounds
    new_dm = max(bounds[0], cur - 1)
    return {
        "reasoning": (f"[MOCK] agreement={report['replicate_agreement']}. "
                      f"Tightening merge_distance_nt {cur}->{new_dm} to reduce noise."),
        "changes": {"pureclip": {"merge_distance_nt": new_dm}},
    }

def agent_decide(state: AgentState) -> dict:
    it = state["current_iteration"]
    log.info("ITERATION %d | agent_decide START", it)

    report = json.load(open(REPORT_PATH))
    objective = report.get(state["objective_metric"]) or 0.0
    log.info("Objective (%s) this round: %.4f | best so far: %.4f",
             state["objective_metric"], objective, state["best_score"])

    if USE_GEMINI:
        if llm is None:
            raise RuntimeError("USE_GEMINI=1 but langchain_openai is not installed")
        prompt = f"""You are optimising PureCLIP parameters for eCLIP data.

PRIOR KNOWLEDGE:
{json.dumps(state['priors'], indent=2)}

CURRENT TUNABLE CONFIG:
{json.dumps(state['current_config']['pureclip'], indent=2)}
{json.dumps(state['current_config']['postprocessing'], indent=2)}

SEARCH BOUNDS (do not exceed):
{json.dumps(state['search_bounds'], indent=2)}

LATEST SCORE REPORT:
{json.dumps(report, indent=2)}

HISTORY:
{json.dumps([{'iter': h['iteration'], 'scores': h['scores'],
              'reasoning': h['reasoning']} for h in state['history']], indent=2)}

Objective to maximise: {state['objective_metric']} (current: {objective:.4f})

Note: replicate_agreement measures the overlap of sites between replicates. If the number of sites is already low, increasing stringency (e.g. increasing min_crosslink_events, decreasing merge_distance_nt) will reduce the number of sites and lower the chance of overlap, which usually causes agreement to drop. When sites are insufficient, consider relaxing parameters to improve sensitivity.

Respond ONLY with JSON:
{{"reasoning": "...", "changes": {{"pureclip": {{...}}, "postprocessing": {{...}}}}}}
Do not repeat parameter sets already in history."""
        t0 = time.time()
        resp = llm.invoke(prompt)
        log.info("Gemini responded in %.1fs", time.time() - t0)
        text = resp.content.replace("```json", "").replace("```", "").strip()
        try:
            decision = json.loads(text)
        except json.JSONDecodeError:
            log.error("Failed to parse Gemini JSON. Raw:\n%s", resp.content)
            raise
    else:
        log.info("[MOCK] USE_GEMINI=0, using offline decision stub")
        decision = _mock_llm_decision(state, report)

    log.info("Decision reasoning: %s", decision["reasoning"])
    log.info("Proposed changes: %s", json.dumps(decision["changes"]))

    new_config = copy.deepcopy(state["current_config"])
    for section, changes in decision["changes"].items():
        new_config[section].update(changes)
    new_config["run_id"] = f"{state['priors']['target_protein']}_iter_{it + 1:02d}"

    improved = objective > state["best_score"] + state["score_improvement_threshold"]
    best_score = objective if improved else state["best_score"]
    best_config = state["current_config"] if improved else state["best_config"]
    streak = 0 if improved else state["no_improvement_streak"] + 1

    if improved:
        log.info("IMPROVED: new best %.4f (was %.4f)", objective, state["best_score"])
    else:
        log.info("No improvement. Streak now %d/%d", streak, state["patience"])

    record: IterationRecord = {
        "iteration": it,
        "config": state["current_config"]["pureclip"],
        "scores": report,
        "reasoning": decision["reasoning"],
    }
    return {
        "current_config": new_config,
        "current_iteration": it + 1,
        "history": [record],
        "best_score": best_score,
        "best_config": best_config,
        "no_improvement_streak": streak,
    }

# STOP LOGIC

def should_continue(state: AgentState) -> str:
    it = state["current_iteration"]
    if it >= state["max_iterations"]:
        log.info("STOP: hard cap reached (%d/%d iterations)", it, state["max_iterations"])
        return "stop"
    if state["no_improvement_streak"] >= state["patience"]:
        log.info("STOP: converged (no improvement for %d rounds)", state["patience"])
        return "stop"
    log.info("CONTINUE: proceeding to iteration %d", it)
    return "continue"

def finalize(state: AgentState) -> dict:
    reason = ("Hard stop: reached max_iterations"
              if state["current_iteration"] >= state["max_iterations"]
              else "Converged: no improvement")
    yaml.safe_dump(state["best_config"], open("config/best_config.yaml", "w"))
    log.info("══════════ [MOCK] RUN COMPLETE ══════════")
    log.info("Reason: %s", reason)
    log.info("Best %s = %.4f", state["objective_metric"], state["best_score"])
    log.info("Total iterations run: %d", state["current_iteration"])
    return {"termination_reason": reason}

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("run_pipeline", run_pipeline)
    g.add_node("run_scorers", run_scorers)
    g.add_node("agent_decide", agent_decide)
    g.add_node("finalize", finalize)
    g.add_edge(START, "run_pipeline")
    g.add_edge("run_pipeline", "run_scorers")
    g.add_edge("run_scorers", "agent_decide")
    g.add_conditional_edges("agent_decide", should_continue,
                            {"continue": "run_pipeline", "stop": "finalize"})
    g.add_edge("finalize", END)
    return g.compile()

# Compile the graph at the module level so LangGraph Studio can discover it
graph = build_graph()

if __name__ == "__main__":
    log.info("############ [MOCK] AGENTIC PURECLIP RUN START ############")
    log.info("USE_GEMINI=%s | MOCK_SCORE_MODE=%s", USE_GEMINI, SCORE_MODE)

    # Seed initial config; create a minimal one if the real yaml isn't present
    if Path(CONFIG_PATH).exists():
        base_config = yaml.safe_load(open(CONFIG_PATH))
    else:
        log.warning("%s not found; using minimal built-in mock config", CONFIG_PATH)
        base_config = {
            "run_id": "PTBP1_iter_00",
            "pureclip": {"bandwidth_nt": 50, "merge_distance_nt": 8,
                         "high_precision_mode": False},
            "postprocessing": {"force_width": 9, "min_crosslink_events": 3},
        }

    priors = (json.load(open("config/priors.json"))
              if Path("config/priors.json").exists()
              else {"target_protein": "PTBP1", "known_motifs": []})
    initial_state: AgentState = {
        "priors": priors,
        "objective_metric": "replicate_agreement",
        "search_bounds": {
            "pureclip": {"merge_distance_nt": [4, 16], "bandwidth_nt": [20, 100]},
            "postprocessing": {"min_crosslink_events": [2, 6]},
        },
        "current_config": base_config,
        "current_iteration": 0,
        "history": [],
        "best_score": 0.0,
        "best_config": base_config,
        "max_iterations": int(os.environ.get("MAX_ITER", "5")),
        "score_improvement_threshold": 0.01,
        "no_improvement_streak": 0,
        "patience": 2,
        "termination_reason": None,
    }
    try:
        graph.invoke(initial_state, {"recursion_limit": 50})
    except Exception:
        log.exception("[MOCK] RUN ABORTED")
        raise
    log.info("############ [MOCK] RUN END ############")
