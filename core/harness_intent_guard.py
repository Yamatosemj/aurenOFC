"""Guarda semantica integrada ao Harness, antes de qualquer efeito de ferramenta."""
from __future__ import annotations

from typing import Any, Callable

from core.intent_verification import precisa_verificar, proposta_simples_exata


def verificar_antes_de_agir(
    harness: Any,
    objetivo: str,
    chamadas: list[Any],
    historico: list[dict[str, str]],
    *,
    rodada: int,
    resposta_wrapper: Callable[[str], Any],
    write_log: Callable[..., Any],
) -> tuple[bool, Any] | None:
    """None = aprovado ou apenas leitura; tupla = tarefa interrompida sem executar."""
    if harness.verificar_intencao is None or not precisa_verificar(chamadas):
        return None

    if proposta_simples_exata(objetivo, chamadas, historico):
        write_log(
            "INTENT_VERIFICATION_SKIPPED",
            task_id=harness._task_id,
            rodada=rodada,
            motivo="pedido_simples_argumentos_exatos",
            quantidade=len(chamadas),
        )
        return None

    if harness.task_manager.should_cancel(harness._task_id):
        return harness._encerrar_cancelado("cancelado antes da revisao de intencao", rodada)

    write_log(
        "INTENT_VERIFICATION_REQUEST",
        task_id=harness._task_id,
        rodada=rodada,
        quantidade=len(chamadas),
    )
    try:
        decisao = harness.verificar_intencao(objetivo, chamadas, historico)
        if getattr(decisao, "decisao", None) not in {"aprovar", "esclarecer", "bloquear"}:
            raise ValueError("Decisao semantica desconhecida.")
    except Exception as exc:
        write_log(
            "INTENT_VERIFICATION_ERROR",
            task_id=harness._task_id,
            rodada=rodada,
            erro=str(exc),
        )
        return harness._encerrar_falha(
            "intent_verification_unavailable",
            "Nao consegui verificar com seguranca a acao proposta. Nada foi executado nesta etapa.",
            rodada,
        )

    write_log(
        "INTENT_VERIFICATION_RESULT",
        task_id=harness._task_id,
        rodada=rodada,
        decisao=decisao.decisao,
    )

    if decisao.decisao == "esclarecer":
        pergunta = str(decisao.pergunta or "").strip()
        if not pergunta:
            return harness._encerrar_falha(
                "intent_verification_empty_question",
                "Preciso de um esclarecimento antes de agir, mas nao consegui formular a pergunta.",
                rodada,
            )
        if harness.task_manager.should_cancel(harness._task_id):
            return harness._encerrar_cancelado("cancelado antes do esclarecimento", rodada)
        harness._guardar_esclarecimento(objetivo, pergunta)
        harness.task_manager.complete(pergunta, task_id=harness._task_id)
        harness._registrar_turno("assistant", pergunta)
        write_log("TASK_END", task_id=harness._task_id, status="needs_clarification", rodada=rodada)
        return False, resposta_wrapper(pergunta)

    if decisao.decisao == "bloquear":
        return harness._encerrar_falha(
            "intent_verification_blocked",
            "Nao executei a acao proposta porque ela nao corresponde com seguranca ao seu pedido. "
            "Pode reformular o que voce deseja fazer?",
            rodada,
        )

    if harness.task_manager.should_cancel(harness._task_id):
        return harness._encerrar_cancelado("cancelado apos revisao de intencao", rodada)

    return None
