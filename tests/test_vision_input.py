"""Testes do formato multimodal usado pelo Harness na Responses API."""
from __future__ import annotations

from types import SimpleNamespace

from core.harness import AurenHarness


def _harness() -> AurenHarness:
    return AurenHarness(
        criar_resposta=lambda *_args, **_kwargs: None,
        executar_ferramenta=lambda _item: "ok",
        mostrar_uso=lambda: None,
        obter_chamadas=lambda _resposta: [],
        comando_rapido=lambda _mensagem: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
    )


def test_imagem_da_tool_e_enviada_dentro_de_mensagem_de_usuario(tmp_path):
    imagem = tmp_path / "screen.png"
    imagem.write_bytes(b"png-test")

    resposta_anterior = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                call_id="call-1",
                name="capturar_tela_windows",
                arguments="{}",
            )
        ]
    )
    resultados = [
        {
            "call_id": "call-1",
            "ferramenta": "capturar_tela_windows",
            "argumentos": "{}",
            "resultado": "Tela capturada.",
            "image_path": str(imagem),
        }
    ]

    entrada = _harness()._montar_input_da_rodada(
        "analise minha tela",
        [],
        resposta_anterior,
        resultados,
    )

    assert entrada[0]["role"] == "user"
    assert entrada[1].type == "function_call"
    assert entrada[2]["type"] == "function_call_output"

    mensagens_com_imagem = [
        item
        for item in entrada
        if isinstance(item, dict)
        and item.get("role") == "user"
        and isinstance(item.get("content"), list)
        and any(
            isinstance(parte, dict) and parte.get("type") == "input_image"
            for parte in item["content"]
        )
    ]
    assert len(mensagens_com_imagem) == 1

    imagem_message = mensagens_com_imagem[0]
    image_parts = [
        parte
        for parte in imagem_message["content"]
        if parte.get("type") == "input_image"
    ]
    assert len(image_parts) == 1
    assert image_parts[0]["image_url"].startswith("data:image/png;base64,")

    assert not any(
        isinstance(item, dict) and item.get("type") == "input_image"
        for item in entrada
    )
