from __future__ import annotations

import re

from agent.models import VerificationResult
from core.tool_result import ToolResult, from_legacy


class VerificationEngine:
    """Verificação local conservadora do resultado real de uma ferramenta."""

    @staticmethod
    def verify(objective: str, tool_name: str, result, *, history_size: int = 0) -> VerificationResult:
        structured = from_legacy(result, tool_name=tool_name)
        if not structured.ok:
            return VerificationResult(False, "failed", structured.message, needs_next_step=False)

        text = structured.message.strip()
        objective_text = str(objective or "").lower()
        # Evidência de falha textual não deve passar como sucesso mesmo quando
        # uma implementação legada não devolveu ToolResult explicitamente.
        if re.search(r"\b(?:falha|erro|não consegui|nao consegui|bloqueado|negado)\b", text.lower()):
            return VerificationResult(False, "failed", text, needs_next_step=False)

        # Objetivos explicitamente compostos não são marcados como completos
        # só porque um passo teve sucesso. O Harness continua o loop.
        multi = bool(re.search(r"\b(?:e depois|depois|em seguida|entao|então)\b", objective_text))
        multi = multi or len(re.findall(r"\b(?:abra|pesquise|procure|clique|preencha|digite|feche|mova)\w*\b", objective_text)) >= 2
        if multi and history_size == 0:
            return VerificationResult(True, "partial", text, needs_next_step=True)
        return VerificationResult(True, "verified", text, needs_next_step=False)
