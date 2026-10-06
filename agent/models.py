from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AgentPhase(str, Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class PlanStep:
    index: int
    instruction: str
    expected_domain: str | None = None


@dataclass(frozen=True)
class ExecutionPlan:
    objective: str
    complexity: str
    steps: tuple[PlanStep, ...] = ()
    max_rounds: int = 12


@dataclass
class AgentRunState:
    objective: str
    phase: AgentPhase = AgentPhase.PLANNING
    plan: ExecutionPlan | None = None
