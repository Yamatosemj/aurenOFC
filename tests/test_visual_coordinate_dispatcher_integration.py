"""Integracao da origem visual ate a execucao Windows pelo Dispatcher."""
from __future__ import annotations

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


class _FakeConfirmation:
    """Aprova somente handlers simulados pelos testes, sem entrada real."""

    def confirmar(self, _request):
        return True


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
        PermissionManager(max_actions=50, confirmation_channel=_FakeConfirmation()),
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


def test_visao_integrada_origem_negativa_e_arraste(monkeypatch, tmp_path):
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
        PermissionManager(max_actions=50, confirmation_channel=_FakeConfirmation()),
        None,
    )

    assert result.ok is True
    assert chamadas[0]["x_inicial"] == -1440
    assert chamadas[0]["y_inicial"] == -30
    assert chamadas[0]["x_final"] == -960
    assert chamadas[0]["y_final"] == 240
    assert result.data["vision_coordinate_transform"]["snapshot_id"] == geometry["vision_snapshot_id"]


def test_coordenadas_windows_diretas_nao_sao_transformadas(monkeypatch, tmp_path):
    _set_geometry(tmp_path)
    chamadas = []

    def fake_handler(args, _memory, _context):
        chamadas.append(dict(args))
        return ToolResult.success("clique direto")

    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "clicar_mouse_windows", fake_handler)

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
        PermissionManager(max_actions=50, confirmation_channel=_FakeConfirmation()),
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

    pm = PermissionManager(max_actions=50, confirmation_channel=_FakeConfirmation())
    original = pm.autorizar

    def observar_autorizacao(nome, args):
        autorizacoes.append((nome, dict(args)))
        return original(nome, args)

    pm.autorizar = observar_autorizacao

    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "clicar_mouse_windows", fake_handler)

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


