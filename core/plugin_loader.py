from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from core.capabilities import Capability, CAPABILITY_REGISTRY
from core.tool_contracts import registrar_tool_plugin, remover_tool_plugin
from core.tool_result import ToolResult
from tools.dispatcher import registrar_plugin_handler, remover_plugin_handler


_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
_DEFAULT_PARAMS = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}
_APPROVAL_ENV = "AUREN_PLUGINS_APPROVAL_FILE"
_DEFAULT_APPROVAL_FILE = "plugins_aprovados.json"
_FIRST_PARTY_ROOTS = {
    "agent",
    "core",
    "memory",
    "plugins",
    "providers",
    "skills",
    "tools",
    "voice",
}
_FORBIDDEN_CAPABILITY_KEYS = {
    "politica_confirmacao",
    "tools",
    "permission",
    "permissao",
    "permission_level",
    "nivel_permissao",
}
_REQUIRED_CAPABILITY_KEYS = {
    "id",
    "descricao",
    "local",
    "deterministica",
    "multi_etapa",
    "exige_raciocinio",
    "resolver",
}


@dataclass(frozen=True)
class PluginRecord:
    name: str
    file: str
    capability_id: str = ""
    valid: bool = False
    active: bool = False
    enabled: bool = True
    approved: bool = False
    error: str = ""


class PluginRegistry:
    """Mantem os plugins descobertos e as entradas dinamicas do Core."""

    def __init__(
        self,
        plugins_dir: Path,
        approval_file: Path,
        logger: Callable[[str], None] = print,
    ) -> None:
        self.plugins_dir = Path(plugins_dir)
        self.approval_file = Path(approval_file)
        self.logger = logger
        self._records: list[PluginRecord] = []
        self._active_names: set[str] = set()
        self.recarregar()

    @property
    def records(self) -> tuple[PluginRecord, ...]:
        return tuple(self._records)

    @property
    def active_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._active_names))

    def descarregar(self) -> None:
        """Remove os plugins ativos sem tocar nas tools nativas do Auren.
        O Dispatcher, o contrato e a capacidade sao desregistrados juntos.
        Custo: proporcional ao numero de plugins atualmente ativos."""
        for name in tuple(sorted(self._active_names)):
            remover_plugin_handler(name)
            remover_tool_plugin(name)
            CAPABILITY_REGISTRY.remover(f"plugin.{name}")
        self._active_names.clear()

    def recarregar(self) -> "PluginRegistry":
        """Relê os arquivos, dependencias e aprovacoes sem reiniciar o processo.
        Plugins desligados saem do Dispatcher antes de uma nova descoberta.
        Custo: uma varredura de plugins mais os imports dos plugins habilitados."""
        self.descarregar()
        self._records.clear()
        self._discover()
        return self

    def _discover(self) -> None:
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        arquivos = sorted(self.plugins_dir.glob("*.py"), key=lambda path: path.name)
        nomes_reservados = {item["name"] for item in _runtime_tools_registry()}

        vistos: dict[str, str] = {}
        for path in arquivos:
            if path.name.startswith("_"):
                continue

            try:
                estatica = _ler_declaracoes_estaticas(path)
            except (OSError, SyntaxError, ValueError) as exc:
                self._reject(path.stem, path.name, f"Arquivo de plugin invalido: {exc}")
                continue

            nome = estatica.get("tool_name") or path.stem
            habilitado, aprovado = _approval_status(self.approval_file, nome)

            if not habilitado:
                self._reject(
                    nome,
                    path.name,
                    "Plugin desativado em plugins_aprovados.json; modulo nao foi importado.",
                    enabled=False,
                    approved=aprovado,
                )
                continue

            if not _NAME_RE.match(str(nome)):
                self._reject(nome, path.name, "Nome invalido: use letras, numeros e '_' e comece por letra/'_'.")
                continue

            if nome in nomes_reservados:
                self._reject(
                    nome,
                    path.name,
                    f"Nome '{nome}' reservado por uma tool do Core; plugin ignorado.",
                    approved=aprovado,
                )
                continue

            if nome in vistos:
                self._reject(
                    nome,
                    path.name,
                    f"Nome duplicado '{nome}'; o primeiro arquivo valido ({vistos[nome]}) venceu.",
                    approved=aprovado,
                )
                continue

            vistos[nome] = path.name

            dependencias = estatica.get("dependencias", ())
            erro_dependencia = _verificar_dependencias(path, dependencias)
            if erro_dependencia:
                self._reject(nome, path.name, erro_dependencia, approved=aprovado)
                continue

            try:
                module = _import_plugin(path)
                record = _validar_e_registrar(module, path.name)
                self._records.append(
                    PluginRecord(
                        name=record.name,
                        file=path.name,
                        capability_id=record.capability_id,
                        valid=True,
                        active=True,
                        enabled=habilitado,
                        approved=aprovado,
                    )
                )
                self._active_names.add(record.name)
                self.logger(f"Plugin carregado: {record.name} ({path.name})")
            except Exception as exc:
                self._reject(nome, path.name, _mensagem_erro_importacao(path, exc), approved=aprovado)

        rejeitados = len([record for record in self._records if not record.valid])
        self.logger(
            f"Descoberta de plugins concluida: {len(self._active_names)} ativos, "
            f"{rejeitados} rejeitados/desativados, {len(self._records)} total."
        )

    def _reject(
        self,
        name: str,
        filename: str,
        error: str,
        *,
        enabled: bool = True,
        approved: bool = False,
    ) -> None:
        self._records.append(
            PluginRecord(
                name=str(name),
                file=filename,
                valid=False,
                active=False,
                enabled=enabled,
                approved=approved,
                error=str(error),
            )
        )
        self.logger(f"Plugin ignorado: {filename} — {error}")


