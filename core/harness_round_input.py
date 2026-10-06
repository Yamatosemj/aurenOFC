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
        incluir_contexto=False,
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

    # Modelos de raciocínio exigem que os itens de reasoning da resposta
    # anterior acompanhem os function calls e os respectivos outputs.
    # Enviamos somente a resposta da rodada imediatamente anterior,
    # nunca toda a cadeia da tarefa.
    for item in getattr(resposta_anterior, "output", []):
        if getattr(item, "type", "") == "function_call":
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
