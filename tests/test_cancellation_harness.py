
from types import SimpleNamespace
from core.harness import AurenHarness
from core.task_manager import TaskState
from core.tool_result import ToolResult


def test_tool_success_after_cancel_request_ends_cancelled():
    holder = {}
    call = SimpleNamespace(type="function_call", name="abrir_programa", arguments='{"programa":"Notepad"}', call_id="1")
    responses = [SimpleNamespace(output=[call], output_text="", usage=None)]
    def exec_tool(_item):
        holder["harness"].cancel_current_task("during tool")
        return ToolResult.success("executado", data={})
    def provider(*_args, **_kwargs):
        return responses.pop(0)
    harness = AurenHarness(
        criar_resposta=provider,
        executar_ferramenta=exec_tool,
        mostrar_uso=lambda: None,
        obter_chamadas=lambda response: list(response.output),
        comando_rapido=lambda _msg: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
    )
    holder["harness"] = harness
    _, resposta = harness.processar_mensagem("abra o notepad")
    snap = harness.current_task()
    assert snap.state is TaskState.CANCELLED
    assert snap.steps[0].success is True
    assert "cancelada" in resposta.output_text.lower()
