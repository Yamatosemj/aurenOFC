import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from core.permission_manager import PermissionManager
from core.tool_result import ToolResult
from core.undo import MAX_DEPTH, can_undo, clear, history, peek, push_undo, undo_last
from tools import dispatcher
from tools import windows_audio
from tools.undo import desfazer_ultima_acao


@pytest.fixture(autouse=True)
def limpar_undo():
    clear()
    yield
    clear()


def test_undo_lifo():
    efeitos = []
    push_undo("primeiro", lambda: efeitos.append("primeiro"))
    push_undo("segundo", lambda: efeitos.append("segundo"))

    resultado = undo_last()

    assert resultado.ok is True
    assert resultado.label == "segundo"
    assert efeitos == ["segundo"]
    assert history() == ["primeiro"]


def test_undo_11th_entry_discards_oldest():
    for indice in range(MAX_DEPTH + 1):
        push_undo(f"acao-{indice}", lambda: None)

    assert len(history()) == MAX_DEPTH
    assert "acao-0" not in history()
    assert history()[0] == f"acao-{MAX_DEPTH}"


def test_two_threads_can_push_without_corrupting_stack():
    barreira = threading.Barrier(2)

    def trabalhador(prefixo):
        barreira.wait()
        for indice in range(8):
            push_undo(f"{prefixo}-{indice}", lambda: None)

    threads = [
        threading.Thread(target=trabalhador, args=("A",)),
        threading.Thread(target=trabalhador, args=("B",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    trilha = history()
    assert len(trilha) == MAX_DEPTH
    assert all(item.startswith(("A-", "B-")) for item in trilha)


def test_failed_undo_preserves_entry_for_retry():
    tentativas = {"n": 0}

    def quebrar():
        tentativas["n"] += 1
        return ToolResult.failure(
            "estado original nao pode ser reaplicado",
            error_code="restore_failed",
        )

    push_undo("volume para 60%", quebrar)

    resultado = undo_last()

    assert resultado.status == "failed"
    assert resultado.error_code == "restore_failed"
    assert peek() == "volume para 60%"
    assert tentativas["n"] == 1
    assert can_undo() is True


def test_undo_entry_keeps_timestamp():
    push_undo("com horario", lambda: None)

    resultado = undo_last()

    assert resultado.ok is True
    assert resultado.at is not None
    assert resultado.at.tzinfo is not None


def test_volume_30_to_60_then_dispatcher_undo_returns_to_30(monkeypatch):
    estado = {"volume": 30, "mudo": False}

    def ler_audio():
        return ToolResult.success(
            "audio",
            data={"percentual": estado["volume"], "mudo": estado["mudo"]},
            tool_name="obter_audio_windows",
        )

    def aplicar_volume(percentual):
        estado["volume"] = percentual
        return ToolResult.success(
            f"Volume definido para {percentual}%.",
            tool_name="definir_volume_windows",
        )

    monkeypatch.setattr(windows_audio.os, "name", "nt")
    monkeypatch.setattr(windows_audio, "obter_audio_windows", ler_audio)
    monkeypatch.setattr(windows_audio, "_aplicar_volume_windows", aplicar_volume)

    class Item:
        def __init__(self, name, arguments):
            self.name = name
            self.arguments = arguments

    permission = PermissionManager()
    permission.iniciar_tarefa()

    definido = dispatcher.executar_ferramenta(
        Item("definir_volume_windows", '{"percentual": 60}'),
        permission,
        None,
    )
    assert definido.ok is True
    assert estado["volume"] == 60

    desfeito = dispatcher.executar_ferramenta(
        Item("desfazer_ultima_acao", "{}"),
        permission,
        None,
    )
    assert desfeito.ok is True
    assert estado["volume"] == 30
    assert desfeito.data["acao"] == "volume para 60%"


def test_mute_undo_restores_previous_state(monkeypatch):
    estado = {"volume": 30, "mudo": False}

    def ler_audio():
        return ToolResult.success(
            "audio",
            data=estado.copy(),
            tool_name="obter_audio_windows",
        )

    def aplicar_mudo(ativado):
        estado["mudo"] = ativado
        return ToolResult.success(
            f"Mudo {'ativado' if ativado else 'desativado'}.",
            tool_name="definir_mudo_windows",
        )

    monkeypatch.setattr(windows_audio.os, "name", "nt")
    monkeypatch.setattr(windows_audio, "obter_audio_windows", ler_audio)
    monkeypatch.setattr(windows_audio, "_aplicar_mudo_windows", aplicar_mudo)

    resultado = windows_audio.definir_mudo_windows(True)

    assert resultado.ok is True
    assert estado["mudo"] is True
    assert undo_last().ok is True
    assert estado["mudo"] is False


def test_previous_audio_value_missing_means_no_undo_registration(monkeypatch):
    def leitura_sem_estado():
        return ToolResult.success("audio sem dados", tool_name="obter_audio_windows")

    monkeypatch.setattr(windows_audio.os, "name", "nt")
    monkeypatch.setattr(windows_audio, "obter_audio_windows", leitura_sem_estado)
    monkeypatch.setattr(
        windows_audio,
        "_aplicar_volume_windows",
        lambda percentual: ToolResult.success("volume alterado", tool_name="definir_volume_windows"),
    )

    resultado = windows_audio.definir_volume_windows(60)

    assert resultado.ok is True
    assert can_undo() is False


def test_read_failure_means_no_undo_registration(monkeypatch):
    def leitura_falha():
        return ToolResult.failure(
            "falha de leitura",
            error_code="audio_read_failed",
            tool_name="obter_audio_windows",
        )

    monkeypatch.setattr(windows_audio.os, "name", "nt")
    monkeypatch.setattr(windows_audio, "obter_audio_windows", leitura_falha)
    monkeypatch.setattr(
        windows_audio,
        "_aplicar_mudo_windows",
        lambda ativado: ToolResult.success("mudo alterado", tool_name="definir_mudo_windows"),
    )

    resultado = windows_audio.definir_mudo_windows(True)

    assert resultado.ok is True
    assert can_undo() is False


def test_undo_tool_empty_returns_structured_tool_result():
    resultado = desfazer_ultima_acao()

    assert isinstance(resultado, ToolResult)
    assert resultado.ok is True
    assert resultado.data["desfeito"] is False


def test_undo_tool_failure_is_structured_and_preserves_entry():
    push_undo(
        "acao quebrada",
        lambda: ToolResult.failure(
            "nao foi possivel restaurar",
            error_code="restore_failed",
        ),
    )

    resultado = desfazer_ultima_acao()

    assert resultado.ok is False
    assert resultado.error_code == "restore_failed"
    assert resultado.data["preservada_em_falha"] is True
    assert peek() == "acao quebrada"


def test_registry_handlers_still_validate():
    ok, motivo = dispatcher.validar_registry_handlers()
    assert ok is True
    assert motivo == ""


def test_undo_uses_registered_capability_and_auto_permission():
    manager = PermissionManager(max_actions=2)
    assert manager.capability("desfazer_ultima_acao") == "undo.control"

    nivel, _ = manager.nivel_da_acao("desfazer_ultima_acao", {})
    assert nivel.value == "auto"

    permitido, _ = manager.autorizar("desfazer_ultima_acao", {})
    assert permitido is True
    assert manager.actions_attempted == 1
