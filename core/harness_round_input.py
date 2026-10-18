from __future__ import annotations

from typing import Any, Callable


def _montar_input_da_rodada(
    objetivo: str,
    historico: list[dict[str, str]],
    resposta_anterior: Any,
    resultados: list[dict[str, Any]],
    *,
    montar_estado: Callable[..., str],
    preparar_resultado_visual: Callable[[dict], tuple[list[dict], bool] | None],
    ao_atualizar_geometria: Callable[[], None],
) -> list[Any]:
    """Monta um input novo sem previous_response_id.

    Mantemos apenas a resposta da rodada anterior e seus outputs,
    incluindo reasoning quando o modelo precisar dele. Nunca reenviamos
    a cadeia inteira da tarefa nem usamos previous_response_id.
    """
    # A rodada atual já será enviada como function_call_output.
    # Não repetimos o mesmo resultado no texto do estado.
    historico_anterior = historico
    if resultados:
        quantidade_atual = len(resultados)
        if quantidade_atual <= len(historico_anterior):
            historico_anterior = historico_anterior[:-quantidade_atual]

    estado = montar_estado(
        objetivo,
        historico_anterior,
        incluir_contexto=True,
    )

    input_items: list[Any] = [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": estado,
                }
            ],
        }
    ]

    # Preservamos os itens reasoning e function_call da resposta anterior
    # na ordem original. Eles pertencem a mesma rodada e antecedem os outputs
    # das ferramentas. Nao copiamos mensagens finais nem rodadas mais antigas.
    # O SDK devolve itens como objetos com .type; nao os converter em texto.
    for item in getattr(resposta_anterior, "output", []) or []:
        if getattr(item, "type", "") in {"reasoning", "function_call"}:
            input_items.append(item)

    for resultado in resultados:
        input_items.append(
            {
                "type": "function_call_output",
                "call_id": resultado["call_id"],
                "output": resultado["resultado"],
            }
        )
        partes_visao = preparar_resultado_visual(resultado)
        if partes_visao is not None:
            partes_imagem, geometria_atualizada = partes_visao
            if geometria_atualizada:
                ao_atualizar_geometria()

            # input_image e um content part de uma mensagem, nao um
            # item de topo da lista input. Mantemos imagem e sua
            # geometria no mesmo bloco user para evitar perder a
            # relacao entre os pixels observados e as coordenadas.
            input_items.append(
                {
                    "role": "user",
                    "content": partes_imagem,
                }
            )

    return input_items


def _montar_input_e_estado_da_rodada(
    objetivo: str,
    historico: list[dict[str, str]],
    resposta_anterior: Any,
    resultados: list[dict[str, Any]],
    *,
    montar_estado: Callable[..., str],
    preparar_resultado_visual: Callable[[dict], tuple[list[dict], bool] | None],
    ao_atualizar_geometria: Callable[[], None],
) -> tuple[list[Any], str]:
    """Monta o input seguinte e devolve o estado textual efetivamente enviado."""
    input_items = _montar_input_da_rodada(
        objetivo,
        historico,
        resposta_anterior,
        resultados,
        montar_estado=montar_estado,
        preparar_resultado_visual=preparar_resultado_visual,
        ao_atualizar_geometria=ao_atualizar_geometria,
    )

    estado_enviado = ""
    if input_items and isinstance(input_items[0], dict):
        conteudo = input_items[0].get("content", [])
        if conteudo and isinstance(conteudo, list):
            primeiro = conteudo[0]
            if isinstance(primeiro, dict):
                estado_enviado = str(primeiro.get("text", ""))

    return input_items, estado_enviado
