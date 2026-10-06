from types import SimpleNamespace

from core.permission_manager import PermissionManager
from core.tool_result import ToolResult, from_legacy
import tools.dispatcher as dispatcher


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


def test_verifier_respects_structured_success_even_with_failure_like_message():
    from agent.verifier import VerificationEngine

    result = ToolResult.success(
        "Nao consegui concluir a etapa anterior, mas esta chamada foi concluida com sucesso.",
        tool_name="teste",
    )

    verification = VerificationEngine.verify(
        "execute a tarefa", "teste", result
    )

    assert verification.ok is True
    assert verification.status == "verified"


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
