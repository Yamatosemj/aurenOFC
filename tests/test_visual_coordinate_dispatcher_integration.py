"""Integracao da origem visual ate a execucao Windows pelo Dispatcher."""
from __future__ import annotations

import builtins
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import tools.dispatcher as dispatcher
from core.permission_manager import PermissionManager
from core.tool_result import ToolResult
from core.vision import (
    build_vision_geometry,
    clear_active_vision_geometry,
    prepare_image_input,
    set_active_vision_geometry,
)


def _item(nome: str, argumentos: dict) -> SimpleNamespace:
    return SimpleNamespace(
        name=nome,
        arguments=json.dumps(argumentos),
        call_id=f"call-{nome}",
    )


def _png(tmp_path: Path, name: str, size: tuple[int, int]) -> str:
    path = tmp_path / name
    Image.new("RGB", size, (40, 80, 120)).save(path, format="PNG")
    return str(path)


def _set_geometry(
    tmp_path: Path,
    *,
    source_size: tuple[int, int] = (960, 540),
    virtual: tuple[int, int, int, int] = (0, 0, 1920, 1080),
    dpi_per_monitor_aware: bool = True,
) -> dict:
    image_path = _png(tmp_path, "screen.png", source_size)
    prepared = prepare_image_input(image_path, preserve_dimensions=True)
    assert prepared is not None
    capture = {
        "image_path": image_path,
        "image_width": source_size[0],
        "image_height": source_size[1],
        "virtual_screen_x": virtual[0],
        "virtual_screen_y": virtual[1],
        "virtual_screen_width": virtual[2],
        "virtual_screen_height": virtual[3],
        "dpi_per_monitor_aware": dpi_per_monitor_aware,
    }
    geometry = build_vision_geometry(capture, prepared)
    assert geometry is not None
    set_active_vision_geometry(geometry)
    return geometry


def test_visao_integrada_imagem_ate_clique_no_windows(monkeypatch, tmp_path):
    geometry = _set_geometry(
        tmp_path,
        source_size=(960, 540),
        virtual=(0, 0, 1920, 1080),
    )
    chamadas = []

    def fake_handler(args, _memory, _context):
        chamadas.append(dict(args))
        return ToolResult.success("clique executado")

    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "clicar_mouse_windows", fake_handler)
    monkeypatch.setattr(builtins, "input", lambda *_: "s")

    result = dispatcher.executar_ferramenta(
        _item(
            "clicar_mouse_windows",
            {
                "x": 480,
                "y": 270,
                "botao": "esquerdo",
                "descricao": "botao visual",
                "coordinate_space": "vision_image",
                "vision_snapshot_id": geometry["vision_snapshot_id"],
            },
        ),
        PermissionManager(max_actions=50),
        None,
    )

    assert result.ok is True
    assert chamadas == [
        {
            "x": 960,
            "y": 540,
            "botao": "esquerdo",
            "descricao": "botao visual",
            "coordinate_space": "windows",
        }
    ]
    assert result.data["vision_coordinate_transform"]["pontos"]["destino_windows"] == {
        "x": 960,
        "y": 540,
    }


def test_visao_integrada_resize_origem_negativa_e_arraste(monkeypatch, tmp_path):
    geometry = _set_geometry(
        tmp_path,
        source_size=(1920, 1080),
        virtual=(-1920, -300, 1920, 1080),
    )
    chamadas = []

    def fake_handler(args, _memory, _context):
        chamadas.append(dict(args))
        return ToolResult.success("arraste executado")

    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "arrastar_mouse_windows", fake_handler)
    monkeypatch.setattr(builtins, "input", lambda *_: "s")

    result = dispatcher.executar_ferramenta(
        _item(
            "arrastar_mouse_windows",
            {
                "x_inicial": 480,
                "y_inicial": 270,
                "x_final": 960,
                "y_final": 540,
                "botao": "esquerdo",
                "duracao_ms": 50,
                "descricao": "arraste visual",
                "coordinate_space": "vision_image",
                "vision_snapshot_id": geometry["vision_snapshot_id"],
            },
        ),
        PermissionManager(max_actions=50),
        None,
    )

    assert result.ok is True
    assert chamadas[0]["x_inicial"] == -960
    assert chamadas[0]["y_inicial"] == 240
    assert chamadas[0]["x_final"] == 0
    assert chamadas[0]["y_final"] == 780
    assert result.data["vision_coordinate_transform"]["snapshot_id"] == geometry["vision_snapshot_id"]


