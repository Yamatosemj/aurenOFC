"""Guarda semantica integrada ao Harness, antes de qualquer efeito de ferramenta."""
from __future__ import annotations

from typing import Any, Callable
import json
import re
import time
from dataclasses import dataclass

from core.intent_verification import IntentVerificationFailure, precisa_verificar, proposta_simples_exata
from core.utils import normalizar_nome


@dataclass(frozen=True)
class PedidoReplanejamento:
    motivo: str


def _diagnostico_propostas_bloqueadas(chamadas: list[Any]) -> list[dict[str, Any]]:
    """Registra apenas o nome das tools e o alvo de eventual encerramento.

    Nunca registra argumentos genericos (texto de formularios, clipboard,
    mensagens ou outros dados privados) no evento de bloqueio.
    """
    diagnostico: list[dict[str, Any]] = []
    for item in chamadas[:12]:
        nome = str(getattr(item, "name", "") or "")[:100]
        resumo: dict[str, Any] = {"ferramenta": nome}
        if nome == "encerrar_processo_windows":
            try:
                args = json.loads(str(getattr(item, "arguments", "") or "{}"))
            except (TypeError, ValueError):
                args = {}
            if isinstance(args, dict):
                processo = str(args.get("nome") or "").strip()
                pid = args.get("pid")
                if processo and re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}", processo):
                    resumo["nome_processo"] = processo
                if type(pid) is int and 0 < pid <= 2**32 - 1:
                    resumo["pid"] = pid
        diagnostico.append(resumo)
    return diagnostico


def verificar_antes_de_agir(
    harness: Any,
    objetivo: str,
    chamadas: list[Any],
    historico: list[dict[str, str]],
    *,
    rodada: int,
    resposta_wrapper: Callable[[str], Any],
    write_log: Callable[..., Any],
    permitir_replanejamento: bool = False,
) -> tuple[bool, Any] | PedidoReplanejamento | None:
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
    review_started = time.perf_counter()
    try:
        historico_revisor = list(historico)
        pergunta_confirmada = getattr(harness, "_confirmacao_esclarecimento", None)
        if pergunta_confirmada:
            historico_revisor.append({
                "ferramenta": "__confirmacao_usuario_pendente__",
                "resultado": str(pergunta_confirmada)[:350],
            })
        decisao = harness.verificar_intencao(objetivo, chamadas, historico_revisor)
        if getattr(decisao, "decisao", None) not in {"aprovar", "esclarecer", "bloquear"}:
            raise ValueError("Decisao semantica desconhecida.")
    except Exception as exc:
        review_ms = (time.perf_counter() - review_started) * 1000.0
        review_usage = getattr(exc, "metricas_uso", None)
        trace = getattr(harness, "_trace", None)
        if trace is not None and isinstance(exc, IntentVerificationFailure):
            try:
                trace.record_model(rodada, review_ms, review_usage or {})
                record_stage = getattr(trace, "record_stage", None)
                if callable(record_stage):
                    record_stage("intent_review_error", review_ms, category="review_error",
                                 success=False, metadata={"uso_conhecido": review_usage is not None})
            except Exception as trace_error:
                write_log("TRACE_ERROR", task_id=harness._task_id, etapa="intent_review_error", erro=str(trace_error))
        write_log(
            "INTENT_VERIFICATION_ERROR",
            task_id=harness._task_id,
            rodada=rodada,
            erro=str(exc),
            uso_conhecido=review_usage is not None,
            latencia_ms=round(review_ms, 3),
            **({"uso": review_usage} if review_usage is not None else {}),
        )
        return harness._encerrar_falha(
            "intent_verification_unavailable",
            "Nao consegui verificar com seguranca a acao proposta. Nada foi executado nesta etapa.",
            rodada,
        )

    review_ms = (time.perf_counter() - review_started) * 1000.0
    review_usage = getattr(decisao, "metricas_uso", None)
    trace = getattr(harness, "_trace", None)
    if trace is not None and review_usage is not None:
        try:
            trace.record_model(rodada, review_ms, review_usage)
        except Exception as exc:
            write_log("TRACE_ERROR", task_id=harness._task_id, etapa="intent_review", erro=str(exc))

    write_log(
        "INTENT_VERIFICATION_RESULT",
        task_id=harness._task_id,
        rodada=rodada,
        decisao=decisao.decisao,
        **({"uso": review_usage, "latencia_ms": round(review_ms, 3)} if review_usage is not None else {}),
        **({
            "motivo": str(decisao.motivo or "")[:350],
            "propostas": _diagnostico_propostas_bloqueadas(chamadas),
        } if decisao.decisao == "bloquear" else {}),
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
        pergunta_confirmada = getattr(harness, "_confirmacao_esclarecimento", None)
        if (
            pergunta_confirmada
            and normalizar_nome(pergunta_confirmada) == normalizar_nome(pergunta)
        ):
            write_log(
                "INTENT_CLARIFICATION_LOOP_GUARD",
                task_id=harness._task_id,
                rodada=rodada,
                motivo="pergunta_ja_confirmada_pelo_usuario",
            )
            return harness._encerrar_falha(
                "repeated_clarification",
                "Voce ja respondeu essa pergunta, mas o verificador continua "
                "pedindo a mesma confirmacao. Interrompi a tarefa para evitar "
                "um ciclo de perguntas sem executar a acao.",
                rodada,
            )
        harness._guardar_esclarecimento(objetivo, pergunta)
        harness.task_manager.complete(pergunta, task_id=harness._task_id)
        harness._registrar_turno("assistant", pergunta)
        write_log("TASK_END", task_id=harness._task_id, status="needs_clarification", rodada=rodada)
        return False, resposta_wrapper(pergunta)

    if decisao.decisao == "bloquear":
        if permitir_replanejamento:
            return PedidoReplanejamento(str(decisao.motivo or "")[:350])
        return harness._encerrar_falha(
            "intent_verification_blocked",
            "Nao executei a acao proposta porque ela nao corresponde com seguranca ao seu pedido. "
            "Pode reformular o que voce deseja fazer?",
            rodada,
        )

    if harness.task_manager.should_cancel(harness._task_id):
        return harness._encerrar_cancelado("cancelado apos revisao de intencao", rodada)

    return None
