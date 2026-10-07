"""Runner live/manual do Auren.

Nao faz parte da suite pytest. Execute este arquivo explicitamente em um ambiente Windows real
quando quiser validar modelo + ferramentas e efeitos integrados.
"""

from __future__ import annotations

import sys
from pathlib import Path as _PathBootstrap
ROOT_BOOTSTRAP = _PathBootstrap(__file__).resolve().parent
if str(ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(ROOT_BOOTSTRAP))

import ast
import builtins
import contextlib
import ctypes
from datetime import datetime
from ctypes import wintypes
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import types
from dataclasses import dataclass
import core.harness as harness_module
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TEST_SUITE_VERSION = 46
TESTER_BUILD = 'V18-p0-3-bateria-fast-path-aware'
MIN_REQUIRED_VERSION = 46
REQUIRED_TOOLS = [
    "abrir_programa",
    "listar_janelas_windows",
    "focar_janela_windows",
    "minimizar_janela_windows",
    "maximizar_janela_windows",
    "obter_geometria_janela_windows",
    "mover_janela_windows",
    "redimensionar_janela_windows",
    "restaurar_janela_windows",
    "fechar_janela_windows",
    "obter_status_windows",
    "obter_audio_windows",
    "definir_volume_windows",
    "definir_mudo_windows",
    "controle_midia_windows",
    "listar_processos_windows",
    "encerrar_processo_windows",
    "ler_area_transferencia_windows",
    "definir_area_transferencia_windows",
    "pressionar_tecla_windows",
    "mover_mouse_windows",
    "clicar_mouse_windows",
    "inspecionar_interface_windows",
    "clicar_elemento_windows",
    "preencher_elemento_windows",
    "alternar_elemento_windows",
    "selecionar_elemento_windows",
    "obter_contexto_navegador",
    "salvar_memoria_persistente",
    "consultar_memoria_persistente",
    "esquecer_memoria_persistente",
]


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""
    layer: str = "L0"


AVAILABLE_LAYERS = ("L0", "L1", "L2", "L3", "L4", "L5")


def _requested_layers_from_argv(argv: list[str] | None = None) -> set[str]:
    args = list(argv if argv is not None else sys.argv[1:])
    requested: set[str] | None = None
    for index, arg in enumerate(args):
        if arg == "--camada" and index + 1 < len(args):
            requested = {item.strip().upper() for item in args[index + 1].split(",") if item.strip()}
            break
        if arg.startswith("--camada="):
            requested = {item.strip().upper() for item in arg.split("=", 1)[1].split(",") if item.strip()}
            break

    if requested is None:
        if "--completo" in args:
            requested = {"L0", "L1", "L2", "L4", "L5"}
        else:
            # O modo padrão/rápido é deliberadamente sem API.
            requested = {"L0", "L1"}

    invalid = requested - set(AVAILABLE_LAYERS)
    if invalid:
        raise SystemExit(f"Camadas invalidas: {sorted(invalid)}. Use L0,L1,L2,L3,L4,L5.")

    # Camadas dependem das inferiores para manter o teste reproduzível.
    if "L5" in requested:
        requested.update({"L0", "L1", "L2", "L4"})
    if "L4" in requested:
        requested.update({"L0", "L1", "L2"})
    if "L3" in requested:
        requested.update({"L0", "L1"})
    if "L2" in requested:
        requested.update({"L0", "L1"})
    if "L1" in requested:
        requested.add("L0")
    return requested


ACTIVE_LAYERS = _requested_layers_from_argv()
CURRENT_LAYER = "L0"
RESULTS: list[Result] = []
INTEGRATION_CHAT_LOG = ""
INTEGRATION_CHAT_LOG_PATH: Path | None = None


def _ui_inspecao_confirmou_texto(resultado: str, texto: str) -> bool:
    bruto = str(resultado or "")
    normalizado = bruto.replace("\\r\\n", "\n").replace("\\n", "\n")
    linhas = [linha.strip() for linha in normalizado.splitlines()]
    possui_bloco_exato = any(re.match(r"^Controles exibidos:\s*1\s*$", linha) for linha in linhas)
    possui_controle = any(f"texto={texto}" in linha and "Nenhum controle correspondeu" not in linha for linha in linhas)
    return possui_bloco_exato and possui_controle

def _ui_preenchimento_confirmado(resultado: str, automation_id: str) -> bool:
    texto = str(resultado or "")
    return "Preenchimento concluido" in texto and bool(re.search(rf"automation_id=[\"']?{re.escape(automation_id)}", texto))


def _normalize_detail(detail: str) -> str:
    return re.sub(r"\s+", " ", str(detail or "")).strip()


def _compact_pass_detail(detail: str, limit: int = 180) -> str:
    texto = _normalize_detail(detail)
    if not texto:
        return "assertion=True; execucao sem excecao"
    if len(texto) <= limit:
        return texto
    return texto[: max(0, limit - 14)].rstrip() + " ...[cortado]"


def _compact_fail_detail(detail: str, limit: int = 6000) -> str:
    texto = _normalize_detail(detail)
    if len(texto) <= limit:
        return texto
    return texto[: max(0, limit - 14)].rstrip() + " ...[cortado]"


def layer_enabled(layer: str) -> bool:
    return layer.upper() in ACTIVE_LAYERS


def set_layer(layer: str) -> None:
    global CURRENT_LAYER
    CURRENT_LAYER = layer.upper()


def record(name: str, ok: bool, detail: str = "", *, layer: str | None = None) -> None:
    resolved_layer = (layer or CURRENT_LAYER).upper()
    if resolved_layer not in ACTIVE_LAYERS:
        return
    RESULTS.append(Result(name, ok, detail, resolved_layer))
    tag = "PASS" if ok else "FAIL"
    detalhe = _compact_pass_detail(detail) if ok else _compact_fail_detail(detail)
    print(f"[{tag}] [{resolved_layer}] {name} — {detalhe}")


def _window_snapshot(auren) -> list[tuple[int, str]]:
    try:
        return list(auren._enumerar_janelas_windows())
    except Exception:
        return []


def _find_new_notepad_window(auren, before_hwnds: set[int], timeout: float = 5.0) -> tuple[int, str] | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for hwnd, titulo in _window_snapshot(auren):
            if hwnd in before_hwnds:
                continue
            try:
                processo = auren._processo_da_janela_windows(hwnd)
            except Exception:
                processo = ""
            if processo.lower() == "notepad.exe":
                return hwnd, titulo
        time.sleep(0.25)
    return None


