from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AgentPhase(str, Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    REFLECTING = "reflecting"
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


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    status: str
    evidence: str
    needs_next_step: bool = False


@dataclass(frozen=True)
class ReflectionResult:
    should_retry: bool
    guidance: str
    repeated_failure: bool = False


@dataclass
class AgentRunState:
    objective: str
    phase: AgentPhase = AgentPhase.PLANNING
    plan: ExecutionPlan | None = None
    tool_history: list[dict[str, str]] = field(default_factory=list)
    failures: dict[str, int] = field(default_factory=dict)
