import ast
import inspect
from types import SimpleNamespace

from core.permission_manager import PermissionManager
from core.tool_result import ToolResult, from_legacy
import tools.dispatcher as dispatcher
import tools.applications as applications
import tools.files as files
import tools.memory as memory_tools
import tools.browser_reading as browser_reading
import tools.windows_audio as windows_audio
import tools.windows_clipboard as windows_clipboard
import tools.windows_input as windows_input
import tools.windows_processes as windows_processes
import tools.windows_system as windows_system
import tools.windows_uia as windows_uia
import tools.windows_window as windows_window


def test_structured_success_has_explicit_state():
    result = ToolResult.success("Volume definido.", data={"percentual": 37})
    assert result.ok is True
    assert result.error_code is None
    assert '"ok":true' in result.for_model()
    assert str(result) == result.for_model()


def test_structured_failure_never_depends_on_error_text():
    result = ToolResult.failure("PID invalido.", error_code="pid_invalid")
    assert result.ok is False
    assert result.error_code == "pid_invalid"
    assert '"codigo_erro":"pid_invalid"' in result.for_model()


def test_legacy_missing_error_marker_is_still_caught():
    result = from_legacy("PID invalido. Informe um PID maior que zero.")
    assert result.ok is False
    assert result.error_code == "legacy_text_error"


def test_dispatcher_uses_structured_tool_result_for_permission_accounting(monkeypatch):
    manager = PermissionManager(max_actions=10)
    item = SimpleNamespace(
        name="mover_mouse_windows",
        arguments='{"x":960,"y":540}',
    )

    monkeypatch.setitem(
        dispatcher.TOOL_HANDLERS,
        "mover_mouse_windows",
        lambda args, memory, context: ToolResult.failure(
            "Coordenadas rejeitadas.",
            error_code="coordinates_rejected",
            tool_name="mover_mouse_windows",
        ),
    )

    result = dispatcher.executar_ferramenta(item, manager, None)

    assert result.ok is False
    assert manager.actions_failed == 1
    assert manager.actions_executed == 0


def test_migrated_dispatcher_tools_return_toolresult_directly():
    functions = [
        applications.abrir_programa,
        files.buscar_arquivo,
        memory_tools.salvar_memoria_persistente,
        memory_tools.consultar_memoria_persistente,
        memory_tools.esquecer_memoria_persistente,
        browser_reading.ler_pagina,
        windows_audio.obter_audio_windows,
        windows_audio.definir_volume_windows,
        windows_audio.definir_mudo_windows,
        windows_clipboard.ler_area_transferencia_windows,
        windows_clipboard.definir_area_transferencia_windows,
        windows_input.controle_midia_windows,
        windows_input.pressionar_tecla_windows,
        windows_input.mover_mouse_windows,
        windows_input.clicar_mouse_windows,
        windows_input.arrastar_mouse_windows,
        windows_processes.listar_processos_windows,
        windows_processes.encerrar_processo_windows,
        windows_system.obter_status_windows,
        windows_uia.inspecionar_interface_windows,
        windows_uia.clicar_elemento_windows,
        windows_uia.preencher_elemento_windows,
        windows_uia.alternar_elemento_windows,
        windows_uia.selecionar_elemento_windows,
        windows_window.listar_janelas_windows,
        windows_window.focar_janela_windows,
        windows_window.minimizar_janela_windows,
        windows_window.maximizar_janela_windows,
        windows_window.obter_geometria_janela_windows,
        windows_window.mover_janela_windows,
        windows_window.redimensionar_janela_windows,
        windows_window.restaurar_janela_windows,
        windows_window.fechar_janela_windows,
    ]

    for function in functions:
        tree = ast.parse(inspect.getsource(function))
        root = tree.body[0]
        direct_returns = []

        def collect_direct_returns(node):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    continue
                if isinstance(child, ast.Return):
                    direct_returns.append(child.value)
                    continue
                collect_direct_returns(child)

        collect_direct_returns(root)
        assert direct_returns, function.__name__
        assert all(
            isinstance(value, ast.Call)
            and (
                (
                    isinstance(value.func, ast.Attribute)
                    and isinstance(value.func.value, ast.Name)
                    and value.func.value.id == "ToolResult"
                    and value.func.attr in {"success", "failure"}
                )
                or (
                    isinstance(value.func, ast.Name)
                    and value.func.id in {"_resultado_memoria", "_executar_acao_ui_windows"}
                )
            )
            for value in direct_returns
        ), function.__name__


def test_memory_tool_preserves_legacy_json_message_while_structuring_state():
    class FakeStore:
        def salvar(self, *args):
            return {"ok": False, "erro": "falha controlada"}

        def consultar(self, *args):
            return {"ok": True, "total": 0, "memorias": []}

        def esquecer(self, *args):
            return {"ok": True, "chave": "x"}

    failure = memory_tools.salvar_memoria_persistente(FakeStore(), "x", "y")
    success = memory_tools.consultar_memoria_persistente(FakeStore(), "x")
    assert failure.ok is False
    assert failure.error_code == "memory_error"
    assert failure.message == '{"ok":false,"erro":"falha controlada"}'
    assert success.ok is True
    assert success.message == '{"ok":true,"total":0,"memorias":[]}'
