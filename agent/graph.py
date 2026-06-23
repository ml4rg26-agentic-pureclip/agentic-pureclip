# agent/graph.py
import os
from dotenv import load_dotenv

# Automatically load environment variables from .env file
load_dotenv()

import json
import yaml
import subprocess
import copy
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from agent.state import AgentState, IterationRecord
from agent.logging_config import setup_logger

logger = setup_logger("agent_graph", "results/logs/agent_graph.log")

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.2)

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config/run_config.yaml")
REPORT_PATH = "results/score_report.json"

def run_pipeline(state: AgentState) -> dict:
    logger.info(f"Running pipeline for iteration {state['current_iteration']}")
    yaml.safe_dump(state["current_config"], open(CONFIG_PATH, "w"))

    subprocess.run(
        ["snakemake", "-j", "16", "--configfile", CONFIG_PATH, 
         "--rerun-incomplete", "-R", "pureclip", "pureclip_per_replicate", "postprocess"],
        check=True
    )
    return {}

def run_scorers(state: AgentState) -> dict:
    logger.info("Running scorers")
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    subprocess.run(
        ["python", "scorers/run_scorers.py", CONFIG_PATH, REPORT_PATH],
        env=env,
        check=True
    )
    return {}

def agent_decide(state: AgentState) -> dict:
    logger.info("Agent is deciding on next config")
    report = json.load(open(REPORT_PATH))
    objective = report.get(state["objective_metric"]) or 0.0

    prompt = f"""You are optimising PureCLIP parameters for eCLIP data.
Your goal is to MAXIMISE replicate_agreement.

PRIOR KNOWLEDGE:
{json.dumps(state['priors'], indent=2)}

SEARCH BOUNDS (never exceed these):
{json.dumps(state['search_bounds'], indent=2)}

CURRENT TUNABLE PARAMETERS:
{json.dumps(state['current_config']['pureclip'], indent=2)}
{json.dumps(state['current_config']['postprocessing'], indent=2)}

LATEST SCORE: {json.dumps(report, indent=2)}

FULL HISTORY OF ALL PREVIOUS ATTEMPTS (parameters -> resulting score):
{json.dumps([{'iter': h['iteration'],
              'params': h['config'],
              'agreement': h['scores']['replicate_agreement'],
              'n_sites': h['scores']['n_binding_sites']}
             for h in state['history']], indent=2)}

HOW TO DECIDE YOUR NEXT MOVE — follow this reasoning explicitly:

1. ANALYSE THE TREND. Look at the history. For each parameter you changed,
   did the score go UP or DOWN afterwards?

2. IF A DIRECTION IS FAILING, REVERSE IT. If you increased a parameter and
   the score dropped, do NOT increase it further. Try decreasing it instead,
   or return to the parameter values from the best-scoring iteration so far
   and explore a different parameter.

3. IF A DIRECTION IS WORKING, CONTINUE IT — but in smaller steps as you get
   closer, to avoid overshooting.

4. CHANGE ONE PARAMETER AT A TIME where possible, so the effect of each
   change is interpretable. Avoid changing everything at once.

5. DO NOT REPEAT a parameter set already tried in the history.

6. There is no rule that "relaxing always helps" or "stringency always hurts".
   Let the OBSERVED scores in the history decide the direction, not any
   fixed assumption.

The best score so far is {state['best_score']:.4f} with parameters:
{json.dumps(state['best_config']['pureclip'], indent=2)}

Respond ONLY with JSON:
{{"reasoning": "state the trend you observed and why you chose this direction",
  "changes": {{"pureclip": {{...}}, "postprocessing": {{...}}}}}}"""

    resp = llm.invoke(prompt)
    import re
    text = resp.content.strip()
    match = re.search(r'```(?:json)?(.*?)```', text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    else:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            text = text[start:end+1]
            
    try:
        decision = json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse LLM response as JSON. Raw response:\n{resp.content}")
        raise

    logger.info(f"Agent decision reasoning: {decision['reasoning']}")

    new_config = copy.deepcopy(state["current_config"])
    for section, changes in decision["changes"].items():
        new_config[section].update(changes)
    new_config["run_id"] = f"{state['priors']['target_protein']}_iter_{state['current_iteration']+1:02d}"

    improved = objective > state["best_score"] + state["score_improvement_threshold"]
    best_score = objective if improved else state["best_score"]
    best_config = state["current_config"] if improved else state["best_config"]
    streak = 0 if improved else state["no_improvement_streak"] + 1

    record: IterationRecord = {
        "iteration": state["current_iteration"],
        "config": {
            "pureclip": state["current_config"]["pureclip"],
            "postprocessing": state["current_config"].get("postprocessing", {})
        },
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
    if state["current_iteration"] >= state["max_iterations"]:
        logger.info("Hard stop reached")
        return "stop"
    if state["no_improvement_streak"] >= state["patience"]:
        logger.info("Convergence reached")
        return "stop"
    return "continue"

def finalize(state: AgentState) -> dict:
    reason = ("Hard stop: reached max_iterations"
              if state["current_iteration"] >= state["max_iterations"]
              else "Converged: no improvement")
    yaml.safe_dump(state["best_config"], open("config/best_config.yaml", "w"))
    logger.info(f"DONE. {reason}. Best {state['objective_metric']}={state['best_score']:.4f}")
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
    g.add_conditional_edges(
        "agent_decide",
        should_continue,
        {"continue": "run_pipeline", "stop": "finalize"}
    )
    g.add_edge("finalize", END)
    return g.compile()

# Compile the graph at the module level so LangGraph Studio can discover it
graph = build_graph()

if __name__ == "__main__":
    initial_state: AgentState = {
        "priors": json.load(open("config/priors.json")),
        "objective_metric": "replicate_agreement",
        "search_bounds": {
            "pureclip": {"merge_distance_nt": [4, 16], "bandwidth_nt": [20, 100]},
            "postprocessing": {"min_crosslink_events": [2, 6]},
        },
        "current_config": yaml.safe_load(open(CONFIG_PATH)),
        "current_iteration": 0,
        "history": [],
        "best_score": 0.0,
        "best_config": yaml.safe_load(open(CONFIG_PATH)),
        "max_iterations": int(os.environ.get("MAX_ITER", "5")),
        "score_improvement_threshold": 0.01,
        "no_improvement_streak": 0,
        "patience": 10,
        "termination_reason": None,
    }
    logger.info("Starting Agent Graph")
    graph.invoke(initial_state, {"recursion_limit": 50})
