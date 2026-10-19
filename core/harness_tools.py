from __future__ import annotations

import time
from typing import Any, Callable

from core.harness_serialization import _argumentos_da_chamada, _texto_seguro, _identidade_da_chamada
from core.tool_result import ToolResult, from_legacy
from core.tool_failures import STOP_MESSAGES


def _executar_chamadas_rodada(
    chamadas: list[Any],
    *,
    historico: list[dict[str, str]],
    task_manager: Any,
    task_id: str,
    rodada: int,
    executar_ferramenta: Callable[[Any], Any],
    trace: Any,
    vision_state_mutating_tools: set[str],
    vision_reobserve_pending: bool,
    falha_nao_recuperada: bool,
    max_tool_result_chars: int,
    get_active_vision_geometry: Callable[[], Any],
    clear_active_vision_geometry: Callable[[], Any],
    write_log: Callable[..., Any],
    browser_verification_state: dict[str, Any] | None = None,
    browser_state_mutating_tools: set[str] | None = None,
    browser_verification_tool: str = "obter_contexto_navegador",
    browser_verifier: Callable[[str, str, Any, Any], bool | None] | None = None,
    falhas_pendentes: set[tuple[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], int, bool, bool, bool]:
    """Executa a rodada sem apagar falhas anteriores por sucessos nao relacionados.

    O ciclo compartilha ``falhas_pendentes`` entre rodadas. Uma falha so e
    recuperada por sucesso posterior da mesma ferramenta com os mesmos
    argumentos originais canonicos (hash privado, separado do log redigido).
    """
    resultados_rodada: list[dict[str, Any]] = []
    ferramentas_executadas = 0
    cancelado = False
    browser_verification_pending = bool(
        browser_verification_state.get("pending", False)
        if browser_verification_state is not None
        else False
    )
    browser_state_mutating_tools = browser_state_mutating_tools or set()

    interrupted = False
    for item in chamadas:
        if interrupted:
            # Every model call ID gets an output, but skipped calls are never
            # recorded as executed TaskSteps or sent to the Dispatcher.
            skipped = ToolResult.failure('Chamada nao executada: uma etapa anterior falhou. Reavalie a sequencia.',
                error_code='sequence_aborted', tool_name=str(getattr(item, 'name', '')))
            resultados_rodada.append({'call_id': str(getattr(item, 'call_id', '')),
                'ferramenta': str(getattr(item, 'name', '')), 'argumentos': _argumentos_da_chamada(item),
                'resultado': skipped.for_model(), 'sucesso': False, 'executado': False,
                'codigo_erro': 'sequence_aborted', 'image_path': '', 'dados': {}})
            continue
        if task_manager.should_cancel(task_id):
            cancelado = True
            break

        nome = str(getattr(item, "name", "desconhecida"))
        argumentos = _argumentos_da_chamada(item)
        task_manager.begin_step(
            nome,
            argumentos,
            task_id=task_id,
            step=len(historico) + 1,
            **({'signature': _identidade_da_chamada(item)} if getattr(task_manager, 'persistent', False) else {}),
        )

        write_log(
            "TOOL_CALL",
            task_id=task_id,
            rodada=rodada,
            ferramenta=nome,
            argumentos=argumentos,
        )

        tool_started_perf = time.perf_counter()
        try:
            resultado_bruto = executar_ferramenta(item)
        except Exception as erro:
            resultado_bruto = ToolResult.failure(
                f"Falha inesperada no harness: {erro}",
                error_code="harness_exception",
                tool_name=nome,
            )

        resultado_estruturado = from_legacy(
            resultado_bruto,
            tool_name=nome,
        )
        ferramenta_sucesso = resultado_estruturado.ok
        interrupted = not ferramenta_sucesso
        tool_ms = (time.perf_counter() - tool_started_perf) * 1000.0

        if ferramenta_sucesso and nome in browser_state_mutating_tools:
            browser_verification_pending = True
            if browser_verification_state is not None:
                browser_verification_state["ferramenta"] = nome
                browser_verification_state["argumentos"] = argumentos
                browser_verification_state["argumentos_operacionais"] = str(getattr(item, "arguments", "{}"))
                browser_verification_state["dados_acao"] = dict(resultado_estruturado.data or {})
        elif ferramenta_sucesso and nome == browser_verification_tool and browser_verification_pending:
            verificado = None
            if browser_verifier is not None and browser_verification_state is not None:
                verificado = browser_verifier(
                    str(browser_verification_state.get("ferramenta") or ""),
                    str(browser_verification_state.get("argumentos_operacionais") or browser_verification_state.get("argumentos") or "{}"),
                    resultado_estruturado.data or {},
                    browser_verification_state.get("dados_acao"),
                )
            write_log(
                "TASK_BROWSER_VERIFICATION",
                task_id=task_id,
                rodada=rodada,
                ferramenta=str(browser_verification_state.get("ferramenta") or ""),
                verificado=verificado,
            )
            if verificado is not True:
                # Verificacao obrigatoria so termina com evidencia deterministica
                # explicita. None significa que nao foi possivel provar o resultado.
                browser_verification_pending = True
            else:
                browser_verification_pending = False
                browser_verification_state.pop("ferramenta", None)
                browser_verification_state.pop("argumentos", None)
                browser_verification_state.pop("argumentos_operacionais", None)
                browser_verification_state.pop("dados_acao", None)
        if trace is not None:
            try:
                trace.record_tool(
                    nome,
                    tool_ms,
                    success=ferramenta_sucesso,
                )
            except Exception as exc:
                write_log(
                    "TRACE_ERROR",
                    task_id=task_id,
                    etapa="tool",
                    erro=str(exc),
                )

        if (
            ferramenta_sucesso
            and nome != "capturar_tela_windows"
            and get_active_vision_geometry() is not None
            and nome in vision_state_mutating_tools
        ):
            vision_reobserve_pending = True
            clear_active_vision_geometry()

        resultado = resultado_estruturado.for_model()
        imagem_path = None
        if isinstance(resultado_estruturado.data, dict):
            imagem_path = resultado_estruturado.data.get("image_path")

        write_log(
            "TOOL_RESULT",
            task_id=task_id,
            rodada=rodada,
            ferramenta=nome,
            resultado=resultado,
            sucesso=ferramenta_sucesso,
            latencia_ms=round(tool_ms, 3),
            error_code=resultado_estruturado.error_code,
        )

        resultado_compacto = _texto_seguro(
            resultado,
            max_tool_result_chars,
        )
        task_manager.finish_step(
            success=ferramenta_sucesso,
            result=resultado_compacto,
            error="" if ferramenta_sucesso else resultado_compacto,
            task_id=task_id,
        )
        ferramentas_executadas += 1
        if falhas_pendentes is None:
            # Chamadores sem rastreador nao podem presumir que outro sucesso
            # recuperou a falha anterior.
            falha_nao_recuperada = falha_nao_recuperada or not ferramenta_sucesso
        else:
            # O ciclo compartilha este conjunto durante a tarefa inteira.
            # Um sucesso de outra ferramenta/alvo nao limpa falhas pendentes.
            assinatura = (nome, _identidade_da_chamada(item))
            if ferramenta_sucesso:
                falhas_pendentes.discard(assinatura)
            else:
                falhas_pendentes.add(assinatura)
            falha_nao_recuperada = bool(falhas_pendentes)

        historico.append(
            {
                "ferramenta": nome,
                "argumentos": argumentos,
                "resultado": resultado_compacto,
            }
        )

        resultados_rodada.append(
            {
                "call_id": str(getattr(item, "call_id", "")),
                "ferramenta": nome,
                "argumentos": argumentos,
                "resultado": resultado_compacto,
                "sucesso": ferramenta_sucesso,
                "codigo_erro": resultado_estruturado.error_code,
                "image_path": str(imagem_path) if imagem_path else "",
                "dados": dict(resultado_estruturado.data or {}),
            }
        )

        if not ferramenta_sucesso and resultado_estruturado.error_code in STOP_MESSAGES:
            # A later call from the same proposal must not run after a refusal
            # or an uncertain launch. The cycle still records task failure.
            break

    if browser_verification_state is not None:
        browser_verification_state["pending"] = browser_verification_pending

    return (
        resultados_rodada,
        ferramentas_executadas,
        falha_nao_recuperada,
        vision_reobserve_pending,
        cancelado,
    )