@dataclass(frozen=True)
class _ValidatedPlugin:
    name: str
    capability_id: str


def _runtime_tools_registry() -> list[dict[str, Any]]:
    from core.tools_registry import tools
    return tools


def _approval_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    configured = os.getenv(_APPROVAL_ENV, "").strip()
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[1] / _DEFAULT_APPROVAL_FILE


def _approval_status(path: Path, name: str) -> tuple[bool, bool]:
    path = Path(path)
    try:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
            return True, False
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return True, False

    if not isinstance(raw, dict):
        return True, False

    value = raw.get(name)
    if isinstance(value, bool):
        return value, False
    if isinstance(value, dict):
        return bool(value.get("habilitado", True)), bool(value.get("aprovado", False))
    return True, False


def plugin_aprovado(nome: str) -> bool:
    """Consulta a aprovacao local de um plugin, sem confiar no proprio plugin.
    O arquivo e relido para que uma aprovacao possa entrar em vigor sem reboot.
    Custo: leitura e parse de um JSON pequeno por verificacao de permissao."""
    habilitado, aprovado = _approval_status(_approval_path(), str(nome))
    return habilitado and aprovado


def plugin_habilitado(nome: str) -> bool:
    """Consulta se um plugin esta habilitado no arquivo local de controle.
    O estado serve para descoberta/recarregamento, nao para autorizar execucao.
    Custo: leitura e parse de um JSON pequeno por consulta."""
    habilitado, _ = _approval_status(_approval_path(), str(nome))
    return habilitado


def discover_plugins(
    plugins_dir: str | Path | None = None,
    *,
    approval_file: str | Path | None = None,
    logger: Callable[[str], None] = print,
) -> PluginRegistry:
    """Descobre plugins locais e os conecta aos registries oficiais do Auren.
    Cada modulo e importado isoladamente somente depois de passar nas pre-checagens.
    Custo: uma varredura dos arquivos mais o import dos plugins habilitados."""
    return PluginRegistry(
        Path(plugins_dir) if plugins_dir is not None else _default_plugins_dir(),
        _approval_path(approval_file),
        logger,
    )


_GLOBAL_REGISTRY: PluginRegistry | None = None


def carregar_plugins(
    plugins_dir: str | Path | None = None,
    *,
    approval_file: str | Path | None = None,
    logger: Callable[[str], None] = print,
) -> PluginRegistry:
    """Carrega os plugins uma vez no processo para o caminho oficial do runtime.
    O resultado passa a alimentar tools, contratos, capacidades e Dispatcher.
    Custo: igual a uma descoberta inicial de plugins habilitados."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = discover_plugins(
            plugins_dir,
            approval_file=approval_file,
            logger=logger,
        )
    return _GLOBAL_REGISTRY


def recarregar_plugins() -> PluginRegistry:
    """Relê o estado local dos plugins e aplica liga/desliga sem reiniciar.
    A troca remove primeiro os registros antigos e depois descobre os atuais.
    Custo: uma descoberta completa mais os imports necessarios."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        return carregar_plugins()
    return _GLOBAL_REGISTRY.recarregar()


def _default_plugins_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "plugins"


