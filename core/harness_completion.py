from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal
import json


@dataclass(frozen=True)
class _ResultadoRetryRespostaVazia:
    acao: Literal["continuar", "retornar", "falhar"]
    resposta: Any = None
    empty_response_retries: int = 0
    failure_code: str | None = None
    failure_message: str | None = None


def _tentar_retry_resposta_vazia(
    objetivo: str,
    historico: list[dict[str, str]],
    *,
    rodada: int,
    exigir_ferramenta: bool,
    empty_response_retries: int,
    task_id: str,
    mensagem_erro_provider: str,
    task_manager: Any,
    montar_estado: Callable[..., str],
    pedir_modelo: Callable[..., Any],
    log_resposta_modelo: Callable[..., None],
    write_log: Callable[..., None],
    should_cancel: Callable[[str], bool],
    encerrar_cancelado: Callable[[str, int], Any],
    criar_resposta: Callable[[str], Any],
) -> _ResultadoRetryRespostaVazia:
    if empty_response_retries >= 1:
        return _ResultadoRetryRespostaVazia(
            acao="falhar",
            empty_response_retries=empty_response_retries,
            failure_code="empty_response",
            failure_message="Nao consegui produzir uma resposta final.",
        )

    empty_response_retries += 1
    estado_retry = montar_estado(
        objetivo,
        historico,
        [{
            "ferramenta": "nenhuma",
            "argumentos": "{}",
            "resultado": "A resposta final veio vazia. Responda de forma objetiva ou continue a execucao necessaria.",
        }],
    )
    if should_cancel(task_id):
        return _ResultadoRetryRespostaVazia(
            acao="retornar",
            resposta=encerrar_cancelado(
                "cancelado antes do retry de resposta vazia",
                rodada,
            ),
            empty_response_retries=empty_response_retries,
        )

    tool_choice_retry = "required" if exigir_ferramenta else None
    task_manager.wait_for_model(task_id)
    write_log(
        "MODEL_ROUND_REQUEST",
        task_id=task_id,
        rodada=rodada + 1,
        input_items=1,
        estado_chars=len(estado_retry),
        tool_choice=tool_choice_retry,
        motivo="empty_response_retry",
    )
    chamada = pedir_modelo(estado_retry, tool_choice_retry)
    if chamada is None:
        return _ResultadoRetryRespostaVazia(
            acao="retornar",
            resposta=criar_resposta(mensagem_erro_provider),
            empty_response_retries=empty_response_retries,
        )

    resposta, latencia_ms, metricas_roteamento = chamada
    log_resposta_modelo(
        rodada + 1,
        resposta,
        latencia_ms,
        metricas_roteamento,
        motivo="empty_response_retry",
    )
    task_manager.resume(task_id)
    return _ResultadoRetryRespostaVazia(
        acao="continuar",
        resposta=resposta,
        empty_response_retries=empty_response_retries,
    )


def _finalizar_resposta_sucesso(
    objetivo: str,
    historico: list[dict[str, str]],
    resposta: Any,
    *,
    apos_tarefa: Callable[[str, list[dict[str, str]]], Any] | None,
    task_id: str,
    salvar_estrategia: Callable[[str, list[dict[str, str]], str, bool], None],
    task_manager: Any,
    registrar_turno: Callable[[str, str], None],
    write_log: Callable[..., None],
    criar_resposta: Callable[[str], Any],
) -> Any:
    extra = None
    if apos_tarefa is not None and historico:
        try:
            extra = apos_tarefa(objetivo, historico)
        except Exception as erro:
            write_log(
                "MEMORY_ERROR",
                task_id=task_id,
                erro=str(erro),
            )

    if extra:
        texto_final = getattr(resposta, "output_text", "") or ""
        resposta = criar_resposta(texto_final + str(extra))

    final_texto = str(getattr(resposta, "output_text", "") or "").strip()
    salvar_estrategia(
        objetivo,
        historico,
        final_texto,
        True,
    )
    task_manager.complete(
        final_texto,
        task_id=task_id,
    )
    registrar_turno("assistant", final_texto)

    snapshot = task_manager.current_snapshot()
    write_log(
        "TASK_STATE",
        task_id=task_id,
        estado=snapshot.state.value if snapshot else "completed",
    )
    return resposta



def _concluir_tarefa_localmente(
    objetivo: str,
    historico: list[dict[str, str]],
    mensagem_final: str,
    *,
    rodada: int,
    ferramenta_final: str,
    task_id: str,
    apos_tarefa: Callable[[str, list[dict[str, str]]], Any] | None,
    salvar_estrategia: Callable[[str, list[dict[str, str]], str, bool], None],
    task_manager: Any,
    registrar_turno: Callable[[str, str], None],
    write_log: Callable[..., None],
    criar_resposta: Callable[[str], Any],
) -> Any:
    write_log(
        "TASK_LOCAL_COMPLETION",
        task_id=task_id,
        rodada=rodada,
        ferramenta=ferramenta_final,
        objetivo=objetivo,
    )
    write_log(
        "TASK_END",
        task_id=task_id,
        status="local_completion",
        rodada=rodada,
    )

    extra = None
    if apos_tarefa is not None:
        try:
            extra = apos_tarefa(objetivo, historico)
        except Exception as erro:
            write_log(
                "MEMORY_ERROR",
                task_id=task_id,
                erro=str(erro),
            )

    if extra:
        mensagem_final += str(extra)

    salvar_estrategia(
        objetivo,
        historico,
        mensagem_final,
        True,
    )
    task_manager.complete(
        mensagem_final,
        task_id=task_id,
    )
    registrar_turno("assistant", mensagem_final)
    return criar_resposta(mensagem_final)


def _mensagem_conclusao_local(
    objetivo: str,
    ferramenta: str,
    resultado: str | None = None,
    *,
    terminal_result_tools: set[str],
    multietapa_browser: bool,
) -> str:
    if ferramenta == "listar_abas" and multietapa_browser and resultado:
        return "Concluído: as abas solicitadas foram abertas e verificadas com sucesso."
    if ferramenta in terminal_result_tools and resultado:
        try:
            payload = json.loads(resultado)
            if isinstance(payload, dict) and payload.get('ok') is True and isinstance(payload.get('mensagem'), str):
                return payload['mensagem']
        except (TypeError, ValueError):
            pass
        return str(resultado)

    mensagens = {
        "clicar_elemento": "Concluído: executei o clique solicitado com sucesso.",
        "preencher_elemento": "Concluído: preenchi o campo solicitado com sucesso.",
        "pressionar_tecla": "Concluído: pressionei a tecla solicitada com sucesso.",
        "voltar_pagina": "Concluído: voltei uma página.",
        "avancar_pagina": "Concluído: avancei uma página.",
        "recarregar_pagina": "Concluído: recarreguei a página.",
        "rolar_pagina": "Concluído: rolei a página conforme solicitado.",
    }
    return mensagens.get(
        ferramenta,
        "Concluído: a última ação solicitada foi executada com sucesso.",
    )
