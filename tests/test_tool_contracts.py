from __future__ import annotations

from core.tool_contracts import DEFAULT_TOOL_CONTRACTS, validate_tool_arguments
from core.tools_registry import tools
from core.permission_manager import PermissionManager
from tools.dispatcher import executar_ferramenta
from types import SimpleNamespace


def _sample_for_schema(schema: dict) -> dict:
    result = {}
    for name, spec in (schema.get("properties") or {}).items():
        if "enum" in spec:
            result[name] = spec["enum"][0]
        elif spec.get("type") == "string":
            result[name] = ""
        elif spec.get("type") == "integer":
            result[name] = int(spec.get("minimum", 0))
        elif spec.get("type") == "number":
            result[name] = spec.get("minimum", 0)
        elif spec.get("type") == "boolean":
            result[name] = False
    return result


def test_all_registry_tools_have_generic_contracts() -> None:
    assert len(tools) == 49
    assert set(DEFAULT_TOOL_CONTRACTS.names()) == {item["name"] for item in tools}
    DEFAULT_TOOL_CONTRACTS.validate_registry()


def test_valid_samples_pass_contract_validation() -> None:
    for item in tools:
        args = _sample_for_schema(item["parameters"])
        ok, error = validate_tool_arguments(item["name"], args)
        assert ok, f"{item['name']}: {error}"


def test_invalid_shape_and_enum_are_rejected_before_execution() -> None:
    ok, error = validate_tool_arguments(
        "mover_mouse_windows",
        {"x": "960", "y": 540},
    )
    assert not ok and "tipo integer" in error

    ok, error = validate_tool_arguments(
        "navegar_navegador",
        {"url": "https://example.com", "modo": "invalido"},
    )
    assert not ok and "opcoes permitidas" in error

    ok, error = validate_tool_arguments("abrir_programa", {})
    assert not ok and "obrigatorio ausente" in error


def test_dispatcher_rejects_invalid_arguments_before_execution() -> None:
    manager = PermissionManager(max_actions=10)
    item = SimpleNamespace(
        name="mover_mouse_windows",
        arguments='{"x":"960","y":540}',
    )
    result = executar_ferramenta(item, manager, None)
    assert result.ok is False
    assert result.error_code == "contract_error"
    assert result.message.startswith("Argumentos invalidos")
    assert "tipo integer" in result.message


def test_all_tools_have_registered_handlers() -> None:
    from tools.dispatcher import TOOL_HANDLERS, validar_registry_handlers
    ok, error = validar_registry_handlers()
    assert ok, error
    assert len(TOOL_HANDLERS) == len(tools) == 49


def test_permissions_are_keyed_by_capability_not_tool_name() -> None:
    from core.permission_manager import PermissionManager, PermissionLevel
    pm = PermissionManager(max_actions=10)
    capability_names = set(DEFAULT_TOOL_CONTRACTS.capabilities().values())
    assert capability_names <= set(pm.policy)
    assert not (set(pm.policy) & {item["name"] for item in tools})
    assert pm.nivel("listar_janelas_windows") == PermissionLevel.AUTO
    assert pm.capability("listar_janelas_windows") == "windows.window.read"


def test_fechar_aba_schema_keeps_indice_optional():
    from core.tools_registry import tools

    schema = next(item for item in tools if item["name"] == "fechar_aba")
    assert schema["parameters"]["required"] == []
