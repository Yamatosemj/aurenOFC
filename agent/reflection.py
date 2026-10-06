from __future__ import annotations

from agent.models import ReflectionResult


class ReflectionEngine:
    """Produz orientações de recuperação sem introduzir uma segunda chamada ao LLM."""

    @staticmethod
    def reflect(tool_name: str, verification, failure_count: int) -> ReflectionResult:
        if verification.ok:
            if verification.needs_next_step:
                return ReflectionResult(False, f"{tool_name} concluiu um passo, mas o objetivo ainda pode exigir etapas seguintes.")
            return ReflectionResult(False, f"{tool_name} retornou evidência compatível com sucesso. Confirme o estado antes de repetir.")

        repeated = failure_count >= 2
        if repeated:
            return ReflectionResult(True, f"{tool_name} falhou novamente. Verifique o estado real e abandone a repetição cega; procure uma alternativa.", True)
        return ReflectionResult(True, f"{tool_name} falhou. Verifique a causa e tente uma alternativa compatível antes de repetir a mesma chamada.", False)
