import ast
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.tool_result import ToolResult


def test_aud034_assertion_really_checks_exact_proposal(monkeypatch):
    import tests.test_intent_multistep_progress as checks
    monkeypatch.setattr(checks, "proposta_simples_exata", lambda *a: False)
    with pytest.raises(AssertionError):
        checks.test_proposta_de_pid_principal_com_evidencia_passou_a_fast_review_local()


def test_aud035_runner_consumes_real_structured_process_contract():
    # Compilar somente os quatro blocos do testador relacionados a processos.
    # Os executores sao falsos e o restante do testador Live nunca e chamado.
    import testes_auren_live as live
    source = ast.parse(Path(live.__file__).read_text(encoding="utf-8"))
    blocks = []
    for node in ast.walk(source):
        if not isinstance(node, ast.Try) or not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Assign) and isinstance(first.value, ast.Call):
            call = first.value.func
            if isinstance(call, ast.Attribute) and call.attr in {"encerrar_processo_windows", "listar_processos_windows"}:
                blocks.append(node)
    assert len(blocks) == 4
    observations = []
    def reject(**kw):
        code = ("self_process_blocked" if "pid" in kw else
                "protected_process_blocked" if kw.get("nome") == "explorer.exe" else "process_wildcard_rejected")
        return ToolResult.failure("bloqueado", error_code=code)
    scope = dict(vars(live))
    scope.update(auren=SimpleNamespace(encerrar_processo_windows=reject,
        listar_processos_windows=lambda: ToolResult.success("Processos encontrados: 1\nficticio | PID 42")),
        os=SimpleNamespace(getpid=lambda: 42), record=lambda name, ok, *a, **kw: observations.append((name, ok)))
    function = ast.FunctionDef(name="check", args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
                               body=blocks, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    compiled = compile(module, "<blocos-ficticios-aud035>", "exec")
    body = next(item for item in compiled.co_consts if isinstance(item, types.CodeType))
    types.FunctionType(body, scope)()
    assert len(observations) == 4
    assert all(ok for _, ok in observations), observations
