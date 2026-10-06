from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.harness import AurenHarness
from core.task_manager import TaskManager, TaskState


def test_task_manager_lifecycle() -> None:
    manager = TaskManager(max_history=10)
    created = manager.create("teste task manager", chat_id="chat-test")
    assert created.state is TaskState.CREATED
    assert created.objective == "teste task manager"

    running = manager.start()
    assert running.state is TaskState.RUNNING
    assert running.started_at

    manager.begin_step("abrir_programa", '{"programa":"Notepad"}')
    manager.finish_step(success=True, result="Notepad aberto")
    waiting = manager.wait_for_model()
    assert waiting.state is TaskState.WAITING
    resumed = manager.resume()
    assert resumed.state is TaskState.RUNNING

    manager.complete("concluido")
    final = manager.current_snapshot()
    assert final is not None
    assert final.state is TaskState.COMPLETED
    assert final.result == "concluido"
    assert len(final.steps) == 1
    assert final.steps[0].success is True


def test_harness_integration() -> None:
    class FakeResponse:
        def __init__(self, output, output_text=""):
            self.output = output
            self.output_text = output_text
            self.usage = None

    call = SimpleNamespace(
        type="function_call",
        name="abrir_programa",
        arguments='{"programa":"Notepad"}',
        call_id="call-1",
    )
    responses = [
        FakeResponse([call]),
        FakeResponse([], "Concluido."),
    ]

    manager = TaskManager()

    def criar_resposta(_entrada, _response_id, _reasoning="none", _tool_choice=None):
        return responses.pop(0)

    harness = AurenHarness(
        criar_resposta=criar_resposta,
        executar_ferramenta=lambda _item: "Notepad aberto",
        mostrar_uso=lambda: None,
        obter_chamadas=lambda response: [
            item for item in response.output if item.type == "function_call"
        ],
        comando_rapido=lambda _mensagem: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        task_manager=manager,
        max_model_rounds=3,
    )

    tratado, resposta = harness.processar_mensagem("abra o Notepad")
    assert tratado is False
    assert resposta.output_text == "Concluido."

    snapshot = harness.current_task()
    assert snapshot is not None
    assert snapshot.state is TaskState.COMPLETED
    assert snapshot.current_tool == "abrir_programa"
    assert snapshot.attempts == 1
    assert len(snapshot.steps) == 1
    assert snapshot.steps[0].success is True


def test_failure_path() -> None:
    manager = TaskManager()

    def criar_resposta(*_args, **_kwargs):
        raise RuntimeError("falha simulada do provider")

    harness = AurenHarness(
        criar_resposta=criar_resposta,
        executar_ferramenta=lambda _item: "nao deveria executar",
        mostrar_uso=lambda: None,
        obter_chamadas=lambda response: [],
        comando_rapido=lambda _mensagem: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        task_manager=manager,
        max_model_rounds=2,
    )

    tratado, resposta = harness.processar_mensagem("teste falha")
    assert tratado is False
    assert "problema ao acessar o modelo" in resposta.output_text

    snapshot = harness.current_task()
    assert snapshot is not None
    assert snapshot.state is TaskState.FAILED
    assert "falha simulada" in snapshot.error


def test_cancel_path() -> None:
    manager = TaskManager()
    class FakeResponse:
        def __init__(self, output, output_text=""):
            self.output = output
            self.output_text = output_text
            self.usage = None

    def criar_resposta(*_args, **_kwargs):
        harness_ref["harness"].cancel_current_task("teste cancelamento")
        return FakeResponse([], "ignorado")

    harness_ref = {}
    harness = AurenHarness(
        criar_resposta=criar_resposta,
        executar_ferramenta=lambda _item: "nao deveria executar",
        mostrar_uso=lambda: None,
        obter_chamadas=lambda response: [
            item for item in response.output if item.type == "function_call"
        ],
        comando_rapido=lambda _mensagem: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        task_manager=manager,
        max_model_rounds=2,
    )
    harness_ref["harness"] = harness

    _tratado, resposta = harness.processar_mensagem("abra o Notepad")
    assert resposta.output_text == "Tarefa cancelada."
    snapshot = harness.current_task()
    assert snapshot is not None
    assert snapshot.state is TaskState.CANCELLED
    assert snapshot.cancel_requested is True


if __name__ == "__main__":
    test_task_manager_lifecycle()
    test_harness_integration()
    test_cancel_path()
    test_failure_path()
    print("TASK_MANAGER_TESTS: PASS")