def test_coordenadas_windows_diretas_nao_sao_transformadas(monkeypatch, tmp_path):
    _set_geometry(tmp_path)
    chamadas = []

    def fake_handler(args, _memory, _context):
        chamadas.append(dict(args))
        return ToolResult.success("clique direto")

    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "clicar_mouse_windows", fake_handler)
    monkeypatch.setattr(builtins, "input", lambda *_: "s")

    result = dispatcher.executar_ferramenta(
        _item(
            "clicar_mouse_windows",
            {
                "x": 100,
                "y": 200,
                "botao": "esquerdo",
                "descricao": "coordenada windows explicita",
                "coordinate_space": "windows",
            },
        ),
        PermissionManager(max_actions=50),
        None,
    )

    assert result.ok is True
    assert chamadas == [
        {
            "x": 100,
            "y": 200,
            "botao": "esquerdo",
            "descricao": "coordenada windows explicita",
            "coordinate_space": "windows",
        }
    ]


def test_snapshot_antigo_e_rejeitado_antes_da_permissao(monkeypatch, tmp_path):
    geometry = _set_geometry(tmp_path)
    chamadas = []
    autorizacoes = []

    def fake_handler(args, _memory, _context):
        chamadas.append(dict(args))
        return ToolResult.success("nao deveria executar")

    pm = PermissionManager(max_actions=50)
    original = pm.autorizar

    def observar_autorizacao(nome, args):
        autorizacoes.append((nome, dict(args)))
        return original(nome, args)

    pm.autorizar = observar_autorizacao

    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "clicar_mouse_windows", fake_handler)
    monkeypatch.setattr(builtins, "input", lambda *_: "s")

    result = dispatcher.executar_ferramenta(
        _item(
            "clicar_mouse_windows",
            {
                "x": 100,
                "y": 100,
                "botao": "esquerdo",
                "descricao": "snapshot antigo",
                "coordinate_space": "vision_image",
                "vision_snapshot_id": geometry["vision_snapshot_id"] + "-old",
            },
        ),
        pm,
        None,
    )

    assert result.ok is False
    assert result.error_code == "vision_coordinate_rejected"
    assert chamadas == []
    assert autorizacoes == []


def test_geometria_sem_dpi_verificado_nao_pode_clicar(monkeypatch, tmp_path):
    geometry = _set_geometry(
        tmp_path,
        dpi_per_monitor_aware=False,
    )
    chamadas = []

    monkeypatch.setitem(
        dispatcher.TOOL_HANDLERS,
        "clicar_mouse_windows",
        lambda args, _memory, _context: chamadas.append(dict(args))
        or ToolResult.success("nao deveria executar"),
    )
    monkeypatch.setattr(builtins, "input", lambda *_: "s")

    result = dispatcher.executar_ferramenta(
        _item(
            "clicar_mouse_windows",
            {
                "x": 10,
                "y": 10,
                "botao": "esquerdo",
                "descricao": "dpi inseguro",
                "coordinate_space": "vision_image",
                "vision_snapshot_id": geometry["vision_snapshot_id"],
            },
        ),
        PermissionManager(max_actions=50),
        None,
    )

    assert result.ok is False
    assert result.error_code == "vision_coordinate_rejected"
    assert chamadas == []


def test_coordenada_visual_fora_da_imagem_e_rejeitada_antes_da_execucao(
    monkeypatch,
    tmp_path,
):
    geometry = _set_geometry(tmp_path)
    chamadas = []
    monkeypatch.setitem(
        dispatcher.TOOL_HANDLERS,
        "clicar_mouse_windows",
        lambda args, _memory, _context: chamadas.append(dict(args))
        or ToolResult.success("nao deveria executar"),
    )

    result = dispatcher.executar_ferramenta(
        _item(
            "clicar_mouse_windows",
            {
                "x": 960,
                "y": 540,
                "botao": "esquerdo",
                "descricao": "fora da imagem",
                "coordinate_space": "vision_image",
                "vision_snapshot_id": geometry["vision_snapshot_id"],
            },
        ),
        PermissionManager(max_actions=50),
        None,
    )

    assert result.ok is False
    assert result.error_code == "vision_coordinate_rejected"
    assert chamadas == []


@pytest.fixture(autouse=True)
def _limpar_snapshot_visual():
    yield
    clear_active_vision_geometry()