def test_harness_exige_nova_observacao_apos_acao_visual(monkeypatch, tmp_path):
    from core.harness import AurenHarness
    from core.task_manager import TaskManager

    image_path = _png(tmp_path, "screen.png", (960, 540))
    calls = []
    pm = PermissionManager(max_actions=50, confirmation_channel=_FakeConfirmation())

    def fake_capture(_args, _memory, _context):
        calls.append(("captura", None))
        return ToolResult.success(
            "Tela capturada.",
            data={
                "image_path": image_path,
                "image_width": 960,
                "image_height": 540,
                "virtual_screen_x": 0,
                "virtual_screen_y": 0,
                "virtual_screen_width": 1920,
                "virtual_screen_height": 1080,
                "dpi_per_monitor_aware": True,
            },
        )

    def fake_click(args, _memory, _context):
        calls.append(("clique", dict(args)))
        return ToolResult.success("clique executado")

    monkeypatch.setitem(
        dispatcher.TOOL_HANDLERS,
        "capturar_tela_windows",
        fake_capture,
    )
    monkeypatch.setitem(
        dispatcher.TOOL_HANDLERS,
        "clicar_mouse_windows",
        fake_click,
    )

    capture_call = lambda n: SimpleNamespace(
        type="function_call",
        name="capturar_tela_windows",
        arguments="{}",
        call_id=f"capture-{n}",
    )

    def model_response(n, _bench):
        if n == 1:
            return SimpleNamespace(output=[capture_call(1)], output_text="")
        if n == 2:
            return SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="clicar_mouse_windows",
                        arguments=json.dumps({
                            "x": 480,
                            "y": 270,
                            "botao": "esquerdo",
                            "descricao": "botao visual",
                            "coordinate_space": "vision_image",
                            "vision_snapshot_id": "screen",
                        }),
                        call_id="click-1",
                    )
                ],
                output_text="",
            )
        if n == 3:
            # O snapshot anterior foi invalidado pelo clique. Tentar reutiliza-lo
            # deve falhar no Dispatcher, antes da permissao/execucao.
            return SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="clicar_mouse_windows",
                        arguments=json.dumps({
                            "x": 500,
                            "y": 280,
                            "botao": "esquerdo",
                            "descricao": "segundo botao visual",
                            "coordinate_space": "vision_image",
                            "vision_snapshot_id": "screen",
                        }),
                        call_id="click-2",
                    )
                ],
                output_text="",
            )
        if n == 4:
            return SimpleNamespace(output=[capture_call(2)], output_text="")
        return SimpleNamespace(output=[], output_text="ok")

    def provider(input_items, response_id=None, reasoning="none", tool_choice=None):
        return model_response(provider.calls + 1, None)
    provider.calls = 0

    def counted_provider(input_items, response_id=None, reasoning="none", tool_choice=None):
        provider.calls += 1
        return model_response(provider.calls, None)

    harness = AurenHarness(
        criar_resposta=counted_provider,
        executar_ferramenta=lambda item: dispatcher.executar_ferramenta(item, pm, None),
        mostrar_uso=lambda: None,
        obter_chamadas=lambda response: [
            item for item in response.output
            if getattr(item, "type", "") == "function_call"
        ],
        comando_rapido=lambda _mensagem: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        task_manager=TaskManager(),
    )

    tratado, resposta = harness.processar_mensagem("analise minha tela e clique no botao depois confirme")
    snapshot = harness.task_manager.current_snapshot()

    assert tratado is False
    # A segunda tentativa usa um snapshot invalidado e e rejeitada. Uma
    # recaptura posterior nao reexecuta nem repara esse clique: a tarefa
    # inteira nao pode terminar como "completed" apenas por ler a tela.
    assert "etapa falhou sem recuperacao" in resposta.output_text
    assert snapshot is not None
    assert snapshot.state.value == "failed"
    assert snapshot.error == "step_failed_unrecovered"
    assert provider.calls == 5

    cliques = [item for item in calls if item[0] == "clique"]
    capturas = [item for item in calls if item[0] == "captura"]
    assert len(cliques) == 1
    assert len(capturas) == 2
    assert cliques[0][1]["x"] == 960
    assert cliques[0][1]["y"] == 540
    assert all(
        step.success
        for step in snapshot.steps
        if step.tool == "capturar_tela_windows"
    )


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
        PermissionManager(max_actions=50, confirmation_channel=_FakeConfirmation()),
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
        PermissionManager(max_actions=50, confirmation_channel=_FakeConfirmation()),
        None,
    )

    assert result.ok is False
    assert result.error_code == "vision_coordinate_rejected"
    assert chamadas == []


@pytest.fixture(autouse=True)
def _limpar_snapshot_visual():
    yield
    clear_active_vision_geometry()



@pytest.mark.parametrize("ok", [True, False])
def test_visual_transform_preserves_untrusted_provenance(monkeypatch, tmp_path, ok):
    """Anexar geometria nao pode apagar origem externa nem codigo de erro."""
    geometry = _set_geometry(tmp_path)

    def fake_handler(_args, _memory, _context):
        fields = {
            "data": {"evidencia": "conteudo externo"},
            "tool_name": "clicar_mouse_windows",
            "conteudo_nao_confiavel": True,
        }
        if ok:
            return ToolResult.success("retorno externo", **fields)
        return ToolResult.failure(
            "retorno externo falhou", error_code="external_failure", **fields,
        )

    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "clicar_mouse_windows", fake_handler)

    result = dispatcher.executar_ferramenta(
        _item(
            "clicar_mouse_windows",
            {
                "x": 100,
                "y": 120,
                "botao": "esquerdo",
                "descricao": "teste de proveniencia",
                "coordinate_space": "vision_image",
                "vision_snapshot_id": geometry["vision_snapshot_id"],
            },
        ),
        PermissionManager(max_actions=10, confirmation_channel=_FakeConfirmation()),
        None,
    )

    assert result.ok is ok
    assert result.error_code == (None if ok else "external_failure")
    assert result.conteudo_nao_confiavel is True
    assert result.data["evidencia"] == "conteudo externo"
    assert result.data["vision_coordinate_transform"]["snapshot_id"] == geometry["vision_snapshot_id"]
    assert json.loads(result.for_model())["conteudo_nao_confiavel"] is True
    assert result.as_dict()["conteudo_nao_confiavel"] is True
