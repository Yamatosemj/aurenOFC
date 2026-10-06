
from types import SimpleNamespace
from core.harness import AurenHarness
from core.task_manager import TaskState


def test_provider_exception_marks_task_failed_and_returns_message():
    manager = None
    def provider(*_args, **_kwargs):
        raise TimeoutError("provider timeout")
    harness = AurenHarness(
        criar_resposta=provider,
        executar_ferramenta=lambda _item: "never",
        mostrar_uso=lambda: None,
        obter_chamadas=lambda response: [],
        comando_rapido=lambda _msg: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
    )
    tratado, resposta = harness.processar_mensagem("oi")
    assert tratado is False
    assert "problema ao acessar o modelo" in resposta.output_text
    snap = harness.current_task()
    assert snap.state is TaskState.FAILED
    assert "provider timeout" in snap.error


def test_provider_failure_does_not_poison_next_task():
    responses = [TimeoutError("first"), SimpleNamespace(output=[], output_text="segunda ok", usage=None)]
    def provider(*_args, **_kwargs):
        value=responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value
    harness = AurenHarness(
        criar_resposta=provider,
        executar_ferramenta=lambda _item: "never",
        mostrar_uso=lambda: None,
        obter_chamadas=lambda response: [],
        comando_rapido=lambda _msg: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
    )
    _, first = harness.processar_mensagem("primeira")
    _, second = harness.processar_mensagem("segunda")
    assert "problema ao acessar o modelo" in first.output_text
    assert second.output_text == "segunda ok"
    assert harness.current_task().state is TaskState.COMPLETED
