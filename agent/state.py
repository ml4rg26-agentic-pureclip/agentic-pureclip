# agent/state.py
from typing import TypedDict, Literal, Optional
from typing_extensions import Annotated
import operator


class IterationRecord(TypedDict):
    iteration: int
    config: dict
    scores: dict
    reasoning: str


class AgentState(TypedDict):
    # Static context
    priors: dict
    objective_metric: str
    search_bounds: dict

    # Mutable across loop
    current_config: dict
    current_iteration: int
    history: Annotated[list[IterationRecord], operator.add]
    best_score: float
    best_config: dict

    # Hard stop controls
    max_iterations: int
    score_improvement_threshold: float
    no_improvement_streak: int
    patience: int
    termination_reason: Optional[str]
