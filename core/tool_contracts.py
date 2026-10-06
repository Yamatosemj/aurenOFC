from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.tools_registry import tools


class ToolContractError(ValueError):
    """Falha de contrato de uma capacidade/tool antes da execucao."""


@dataclass(frozen=True)
class ToolContract:
    """Contrato generico de uma capacidade exposta ao modelo.

    O contrato descreve somente a capacidade e seu schema de argumentos.
    Nunca registra aplicativos, janelas, sites ou outros alvos concretos.
    """

    name: str
    capability: str
    description: str
    parameters: Mapping[str, Any]

    @property
    def required(self) -> tuple[str, ...]:
        return tuple(self.parameters.get("required") or ())

    @property
    def properties(self) -> Mapping[str, Any]:
        return self.parameters.get("properties") or {}

    def validate_arguments(self, arguments: Any) -> None:
        if not isinstance(arguments, dict):
            raise ToolContractError("argumentos devem ser um objeto JSON")

        for name in self.required:
            if name not in arguments:
                raise ToolContractError(f"argumento obrigatorio ausente: '{name}'")

        for name, value in arguments.items():
            schema = self.properties.get(name)
            if schema is None:
                raise ToolContractError(f"propriedade nao declarada no contrato: '{name}'")

            expected_type = schema.get("type")
            if expected_type and not _matches_json_type(value, expected_type):
                raise ToolContractError(
                    f"argumento '{name}' deve ser do tipo {expected_type}"
                )

            enum = schema.get("enum")
            if enum is not None and value not in enum:
                raise ToolContractError(
                    f"argumento '{name}' fora das opcoes permitidas: {', '.join(map(str, enum))}"
                )

            if isinstance(value, (int, float)) and not isinstance(value, bool):
                minimum = schema.get("minimum")
                maximum = schema.get("maximum")
                if minimum is not None and value < minimum:
                    raise ToolContractError(
                        f"argumento '{name}' abaixo do minimo permitido ({minimum})"
                    )
                if maximum is not None and value > maximum:
                    raise ToolContractError(
                        f"argumento '{name}' acima do maximo permitido ({maximum})"
                    )


def _matches_json_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "null":
        return value is None
    return True


# As categorias abaixo descrevem capacidades, nao aplicativos.
# Alvos futuros continuam sendo apenas argumentos dessas capacidades.
_CAPABILITY_RULES: tuple[tuple[str, str], ...] = (
    ("salvar_memoria_persistente", "memory.write"),
    ("consultar_memoria_persistente", "memory.read"),
    ("esquecer_memoria_persistente", "memory.write"),
    ("abrir_programa", "application.open"),
    ("buscar_arquivo", "file.search"),
    ("listar_processos_windows", "windows.process.read"),
    ("encerrar_processo_windows", "windows.process.control"),
    ("listar_janelas_windows", "windows.window.read"),
    ("obter_geometria_janela_windows", "windows.window.read"),
    ("focar_janela_windows", "windows.window.control"),
    ("minimizar_janela_windows", "windows.window.control"),
    ("maximizar_janela_windows", "windows.window.control"),
    ("mover_janela_windows", "windows.window.control"),
    ("redimensionar_janela_windows", "windows.window.control"),
    ("restaurar_janela_windows", "windows.window.control"),
    ("fechar_janela_windows", "windows.window.control"),
    ("obter_status_windows", "windows.status.read"),
    ("capturar_tela_windows", "windows.screen.read"),
    ("ler_area_transferencia_windows", "windows.clipboard.read"),
    ("definir_area_transferencia_windows", "windows.clipboard.write"),
    ("pressionar_tecla_windows", "windows.input"),
    ("mover_mouse_windows", "windows.input"),
    ("clicar_mouse_windows", "windows.input"),
    ("obter_audio_windows", "windows.audio.read"),
    ("definir_volume_windows", "windows.audio.control"),
    ("definir_mudo_windows", "windows.audio.control"),
    ("controle_midia_windows", "windows.audio.control"),
    ("inspecionar_interface_windows", "windows.ui.read"),
    ("clicar_elemento_windows", "windows.ui.control"),
    ("preencher_elemento_windows", "windows.ui.control"),
    ("alternar_elemento_windows", "windows.ui.control"),
    ("selecionar_elemento_windows", "windows.ui.control"),
    ("navegar_navegador", "browser.navigation"),
    ("ler_pagina", "browser.read"),
    ("clicar_elemento", "browser.input"),
    ("preencher_elemento", "browser.input"),
    ("pressionar_tecla", "browser.input"),
    ("listar_abas", "browser.tabs.read"),
    ("abrir_nova_aba", "browser.tabs.control"),
    ("trocar_aba", "browser.tabs.control"),
    ("fechar_aba", "browser.tabs.control"),
    ("voltar_pagina", "browser.navigation"),
    ("avancar_pagina", "browser.navigation"),
    ("recarregar_pagina", "browser.navigation"),
    ("rolar_pagina", "browser.scroll"),
)

_CAPABILITY_BY_TOOL = dict(_CAPABILITY_RULES)


class ToolContractRegistry:
    """Registro de contratos construidos diretamente dos schemas das tools."""

    def __init__(self, schemas: list[dict[str, Any]] | None = None) -> None:
        source = schemas if schemas is not None else tools
        self._contracts = {
            item["name"]: ToolContract(
                name=item["name"],
                capability=_CAPABILITY_BY_TOOL.get(item["name"], "generic"),
                description=str(item.get("description") or ""),
                parameters=item.get("parameters") or {"type": "object"},
            )
            for item in source
        }

    def get(self, name: str) -> ToolContract:
        try:
            return self._contracts[name]
        except KeyError as exc:
            raise ToolContractError(f"tool desconhecida: '{name}'") from exc

    def validate(self, name: str, arguments: Any) -> ToolContract:
        contract = self.get(name)
        contract.validate_arguments(arguments)
        return contract

    def names(self) -> tuple[str, ...]:
        return tuple(self._contracts)

    def capabilities(self) -> dict[str, str]:
        return {name: contract.capability for name, contract in self._contracts.items()}

    def validate_registry(self) -> None:
        if len(self._contracts) != len(tools):
            raise ToolContractError("registro de contratos diverge do registry de tools")
        for item in tools:
            contract = self._contracts.get(item["name"])
            if contract is None:
                raise ToolContractError(f"sem contrato para '{item['name']}'")
            if contract.parameters.get("type") != "object":
                raise ToolContractError(f"schema invalido para '{item['name']}'")


DEFAULT_TOOL_CONTRACTS = ToolContractRegistry()
DEFAULT_TOOL_CONTRACTS.validate_registry()


def capability_for_tool(name: str) -> str:
    """Retorna a capacidade canonica de uma tool."""
    return DEFAULT_TOOL_CONTRACTS.get(name).capability


def validate_tool_arguments(name: str, arguments: Any) -> tuple[bool, str]:
    try:
        DEFAULT_TOOL_CONTRACTS.validate(name, arguments)
    except ToolContractError as exc:
        return False, str(exc)
    return True, ""
