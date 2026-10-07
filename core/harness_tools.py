from __future__ import annotations

from typing import Any, Callable
import time


def _executar_chamadas_rodada(
    chamadas: list[Any],
    *,
    historico: list[dict[str, str]],
    task_manager: Any,
    task_id: str,
    rodada: int,
    executar_ferramenta: Callable[[Any], Any],
    argumentos_da_chamada: Callable[[Any], str],
    texto_seguro: Callable[[Any, int], str],
    trace: Any,
    vision_state_mutating_tools: set[str],
    vision_reobserve_pending: bool,
    falha_nao_recuperada: bool,
    max_tool_result_chars: int,
    get_active_vision_geometry: Callable[[], Any],
    clear_active_vision_geometry: Callable[[], Any],
    from_legacy: Callable[..., Any],
    tool_result_failure: Callable[..., Any],
    write_log: Callable[..., Any],
) -> tuple[list[dict[str, Any]], int, bool, bool, bool]:
    """Executa as chamadas de uma rodada e atualiza historico/estado operacional."""
    resultados_rodada: list[dict[str, Any]] = []
    ferramentas_executadas = 0
    cancelado = False

    for item in chamadas:
        if task_manager.should_cancel(task_id):
            cancelado = True
            break

        nome = str(getattr(item, "name", "desconhecida"))
        argumentos = argumentos_da_chamada(item)
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
        try:
            resultado_bruto = executar_ferramenta(item)
        except Exception as erro:
            resultado_bruto = tool_result_failure(
                f"Falha inesperada no harness: {erro}",
                error_code="harness_exception",
                tool_name=nome,
            )

        resultado_estruturado = from_legacy(
            resultado_bruto,
            tool_name=nome,
        )
        ferramenta_sucesso = resultado_estruturado.ok
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

        resultado_compacto = texto_seguro(
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
        falha_nao_recuperada = not ferramenta_sucesso

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

    return (
        resultados_rodada,
        ferramentas_executadas,
        falha_nao_recuperada,
        vision_reobserve_pending,
        cancelado,
    )
