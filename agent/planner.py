from __future__ import annotations

import re

from agent.models import ExecutionPlan, PlanStep


class PlanBuilder:
    """Planejamento local leve para preparar tarefas longas sem chamar outro LLM."""

    _SPLIT_RE = re.compile(r"\s*(?:;|\.|\b(?:e depois|depois|em seguida|entao|então|a seguir)\b)\s*", re.I)

    @classmethod
    def build(cls, objective: str) -> ExecutionPlan:
        text = " ".join(str(objective or "").split())
        if not text:
            return ExecutionPlan(objective="", complexity="unknown", steps=(), max_rounds=12)

        parts = [p.strip(" ,") for p in cls._SPLIT_RE.split(text) if p.strip(" ,")]
        if len(parts) == 1:
            # Conectores coordenativos adicionais ajudam em frases longas.
            parts = [p.strip(" ,") for p in re.split(r"\s+e\s+(?=(?:abra|abrir|pesquise|procure|clique|preencha|digite|feche|mova|defina|coloque)\b)", text, flags=re.I) if p.strip()]

        commands = len(re.findall(r"\b(?:abra|abrir|pesquise|pesquisar|procure|procurar|clique|preencha|digite|feche|fechar|mova|mover|defina|coloque|analise|resuma)\w*\b", text, re.I))
        if len(parts) >= 4 or commands >= 4 or len(text) > 180:
            complexity = "complex"
            max_rounds = 18
        elif len(parts) >= 2 or commands >= 2:
            complexity = "multi_step"
            max_rounds = 15
        else:
            complexity = "simple"
            max_rounds = 12

        steps = tuple(PlanStep(i, part) for i, part in enumerate(parts, start=1))
        return ExecutionPlan(objective=text, complexity=complexity, steps=steps, max_rounds=max_rounds)
