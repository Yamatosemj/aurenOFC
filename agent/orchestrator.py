from __future__ import annotations

from agent.models import AgentPhase, AgentRunState
from agent.planner import PlanBuilder


class AgentOrchestrator:
    """Camada Ari-style integrada ao Harness existente, sem segundo cérebro."""

    def __init__(self, *, strategy_memory=None) -> None:
        self.strategy_memory = strategy_memory
        self.state: AgentRunState | None = None

    def begin(self, objective: str):
        plan = PlanBuilder.build(objective)
        self.state = AgentRunState(objective=objective, phase=AgentPhase.PLANNING, plan=plan)
        self.state.phase = AgentPhase.EXECUTING
        return plan

    def complete(self) -> None:
        if self.state is not None:
            self.state.phase = AgentPhase.COMPLETED

    def fail(self) -> None:
        if self.state is not None:
            self.state.phase = AgentPhase.FAILED

    def cancel(self) -> None:
        if self.state is not None:
            self.state.phase = AgentPhase.CANCELLED