def _ler_declaracoes_estaticas(path: Path) -> dict[str, Any]:
    arvore = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    valores: dict[str, Any] = {}

    for node in arvore.body:
        target_names: list[str] = []
        if isinstance(node, ast.Assign):
            target_names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_names = [node.target.id]
            value_node = node.value
        else:
            continue

        if "TOOL" in target_names:
            valores["tool_name"] = _static_dict_value(value_node, "name")
        if "DEPENDENCIAS" in target_names:
            try:
                dependencias = ast.literal_eval(value_node)
            except (ValueError, TypeError, SyntaxError) as exc:
                raise ValueError(f"DEPENDENCIAS invalida: {exc}") from exc
            valores["dependencias"] = dependencias

    return valores


def _static_dict_value(node: ast.AST | None, key: str) -> Any:
    if not isinstance(node, ast.Dict):
        return None
    for key_node, value_node in zip(node.keys, node.values):
        try:
            literal_key = ast.literal_eval(key_node)
        except (ValueError, TypeError, SyntaxError):
            continue
        if literal_key == key:
            try:
                return ast.literal_eval(value_node)
            except (ValueError, TypeError, SyntaxError):
                return None
    return None


def _verificar_dependencias(path: Path, dependencias: Any) -> str | None:
    if dependencias in (None, ()):
        return None
    if not isinstance(dependencias, (tuple, list)) or not all(isinstance(item, str) and item.strip() for item in dependencias):
        return "DEPENDENCIAS deve ser uma lista/tupla literal de nomes de modulos."

    for dependencia in dependencias:
        nome = dependencia.strip()
        try:
            spec = importlib.util.find_spec(nome)
        except (ImportError, ModuleNotFoundError, AttributeError, ValueError):
            spec = None
        if spec is not None:
            continue

        raiz = nome.split(".", 1)[0]
        if raiz in _FIRST_PARTY_ROOTS:
            return (
                f"Modulo do proprio Auren ausente: '{nome}'. "
                "Nao instale com pip; o plugin depende de um modulo que deveria vir com o projeto."
            )
        return f"Dependencia ausente: '{nome}'. Instale a dependencia necessaria antes de habilitar o plugin."

    return None


def _import_plugin(path: Path):
    module_name = f"plugins.{path.stem}"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError("nao foi possivel criar o spec de importacao")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _validar_e_registrar(module: Any, filename: str) -> _ValidatedPlugin:
    tool = getattr(module, "TOOL", None)
    capability = getattr(module, "CAPABILITY", None)
    handler = tool.get("handler") if isinstance(tool, dict) else None

    if not isinstance(tool, dict):
        raise ValueError("TOOL deve ser um dicionario de declaracao.")
    if not isinstance(capability, dict):
        raise ValueError("CAPABILITY deve ser um dicionario de capacidade.")
    if not isinstance(tool.get("name"), str) or not _NAME_RE.match(tool["name"]):
        raise ValueError("TOOL['name'] ausente ou invalido.")
    if not isinstance(tool.get("description"), str) or not tool["description"].strip():
        raise ValueError("TOOL['description'] ausente ou vazia.")
    parameters = tool.get("parameters", _DEFAULT_PARAMS)
    if not isinstance(parameters, dict) or parameters.get("type") != "object":
        raise ValueError("TOOL['parameters'] deve ser schema JSON com type='object'.")
    if not callable(handler):
        raise ValueError("TOOL['handler'] deve ser chamavel.")
    if set(capability) & _FORBIDDEN_CAPABILITY_KEYS:
        bloqueadas = sorted(set(capability) & _FORBIDDEN_CAPABILITY_KEYS)
        raise ValueError(
            "CAPABILITY nao pode escolher permissao nem ferramentas: "
            + ", ".join(bloqueadas)
        )
    ausentes = sorted(_REQUIRED_CAPABILITY_KEYS - set(capability))
    if ausentes:
        raise ValueError("CAPABILITY incompleta; faltam: " + ", ".join(ausentes) + ".")
    nome = tool["name"]
    capability_id = capability.get("id")
    if capability_id != f"plugin.{nome}":
        raise ValueError(f"CAPABILITY['id'] deve ser exatamente 'plugin.{nome}'.")
    for campo in ("local", "deterministica", "multi_etapa", "exige_raciocinio"):
        if not isinstance(capability.get(campo), bool):
            raise ValueError(f"CAPABILITY['{campo}'] deve ser booleano.")
    descricao = capability.get("descricao")
    resolver = capability.get("resolver")
    if not isinstance(descricao, str) or not descricao.strip():
        raise ValueError("CAPABILITY['descricao'] ausente ou vazia.")
    if not isinstance(resolver, str) or not resolver.strip():
        raise ValueError("CAPABILITY['resolver'] ausente ou vazio.")

    obrigatorios = tuple(capability.get("parametros_obrigatorios", parameters.get("required", ())) or ())
    opcionais = tuple(capability.get("parametros_opcionais", (key for key in (parameters.get("properties") or {}) if key not in obrigatorios)))
    properties = set(parameters.get("properties") or {})
    if not all(isinstance(item, str) for item in (*obrigatorios, *opcionais)):
        raise ValueError("parametros_obrigatorios/opcionais devem conter somente strings.")
    if not set(obrigatorios) <= properties:
        raise ValueError("CAPABILITY declara parametro obrigatorio fora do schema da TOOL.")
    if set(obrigatorios) & set(opcionais):
        raise ValueError("Um parametro nao pode ser simultaneamente obrigatorio e opcional.")

    capability_registro = Capability(
        id=capability_id,
        descricao=descricao.strip(),
        local=capability["local"],
        deterministica=capability["deterministica"],
        multi_etapa=capability["multi_etapa"],
        exige_raciocinio=capability["exige_raciocinio"],
        parametros_obrigatorios=obrigatorios,
        parametros_opcionais=opcionais,
        politica_confirmacao="confirm",
        resolver=resolver.strip(),
        tools=(nome,),
        prioridade=int(capability.get("prioridade", 1000)),
        padroes_objetivo=tuple(capability.get("padroes_objetivo", ()) or ()),
    )

    normalized_tool = {
        "type": "function",
        "name": nome,
        "description": tool["description"].strip(),
        "parameters": parameters,
        "strict": bool(tool.get("strict", True)),
    }

    wrapper = _wrap_handler(nome, handler)
    CAPABILITY_REGISTRY.registrar(capability_registro)
    try:
        registrar_tool_plugin(normalized_tool, capability_id)
        registrar_plugin_handler(nome, wrapper)
    except Exception:
        remover_plugin_handler(nome)
        remover_tool_plugin(nome)
        CAPABILITY_REGISTRY.remover(capability_id)
        raise

    return _ValidatedPlugin(nome, capability_id)


