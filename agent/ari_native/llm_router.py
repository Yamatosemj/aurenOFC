"""LLM task router inspirado no componente real do Ari.

No Auren ele decide apenas o perfil do cérebro (fast/deep); o provider e o
modelo continuam sendo os do Auren.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteResult:
    task_type: str
    role: str


class LLMRouter:
    ROLE_MAP = {
        "simple_chat": "fast",
        "complex_plan": "deep",
        "code_gen": "deep",
        "long_analysis": "deep",
    }

    CODE_KEYWORDS = (
        "codigo", "código", "python", "bug", "erro", "refator",
        "teste", "testar", "cmd", "powershell", "shell",
        "code", "refactor",
    )
    PLAN_KEYWORDS = (
        "plano", "etapa", "automat", "analise", "análise", "relatório",
        "relatorio", "projeto", "implementar", "arquitetura", "planejar",
        "plan", "automate", "analyze", "report", "design",
    )
    LONG_KEYWORDS = (
        "comparar", "compare", "detalhad", "profund", "profundo",
        "explica tudo", "análise completa", "analise completa",
        "in-depth", "elaborate",
    )

    def route(self, message: str, context: dict | None = None) -> RouteResult:
        del context
        task_type = self._classify_task(message)
        return RouteResult(task_type, self.ROLE_MAP[task_type])

    def _classify_task(self, message: str) -> str:
        text = " ".join(str(message or "").strip().lower().split())
        if any(keyword in text for keyword in self.CODE_KEYWORDS):
            return "code_gen"
        if any(keyword in text for keyword in self.PLAN_KEYWORDS):
            return "complex_plan"
        if len(text) > 180 or any(keyword in text for keyword in self.LONG_KEYWORDS):
            return "long_analysis"
        return "simple_chat"
