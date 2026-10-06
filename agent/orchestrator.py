from __future__ import annotations

from agent.models import AgentPhase, AgentRunState
from agent.planner import PlanBuilder
from agent.reflection import ReflectionEngine
from agent.verifier import VerificationEngine


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

    def observe(self, tool_name: str, result):
        if self.state is None:
            self.begin("")
        assert self.state is not None
        verification = VerificationEngine.verify(
            self.state.objective, tool_name, result, history_size=len(self.state.tool_history)
        )
        if not verification.ok:
            self.state.failures[tool_name] = self.state.failures.get(tool_name, 0) + 1
        reflection = ReflectionEngine.reflect(
            tool_name, verification, self.state.failures.get(tool_name, 0)
        )
        self.state.tool_history.append({
            "ferramenta": tool_name,
            "verificacao": verification.status,
            "reflexao": reflection.guidance,
        })
        if verification.ok:
            self.state.phase = AgentPhase.VERIFYING
        else:
            self.state.phase = AgentPhase.REFLECTING
        return verification, reflection

    def complete(self) -> None:
        if self.state is not None:
            self.state.phase = AgentPhase.COMPLETED

    def fail(self) -> None:
        if self.state is not None:
            self.state.phase = AgentPhase.FAILED

    def cancel(self) -> None:
        if self.state is not None:
            self.state.phase = AgentPhase.CANCELLED