def _version_from_source(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    match = re.search(r'AUREN_VERSION\s*=\s*(\d+)', text)
    if match:
        return int(match.group(1))
    match = re.search(r'CACHE_KEY\s*=\s*["\']auren-v(\d+)["\']', text)
    return int(match.group(1)) if match else None


def _model_from_source(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    match = re.search(r'MODEL\s*=\s*["\']([^"\']+)["\']', text)
    return match.group(1) if match else None


def _cache_version_from_source(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    match = re.search(r'CACHE_KEY\s*=\s*["\']auren-v(\d+)["\']', text)
    if match:
        return int(match.group(1))

    # Auren pode manter a chave sincronizada automaticamente com AUREN_VERSION.
    if re.search(r'CACHE_KEY\s*=\s*f["\']auren-v\{AUREN_VERSION\}["\']', text):
        version_match = re.search(r'AUREN_VERSION\s*=\s*(\d+)', text)
        return int(version_match.group(1)) if version_match else None

    return None




def _source_tool_consistency(path: Path) -> tuple[bool, str]:
    """Confere schema de ferramentas e registry de handlers."""
    registry_path = ROOT / "core" / "tools_registry.py"
    dispatcher_path = ROOT / "tools" / "dispatcher.py"
    try:
        registry_tree = ast.parse(registry_path.read_text(encoding="utf-8", errors="replace"), filename=str(registry_path))
        tools_node = next(
            n.value for n in registry_tree.body
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "tools" for t in n.targets)
        )
        tools = ast.literal_eval(tools_node)
        schema = {str(item.get("name")) for item in tools if isinstance(item, dict) and item.get("name")}
        dispatch_tree = ast.parse(dispatcher_path.read_text(encoding="utf-8", errors="replace"), filename=str(dispatcher_path))
        handler_node = next(
            n.value for n in dispatch_tree.body
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TOOL_HANDLERS" for t in n.targets)
        )
        handlers = {
            str(key.value) for key in handler_node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
    except Exception as exc:
        return False, f"nao consegui analisar schema/registry: {exc}"
    faltando_dispatch = sorted(schema - handlers)
    sem_schema = sorted(handlers - schema)
    if faltando_dispatch or sem_schema:
        return False, f"faltando_handlers={faltando_dispatch}; sem_schema={sem_schema}"
    return True, f"{len(schema)} ferramentas alinhadas"


def _source_has_required_tools(path: Path) -> tuple[bool, list[str]]:
    try:
        trees = [
            ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path)),
            ast.parse((ROOT / "core" / "facade.py").read_text(encoding="utf-8", errors="replace"), filename=str(ROOT / "core" / "facade.py")),
        ]
    except Exception:
        return False, REQUIRED_TOOLS[:]

    functions = set()
    imported = set()
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.add(node.name)
            elif isinstance(node, ast.ImportFrom) and node.module == "core.facade":
                imported.update(alias.name for alias in node.names)
    available = functions | imported
    missing = [name for name in REQUIRED_TOOLS if name not in available]
    return not missing, missing


def find_auren() -> tuple[Path | None, dict[Path, dict[str, object]]]:
    # REGRA INTENCIONAL DO TESTER:
    # O unico Auren que pode ser testado e o auren.py que esta
    # exatamente na mesma pasta deste arquivo / TESTAR_AUREN.bat.
    # Nada de procurar em outras pastas, ZIPs, Desktop ou versoes antigas.
    source = ROOT / "auren.py"
    inspected: dict[Path, dict[str, object]] = {}

    if not source.is_file():
        return None, inspected

    version = _version_from_source(source)
    cache_version = _cache_version_from_source(source)
    model = _model_from_source(source)
    has_tools, missing = _source_has_required_tools(source)
    version_consistent = version is not None and cache_version == version
    inspected[ROOT] = {
        "version": version,
        "cache_version": cache_version,
        "model": model,
        "has_tools": has_tools,
        "missing": missing,
        "mtime": source.stat().st_mtime,
    }

    if (
        version is not None
        and version >= MIN_REQUIRED_VERSION
        and version_consistent
        and model == "gpt-5.6-luna"
        and has_tools
    ):
        return ROOT, inspected

    return None, inspected


def load_auren_module():
    source = ROOT / "auren.py"
    if not source.is_file():
        raise RuntimeError("Nao encontrei auren.py na mesma pasta do tester.")

    # O smoke test nao precisa da API. Substituimos apenas a classe OpenAI
    # durante o import para evitar custo e dependencia da chave da API.
    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = lambda: object()
    sys.modules["openai"] = fake_openai

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    spec = importlib.util.spec_from_file_location("auren_under_test", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("Nao consegui carregar auren.py")

    modulo = importlib.util.module_from_spec(spec)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        spec.loader.exec_module(modulo)
    return modulo


def run_discovery_tests() -> bool:
    set_layer("L0")
    print("\n=== LOCALIZACAO E VALIDACAO DA VERSAO ===")

    compatible_path, discovery = find_auren()
    source = ROOT / "auren.py"

    if compatible_path is None:
        if not source.is_file():
            record("Localizacao do Auren", False, f"Nao encontrei {source}. O auren.py precisa estar na mesma pasta deste tester.")
        else:
            info = discovery[ROOT]
            record(
                "Localizacao do Auren",
                False,
                f"auren.py local encontrado, mas nao compativel: versao={info['version']}, cache={info['cache_version']}, modelo={info['model']}, ferramentas_ok={info['has_tools']}"
            )
            if info["missing"]:
                record("Ferramentas esperadas", False, f"faltando: {info['missing']}")
        record("Bloqueio contra versao errada", True, "Teste interrompido corretamente porque o auren.py local nao atende aos requisitos.")
        return False

    info = discovery[ROOT]
    version = int(info["version"])
    record("Localizacao do Auren", True, str(ROOT))
    record("Versao minima do Auren", version >= MIN_REQUIRED_VERSION, f"auren-v{version}")
    record("Modelo configurado", info["model"] == "gpt-5.6-luna", str(info["model"]))
    record("Versao e cache consistentes", info["cache_version"] == version, f"AUREN_VERSION={version}; CACHE_KEY=auren-v{info['cache_version']}")
    record("Ferramentas Windows presentes na fonte", bool(info["has_tools"]), f"faltando: {info['missing']}" if info["missing"] else "ferramentas Windows encontradas na fonte")
    schema_ok, schema_detail = _source_tool_consistency(source)
    record("Schema e dispatcher das ferramentas", schema_ok, schema_detail)
    bridge_ok = False
    try:
        bridge_tokens = [
            "Add-Type -AssemblyName UIAutomationClient",
            "AutomationElement",
            "InvokePattern",
            "ValuePattern",
            "TogglePattern",
            "SelectionItemPattern",
            "IsPassword",
            "ConvertTo-Json",
            "FromBase64String",
        ]
        source_text = (ROOT / "tools" / "windows.py").read_text(encoding="utf-8", errors="replace")
        bridge_ok = all(token in source_text for token in bridge_tokens)
        record("UI Automation bridge", bridge_ok, "componentes nativos e protecao IsPassword presentes" if bridge_ok else "Faltam componentes obrigatorios do bridge UIA")
    except Exception as exc:
        record("UI Automation bridge", False, repr(exc))
    return version >= MIN_REQUIRED_VERSION and info["cache_version"] == version and info["model"] == "gpt-5.6-luna" and bool(info["has_tools"]) and schema_ok and bridge_ok


def run_smoke_tests() -> None:
    if not layer_enabled("L1"):
        return
    set_layer("L1")
    print("\n=== TESTE AUTOMATICO DAS FERRAMENTAS ===")

    if os.name != "nt" and not layer_enabled("L2"):
        # L1 continua rodando fora do Windows; L2 e o bloco que exige Windows real.
        pass

    try:
        auren = load_auren_module()
        record("Carregamento do Auren", True, "modulo carregado sem excecao")
    except Exception as exc:
        record("Carregamento do Auren", False, repr(exc))
        return

    try:
        from core.task_manager import TaskManager, TaskState
        tm = TaskManager(max_history=10)
        s0 = tm.create("teste de ciclo", chat_id="chat-teste")
        s1 = tm.start()
        s2 = tm.begin_step("teste", "{}")
        s3 = tm.finish_step(success=True, result="ok")
        s4 = tm.complete("concluido")
        ciclo_ok = (
            s0.state == TaskState.CREATED
            and s1.state == TaskState.RUNNING
            and s2.current_step == 1
            and s3.steps[-1].success is True
            and s4.state == TaskState.COMPLETED
            and s4.finished_at
        )
        record("Task Manager: ciclo real de tarefa", ciclo_ok, f"estados={s0.state.value}->{s1.state.value}->{s4.state.value}; passo={s2.current_step}; finalizada={bool(s4.finished_at)}")
    except Exception as exc:
        record("Task Manager: ciclo real de tarefa", False, repr(exc))

    try:
        avancadas = [
            "obter_geometria_janela_windows",
            "mover_janela_windows",
            "redimensionar_janela_windows",
            "restaurar_janela_windows",
        ]
        niveis = {}
        for nome in avancadas:
            niveis[nome] = auren.permission_manager.nivel(nome).value
        ok = all(nivel == "auto" for nivel in niveis.values())
        record("Permissões do controle avançado de janelas", ok, "; ".join(f"{k}={v}" for k, v in niveis.items()))
    except Exception as exc:
        record("Permissões do controle avançado de janelas", False, repr(exc))

    try:
        from core.tool_contracts import DEFAULT_TOOL_CONTRACTS
        declaradas = {str(item.get("name")) for item in getattr(auren, "tools", []) if isinstance(item, dict) and item.get("name")}
        capacidades = set(DEFAULT_TOOL_CONTRACTS.capabilities().values())
        politica = set(auren.permission_manager.policy)
        faltantes = sorted(capacidades - politica)
        ok = not faltantes and not (politica & declaradas)
        detalhe = f"{len(declaradas)} ferramentas; {len(capacidades)} capacidades; faltando={faltantes}"
        record("Cobertura da política de permissões", ok, detalhe)
    except Exception as exc:
        record("Cobertura da política de permissões", False, repr(exc))

    try:
        pm = auren.PermissionManager(max_actions=10)
        counted = {name for name in ("clicar_elemento_windows", "preencher_elemento_windows", "alternar_elemento_windows", "selecionar_elemento_windows") if pm.conta_para_limite(name)}
        ok = (
            not pm.conta_para_limite("inspecionar_interface_windows")
            and len(counted) == 4
        )
        record("Ferramentas UI Automation contadas", ok, "inspecao=leitura; clique/preenchimento/toggle/selecao=contadas")
    except Exception as exc:
        record("Ferramentas UI Automation contadas", False, repr(exc))

    try:
        source_text = (ROOT / "auren.py").read_text(encoding="utf-8", errors="replace")
        windows_source_text = (ROOT / "tools" / "windows.py").read_text(encoding="utf-8", errors="replace")
        uia_source_text = source_text + "\n" + windows_source_text
        pm = auren.PermissionManager(max_actions=10)
        pm.iniciar_tarefa()
        protected_level, protected_reason = pm.nivel_da_acao(
            "preencher_elemento_windows",
            {"alvo": "Campo normal", "_uia_protegido": True},
        )
        record(
            "UIA: IsPassword exige confirmacao",
            protected_level.value == "confirm" and "IsPassword" in protected_reason,
            f"nivel={protected_level.value}; motivo={protected_reason}",
        )
        protected_block_start = uia_source_text.find("if ($item.IsPassword -or $confirmado -ne $textoDesejado)")
        protected_block_end = uia_source_text.find("$resultado = [pscustomobject]", protected_block_start)
        protected_block = uia_source_text[protected_block_start:protected_block_end] if protected_block_start >= 0 and protected_block_end >= 0 else ""
        protected_result_start = uia_source_text.find("$confirmadoProtegidoSemLeitura =")
        protected_result_end = uia_source_text.find("$resultado = [pscustomobject]", protected_result_start)
        protected_result_block = uia_source_text[protected_result_start:protected_result_end] if protected_result_start >= 0 and protected_result_end >= 0 else ""
        guard_pos = protected_block.find("if ($foregroundSeguro -and $physicalClickConfirmed -and $controleFocado)")
        input_match = re.search(r"\[AurenUiWin32\]::Send(?:Text|UnicodeText)\(", protected_block[max(guard_pos, 0):]) if guard_pos >= 0 else None
        input_pos = (max(guard_pos, 0) + input_match.start()) if input_match else -1
        physical_input_guard = (
            guard_pos >= 0
            and input_pos > guard_pos
            and "foregroundSeguro" in protected_block
            and "physicalClickConfirmed" in protected_block
            and "controleFocado" in protected_block
        )
        protected_static = (
            "if (-not [bool]$item.IsPassword) {" in uia_source_text
            and "if ($item.IsPassword -or $confirmado -ne $textoDesejado)" in uia_source_text
            and physical_input_guard
            and "($setValueExecutado -or" not in protected_result_block
            and "$fallbackExecutado" in protected_result_block
            and "$controleFocado" in protected_result_block
            and "$physicalClickConfirmed" in protected_result_block
        )
        record(
            "UIA: protegido usa entrada fisica",
            protected_static,
            "PasswordBox exige foreground + clique fisico + foco confirmado antes de SendInput" if protected_static else "Fluxo protegido ainda permite entrada fisica sem foco confirmado",
        )

        sendkeys_guarded = (guard_pos >= 0 and input_pos > guard_pos)
        preenchimento_start = uia_source_text.find("if ($payload.operacao -eq 'preencher')")
        preflight_end = uia_source_text.find("# O fluxo recomendado para entrada via UI Automation", preenchimento_start)
        preflight_block = uia_source_text[preenchimento_start:preflight_end] if preenchimento_start >= 0 and preflight_end >= 0 else ""
        protected_branch_match = re.search(
            r"if \(-not \[bool\]\$item\.IsPassword\) \{.*?GetCurrentPattern\(\[System\.Windows\.Automation\.ValuePattern\]::Pattern\)",
            uia_source_text[uia_source_text.find("# O fluxo recomendado para entrada via UI Automation"):uia_source_text.find("# O fluxo recomendado para entrada via UI Automation") + 1600],
            re.S,
        )
        protected_no_value_dependency = (
            "if (-not [bool]$item.IsPassword -and -not ($item.Patterns -contains 'Value'))" in uia_source_text
            and bool(protected_branch_match)
        )
        record(
            "UIA: PasswordBox nao depende de ValuePattern",
            protected_no_value_dependency,
            "Caminho protegido usa foco + entrada fisica mesmo sem ValuePattern" if protected_no_value_dependency else "Caminho protegido ainda depende de ValuePattern",
        )
        record(
            "UIA: entrada protegida bloqueada sem foco confirmado",
            sendkeys_guarded,
            "Entrada protegida so roda apos validar foreground, clique fisico e FocusedElement" if sendkeys_guarded else "Entrada protegida pode rodar sem confirmar o controle em foco",
        )


        try:
            memoria_path = Path(tempfile.gettempdir()) / f"AUREN_MEMORIA_TESTE_{os.getpid()}_{int(time.time() * 1000)}.sqlite3"
            if memoria_path.exists():
                memoria_path.unlink()
            store = auren.PersistentMemoryStore(memoria_path)
            salvo = store.salvar("preferencia de teste", "Auren usa memoria local", "teste")
            nova_instancia = auren.PersistentMemoryStore(memoria_path)
            consulta = nova_instancia.consultar("preferencia de teste", 5)
            bloqueio = nova_instancia.salvar("credencial de teste", "token secreto")
            removido = nova_instancia.esquecer("preferencia de teste")
            depois = nova_instancia.consultar("preferencia de teste", 5)
            memoria_ok = (
                salvo.get("ok") is True
                and consulta.get("ok") is True
                and consulta.get("total") == 1
                and consulta["memorias"][0]["valor"] == "Auren usa memoria local"
                and bloqueio.get("ok") is False
                and removido.get("ok") is True
                and depois.get("total") == 0
            )
            record("Memoria persistente local: salva, sobrevive ao reload, bloqueia credencial e esquece", memoria_ok, f"salvo={salvo.get('ok')}; consulta={consulta.get('total')}; bloqueio={bloqueio.get('ok')}; removido={removido.get('ok')}" )

            levels = {
                "salvar_memoria_persistente": pm.nivel("salvar_memoria_persistente").value,
                "consultar_memoria_persistente": pm.nivel("consultar_memoria_persistente").value,
                "esquecer_memoria_persistente": pm.nivel("esquecer_memoria_persistente").value,
            }
            record("Permissoes da memoria persistente", levels == {"salvar_memoria_persistente": "confirm", "consultar_memoria_persistente": "auto", "esquecer_memoria_persistente": "confirm"}, str(levels))

            descricao_confirmacao_ok = "memoria" in pm._descrever_acao(
                "salvar_memoria_persistente",
                {"chave": "teste", "valor": "valor persistente", "categoria": "teste"},
            ).lower()
            record("Permission Manager: descricao de acao confirmavel", descricao_confirmacao_ok, "_descrever_acao executou sem NameError")

            original_store = auren.memory_store
            original_input = builtins.input
            try:
                auren.memory_store = store
                builtins.input = lambda *args, **kwargs: "s"
                salvar_item = types.SimpleNamespace(
                    name="salvar_memoria_persistente",
                    arguments=json.dumps({"chave": "teste dispatcher", "valor": "valor persistente", "categoria": "teste"}, ensure_ascii=False),
                )
                consultar_item = types.SimpleNamespace(
                    name="consultar_memoria_persistente",
                    arguments=json.dumps({"consulta": "teste dispatcher", "limite": 5}, ensure_ascii=False),
                )
                esquecer_item = types.SimpleNamespace(
                    name="esquecer_memoria_persistente",
                    arguments=json.dumps({"chave": "teste dispatcher"}, ensure_ascii=False),
                )
                r_save = auren.executar_ferramenta(salvar_item)
                r_query = auren.executar_ferramenta(consultar_item)
                r_forget = auren.executar_ferramenta(esquecer_item)
                save_text = str(r_save)
                query_text = str(r_query)
                forget_text = str(r_forget)
                dispatcher_ok = (
                    getattr(r_save, "ok", False) is True
                    and "valor persistente" in query_text
                    and getattr(r_query, "ok", False) is True
                    and getattr(r_forget, "ok", False) is True
                )
                record("Memoria persistente: dispatcher completo", dispatcher_ok, f"save={save_text[:180]}; query={query_text[:220]}; forget={forget_text[:180]}")
            finally:
                builtins.input = original_input
                auren.memory_store = original_store
            try:
                memoria_path.unlink()
            except OSError:
                pass
        except Exception as exc:
            record("Memoria persistente local", False, repr(exc))
        pm.registrar_resultado(True, "listar_janelas_windows", {})
        ok = pm.actions_executed == 0 and pm.actions_failed == 0 and pm.actions_attempted == 0
        record("Leituras nao consomem o controle de acoes", ok, f"tentadas={pm.actions_attempted}; executadas={pm.actions_executed}; falhas={pm.actions_failed}")
        parser_cases = {
            "Preenchimento nao confirmado em 'Campo'": False,
            "Volume invalido. Informe 0 a 100.": False,
            "Coordenadas fora da tela.": False,
            "Nao consegui clicar no botao.": False,
            "Nao existe a aba 3. Existem 2 abas abertas.": False,
            "Posicao fora da area de trabalho virtual: (5, 5).": False,
            "Tecla vazia.": False,
            "Nao reconheco a tecla global 'X'.": False,
            "Nao vou encerrar o proprio processo do Auren por PID.": False,
            "Indice de aba invalido.": False,
            "Volume definido para 17%.": True,
        }
        parser_ok = all(auren._resultado_ferramenta_bem_sucedido(texto) == esperado for texto, esperado in parser_cases.items())
        record("Classificacao de falhas das ferramentas", parser_ok, str(parser_cases))
    except Exception as exc:
        record("Leituras nao consomem o controle de acoes", False, repr(exc))

    try:
        exemplo = {
            "input_tokens": 123,
            "token": "SEGREDO_TOKEN",
            "texto": "SEGREDO_TEXTO",
        }
        redigido = harness_module._redact_value(exemplo)
        ok = (
            redigido.get("input_tokens") == 123
            and redigido.get("token") == "[REDACTED]"
            and redigido.get("texto") == "[REDACTED]"
        )
        record(
            "Redaction: chaves exatas e texto sensivel",
            ok,
            str(redigido),
        )
    except Exception as exc:
        record("Redaction: chaves exatas e texto sensivel", False, repr(exc))

    if layer_enabled("L2") and os.name == "nt":
        set_layer("L2")
        try:
            guard = auren.encerrar_processo_windows(pid=os.getpid(), nome="")
            ok = "proprio processo do auren" in guard.lower()
            record("Protecao contra encerrar o proprio Auren por PID", ok, guard, layer="L2")
        except Exception as exc:
            record("Protecao contra encerrar o proprio Auren por PID", False, repr(exc), layer="L2")
        set_layer("L1")

    try:
        literal = auren._powershell_literal("a'b")
        ok = literal == "'a''b'"
        record("Escape seguro de literais PowerShell", ok, literal)
    except Exception as exc:
        record("Escape seguro de literais PowerShell", False, repr(exc))

    try:
        safe_key, _ = auren.permission_manager.nivel_da_acao(
            "pressionar_tecla_windows", {"tecla": "escape"}
        )
        risky_key, _ = auren.permission_manager.nivel_da_acao(
            "pressionar_tecla_windows", {"tecla": "enter"}
        )
        from core.permission_manager import PermissionLevel
        ok = safe_key == PermissionLevel.AUTO and risky_key == PermissionLevel.CONFIRM
        record("Classificação de teclado sensível por caixa", ok, f"escape={safe_key.value}; enter={risky_key.value}")
    except Exception as exc:
        record("Classificação de teclado sensível por caixa", False, repr(exc))

    try:
        nomes_audio = [
            "obter_audio_windows",
            "definir_volume_windows",
            "definir_mudo_windows",
            "controle_midia_windows",
        ]
        politica_audio = {nome: auren.permission_manager.nivel(nome).value for nome in nomes_audio}
        ok = all(nivel == "auto" for nivel in politica_audio.values())
        record("Permissões de audio e midia", ok, "; ".join(f"{k}={v}" for k, v in politica_audio.items()))
    except Exception as exc:
        record("Permissões de audio e midia", False, repr(exc))

    try:
        pm = auren.PermissionManager(max_actions=10)
        leitura = pm.conta_para_limite("obter_audio_windows")
        volume = pm.conta_para_limite("definir_volume_windows")
        mudo = pm.conta_para_limite("definir_mudo_windows")
        midia = pm.conta_para_limite("controle_midia_windows")
        ok = (not leitura and volume and mudo and midia)
        detalhe = f"obter={'contada' if leitura else 'leitura'}; volume={'contada' if volume else 'fora'}; mudo={'contada' if mudo else 'fora'}; midia={'contada' if midia else 'fora'}"
        record("Audio: leitura nao consome e alteracoes contam", ok, detalhe)
    except Exception as exc:
        record("Audio: leitura nao consome e alteracoes contam", False, repr(exc))

    try:
        nomes_uia = [
            "inspecionar_interface_windows",
            "clicar_elemento_windows",
            "preencher_elemento_windows",
            "alternar_elemento_windows",
            "selecionar_elemento_windows",
        ]
        politica_uia = {nome: auren.permission_manager.nivel(nome).value for nome in nomes_uia}
        classificacoes = {
            "inspecao": auren.permission_manager.nivel_da_acao("inspecionar_interface_windows", {"alvo_janela": "", "foco": "", "max_itens": 10})[0].value,
            "clique_normal": auren.permission_manager.nivel_da_acao("clicar_elemento_windows", {"alvo": "abrir"})[0].value,
            "clique_sensivel": auren.permission_manager.nivel_da_acao("clicar_elemento_windows", {"alvo": "excluir"})[0].value,
            "preenchimento_sensivel": auren.permission_manager.nivel_da_acao("preencher_elemento_windows", {"alvo": "senha"})[0].value,
        }
        ok = (
            all(valor == "auto" for valor in politica_uia.values())
            and classificacoes == {
                "inspecao": "auto",
                "clique_normal": "auto",
                "clique_sensivel": "confirm",
                "preenchimento_sensivel": "confirm",
            }
        )
        detalhe = "; ".join(f"{k}={v}" for k, v in {**politica_uia, **classificacoes}.items())
        record("Permissoes e risco da UI Automation", ok, detalhe)
        mouse_level, mouse_reason = auren.permission_manager.nivel_da_acao(
            "clicar_mouse_windows",
            {"x": 10, "y": 10, "botao": "esquerdo", "descricao": "botao Pesquisar"},
        )
        record("Clique por coordenada exige confirmacao", mouse_level.value == "confirm" and "coordenada" in mouse_reason.lower(), f"nivel={mouse_level.value}; motivo={mouse_reason}")
    except Exception as exc:
        record("Permissoes e risco da UI Automation", False, repr(exc))

    if not layer_enabled("L2"):
        return
    if os.name != "nt":
        print("[SKIP] Camada L2 requer Windows real; L0/L1 podem continuar fora do Windows.")
        return
    set_layer("L2")

    try:
        estado_audio = auren.obter_audio_windows()
        audio_ok = estado_audio.startswith("Volume atual:") and "Mudo:" in estado_audio
        record("Audio: leitura do estado", audio_ok, estado_audio)
        if audio_ok:
            match_volume = re.search(r"Volume atual:\s*(\d+)%", estado_audio)
            match_mute = re.search(r"Mudo:\s*(ativado|desativado)", estado_audio)
            original_volume = int(match_volume.group(1)) if match_volume else None
            original_mute = (match_mute.group(1) == "ativado") if match_mute else None

            if original_volume is not None:
                set_same = auren.definir_volume_windows(original_volume)
                read_back = auren.obter_audio_windows()
                same_ok = f"{original_volume}%" in read_back and "Volume atual:" in read_back
                record("Audio: definir volume e confirmar", "Volume definido para" in set_same and same_ok, f"set={set_same}; read={read_back}")

            if original_mute is not None:
                opposite = auren.definir_mudo_windows(not original_mute)
                restore = auren.definir_mudo_windows(original_mute)
                final_audio = auren.obter_audio_windows()
                expected_word = "ativado" if original_mute else "desativado"
                mute_ok = expected_word in final_audio.lower()
                record("Audio: mudo reversivel", "Mudo" in opposite and "Mudo" in restore and mute_ok, f"original={'ativado' if original_mute else 'desativado'}; final={final_audio}")
    except Exception as exc:
        record("Audio: leitura e reversibilidade", False, repr(exc))

    try:
        invalid_volume = auren.definir_volume_windows(101)
        ok = getattr(invalid_volume, "ok", True) is False and "0 a 100" in str(invalid_volume)
        record("Audio: bloqueia volume fora do intervalo", ok, str(invalid_volume))
    except Exception as exc:
        record("Audio: bloqueia volume fora do intervalo", False, repr(exc))

    try:
        chamadas = []
        original_press = auren.windows._pressionar_vk
        auren.windows._pressionar_vk = lambda vk, soltura=False: chamadas.append((vk, soltura)) or True
        midia = auren.controle_midia_windows("play_pause") if os.name == "nt" else ""
        auren.windows._pressionar_vk = original_press
        ok = midia.startswith("Comando de midia enviado") and chamadas == [(0xB3, False), (0xB3, True)]
        record("Midia: play/pause usa tecla global correta", ok, midia or "teste ignorado fora do Windows")
    except Exception as exc:
        try:
            auren.windows._pressionar_vk = original_press
        except Exception:
            pass
        record("Midia: play/pause usa tecla global correta", False, repr(exc))

    try:
        status = auren.obter_status_windows()
        ok = all(token in status for token in ("Hora local:", "Data local:", "RAM:", "Tempo ligado:"))
        record("Status do Windows", ok, status.replace("\n", " | ")[:260])
    except Exception as exc:
        record("Status do Windows", False, repr(exc))

    try:
        janelas = auren.listar_janelas_windows()
        ok = not janelas.lower().startswith("nao consegui") and "Janelas visiveis" in janelas
        record("Listagem de janelas", ok, janelas.splitlines()[0] if janelas else "")
    except Exception as exc:
        record("Listagem de janelas", False, repr(exc))

    original_clipboard = None
    try:
        original = auren.ler_area_transferencia_windows()
        if not original.lower().startswith("nao consegui") and not original.lower().startswith("a area de transferencia nao contem"):
            original_clipboard = original

        marker = "AUREN_TESTE_AUTOMATICO_20260920"
        auren.definir_area_transferencia_windows(marker)
        read_result = auren.ler_area_transferencia_windows()
        ok = read_result == marker
        record("Clipboard: escrever e ler", ok, read_result if ok else f"esperado={marker!r}, recebido={read_result!r}")
    except Exception as exc:
        record("Clipboard: escrever e ler", False, repr(exc))
    finally:
        try:
            if original_clipboard is not None:
                auren.definir_area_transferencia_windows(original_clipboard)
            else:
                auren.definir_area_transferencia_windows("")
        except Exception:
            pass

    try:
        processos = auren.listar_processos_windows()
        ok = "Processos encontrados:" in processos or "Nenhum processo" not in processos
        record("Listagem de processos", ok, processos.splitlines()[0] if processos else "")
    except Exception as exc:
        record("Listagem de processos", False, repr(exc))

    if layer_enabled("L2") and os.name == "nt":
        set_layer("L2")
        try:
            guard = auren.encerrar_processo_windows(nome="explorer.exe")
            ok = "protegido" in guard.lower()
            record("Protecao contra encerrar Explorer", ok, guard, layer="L2")
        except Exception as exc:
            record("Protecao contra encerrar Explorer", False, repr(exc), layer="L2")

        try:
            guard = auren.encerrar_processo_windows(nome="*")
            ok = "curingas" in guard.lower()
            record("Protecao contra curingas em taskkill", ok, guard, layer="L2")
        except Exception as exc:
            record("Protecao contra curingas em taskkill", False, repr(exc), layer="L2")
        set_layer("L1")

    try:
        import ctypes
        user32 = ctypes.windll.user32
        x = user32.GetSystemMetrics(0) // 2
        y = user32.GetSystemMetrics(1) // 2
        moved = auren.mover_mouse_windows(x, y)
        record("Mouse global: mover", "movido" in moved.lower(), moved)
    except Exception as exc:
        record("Mouse global: mover", False, repr(exc))

    try:
        pressed = auren.pressionar_tecla_windows("escape")
        record("Teclado global: Escape", "pression" in pressed.lower(), pressed)
    except Exception as exc:
        record("Teclado global: Escape", False, repr(exc))

    try:
        before = _window_snapshot(auren)
        before_hwnds = {hwnd for hwnd, _ in before}

        opened = auren.abrir_programa("notepad.exe")
        record("Abrir Notepad", "aberto" in opened.lower(), opened)
        janela_teste = _find_new_notepad_window(auren, before_hwnds)

        if not janela_teste:
            record("Janela Notepad isolada", False, "Nao surgiu uma nova janela do Notepad; o teste nao vai tocar em uma janela preexistente.")
        else:
            _hwnd_teste, titulo_teste = janela_teste
            record("Janela Notepad isolada", True, titulo_teste)

            focused = auren.focar_janela_windows(titulo_teste)
            record("Focar Notepad", "janela ativada" in focused.lower(), focused)

            moved = auren.mover_janela_windows(titulo_teste, 120, 140)
            record("Mover Notepad", "janela movida" in moved.lower(), moved)

            resized = auren.redimensionar_janela_windows(titulo_teste, 800, 500)
            record("Redimensionar Notepad", "janela redimensionada" in resized.lower(), resized)

            geometry = auren.obter_geometria_janela_windows(titulo_teste)
            geometry_ok = all(token in geometry for token in ("Posicao:", "Tamanho:", "800x500"))
            record("Geometria do Notepad", geometry_ok, geometry.replace("\n", " | "))

            minimized = auren.minimizar_janela_windows(titulo_teste)
            record("Minimizar Notepad", "minimizada" in minimized.lower(), minimized)

            maximized = auren.maximizar_janela_windows(titulo_teste)
            record("Maximizar Notepad", "maximizada" in maximized.lower(), maximized)

            restored = auren.restaurar_janela_windows(titulo_teste)
            record("Restaurar Notepad", "janela restaurada" in restored.lower(), restored)

            geometry_after_restore = auren.obter_geometria_janela_windows(titulo_teste)
            restore_ok = "Estado: normal" in geometry_after_restore
            record("Notepad restaurado ao estado normal", restore_ok, geometry_after_restore.replace("\n", " | "))

            janela = auren._encontrar_janela_windows(titulo_teste)
            if janela:
                hwnd, _titulo = janela
                import ctypes
                user32 = ctypes.windll.user32
                rect = wintypes.RECT()
                if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    cx = (rect.left + rect.right) // 2
                    cy = (rect.top + rect.bottom) // 2
                    clicked = auren.clicar_mouse_windows(cx, cy, "esquerdo", "area vazia da janela isolada criada pelo teste")
                    record("Mouse global: clique seguro", "clique global executado" in clicked.lower(), clicked)
                else:
                    record("Mouse global: clique seguro", False, "Nao consegui obter o retangulo do Notepad isolado")
            else:
                record("Mouse global: clique seguro", False, "Nao encontrei a janela isolada do Notepad")

            closed = auren.fechar_janela_windows(titulo_teste)
            record("Fechar Notepad", "solicitei o fechamento" in closed.lower(), closed)
    except Exception as exc:
        record("Ciclo de janela controlada", False, repr(exc))






    _testar_ui_automation_local(auren)

def _rodar_janela_controle_de_teste():
    import shutil as _shutil
    titulo = f"AUREN_JANELA_CONTROLE_TESTE_{int(time.time_ns())}"
    script = r'''Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
$title = '__TITLE__'
$window = New-Object System.Windows.Window
$window.Title = $title
$window.Width = 640
$window.Height = 360
$window.WindowStartupLocation = 'CenterScreen'
$text = New-Object System.Windows.Controls.TextBlock
$text.Text = 'AUREN WINDOW CONTROL TEST'
$text.Margin = '20'
$text.FontSize = 20
$window.Content = $text
$window.ShowDialog() | Out-Null
'''.replace('__TITLE__', titulo)
    script_path = Path(tempfile.gettempdir()) / f"auren_window_control_{int(time.time_ns())}.ps1"
    script_path.write_text(script, encoding='utf-8')
    powershell = _shutil.which('powershell.exe') or _shutil.which('powershell')
    if not powershell:
        return None, None, None, 'Windows PowerShell nao encontrado.'
    try:
        proc = subprocess.Popen(
            [powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc, script_path, titulo, None
    except Exception as exc:
        try:
            script_path.unlink()
        except OSError:
            pass
        return None, None, None, repr(exc)

def _rodar_janela_uia_de_teste():
    import shutil as _shutil
    titulo = f"AUREN_UIA_TESTE_{int(time.time_ns())}"
    script = r'''Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
$title = '__TITLE__'
$xaml = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Title="__TITLE__" Width="520" Height="430" WindowStartupLocation="CenterScreen">
  <StackPanel Margin="20">
    <TextBlock x:Name="Status" Text="PRONTO" Margin="0,0,0,12" FontSize="18"/>
    <TextBox x:Name="Campo" AutomationProperties.Name="Campo de Teste" Width="420" Margin="0,0,0,10"/>
    <PasswordBox x:Name="Senha" AutomationProperties.Name="Senha de Teste" Password="SEGREDO_UIA_TESTE" Width="420" Margin="0,0,0,10"/>
    <TextBlock x:Name="SenhaStatus" AutomationProperties.Name="Status Senha" Text="SENHA_PRONTA" Margin="0,0,0,4"/>
    <TextBlock x:Name="SenhaTelemetria" AutomationProperties.Name="Telemetria Senha" Text="key_down=0;text_input=0;got_focus=0;lost_focus=0;mouse_down=0;mouse_up=0;password_changed=0" Margin="0,0,0,10"/>
    <Button x:Name="Botao" AutomationProperties.Name="Botao Auren Teste" Content="Clique aqui" Width="180" Margin="0,0,0,10"/>
    <CheckBox x:Name="Check" AutomationProperties.Name="Check Auren Teste" Content="Marcar teste" Margin="0,0,0,10"/>
    <ListBox x:Name="Lista" AutomationProperties.Name="Lista Auren Teste" Height="90" Width="420">
      <ListBoxItem AutomationProperties.Name="Opcao Um">Opcao Um</ListBoxItem>
      <ListBoxItem AutomationProperties.Name="Opcao Dois">Opcao Dois</ListBoxItem>
    </ListBox>
  </StackPanel>
</Window>
'@
$window = [Windows.Markup.XamlReader]::Parse($xaml)
$status = $window.FindName('Status')
$senhaStatus = $window.FindName('SenhaStatus')
$senhaTelemetria = $window.FindName('SenhaTelemetria')
$senha = $window.FindName('Senha')
$botao = $window.FindName('Botao')
$check = $window.FindName('Check')
$lista = $window.FindName('Lista')
$script:SenhaKeyDown = 0
$script:SenhaTextInput = 0
$script:SenhaGotFocus = 0
$script:SenhaLostFocus = 0
$script:SenhaMouseDown = 0
$script:SenhaMouseUp = 0
$script:SenhaPasswordChanged = 0
function Update-SenhaTelemetry {
  $telemetria = "key_down=$script:SenhaKeyDown;text_input=$script:SenhaTextInput;got_focus=$script:SenhaGotFocus;lost_focus=$script:SenhaLostFocus;mouse_down=$script:SenhaMouseDown;mouse_up=$script:SenhaMouseUp;password_changed=$script:SenhaPasswordChanged"
  $senhaTelemetria.Text = $telemetria
  [System.Windows.Automation.AutomationProperties]::SetName($senhaTelemetria, "Telemetria Senha | $telemetria")
}
$senha.Add_PreviewKeyDown({ $script:SenhaKeyDown++; Update-SenhaTelemetry })
$senha.Add_PreviewTextInput({ $script:SenhaTextInput++; Update-SenhaTelemetry })
$senha.Add_GotKeyboardFocus({ $script:SenhaGotFocus++; Update-SenhaTelemetry })
$senha.Add_LostKeyboardFocus({ $script:SenhaLostFocus++; Update-SenhaTelemetry })
$senha.Add_PreviewMouseDown({ $script:SenhaMouseDown++; Update-SenhaTelemetry })
$senha.Add_PreviewMouseUp({ $script:SenhaMouseUp++; Update-SenhaTelemetry })
$senha.Add_PasswordChanged({ $script:SenhaPasswordChanged++; $senhaStatus.Text = 'PASSWORD_CHANGED'; Update-SenhaTelemetry })
Update-SenhaTelemetry
$botao.Add_Click({ $status.Text = 'BOTAO_CLICADO' })
$check.Add_Checked({ $status.Text = 'CHECK_MARCADO' })
$check.Add_Unchecked({ $status.Text = 'CHECK_DESMARCADO' })
$lista.Add_SelectionChanged({ if ($lista.SelectedItem) { $status.Text = 'SELECIONADO:' + $lista.SelectedItem.Content } })
$window.ShowDialog() | Out-Null
'''.replace('__TITLE__', titulo)
    script_path = Path(tempfile.gettempdir()) / f"auren_uia_window_{int(time.time_ns())}.ps1"
    script_path.write_text(script, encoding='utf-8')
    powershell = _shutil.which('powershell.exe') or _shutil.which('powershell')
    if not powershell:
        return None, None, None, 'Windows PowerShell nao encontrado.'
    proc = subprocess.Popen([powershell, '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-STA', '-File', str(script_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    return proc, script_path, titulo, None


def _testar_ui_automation_local(auren):
    set_layer("L2")
    print('\n=== TESTE LOCAL: UI AUTOMATION DO WINDOWS ===')
    if os.name != 'nt':
        record('UI Automation local', True, 'Teste real sera executado no Windows do usuario.')
        return
    proc = script_path = titulo = None
    try:
        proc, script_path, titulo, erro = _rodar_janela_uia_de_teste()
        if erro:
            record('Preparacao da janela UI Automation', False, erro)
            return
        janela = next((item for item in _window_snapshot(auren) if item[1] == titulo), None)
        if not janela:
            time.sleep(1)
            janela = next((item for item in _window_snapshot(auren) if item[1] == titulo), None)
        record('Preparacao da janela UI Automation', bool(janela), titulo if janela else 'Janela de teste nao encontrada')
        if not janela:
            return

        inspecao = auren.inspecionar_interface_windows(titulo, '', 60)
        if inspecao.startswith('Nao consegui inspecionar a interface'):
            record('UIA: smoke test do bridge', False, inspecao[:1600])
            return
        record('UIA: smoke test do bridge', True, 'Bridge retornou a arvore inicial da janela.')
        ok = all(x in inspecao for x in ('Campo de Teste','Senha de Teste','Botao Auren Teste','Check Auren Teste','Opcao Um','Opcao Dois'))
        record('UIA: inspecionar controles', ok, inspecao[:1200])
        foco_botao = auren.inspecionar_interface_windows(titulo, 'botao Botao Auren Teste', 5)
        record('UIA: busca semantica por tipo e nome', 'Botao Auren Teste' in foco_botao and 'tipo=Button' in foco_botao, foco_botao[:500])
        foco_tipo = auren.inspecionar_interface_windows(titulo, 'botao', 10)
        record('UIA: filtro por tipo', 'tipo=Button' in foco_tipo and 'tipo=Edit' not in foco_tipo, foco_tipo[:700])
        senha_segura = ('SEGREDO_UIA_TESTE' not in inspecao) and ('protegido=True' in inspecao)
        record('UIA: protege conteudo de senha', senha_segura, 'Conteudo secreto nao foi exposto pelo inspetor.' if senha_segura else inspecao[:1400])

        # PasswordBox continua sendo uma capacidade protegida do Auren,
        # mas a regressao funcional nao executa preenchimento real de senha.
        # O objetivo desta bateria e validar que o segredo nao e exposto e
        # que o caminho protegido continua exigindo confirmacao; nao testar
        # entrada efetiva em um campo de senha.
        r = auren.preencher_elemento_windows(titulo, 'Campo de Teste', 'AUREN_V42_UIA', 1)
        record('UIA: preencher campo', _ui_preenchimento_confirmado(r, 'Campo'), r)
        r2 = auren.inspecionar_interface_windows(titulo, 'Campo de Teste', 5)
        record('UIA: confirmar valor preenchido', 'AUREN_V42_UIA' in r2, r2[:600])

        r = auren.clicar_elemento_windows(titulo, 'Botao Auren Teste', 1)
        record('UIA: clicar botao', 'Clique executado' in r, r)
        r2 = auren.inspecionar_interface_windows(titulo, 'BOTAO_CLICADO', 5)
        record('UIA: confirmar clique', _ui_inspecao_confirmou_texto(r2, 'BOTAO_CLICADO'), r2[:400])

        r = auren.alternar_elemento_windows(titulo, 'Check Auren Teste', 1)
        record('UIA: alternar checkbox', 'Estado alternado' in r and 'On' in r, r)
        r2 = auren.inspecionar_interface_windows(titulo, 'Check Auren Teste', 5)
        record('UIA: confirmar checkbox', 'toggle=On' in r2, r2[:400])

        r = auren.selecionar_elemento_windows(titulo, 'Opcao Dois', 1)
        record('UIA: selecionar item', 'Elemento selecionado' in r, r)
        r2 = auren.inspecionar_interface_windows(titulo, 'Opcao Dois', 5)
        record('UIA: confirmar selecao', 'selected=True' in r2, r2[:400])
        r = auren.clicar_elemento_windows(titulo, 'Opcao Dois', 1)
        ambiguidade_ou_escolha = ('Alvo ambiguo' in r) or ('Clique executado' in r and 'Opcao Dois' in r)
        record('UIA: empate de controles e tratado', ambiguidade_ou_escolha, r)

        r = auren.clicar_elemento_windows(titulo, 'Controle Que Nao Existe AUREN', 1)
        record('UIA: recusar alvo inexistente', 'Nao consegui clicar' in r and 'Nao encontrei' in r, r)
    except Exception as exc:
        record('UI Automation local', False, repr(exc))
    finally:
        try:
            if titulo:
                auren.fechar_janela_windows(titulo)
        except Exception:
            pass
        time.sleep(0.3)
        try:
            if proc is not None and proc.poll() is None:
                proc.terminate()
        except Exception:
            pass
        try:
            if script_path:
                script_path.unlink()
        except OSError:
            pass


def _testes_estaticos_v42() -> None:
    set_layer("L0")
    fonte_auren = (ROOT / "auren.py").read_text(encoding="utf-8", errors="replace")
    fonte_prompt = (ROOT / "core" / "prompt.py").read_text(encoding="utf-8", errors="replace")
    fonte_harness = (ROOT / "core" / "harness.py").read_text(encoding="utf-8", errors="replace")
    fonte_pm = (ROOT / "core" / "permission_manager.py").read_text(encoding="utf-8", errors="replace")
    match_versao = re.search(r"AUREN_VERSION\s*=\s*(\d+)", fonte_auren)
    versao = int(match_versao.group(1)) if match_versao else -1
    prompt_ok = (
        bool(re.search(rf"versao tecnica Auren {versao}\b", fonte_auren, re.IGNORECASE))
        or bool(re.search(rf"versao tecnica Auren {versao}\b", fonte_prompt, re.IGNORECASE))
    ) and versao >= MIN_REQUIRED_VERSION
    record("Prompt e versao sincronizados", prompt_ok, f"AUREN_VERSION={versao}; prompt={'ok' if prompt_ok else 'incompativel'}")
    config_arquivo_versao = None
    try:
        config_text = (ROOT / "config.py").read_text(encoding="utf-8", errors="replace")
        m = re.search(r"AUREN_VERSION\s*=\s*(\d+)", config_text)
        config_arquivo_versao = int(m.group(1)) if m else None
    except Exception:
        pass
    metadata_ok = config_arquivo_versao == versao == TEST_SUITE_VERSION
    record("Metadados V46 sincronizados", metadata_ok, f"AUREN_VERSION={versao}; config={config_arquivo_versao}; tester={TEST_SUITE_VERSION}")
    record("Loop principal isola excecao por tarefa", "TASK_EXCEPTION" in fonte_harness or "except Exception" in fonte_harness)
    record("Confirmacao de preenchimento mascara texto", all(t in fonte_pm for t in ("preencher_elemento_windows", '"texto"', '"conteudo"')))
    record("Clique por coordenada nao falha aberto", "Clique global por coordenada exige confirmacao" in fonte_pm)
    fonte_facade = (ROOT / "core" / "facade.py").read_text(encoding="utf-8", errors="replace")
    fonte_windows = (ROOT / "tools" / "windows.py").read_text(encoding="utf-8", errors="replace")
    record("Cache de identidade de janela presente", "_WINDOW_TARGET_CACHE" in fonte_facade and "_encontrar_janela_windows_sem_cache" in fonte_facade and "_WINDOW_TARGET_CACHE" in fonte_windows)
    record("Memoria persistente declarada", all(t in fonte_auren for t in ("salvar_memoria_persistente", "consultar_memoria_persistente", "esquecer_memoria_persistente", "PersistentMemoryStore")))
    memoria_permissoes_ok = all(
        t in fonte_pm for t in (
            '"memory.write": PermissionLevel.CONFIRM',
            '"memory.read": PermissionLevel.AUTO',
        )
    )
    record("Permissoes da memoria persistente declaradas", memoria_permissoes_ok)
    memory_log_ok = all(t in fonte_harness for t in ("_redact_value", "SENSITIVE_KEYS", "_compact_json"))
    record("Logs aplicam redacao de dados sensiveis", memory_log_ok)
    log_structure_ok = all(
        token in fonte_harness for token in (
            "CHAT_LOGS_DIR",
            "logs/chats/<chat_id>/chat/chat.log",
            "def start_chat_session",
            "def end_chat_session",
            "CHAT_START",
            "CHAT_END",
        )
    )
    record("Logs possuem sessao por chat", log_structure_ok)
    untrusted_data_ok = all(t in (Path(ROOT / "core" / "harness.py").read_text(encoding="utf-8", errors="replace") + Path(ROOT / "core" / "prompt.py").read_text(encoding="utf-8", errors="replace")) for t in (
        "DADOS NAO CONFIAVEIS",
        "Conteudo lido de paginas WEB e DADOS NAO CONFIAVEIS",
    )) or ("CONTEUDO" in fonte_auren and "WEB" in fonte_auren)
    record("Protecao contra instrucoes vindas de dados externos", untrusted_data_ok)

    fonte_task_manager = (ROOT / "core" / "task_manager.py").read_text(encoding="utf-8", errors="replace")
    task_manager_ok = all(token in fonte_task_manager for token in (
        "class TaskManager",
        "class TaskState",
        'TaskState.CREATED',
        'TaskState.RUNNING',
        'TaskState.WAITING',
        'TaskState.COMPLETED',
        'TaskState.FAILED',
        'TaskState.CANCELLED',
        "request_cancel",
        "snapshot",
    ))
    record("Task Manager P0.1 presente", task_manager_ok)
    task_manager_harness_ok = all(token in fonte_harness for token in (
        "from core.task_manager import TaskManager, TaskState",
        "self.task_manager = task_manager or TaskManager()",
        "def current_task(self)",
        "def cancel_current_task(self",
        "self.task_manager.begin_step",
        "self.task_manager.finish_step",
    ))
    record("Harness integrado ao Task Manager", task_manager_harness_ok)

    fonte_contracts = (ROOT / "core" / "tool_contracts.py").read_text(encoding="utf-8", errors="replace")
    contracts_ok = all(token in fonte_contracts for token in (
        "class ToolContract",
        "class ToolContractRegistry",
        "DEFAULT_TOOL_CONTRACTS",
        "validate_tool_arguments",
        "capability",
    ))
    record("Contratos genericos P0.2 presentes", contracts_ok, "ToolContract/Registry/validate/capability encontrados" if contracts_ok else "faltam componentes do contrato")

    from core.tools_registry import tools as _tools_registry
    from core.tool_contracts import DEFAULT_TOOL_CONTRACTS, validate_tool_arguments
    contracts_runtime_ok = (
        len(DEFAULT_TOOL_CONTRACTS.names()) == len(_tools_registry) == 49
        and set(DEFAULT_TOOL_CONTRACTS.names()) == {item["name"] for item in _tools_registry}
        and validate_tool_arguments("listar_janelas_windows", {})[0]
        and not validate_tool_arguments("mover_mouse_windows", {"x": "960", "y": 540})[0]
        and not validate_tool_arguments("navegar_navegador", {"url": "x", "modo": "invalido"})[0]
    )
    record("Contratos P0.2 alinhados às 45 ferramentas", contracts_runtime_ok)

    legacy_files_removed = all(
        not (ROOT / rel).exists()
        for rel in ("harness.py", "permission_manager.py", "memory_store.py", "tests/testes_auren.py")
    )
    legacy_imports = []
    for rel in ("auren.py", "core", "tools"):
        base = ROOT / rel
        if base.is_file():
            files_to_scan = [base]
        else:
            files_to_scan = list(base.rglob("*.py")) if base.exists() else []
        for py in files_to_scan:
            text = py.read_text(encoding="utf-8", errors="replace")
            for legacy in ("from harness import", "from permission_manager import", "from memory_store import"):
                if legacy in text:
                    legacy_imports.append(f"{py.name}:{legacy}")
    legacy_files_ok = legacy_files_removed and not legacy_imports
    record("Limpeza: shims e tester duplicado removidos", legacy_files_ok, f"arquivos_legados={not legacy_files_removed}; imports_legados={legacy_imports}")

    fonte_dispatcher = (ROOT / "tools" / "dispatcher.py").read_text(encoding="utf-8", errors="replace")
    handler_registry_ok = all(token in fonte_dispatcher for token in (
        "TOOL_HANDLERS",
        "validar_registry_handlers",
        "def executar_ferramenta",
    )) and "elif item.name ==" not in fonte_dispatcher
    record("Dispatcher P0.3 usa registry de handlers", handler_registry_ok)

    capability_policy_ok = (
        "CAPABILITY_POLICY" in fonte_pm
        and "COUNTED_CAPABILITIES" in fonte_pm
        and "capability_for_tool" in fonte_pm
        and "self.policy: dict[str, PermissionLevel]" in fonte_pm
    )
    record("Permissoes P0.3 centralizadas por capacidade", capability_policy_ok)

    facade_source = ROOT / "core" / "facade.py"
    facade_cleanup_ok = facade_source.exists() and "from core.facade import" in fonte_auren and fonte_auren.count("def ") <= 12
    record("Limpeza: facade de ferramentas retirado do auren.py", facade_cleanup_ok, f"defs_auren={fonte_auren.count('def ')}")


def run_model_suite() -> None:
    live_layers = [layer for layer in ("L4", "L5") if layer_enabled(layer)]
    for live_layer in live_layers:
        set_layer(live_layer)
        _run_model_suite_layer(live_layer)


def _run_model_suite_layer(suite_layer: str) -> None:
    global INTEGRATION_CHAT_LOG, INTEGRATION_CHAT_LOG_PATH
    source = ROOT / "auren.py"
    compatible_path, _ = find_auren()
    if compatible_path is None:
        record("Localizacao do Auren para teste integrado", False, "auren.py compativel nao encontrado")
        return

    print("\n=== TESTE INTEGRADO: MODELO + FERRAMENTAS ===")
    print("Este bloco usa a API do Auren e pode abrir/fechar janelas e abas conforme os comandos.")

    integration_proc, integration_script_path, titulo_janela, integration_setup_error = _rodar_janela_controle_de_teste()
    uia_proc = None
    uia_script_path = None
    uia_titulo = None
    if integration_setup_error:
        record("Preparacao de janela de controle integrada", False, integration_setup_error)
        return

    commands_file = Path(tempfile.gettempdir()) / "auren_regressao_comandos.txt"
    auren_for_setup = load_auren_module()
    titulo_confirmado = None
    prazo = time.time() + 6
    while time.time() < prazo and titulo_confirmado is None:
        snapshot = _window_snapshot(auren_for_setup)
        for _hwnd, titulo in snapshot:
            if titulo.casefold() == titulo_janela.casefold():
                titulo_confirmado = titulo
                break
        time.sleep(0.25)

    if not titulo_confirmado:
        record("Preparacao de janela de controle integrada", False, f"Nao localizei a janela '{titulo_janela}'")
        try:
            if integration_proc is not None and integration_proc.poll() is None:
                integration_proc.terminate()
        except Exception:
            pass
        try:
            if integration_script_path:
                integration_script_path.unlink()
        except OSError:
            pass
        return

    titulo_janela = titulo_confirmado
    record("Preparacao de janela de controle integrada", True, titulo_janela)

    uia_bridge_ok = False
    try:
        uia_proc, uia_script_path, uia_titulo, uia_erro = _rodar_janela_uia_de_teste()
        if uia_erro:
            record("Preparacao da janela UI Automation integrada", False, uia_erro)
            uia_titulo = None
        else:
            uia_for_setup = load_auren_module()
            prazo_uia = time.time() + 4
            while time.time() < prazo_uia:
                if any(item[1] == uia_titulo for item in _window_snapshot(uia_for_setup)):
                    break
                time.sleep(0.25)
            uia_ok = any(item[1] == uia_titulo for item in _window_snapshot(uia_for_setup))
            record("Preparacao da janela UI Automation integrada", uia_ok, uia_titulo if uia_ok else "Janela de teste nao encontrada")
            if not uia_ok:
                uia_titulo = None
            else:
                # Smoke test unico antes de incluir varias tarefas UIA na bateria integrada.
                smoke = uia_for_setup.inspecionar_interface_windows(uia_titulo, '', 20)
                uia_bridge_ok = not smoke.startswith('Nao consegui inspecionar a interface')
                record("UIA integrado: smoke test do bridge", uia_bridge_ok, smoke[:1200])
                if not uia_bridge_ok:
                    uia_titulo = None
    except Exception as exc:
        record("Preparacao da janela UI Automation integrada", False, repr(exc))
        uia_titulo = None

    # O teste de volume usa o valor atual como alvo para nao alterar o estado
    # do computador do usuario de forma permanente.
    original_audio_volume = None
    original_audio_mute = None
    try:
        estado_inicial_audio = auren_for_setup.obter_audio_windows()
        match_volume = re.search(r"Volume atual:\s*(\d+)%", estado_inicial_audio)
        match_mute = re.search(r"Mudo:\s*(ativado|desativado)", estado_inicial_audio)
        if match_volume:
            original_audio_volume = int(match_volume.group(1))
        if match_mute:
            original_audio_mute = match_mute.group(1) == "ativado"
    except Exception:
        pass

    audio_volume_command = (
        f"defina o volume para {original_audio_volume} por cento"
        if original_audio_volume is not None
        else "qual e o volume do computador agora?"
    )

    # Comandos integrados sao classificados por gatilho de modelo.
    # L4 = comportamentos representativos/decisao real do modelo.
    # L5 = regressao live extensa, usada antes de congelar uma versao.
    command_specs = [
        ("model", "qual seu modelo?", "L4"),
        ("time", "que horas sao?", "L5"),
        ("ram", "quanto da minha memoria ram esta sendo usada?", "L5"),
        ("uptime", "a quanto tempo o computador esta ligado?", "L5"),
        ("audio_read", "qual e o volume do computador agora?", "L5"),
        ("audio_set", audio_volume_command, "L4"),
        ("audio_mute", "qual e o estado atual do mudo?", "L5"),
        ("window_list", "liste as janelas abertas", "L5"),
        ("window_minimize", f"minimize a janela {titulo_janela}", "L5"),
        ("window_maximize", f"maximize a janela {titulo_janela}", "L4"),
        ("window_restore", f"restaure a janela {titulo_janela}", "L5"),
        ("window_move", f"mova a janela {titulo_janela} para 120 por 140", "L4"),
        ("window_resize", f"redimensione a janela {titulo_janela} para 800 por 500", "L5"),
        ("window_geometry", f"qual a posicao e o tamanho da janela {titulo_janela}?", "L5"),
        ("clipboard_set", "coloque AUREN_TESTE_CLIPBOARD_INTEGRADO na minha area de transferencia", "L4"),
        ("clipboard_read", "o que esta na minha area de transferencia?", "L4"),
        ("processes", "liste os processos", "L5"),
        ("mouse", "mova o mouse para o centro da tela", "L5"),
        ("escape", "pressione Escape", "L5"),
        ("window_close", f"feche a janela {titulo_janela}", "L5"),
        ("tabs_reset_before", "feche todas as abas", "L4"),
        ("tabs_github", "abra o github", "L4"),
        ("tabs_new", "abra duas abas", "L4"),
        ("tabs_flow", "abra o discord na segunda aba e o youtube na terceira aba", "L4"),
        ("tabs_reset_after", "feche todas as abas", "L4"),
        ("youtube", "abra o youtube", "L5"),
        ("browser_verify_navigation", "abra o youtube e depois confirme a URL e o titulo da pagina atual", "L4"),
        ("browser_verify_scroll", "na pagina do youtube, role para baixo e confirme a posicao atual da pagina", "L5"),
    ]
    if uia_titulo:
        command_specs.extend([
            ("uia_inspect", f"inspecione a interface da janela {uia_titulo} e diga quais controles existem", "L4"),
            ("uia_fill", f"preencha o campo Campo de Teste da janela {uia_titulo} com AUREN_UIA_INTEGRADO_V42", "L4"),
            ("uia_fill_readback", f"inspecione a interface da janela {uia_titulo} procurando Campo de Teste", "L4"),
            ("uia_click", f"clique no botao Botao Auren Teste da janela {uia_titulo}", "L4"),
            ("uia_click_readback", f"inspecione a interface da janela {uia_titulo} procurando BOTAO_CLICADO", "L4"),
            ("uia_checkbox", f"marque a caixa Check Auren Teste da janela {uia_titulo}", "L4"),
            ("uia_select", f"selecione a Opcao Dois na janela {uia_titulo}", "L5"),
        ])

    selected_specs = [spec for spec in command_specs if spec[2] == suite_layer]
    enabled_keys = {key for key, _cmd, _layer in selected_specs}
    commands = [cmd for _key, cmd, _layer in selected_specs]

    if suite_layer == "L4" and not commands:
        return
    if suite_layer == "L5" and not commands:
        return

    commands_file.write_text("\n".join(commands + ["sair"]) + "\n", encoding="utf-8")

    def command_enabled(key: str) -> bool:
        return key in enabled_keys

    logs_root = ROOT / "logs"
    test_started_ns = time.time_ns()

    def restore_original_audio_state():
        try:
            if original_audio_volume is None and original_audio_mute is None:
                return
            cleanup_audio = load_auren_module()
            if original_audio_volume is not None:
                cleanup_audio.definir_volume_windows(original_audio_volume)
            if original_audio_mute is not None:
                cleanup_audio.definir_mudo_windows(original_audio_mute)
        except Exception:
            pass

    try:
        env = os.environ.copy()
        env["AUREN_TEST_MODE"] = "1"
        with commands_file.open("r", encoding="utf-8") as comandos_entrada:
            proc = subprocess.run(
                [sys.executable, "-u", str(ROOT / "auren.py")],
                cwd=ROOT,
                stdin=comandos_entrada,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=240,
                env=env,
            )
        output = proc.stdout
        record("Execucao integrada terminou", proc.returncode == 0, f"codigo={proc.returncode}")
        # A janela dedicada e finalizada no bloco finally abaixo.

        # O Auren atual escreve cada conversa em logs/chats/<chat_id>/chat/chat.log.
        # O antigo logs/auren.log pode ser apenas historico de sessoes anteriores.
        # Para evitar falsos FAILs, usamos a conversa mais recente criada/modificada
        # depois do inicio deste teste.
        chat_logs = list((logs_root / "chats").glob("*/chat/chat.log")) if (logs_root / "chats").exists() else []

        def _chat_start_ns(path: Path) -> int | None:
            try:
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:3]:
                    match = re.match(r"^\[(?P<timestamp>[^\]]+)\] CHAT_START$", line)
                    if not match:
                        continue
                    return int(datetime.fromisoformat(match.group("timestamp")).timestamp() * 1_000_000_000)
            except Exception:
                return None
            return None

        current_chat_logs = []
        for candidate in chat_logs:
            if not candidate.exists():
                continue
            started_ns = _chat_start_ns(candidate)
            if started_ns is None:
                continue
            if started_ns >= test_started_ns - 2_000_000_000:
                current_chat_logs.append((started_ns, candidate))

        if current_chat_logs:
            _, log_path = max(current_chat_logs, key=lambda item: item[0])
            appended = log_path.read_text(encoding="utf-8", errors="replace")
            INTEGRATION_CHAT_LOG_PATH = log_path
            INTEGRATION_CHAT_LOG = appended
        else:
            log_path = None
            appended = ""
            INTEGRATION_CHAT_LOG_PATH = None
            INTEGRATION_CHAT_LOG = ""

        restore_original_audio_state()

        if log_path is not None and appended:
            def _parse_task_blocks(text: str) -> list[str]:
                pattern = re.compile(
                    r'(?ms)^\[\d{4}-\d{2}-\d{2}T[^\n]+\] TASK_START\n.*?(?=^\[\d{4}-\d{2}-\d{2}T[^\n]+\] TASK_START\n|^\[\d{4}-\d{2}-\d{2}T[^\n]+\] CHAT_END\n|\Z)'
                )
                return [m.group(0) for m in pattern.finditer(text)]

            parsed_task_blocks = _parse_task_blocks(appended)
            leaked_sensitive_values = [secret for secret in (
                "AUREN_TESTE_CLIPBOARD_INTEGRADO",
                "AUREN_UIA_INTEGRADO_V42",
                "AUREN_UIA_INTEGRADO_V42",
                "AUREN_SENHA_CONFIRMADA_V42",
            ) if secret in appended]
            record("Logs integrados nao vazam conteudo sensivel", not leaked_sensitive_values, f"valores_em_claro={leaked_sensitive_values}")

            def task_blocks(objective_fragment: str) -> list[str]:
                alvo = str(objective_fragment or "").strip().casefold()
                if not alvo:
                    return []
                return [
                    block for block in parsed_task_blocks
                    if alvo in block.casefold()
                ]

            def task_block(objective_fragment: str, occurrence: str = "last") -> str:
                blocks = task_blocks(objective_fragment)
                if not blocks:
                    return ""
                return blocks[-1] if occurrence == "last" else blocks[0]

            def tool_call_anywhere(tool_name: str) -> bool:
                pattern = re.compile(
                    rf'(?ms)^\[[^\n]+\] TOOL_CALL\n(?:  [^\n]*\n)*?  ferramenta: "{re.escape(tool_name)}"(?:\n|$)'
                )
                return bool(pattern.search(appended))

            if command_enabled("model"):
                model_block = task_block("qual seu modelo?")
                model_output_ok = bool(re.search(r'output_text: ".*GPT-5\.6 Luna.*"', model_block, re.IGNORECASE))
                model_tool_free = "TOOL_CALL" not in model_block
                model_task_done = 'estado: "completed"' in model_block or 'status: "fast_path"' in model_block
                model_ok = model_output_ok and model_tool_free and model_task_done
                record("Modelo correto", model_ok, f"output_model={model_output_ok}; sem_tool_call={model_tool_free}; task_finalizada={model_task_done}")

            def tool_result_block(task_text: str, tool_name: str) -> str:
                """Extrai o bloco TOOL_CALL + TOOL_RESULT da ferramenta dentro da task."""
                if not task_text:
                    return ""
                pattern = re.compile(
                    rf'(?ms)^\[[^\n]+\] TOOL_CALL\n(?:  [^\n]*\n)*?  ferramenta: "{re.escape(tool_name)}"(?:\n|$).*?^\[[^\n]+\] TOOL_RESULT\n.*?  ferramenta: "{re.escape(tool_name)}"\n(?:  resultado: "(?P<resultado>[^\n]*)"|(?P<resto>[^\n]*)(?:\n|$))'
                )
                match = pattern.search(task_text)
                return match.group(0) if match else ""

            def tool_call_argument_summary(task_text: str, tool_name: str) -> str:
                """Extrai apenas argumentos nao sensiveis do TOOL_CALL para diagnostico."""
                block = tool_result_block(task_text, tool_name)
                if not block:
                    return ""
                match = re.search(r'(?m)^  argumentos: "(?P<args>.*)"$', block)
                if not match:
                    return ""
                raw = match.group('args')
                try:
                    args = json.loads(raw.replace('\\"', '"'))
                except Exception:
                    return raw[:500]
                if isinstance(args, dict):
                    public = {k: args.get(k) for k in ('alvo_janela', 'alvo', 'indice') if k in args}
                    return json.dumps(public, ensure_ascii=False)
                return str(args)[:500]

            def tool_result_summary(task_text: str, tool_name: str) -> str:
                block = tool_result_block(task_text, tool_name)
                if not block:
                    return ""
                match = re.search(r'(?m)^  resultado: "(?P<resultado>.*)"$', block)
                return match.group('resultado') if match else block[-800:]

            status_block = task_block("que horas sao?")
            ram_block = task_block("quanto da minha memoria ram esta sendo usada?")
            uptime_block = task_block("a quanto tempo o computador esta ligado?")

            if command_enabled("time"):
                record(
                    "Status/hora respondeu",
                    ('ferramenta: "obter_status_windows"' in status_block and "Hora local:" in status_block)
                    or ("TASK_FAST_PATH" in status_block and "Hora local:" in status_block),
                    status_block[-500:] if status_block else "task ausente",
                )
            if command_enabled("ram"):
                record(
                    "RAM consultada",
                    ('ferramenta: "obter_status_windows"' in ram_block and "RAM:" in ram_block)
                    or ("TASK_FAST_PATH" in ram_block and "RAM:" in ram_block),
                    ram_block[-500:] if ram_block else "task ausente",
                )
            if command_enabled("uptime"):
                record(
                    "Uptime consultado",
                    ('ferramenta: "obter_status_windows"' in uptime_block and "Tempo ligado:" in uptime_block)
                    or ("TASK_FAST_PATH" in uptime_block and "Tempo ligado:" in uptime_block),
                    uptime_block[-500:] if uptime_block else "task ausente",
                )

            audio_state_block = task_block("qual e o volume do computador agora?")
            audio_set_block = task_block(audio_volume_command)
            audio_mute_block = task_block("qual e o estado atual do mudo?")
            if command_enabled("audio_read"):
                record(
                    "Audio integrado: leitura de volume",
                    'ferramenta: "obter_audio_windows"' in audio_state_block and "Volume atual:" in audio_state_block,
                    audio_state_block[-500:] if audio_state_block else "task ausente",
                )
            if command_enabled("audio_set"):
                record(
                    "Audio integrado: definir volume",
                    'ferramenta: "definir_volume_windows"' in audio_set_block and (original_audio_volume is None or f"Volume definido para {original_audio_volume}%" in audio_set_block),
                    audio_set_block[-500:] if audio_set_block else "task ausente",
                )
            if command_enabled("audio_mute"):
                record(
                    "Audio integrado: leitura de mudo",
                    'ferramenta: "obter_audio_windows"' in audio_mute_block and "Mudo:" in audio_mute_block,
                    audio_mute_block[-500:] if audio_mute_block else "task ausente",
                )

            clipboard_set_block = task_block("area de transferencia")
            clipboard_read_block = task_block("o que esta na minha area de transferencia?")
            clipboard_set = (
                'ferramenta: "definir_area_transferencia_windows"' in clipboard_set_block
                or bool(re.search(r'ferramenta: "definir_area_transferencia_windows"', appended))
            )
            clipboard_read_tool = (
                'ferramenta: "ler_area_transferencia_windows"' in clipboard_read_block
                or bool(re.search(r'ferramenta: "ler_area_transferencia_windows"', appended))
            )
            clipboard_redigido = (
                "[REDACTED clipboard:" in clipboard_read_block
                or "[REDACTED clipboard:" in appended
            )
            clipboard_raw_vazou = "AUREN_TESTE_CLIPBOARD_INTEGRADO" in appended
            clipboard_read = clipboard_read_tool and clipboard_redigido and not clipboard_raw_vazou
            if command_enabled("clipboard_set") or command_enabled("clipboard_read"):
                clipboard_ok = (not command_enabled("clipboard_set") or clipboard_set) and (not command_enabled("clipboard_read") or clipboard_read)
                record("Clipboard integrado", clipboard_ok, "set=%s; read=%s; valor_redigido=%s; valor_em_claro=%s" % (clipboard_set, clipboard_read_tool, clipboard_redigido, clipboard_raw_vazou))

            def task_called_tool(block: str, tool_name: str) -> bool:
                # O log coloca task_id/rodada/output entre TOOL_CALL e ferramenta.
                # Procuramos especificamente o campo ferramenta dentro de um TOOL_CALL,
                # para nao contar TOOL_RESULT como se fosse chamada.
                pattern = re.compile(
                    rf'(?ms)^\[[^\n]+\] TOOL_CALL\n(?:  [^\n]*\n)*?  ferramenta: "{re.escape(tool_name)}"(?:\n|$)'
                )
                return bool(pattern.search(block))

            def task_block_with_tool(tool_name: str, occurrence: str = "last") -> str:
                blocos = [
                    block for block in parsed_task_blocks
                    if re.search(
                        rf'(?ms)^\[[^\n]+\] TOOL_CALL\n(?:  [^\n]*\n)*?  ferramenta: "{re.escape(tool_name)}"(?:\n|$)',
                        block,
                    )
                ]
                if not blocos:
                    return ""
                return blocos[-1] if occurrence == "last" else blocos[0]

            expected_tool_tasks = {
                "processes": ("listar_processos_windows", "liste os processos"),
                "clipboard_set": ("definir_area_transferencia_windows", "coloque AUREN_TESTE_CLIPBOARD_INTEGRADO na minha area de transferencia"),
                "clipboard_read": ("ler_area_transferencia_windows", "o que esta na minha area de transferencia?"),
                "window_list": ("listar_janelas_windows", "liste as janelas abertas"),
                "window_geometry": ("obter_geometria_janela_windows", f"qual a posicao e o tamanho da janela {titulo_janela}?"),
                "window_minimize": ("minimizar_janela_windows", f"minimize a janela {titulo_janela}"),
                "window_maximize": ("maximizar_janela_windows", f"maximize a janela {titulo_janela}"),
                "window_restore": ("restaurar_janela_windows", f"restaure a janela {titulo_janela}"),
                "window_move": ("mover_janela_windows", f"mova a janela {titulo_janela} para 120 por 140"),
                "window_resize": ("redimensionar_janela_windows", f"redimensione a janela {titulo_janela} para 800 por 500"),
                "window_close": ("fechar_janela_windows", f"feche a janela {titulo_janela}"),
                "tabs_new": ("abrir_nova_aba", "abra duas abas"),
                "audio_read": ("obter_audio_windows", "qual e o volume do computador agora?"),
                "audio_set": ("definir_volume_windows", audio_volume_command),
                "tabs_flow": ("navegar_navegador", "abra o discord na segunda aba e o youtube na terceira aba"),
                "browser_verify_navigation": ("obter_contexto_navegador", "abra o youtube e depois confirme a URL e o titulo da pagina atual"),
                "browser_verify_scroll": ("obter_contexto_navegador", "na pagina do youtube, role para baixo e confirme a posicao atual da pagina"),
            }
            if uia_titulo:
                expected_tool_tasks.update({
                    "uia_inspect": ("inspecionar_interface_windows", f"inspecione a interface da janela {uia_titulo} e diga quais controles existem"),
                    "uia_fill": ("preencher_elemento_windows", f"preencha o campo Campo de Teste da janela {uia_titulo} com AUREN_UIA_INTEGRADO_V42"),
                    "uia_click": ("clicar_elemento_windows", f"clique no botao Botao Auren Teste da janela {uia_titulo}"),
                    "uia_checkbox": ("alternar_elemento_windows", f"marque a caixa Check Auren Teste da janela {uia_titulo}"),
                    "uia_select": ("selecionar_elemento_windows", f"selecione a Opcao Dois na janela {uia_titulo}"),
                })

            def browser_verification_succeeded(task_text: str, ferramenta: str) -> bool:
                if not task_text:
                    return False
                pattern = re.compile(
                    rf'(?ms)^\[[^\n]+\] TASK_BROWSER_VERIFICATION\n'
                    rf'(?:  [^\n]*\n)*?  ferramenta: "{re.escape(ferramenta)}"\n'
                    rf'(?:  [^\n]*\n)*?  verificado: true(?:\n|$)'
                )
                return bool(pattern.search(task_text))


            missing_expected = []
            called_expected = []
            for key, (tool_name, objective_fragment) in expected_tool_tasks.items():
                if not command_enabled(key):
                    continue
                bloco = task_block(objective_fragment)
                if not bloco and key in {"uia_fill", "clipboard_set"}:
                    bloco = task_block_with_tool(tool_name)

                # Algumas tarefas possuem caminhos determinísticos (FAST_PATH) que
                # executam a ação diretamente, sem TOOL_CALL do modelo. Isso não é
                # uma falha da arquitetura: o teste deve validar o comportamento
                # real, não exigir uma forma específica de despacho.
                called = task_called_tool(bloco, tool_name)
                fast_path_ok = False
                if key == "tabs_new":
                    fast_path_ok = (
                        "TASK_FAST_PATH" in bloco
                        and "Abri 2 novas abas." in bloco
                    )

                if called or fast_path_ok:
                    called_expected.append(tool_name)
                else:
                    missing_expected.append(f"{key}:{tool_name}")
            if expected_tool_tasks and called_expected:  # pelo menos um teste integrado de ferramenta foi executado nesta camada.
                record(
                    "Integração: ferramentas escolhidas por camada",
                    not missing_expected,
                    f"esperadas={len(called_expected)+len(missing_expected)}; chamadas_ok={sorted(set(called_expected))}; faltando={missing_expected}",
                )

            if command_enabled("browser_verify_navigation"):
                navigation_block = task_block("abra o youtube e depois confirme a URL e o titulo da pagina atual")
                nav_called = task_called_tool(navigation_block, "navegar_navegador")
                nav_context = task_called_tool(navigation_block, "obter_contexto_navegador")
                nav_verified = browser_verification_succeeded(navigation_block, "navegar_navegador")
                record(
                    "Browser Intelligence: verificacao live de navegacao",
                    nav_called and nav_context and nav_verified,
                    f"acao={nav_called}; contexto={nav_context}; verificado={nav_verified}",
                )

            if command_enabled("browser_verify_scroll"):
                scroll_block = task_block("na pagina do youtube, role para baixo e confirme a posicao atual da pagina")
                scroll_called = task_called_tool(scroll_block, "rolar_pagina")
                scroll_context = task_called_tool(scroll_block, "obter_contexto_navegador")
                scroll_verified = browser_verification_succeeded(scroll_block, "rolar_pagina")
                record(
                    "Browser Intelligence: verificacao live de rolagem",
                    scroll_called and scroll_context and scroll_verified,
                    f"acao={scroll_called}; contexto={scroll_context}; verificado={scroll_verified}",
                )

            if command_enabled("window_minimize"):
                min_block = task_block(f"minimize a janela {titulo_janela}")
                record(
                    "Minimizar janela integrado",
                    'ferramenta: "minimizar_janela_windows"' in min_block and "Janela minimizada" in min_block,
                    min_block[-600:] if min_block else "task ausente",
                )

            if command_enabled("window_maximize"):
                max_block = task_block(f"maximize a janela {titulo_janela}")
                record(
                    "Maximizar janela integrado",
                    'ferramenta: "maximizar_janela_windows"' in max_block
                    and "Janela maximizada" in max_block
                    and 'ferramenta: "focar_janela_windows"' not in max_block,
                    "maximizar deve usar a ferramenta diretamente, sem foco previo.",
                )

            if command_enabled("window_move"):
                move_block = task_block(f"mova a janela {titulo_janela} para 120 por 140")
                record("Mover janela integrado", 'ferramenta: "mover_janela_windows"' in move_block and "Janela movida" in move_block, move_block[-600:] if move_block else "task ausente")

            if command_enabled("window_resize"):
                resize_block = task_block(f"redimensione a janela {titulo_janela} para 800 por 500")
                record("Redimensionar janela integrado", 'ferramenta: "redimensionar_janela_windows"' in resize_block and "Janela redimensionada" in resize_block, resize_block[-600:] if resize_block else "task ausente")

            if command_enabled("window_geometry"):
                geometry_block = task_block(f"qual a posicao e o tamanho da janela {titulo_janela}?")
                geometry_ok = 'ferramenta: "obter_geometria_janela_windows"' in geometry_block and "Tamanho:" in geometry_block and "Posicao:" in geometry_block
                record("Geometria da janela integrada", geometry_ok, geometry_block[-700:] if geometry_block else "task ausente")

            if command_enabled("window_restore"):
                restore_block = task_block(f"restaure a janela {titulo_janela}")
                record(
                    "Restaurar janela integrado",
                    'ferramenta: "restaurar_janela_windows"' in restore_block
                    and "Janela restaurada" in restore_block
                    and 'ferramenta: "maximizar_janela_windows"' not in restore_block,
                    restore_block[-600:] if restore_block else "task ausente",
                )

            if uia_titulo and uia_bridge_ok:
                uia_final = uia_for_setup

                if command_enabled("uia_fill") or command_enabled("uia_fill_readback"):
                    campo_estado = ""
                    campo_ok = False
                    for _ in range(8):
                        campo_estado = uia_final.inspecionar_interface_windows(uia_titulo, "Campo de Teste", 5)
                        if "AUREN_UIA_INTEGRADO_V42" in campo_estado:
                            campo_ok = True
                            break
                        time.sleep(0.25)
                    preenchimento_task = task_block(f"preencha o campo Campo de Teste da janela {uia_titulo} com AUREN_UIA_INTEGRADO_V42")
                    if not preenchimento_task:
                        blocos_tool = [
                            bloco for bloco in parsed_task_blocks
                            if re.search(
                                r'(?ms)^\[[^\n]+\] TOOL_CALL\n(?:  [^\n]*\n)*?  ferramenta: "preencher_elemento_windows"(?:\n|$)',
                                bloco,
                            )
                        ]
                        preenchimento_task = blocos_tool[-1] if blocos_tool else ""
                    preenchimento_confirmado = (
                        'ferramenta: "preencher_elemento_windows"' in preenchimento_task
                        and ("Preenchimento concluido" in preenchimento_task or "Preenchimento nao confirmado" not in preenchimento_task)
                    )
                    argumentos_preenchimento = tool_call_argument_summary(preenchimento_task, "preencher_elemento_windows")
                    resultado_preenchimento = tool_result_summary(preenchimento_task, "preencher_elemento_windows")
                    record(
                        "UIA integrado: ferramenta confirmou preenchimento",
                        preenchimento_confirmado,
                        f"tool_call={'sim' if 'ferramenta: \"preencher_elemento_windows\"' in preenchimento_task else 'nao'}; argumentos_publicos={argumentos_preenchimento or '[indisponivel]'}; resultado={resultado_preenchimento or '[indisponivel]'}",
                    )
                    if command_enabled("uia_fill_readback"):
                        campo_task = task_block(f"inspecione a interface da janela {uia_titulo} procurando Campo de Teste")
                        campo_log_ok = "Campo de Teste" in campo_task and "Controles exibidos" in campo_task
                        record("UIA integrado: rechecagem do campo no fluxo", campo_log_ok, campo_task[-700:] if campo_task else "task ausente")
                    if command_enabled("uia_fill"):
                        valor_confirmado = "AUREN_UIA_INTEGRADO_V42" in campo_estado
                        campo_linha = next((linha.strip() for linha in campo_estado.replace("\\n", "\n").splitlines() if "Campo de Teste" in linha), "")
                        record(
                            "UIA integrado: estado do campo",
                            campo_ok and valor_confirmado,
                            f"campo_encontrado={bool(campo_linha)}; valor_confirmado={valor_confirmado}; estado={campo_linha[:260]}",
                        )

                if command_enabled("uia_click") or command_enabled("uia_click_readback"):
                    if command_enabled("uia_click_readback"):
                        botao_task = task_block(f"inspecione a interface da janela {uia_titulo} procurando BOTAO_CLICADO")
                        botao_ok = _ui_inspecao_confirmou_texto(botao_task, "BOTAO_CLICADO")
                        linha_procurada = "\n".join(linha for linha in botao_task.replace("\\n", "\n").splitlines() if "Controles exibidos" in linha or "BOTAO_CLICADO" in linha)
                        record("UIA integrado: estado apos clique", botao_ok, linha_procurada[:700] if linha_procurada else "task ausente")

                if command_enabled("uia_checkbox"):
                    check_estado = uia_final.inspecionar_interface_windows(uia_titulo, "Check Auren Teste", 5)
                    record("UIA integrado: checkbox marcado", "toggle=On" in check_estado, check_estado[:400])

                if command_enabled("uia_select"):
                    selecao_estado = uia_final.inspecionar_interface_windows(uia_titulo, "Opcao Dois", 5)
                    record("UIA integrado: opcao selecionada", "selected=True" in selecao_estado, selecao_estado[:400])

                # Protecao contra exposicao de segredo permanece uma verificacao real
                # mesmo quando o restante do UIA live nao esta selecionado.
                protected_check = uia_final.inspecionar_interface_windows(uia_titulo, "Senha de Teste", 5)
                record("UIA integrado: protege senha", "SEGREDO_UIA_TESTE" not in protected_check and "protegido=True" in protected_check, protected_check[:500])

            if command_enabled("tabs_flow"):
                duas_abas_task = task_block("abra duas abas")
                abas_task = task_block("abra o discord na segunda aba e o youtube na terceira aba")
                fluxo_abas = duas_abas_task + "\n" + abas_task
                # A validacao e pelo estado real observado no TOOL_RESULT da tarefa,
                # nunca pela resposta textual final do modelo.
                count_new_tabs_total = len(re.findall(
                    r'(?ms)^\[[^\n]+\] TOOL_CALL\n(?:  [^\n]*\n)*?  ferramenta: "abrir_nova_aba"(?:\n|$)',
                    fluxo_abas,
                ))
                if "Abri 2 novas abas." in duas_abas_task:
                    count_new_tabs_total = 2
                estado_abas_imediato = abas_task
                total_three_tabs = bool(re.search(r'Abas abertas:\s*3\b', estado_abas_imediato))
                aba2_discord = bool(re.search(r'Aba 2:\s*Discord\b[^|]*\|\s*https?://discord\.com(?:/|\b)', estado_abas_imediato, re.IGNORECASE))
                aba3_youtube = bool(re.search(r'Aba 3:\s*YouTube\s*\|\s*https?://(?:www\.)?youtube\.com', estado_abas_imediato, re.IGNORECASE))
                abas_confirmadas = aba2_discord and aba3_youtube
                record(
                    "Múltiplas abas: fluxo combinado completo",
                    count_new_tabs_total == 2 and total_three_tabs and abas_confirmadas,
                    f"novas_chamadas_no_fluxo={count_new_tabs_total}; tres_abas={total_three_tabs}; aba2_discord={aba2_discord}; aba3_youtube={aba3_youtube}; estado_imediato={estado_abas_imediato[:900]}",
                )
        else:
            INTEGRATION_CHAT_LOG_PATH = None
            INTEGRATION_CHAT_LOG = ""
            record("Log de integração disponível", False, "Nao encontrei um chat.log da sessão atual em logs/chats.")

        # O stdout completo da execucao integrada e mantido apenas para debug
        # quando existe alguma falha na bateria. Em execucoes sem falhas, o
        # resultado enxuto e suficiente e o chat.log continua sendo a fonte
        # detalhada da sessao real.
        if output and any(not resultado.ok for resultado in RESULTS):
            report_path = ROOT / "logs" / "TESTE_REGRESSAO_RAW_ULTIMO.txt"
            report_path.write_text(output, encoding="utf-8")
            print(f"Log bruto de debug salvo em: {report_path}")
    except subprocess.TimeoutExpired:
        record("Execucao integrada terminou", False, "timeout de 240s")
    except Exception as exc:
        record("Execucao integrada terminou", False, repr(exc))
    finally:
        try:
            if uia_titulo:
                cleanup_ui = load_auren_module()
                cleanup_ui.fechar_janela_windows(uia_titulo)
        except Exception:
            pass
        try:
            if uia_proc is not None and uia_proc.poll() is None:
                uia_proc.terminate()
        except Exception:
            pass
        try:
            if uia_script_path:
                uia_script_path.unlink()
        except OSError:
            pass
        restore_original_audio_state()
        try:
            cleanup_auren = load_auren_module()
            cleanup_auren.fechar_janela_windows(titulo_janela)
        except Exception:
            pass
        try:
            if integration_proc is not None and integration_proc.poll() is None:
                integration_proc.terminate()
        except Exception:
            pass
        try:
            if integration_script_path:
                integration_script_path.unlink()
        except OSError:
            pass
        try:
            commands_file.unlink()
        except OSError:
            pass


def main() -> int:
    print(f'Tester build: {TESTER_BUILD}')
    print(f"Camadas ativas: {', '.join(layer for layer in AVAILABLE_LAYERS if layer in ACTIVE_LAYERS)}")
    print(f"AUREN — TESTE AUTOMATICO V{TEST_SUITE_VERSION}")
    print(f"Pasta do tester: {ROOT}")
    print(f"Python em uso: {sys.executable}")

    if "L3" in ACTIVE_LAYERS:
        print("[INFO] L3 (replay/provider roteirizado) esta reservado para a proxima etapa; nenhum teste L3 foi executado nesta versao.")

    compatible = run_discovery_tests() if layer_enabled("L0") else True
    if not compatible:
        print("\nTeste interrompido antes dos testes funcionais para evitar falsos FAILs.")
    else:
        if layer_enabled("L1") or layer_enabled("L2"):
            run_smoke_tests()
        if layer_enabled("L4") or layer_enabled("L5"):
            run_model_suite()

    passed = sum(1 for r in RESULTS if r.ok)
    failed = sum(1 for r in RESULTS if not r.ok)
    weak_passes = [r for r in RESULTS if r.ok and not _normalize_detail(r.detail)]

    print("\n=== RESULTADO ===")
    print(f"PASSOU: {passed}")
    print(f"FALHOU: {failed}")
    print(f"PASS SEM EVIDENCIA FORTE: {len(weak_passes)}")

    report = ROOT / "logs" / "testes" / "RESULTADO_TESTE_AUREN.txt"
    report.parent.mkdir(parents=True, exist_ok=True)
    pass_lines = [
        f"[PASS] [{r.layer}] {r.name} — {_compact_pass_detail(r.detail)}"
        for r in RESULTS
        if r.ok
    ]
    fail_lines = [
        f"[FAIL] [{r.layer}] {r.name} — {_compact_fail_detail(r.detail)}"
        for r in RESULTS
        if not r.ok
    ]
    weak_lines = [
        f"[{r.layer}] {r.name}"
        for r in weak_passes
    ]
    conteudo = [
        f"AUREN — RESULTADO DO TESTE V{TEST_SUITE_VERSION}",
        f"Camadas executadas: {', '.join(layer for layer in AVAILABLE_LAYERS if layer in ACTIVE_LAYERS)}",
        "",
        f"PASSOU: {passed}",
        f"FALHOU: {failed}",
        f"PASS SEM EVIDENCIA FORTE: {len(weak_passes)}",
        "",
        "=== PASSOU (evidencia minima) ===",
        *pass_lines,
        "",
        "=== FALHOU (detalhes) ===",
        *(fail_lines if fail_lines else ["Nenhuma falha registrada."]),
        "",
        "=== PASS SEM EVIDENCIA FORTE (auditoria) ===",
        *(weak_lines if weak_lines else ["Nenhum."]),
        "",
        "=== LOG DETALHADO ===",
        (f"Chat da execucao integrada: {INTEGRATION_CHAT_LOG_PATH}" if INTEGRATION_CHAT_LOG_PATH else "Chat da execucao integrada: nao localizado"),
        "O chat.log do caminho acima continua contendo o historico tecnico completo da sessao real.",
        "O log bruto do subprocesso so e salvo em logs/TESTE_REGRESSAO_RAW_ULTIMO.txt quando a bateria possui alguma falha.",
    ]
    report.write_text("\n".join(conteudo) + "\n", encoding="utf-8")
    print(f"Relatorio enxuto: {report}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
