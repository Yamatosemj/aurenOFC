from __future__ import annotations

import re
import time
from typing import Any, Callable

from core.harness_serialization import _argumentos_da_chamada, _texto_seguro
from core.browser_verification import (
    confirmar_destino_resultado, contexto_resultados, destino_resultado,
)
from core.tool_result import ToolResult, from_legacy


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
    destination_state: dict[str, Any] | None = None,
    result_index: int | None = None,
) -> tuple[list[dict[str, Any]], int, bool, bool, bool]:
    """Executa a rodada sem apagar falhas anteriores por sucessos nao relacionados.

    O ciclo compartilha ``falhas_pendentes`` entre rodadas. Uma falha so e
    recuperada por sucesso posterior da mesma ferramenta com os mesmos
    argumentos normalizados para registro (sem expor valores sensiveis).
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

    for item in chamadas:
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
        )

        write_log(
            "TOOL_CALL",
            task_id=task_id,
            rodada=rodada,
            ferramenta=nome,
            argumentos=argumentos,
        )

        tool_started_perf = time.perf_counter()
        preflight_error = None
        is_search = False
        if destination_state is not None and nome == 'navegar_navegador':
            is_search = bool(re.search(r'(?:[?&](?:q|query|search)=|/search(?:[/?]|$))',
                                       argumentos, flags=re.IGNORECASE))
        if (destination_state is not None and destination_state.get('search_done')
                and nome in {'clicar_elemento', 'navegar_navegador'} and not is_search):
            before = destination_state.get('before')
            expected = (destino_resultado(before, nome, argumentos, result_index)
                        if isinstance(before, dict) else None)
            if expected is None:
                preflight_error = ToolResult.failure(
                    'Nao ha contexto de busca suficiente para confirmar este resultado.',
                    error_code='result_precontext_missing', tool_name=nome,
                )
            else:
                destination_state['pending_action'] = {'before': before, 'expected': expected}
                destination_state['before'] = None
                destination_state['verified'] = False
        try:
            resultado_bruto = preflight_error or executar_ferramenta(item)
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

        result_context_checked = False
        if destination_state is not None and ferramenta_sucesso:
            if nome in browser_state_mutating_tools:
                destination_state['verified'] = False
                destination_state['before'] = None
                if nome not in {'clicar_elemento', 'navegar_navegador'}:
                    destination_state.pop('pending_action', None)
            if nome == 'navegar_navegador' and is_search:
                destination_state.update(search_done=True, before=None,
                                         pending_action=None, verified=False)
            elif nome == browser_verification_tool:
                pending_action = destination_state.get('pending_action')
                dados = dict(resultado_estruturado.data or {})
                if pending_action is not None:
                    result_context_checked = True
                    destination_state['verified'] = confirmar_destino_resultado(
                        pending_action['before'], pending_action['expected'], dados)
                    if destination_state['verified']:
                        destination_state.pop('pending_action', None)
                elif destination_state.get('search_done') and not destination_state.get('verified'):
                    before = contexto_resultados(dados)
                    destination_state['before'] = None
                    if before is not None and re.search(
                        r'(?:[?&](?:q|query|search)=|/search(?:[/?]|$))',
                        before['url'], flags=re.IGNORECASE,
                    ):
                        destination_state['before'] = before
        elif destination_state is not None and nome in {'clicar_elemento', 'navegar_navegador'}:
            destination_state.pop('pending_action', None)

        if ferramenta_sucesso and nome in browser_state_mutating_tools:
            browser_verification_pending = True
            if browser_verification_state is not None:
                browser_verification_state["ferramenta"] = nome
                browser_verification_state["argumentos"] = argumentos
                browser_verification_state["dados_acao"] = dict(resultado_estruturado.data or {})
        elif ferramenta_sucesso and nome == browser_verification_tool and browser_verification_pending:
            verificado = None
            if browser_verifier is not None and browser_verification_state is not None:
                verificado = browser_verifier(
                    str(browser_verification_state.get("ferramenta") or ""),
                    str(browser_verification_state.get("argumentos") or "{}"),
                    resultado_estruturado.data or {},
                    browser_verification_state.get("dados_acao"),
                )
            if (result_context_checked
                    and str(browser_verification_state.get('ferramenta') or '')
                    in {'clicar_elemento', 'navegar_navegador'}):
                verificado = bool(destination_state.get('verified'))
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
                browser_verification_state.pop("dados_acao", None)
        if trace is not None:
            try:
                trace.record_tool(
                    nome,
                    (time.perf_counter() - tool_started_perf) * 1000.0,
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
            assinatura = (nome, argumentos)
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
                "image_path": str(imagem_path) if imagem_path else "",
                "dados": dict(resultado_estruturado.data or {}),
            }
        )

    if browser_verification_state is not None:
        browser_verification_state["pending"] = browser_verification_pending

    return (
        resultados_rodada,
        ferramentas_executadas,
        falha_nao_recuperada,
        vision_reobserve_pending,
        cancelado,
    )
