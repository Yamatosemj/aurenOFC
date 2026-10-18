from __future__ import annotations

import re

from agent.models import ExecutionPlan, PlanStep


class PlanBuilder:
    """Planejamento local leve para preparar tarefas longas sem chamar outro LLM."""

    _SPLIT_RE = re.compile(r'\s*(?:;|\.(?=\s+[A-ZÀ-Ý])|\b(?:e depois|depois|em seguida|entao|então|a seguir)\b|\s+e\s+(?=(?:abra|abrir|pesquise|procure|clique|preencha|digite|feche|mova|redimensione|defina|coloque|consulte|verifique)\b))\s*', re.I)

    @classmethod
    def _parts(cls, text):
        # Mask quoted data without changing offsets; split only outside it.
        masked = list(text)
        quote = None
        for index, char in enumerate(text):
            if quote:
                masked[index] = 'x'
                if char == quote and (index == 0 or text[index - 1] != '\\'):
                    quote = None
            elif char in {'"', "'"}:
                quote = char
                masked[index] = 'x'
        for match in re.finditer(r'(?:https?://|[A-Za-z]:[\\/]|\\\\)\S+', text, re.I):
            masked[match.start():match.end()] = ['x'] * (match.end() - match.start())
        parts, start = [], 0
        for match in cls._SPLIT_RE.finditer(''.join(masked)):
            parts.append(text[start:match.start()].strip(' ,'))
            start = match.end()
        parts.append(text[start:].strip(' ,'))
        return [part for part in parts if part]

    @classmethod
    def build(cls, objective: str) -> ExecutionPlan:
        text = str(objective or "").strip()
        if not text:
            return ExecutionPlan(objective="", complexity="unknown", steps=(), max_rounds=12)

        parts = cls._parts(text)

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