def _wrap_handler(name: str, handler: Callable[..., Any]) -> Callable[..., ToolResult]:
    def dispatcher_handler(arguments: dict[str, Any], memory_store, context) -> ToolResult:
        try:
            result = _call_plugin_handler(handler, arguments, memory_store, context)
        except Exception as exc:
            return ToolResult.failure(
                f"Plugin '{name}' falhou durante a execucao: {exc}",
                error_code="plugin_error",
                tool_name=name,
            )
        if not isinstance(result, ToolResult):
            return ToolResult.failure(
                f"Plugin '{name}' retornou um tipo invalido; o handler deve devolver ToolResult.",
                error_code="plugin_invalid_result",
                tool_name=name,
            )
        if result.tool_name is not None and result.tool_name != name:
            return ToolResult.failure(
                f"Plugin '{name}' devolveu ToolResult de outra ferramenta.",
                error_code="plugin_tool_name_mismatch",
                tool_name=name,
            )
        if result.tool_name is None:
            return ToolResult(
                ok=result.ok,
                message=result.message,
                data=result.data,
                error_code=result.error_code,
                tool_name=name,
                conteudo_nao_confiavel=result.conteudo_nao_confiavel,
            )
        return result

    return dispatcher_handler


def _call_plugin_handler(
    handler: Callable[..., Any],
    arguments: dict[str, Any],
    memory_store: Any,
    context: dict[str, Any],
) -> ToolResult:
    assinatura = inspect.signature(handler)
    parametros = assinatura.parameters
    if "argumentos" in parametros:
        kwargs: dict[str, Any] = {"argumentos": arguments}
    elif "parameters" in parametros:
        kwargs = {"parameters": arguments}
    elif "args" in parametros:
        kwargs = {"args": arguments}
    else:
        posicao = [
            item for item in parametros.values()
            if item.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        if not posicao:
            kwargs = {}
        else:
            return handler(arguments)

    if "memory_store" in parametros:
        kwargs["memory_store"] = memory_store
    if "context" in parametros:
        kwargs["context"] = context
    return handler(**kwargs)


def _mensagem_erro_importacao(path: Path, exc: Exception) -> str:
    if isinstance(exc, ModuleNotFoundError):
        missing = (getattr(exc, "name", "") or "").strip()
        if missing:
            raiz = missing.split(".", 1)[0]
            if raiz in _FIRST_PARTY_ROOTS:
                return (
                    f"Modulo do proprio Auren ausente durante o import: '{missing}'. "
                    "Nao instale com pip; o projeto esta incompleto ou desatualizado para este plugin."
                )
            return f"Dependencia ausente durante o import: '{missing}'. Instale a dependencia necessaria."
    return f"Falha ao importar/validar plugin: {exc}"
