from __future__ import annotations

from core.tool_result import ToolResult
from core.undo import undo_last


def desfazer_ultima_acao() -> ToolResult:
    """Desfaz a ultima acao reversivel registrada pelo Auren.
    O callback salvo na pilha restaura o estado observado antes da mudanca.
    Custo: O(1) de pilha mais o custo da operacao de reversao.
    """
    resultado = undo_last()

    if resultado.status == "empty":
        return ToolResult.success(
            "Nada para desfazer.",
            data={"desfeito": False, "historico_disponivel": False},
            tool_name="desfazer_ultima_acao",
        )

    dados = {
        "acao": resultado.label,
        "horario": resultado.at.isoformat() if resultado.at else None,
        "preservada_em_falha": resultado.status == "failed",
    }

    if resultado.status == "failed":
        mensagem = (
            f"Nao consegui desfazer '{resultado.label}'. "
            "A entrada foi preservada para nova tentativa. "
            f"{resultado.detail}".strip()
        )
        return ToolResult.failure(
            mensagem,
            error_code=resultado.error_code or "undo_failed",
            data=dados,
            tool_name="desfazer_ultima_acao",
        )

    detalhe = f" {resultado.detail}" if resultado.detail else ""
    return ToolResult.success(
        f"Desfeito: {resultado.label}.{detalhe}",
        data={**dados, "desfeito": True},
        tool_name="desfazer_ultima_acao",
    )
