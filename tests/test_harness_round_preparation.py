from __future__ import annotations

from types import SimpleNamespace

from core.harness_round_input import _montar_input_e_estado_da_rodada


def test_prepara_input_e_extrai_estado_enviado():
    resposta = SimpleNamespace(output=[])
    resultados = [{"call_id": "c1", "resultado": "ok"}]

    input_items, estado_enviado = _montar_input_e_estado_da_rodada(
        "objetivo",
        [],
        resposta,
        resultados,
        montar_estado=lambda objetivo, historico, incluir_contexto: "estado pronto",
        preparar_resultado_visual=lambda _resultado: None,
        ao_atualizar_geometria=lambda: None,
    )

    assert input_items == [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "estado pronto"}],
        },
        {
            "type": "function_call_output",
            "call_id": "c1",
            "output": "ok",
        },
    ]
    assert estado_enviado == "estado pronto"


def test_preparacao_preserva_imagem_e_geometria_da_rodada():
    resposta = SimpleNamespace(output=[])
    resultados = [{"call_id": "c1", "resultado": "ok"}]
    imagem = [{"type": "input_image", "image_url": "data:image/png;base64,x"}]
    atualizacoes = []

    input_items, estado_enviado = _montar_input_e_estado_da_rodada(
        "objetivo",
        [],
        resposta,
        resultados,
        montar_estado=lambda *_args, **_kwargs: "estado",
        preparar_resultado_visual=lambda _resultado: (imagem, True),
        ao_atualizar_geometria=lambda: atualizacoes.append(True),
    )

    assert input_items[-1] == {"role": "user", "content": imagem}
    assert estado_enviado == "estado"
    assert atualizacoes == [True]


def test_estado_enviado_pode_ser_vazio_sem_alterar_o_input():
    resposta = SimpleNamespace(output=[])
    input_items, estado_enviado = _montar_input_e_estado_da_rodada(
        "objetivo",
        [],
        resposta,
        [],
        montar_estado=lambda *_args, **_kwargs: "",
        preparar_resultado_visual=lambda _resultado: None,
        ao_atualizar_geometria=lambda: None,
    )
    assert input_items[0]["content"][0]["text"] == ""
    assert estado_enviado == ""
