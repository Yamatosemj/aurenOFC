"""Testes da geometria multimodal usada pelo Harness e pela visao."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from core.harness import AurenHarness
from core.vision import (
    image_point_to_virtual_screen,
    build_vision_geometry,
    prepare_image_input,
)


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


def _png(tmp_path, name: str, size: tuple[int, int]) -> str:
    path = tmp_path / name
    image = Image.new("RGB", size, (80, 120, 160))
    image.save(path, format="PNG")
    return str(path)


def test_imagem_da_tool_e_enviada_dentro_de_mensagem_de_usuario(tmp_path):
    imagem = _png(tmp_path, "screen.png", (10, 10))

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
            "image_path": imagem,
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


def test_preparacao_preserva_dimensoes_quando_imagem_cabe_no_limite(tmp_path):
    imagem = _png(tmp_path, "screen.png", (1920, 1080))

    preparada = prepare_image_input(
        imagem,
        preserve_dimensions=True,
    )

    assert preparada is not None
    assert preparada.source_width == 1920
    assert preparada.source_height == 1080
    assert preparada.sent_width == 1920
    assert preparada.sent_height == 1080
    assert preparada.resized is False


def test_preparacao_registra_resize_quando_limite_exige_reducao(tmp_path):
    imagem = tmp_path / "screen-noisy.png"
    source = Image.effect_noise((2560, 1440), 100)
    source.save(imagem, format="PNG")

    preparada = prepare_image_input(
        imagem,
        max_bytes=3_000_000,
        max_width=1920,
        preserve_dimensions=False,
    )

    assert preparada is not None
    assert preparada.source_width == 2560
    assert preparada.source_height == 1440
    assert preparada.sent_width == 1920
    assert preparada.sent_height == 1080
    assert preparada.resized is True
    assert preparada.scale_x_to_source == pytest.approx(2560 / 1920)
    assert preparada.scale_y_to_source == pytest.approx(1440 / 1080)


def test_transformacao_identity_1920x1080():
    assert image_point_to_virtual_screen(
        123,
        456,
        image_width=1920,
        image_height=1080,
        virtual_screen_x=0,
        virtual_screen_y=0,
        virtual_screen_width=1920,
        virtual_screen_height=1080,
    ) == (123, 456)


def test_transformacao_de_imagem_960x540_para_tela_1920x1080():
    assert image_point_to_virtual_screen(
        480,
        270,
        image_width=960,
        image_height=540,
        virtual_screen_x=0,
        virtual_screen_y=0,
        virtual_screen_width=1920,
        virtual_screen_height=1080,
    ) == (960, 540)


def test_transformacao_de_imagem_1920x1080_para_tela_2560x1440():
    assert image_point_to_virtual_screen(
        480,
        270,
        image_width=1920,
        image_height=1080,
        virtual_screen_x=0,
        virtual_screen_y=0,
        virtual_screen_width=2560,
        virtual_screen_height=1440,
    ) == (640, 360)


def test_transformacao_respeita_origem_x_negativa():
    assert image_point_to_virtual_screen(
        960,
        540,
        image_width=1920,
        image_height=1080,
        virtual_screen_x=-1920,
        virtual_screen_y=0,
        virtual_screen_width=3840,
        virtual_screen_height=1080,
    ) == (0, 540)


def test_transformacao_respeita_origem_y_negativa():
    assert image_point_to_virtual_screen(
        960,
        540,
        image_width=1920,
        image_height=1080,
        virtual_screen_x=0,
        virtual_screen_y=-900,
        virtual_screen_width=1920,
        virtual_screen_height=1080,
    ) == (960, -450)


def test_transformacao_respeita_origem_x_e_y_diferentes_de_zero():
    assert image_point_to_virtual_screen(
        250,
        125,
        image_width=1000,
        image_height=500,
        virtual_screen_x=100,
        virtual_screen_y=200,
        virtual_screen_width=2000,
        virtual_screen_height=1000,
    ) == (600, 450)


def test_transformacao_rejeita_aspect_ratio_incompativel():
    with pytest.raises(ValueError, match="proporcao"):
        image_point_to_virtual_screen(
            100,
            100,
            image_width=1000,
            image_height=500,
            virtual_screen_x=0,
            virtual_screen_y=0,
            virtual_screen_width=1920,
            virtual_screen_height=1080,
        )


def test_transformacao_rejeita_coordenada_fora_da_imagem():
    with pytest.raises(ValueError, match="fora dos limites"):
        image_point_to_virtual_screen(
            1000,
            100,
            image_width=1000,
            image_height=500,
            virtual_screen_x=0,
            virtual_screen_y=0,
            virtual_screen_width=1920,
            virtual_screen_height=960,
        )


def test_geometry_metadata_explica_mapeamento_para_o_modelo():
    from core.vision import PreparedImageInput

    preparada = PreparedImageInput(
        item={"type": "input_image", "image_url": "data:image/png;base64,AA=="},
        source_width=2560,
        source_height=1440,
        sent_width=1920,
        sent_height=1080,
        mime_type="image/png",
        resized=True,
        compressed=True,
    )

    geometria = build_vision_geometry(
        {
            "virtual_screen_x": -1920,
            "virtual_screen_y": 0,
            "virtual_screen_width": 3840,
            "virtual_screen_height": 2160,
        },
        preparada,
    )

    assert geometria is not None
    assert geometria["coordenadas_acao"] == "windows_virtual_screen"
    assert geometria["imagem_enviada_ao_modelo"] == {"width": 1920, "height": 1080}
    assert geometria["escala_imagem_para_windows"]["x"] == pytest.approx(2.0)
    assert geometria["escala_imagem_para_windows"]["y"] == pytest.approx(1.0)
    assert geometria["area_de_trabalho_virtual_windows"]["x"] == -1920


def test_harness_transporta_geometria_da_imagem_enviada(tmp_path):
    imagem = _png(tmp_path, "screen.png", (960, 540))
    resposta_anterior = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                call_id="call-geometry",
                name="capturar_tela_windows",
                arguments="{}",
            )
        ]
    )
    resultados = [
        {
            "call_id": "call-geometry",
            "ferramenta": "capturar_tela_windows",
            "argumentos": "{}",
            "resultado": "Tela capturada.",
            "image_path": imagem,
            "dados": {
                "virtual_screen_x": 0,
                "virtual_screen_y": 0,
                "virtual_screen_width": 1920,
                "virtual_screen_height": 1080,
                "image_width": 960,
                "image_height": 540,
            },
        }
    ]

    entrada = _harness()._montar_input_da_rodada(
        "analise minha tela",
        [],
        resposta_anterior,
        resultados,
    )

    mensagens = [
        item
        for item in entrada
        if isinstance(item, dict)
        and item.get("role") == "user"
        and isinstance(item.get("content"), list)
        and any(
            parte.get("type") == "input_text"
            and "vision_geometry" in str(parte.get("text"))
            for parte in item["content"]
            if isinstance(parte, dict)
        )
    ]
    assert len(mensagens) == 1
    texto = str(mensagens[0]["content"][0]["text"])
    assert '"width":960' in texto
    assert '"height":540' in texto
    assert '"x":1920' in texto


def test_harness_nao_muda_o_contrato_de_imagem_sem_geometria(tmp_path):
    imagem = _png(tmp_path, "screen-sem-geometria.png", (2, 2))
    resposta_anterior = SimpleNamespace(output=[])
    entrada = _harness()._montar_input_da_rodada(
        "analise minha tela",
        [],
        resposta_anterior,
        [
            {
                "call_id": "c",
                "ferramenta": "alguma_tool",
                "argumentos": "{}",
                "resultado": "ok",
                "image_path": imagem,
            }
        ],
    )
    assert any(
        isinstance(item, dict)
        and item.get("role") == "user"
        and isinstance(item.get("content"), list)
        and any(part.get("type") == "input_image" for part in item["content"] if isinstance(part, dict))
        for item in entrada
    )
