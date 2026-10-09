"""Testes do carregador de plugins e de sua integracao com o caminho unico."""
from __future__ import annotations

import builtins
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]

from core.capabilities import CAPABILITY_REGISTRY
from core.permission_manager import PermissionLevel, PermissionManager
from core.tool_result import ToolResult
from core.tools_registry import tools
import tools.dispatcher as dispatcher
from core.plugin_loader import discover_plugins, plugin_aprovado, plugin_habilitado


def _write_approval(path: Path, **entries) -> None:
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")


def _write_plugin(
    directory: Path,
    filename: str,
    body: str,
) -> Path:
    path = directory / filename
    path.write_text(body, encoding="utf-8")
    return path


def _valid_plugin(name: str = "teste_plugin", *, dependency: str = "core.tool_result") -> str:
    return f'''
from core.tool_result import ToolResult

DEPENDENCIAS = ({dependency!r},)

CAPABILITY = {{
    "id": "plugin.{name}",
    "descricao": "Capacidade de teste.",
    "local": True,
    "deterministica": True,
    "multi_etapa": False,
    "exige_raciocinio": False,
    "resolver": "plugin",
}}

def executar(argumentos):
    return ToolResult.success("teste", tool_name=TOOL["name"])

TOOL = {{
    "name": {name!r},
    "description": "Plugin de teste.",
    "parameters": {{
        "type": "object",
        "properties": {{}},
        "required": [],
        "additionalProperties": False,
    }},
    "strict": True,
    "handler": executar,
}}
'''


@pytest.fixture(autouse=True)
def cleanup_plugins(monkeypatch):
    yield
    for nome in list(dispatcher.PLUGIN_TOOL_NAMES):
        dispatcher.remover_plugin_handler(nome)
    for item in list(tools):
        if str(item.get("name", "")).startswith(("plugin_",)):
            pass
    # Cada teste usa nomes unicos sempre que a mutacao global seria relevante.
    monkeypatch.delenv("AUREN_PLUGINS_APPROVAL_FILE", raising=False)


def _unregister(name: str) -> None:
    dispatcher.remover_plugin_handler(name)
    from core.tool_contracts import remover_tool_plugin
    remover_tool_plugin(name)
    CAPABILITY_REGISTRY.remover(f"plugin.{name}")


def test_plugin_exemplo_hora_atual_carrega_e_executa_pelo_dispatcher(monkeypatch, tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(approval, hora_atual={"habilitado": True, "aprovado": True})
    monkeypatch.setenv("AUREN_PLUGINS_APPROVAL_FILE", str(approval))

    registry = discover_plugins(ROOT / "plugins", approval_file=approval, logger=lambda _msg: None)
    try:
        assert "hora_atual" in registry.active_names
        assert "hora_atual" in dispatcher.TOOL_HANDLERS
        assert CAPABILITY_REGISTRY.get("plugin.hora_atual") is not None
        assert any(item["name"] == "hora_atual" for item in tools)

        item = SimpleNamespace(name="hora_atual", arguments="{}")
        resultado = dispatcher.executar_ferramenta(item, PermissionManager(), None)

        assert isinstance(resultado, ToolResult)
        assert resultado.ok
        assert resultado.conteudo_nao_confiavel is True
        assert resultado.tool_name == "hora_atual"
        assert "Hora local atual:" in resultado.message
    finally:
        registry.descarregar()


def test_plugin_entra_em_confirm_e_aprovacao_muda_nivel_sem_reboot(monkeypatch, tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(approval, teste_plugin={"habilitado": True, "aprovado": False})
    monkeypatch.setenv("AUREN_PLUGINS_APPROVAL_FILE", str(approval))

    directory = _tmp_plugins_with(tmp_path, "teste_plugin")
    _write_plugin(directory, "teste_plugin.py", _valid_plugin("teste_plugin"))
    registry = discover_plugins(
        directory,
        approval_file=approval,
        logger=lambda _msg: None,
    )
    try:
        pm = PermissionManager()
        assert pm.nivel("teste_plugin") is PermissionLevel.CONFIRM
        _write_approval(approval, teste_plugin={"habilitado": True, "aprovado": True})
        assert plugin_aprovado("teste_plugin") is True
        assert pm.nivel("teste_plugin") is PermissionLevel.AUTO
    finally:
        registry.descarregar()


def test_aprovacao_nao_bypassa_politica_de_conteudo_nao_confiavel(monkeypatch, tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(approval, teste_untrusted={"habilitado": True, "aprovado": True})
    monkeypatch.setenv("AUREN_PLUGINS_APPROVAL_FILE", str(approval))
    directory = _tmp_plugins_with(tmp_path, "teste_untrusted")
    _write_plugin(directory, "teste_untrusted.py", _valid_plugin("teste_untrusted"))
    registry = discover_plugins(
        directory,
        approval_file=approval,
        logger=lambda _msg: None,
    )
    try:
        pm = PermissionManager()
        monkeypatch.setattr(builtins, "input", lambda *_: "s")
        resultado = dispatcher.executar_ferramenta(
            SimpleNamespace(name="teste_untrusted", arguments="{}"),
            pm,
            None,
        )
        assert resultado.ok and resultado.conteudo_nao_confiavel
        nivel, motivo = pm.nivel_da_acao("abrir_programa", {"programa": "notepad"})
        assert nivel is PermissionLevel.CONFIRM
        assert "conteudo nao confiavel" in motivo
    finally:
        registry.descarregar()


def test_plugin_invalido_e_ignorado_sem_derrumbar_boot(monkeypatch, tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(approval, invalido={"habilitado": True, "aprovado": False})
    directory = _tmp_plugins_with(tmp_path, "invalido")
    _write_plugin(
        directory,
        "invalido.py",
        '''
from core.tool_result import ToolResult

CAPABILITY = {"id": "plugin.invalido"}

def executar(argumentos):
    return ToolResult.success("x", tool_name="invalido")

TOOL = {
    "name": "invalido",
    "description": "x",
    "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    "handler": executar,
}
''',
    )
    registry = discover_plugins(directory, approval_file=approval, logger=lambda _msg: None)
    try:
        record = next(item for item in registry.records if item.name == "invalido")
        assert not record.valid
        assert "CAPABILITY" in record.error
        assert dispatcher.validar_registry_handlers() == (True, "")
    finally:
        registry.descarregar()



def test_nome_invalido_e_rejeitado_antes_do_import(tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(approval, **{"nome invalido": {"habilitado": True, "aprovado": False}})
    directory = tmp_path / "plugins"
    directory.mkdir()
    _write_plugin(
        directory,
        "nome_invalido.py",
        '''
from pathlib import Path
Path(__file__).with_suffix(".importado").write_text("nao deveria")
from core.tool_result import ToolResult

CAPABILITY = {
    "id": "plugin.nome invalido",
    "descricao": "invalido",
    "local": True,
    "deterministica": True,
    "multi_etapa": False,
    "exige_raciocinio": False,
    "resolver": "plugin",
}

def executar(argumentos):
    return ToolResult.success("x", tool_name="nome invalido")

TOOL = {
    "name": "nome invalido",
    "description": "invalido",
    "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    "handler": executar,
}
''',
    )
    registry = discover_plugins(directory, approval_file=approval, logger=lambda _msg: None)
    try:
        record = next(item for item in registry.records if item.name == "nome invalido")
        assert not record.valid
        assert "Nome invalido" in record.error
        assert not (directory / "nome_invalido.importado").exists()
    finally:
        registry.descarregar()


def test_plugin_com_nome_de_core_e_ignorado_antes_do_import(tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(approval, obter_status_windows={"habilitado": True, "aprovado": False})
    directory = tmp_path / "plugins"
    directory.mkdir()
    _write_plugin(
        directory,
        "colisao.py",
        '''
from pathlib import Path
Path(__file__).with_suffix(".importado").write_text("nao deveria")
TOOL = {
    "name": "obter_status_windows",
    "description": "colisao",
    "parameters": {"type": "object"},
    "handler": executar,
}
CAPABILITY = {
    "id": "plugin.obter_status_windows",
    "descricao": "colisao",
    "local": True,
    "deterministica": True,
    "multi_etapa": False,
    "exige_raciocinio": False,
    "resolver": "plugin",
}
def executar(argumentos):
    return ToolResult.success("x")
''',
    )
    (directory / "colisao.importado").unlink(missing_ok=True)
    registry = discover_plugins(directory, approval_file=approval, logger=lambda _msg: None)
    try:
        record = next(item for item in registry.records if item.name == "obter_status_windows")
        assert not record.valid
        assert "reservado" in record.error
        assert not (directory / "colisao.importado").exists()
    finally:
        registry.descarregar()


def test_nome_duplicado_nao_importa_segundo(tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(
        approval,
        duplicado={"habilitado": True, "aprovado": False},
    )
    directory = tmp_path / "plugins"
    directory.mkdir()
    _write_plugin(directory, "a_primeiro.py", _valid_plugin("duplicado"))
    _write_plugin(
        directory,
        "z_segundo.py",
        _valid_plugin("duplicado").replace(
            'from core.tool_result import ToolResult',
            'from pathlib import Path\nPath(__file__).with_suffix(".importado").write_text("sim")\nfrom core.tool_result import ToolResult',
        ),
    )

    registry = discover_plugins(directory, approval_file=approval, logger=lambda _msg: None)
    try:
        duplicados = [item for item in registry.records if item.name == "duplicado"]
        assert sum(item.valid for item in duplicados) == 1
        assert any("duplicado" in item.error for item in duplicados if not item.valid)
        assert not (directory / "z_segundo.importado").exists()
    finally:
        registry.descarregar()


def test_dependencia_ausente_e_legivel_sem_importar_o_plugin(tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(approval, faltante={"habilitado": True, "aprovado": False})
    directory = _tmp_plugins_with(tmp_path, "faltante")
    _write_plugin(
        directory,
        "faltante.py",
        _valid_plugin("faltante", dependency="pacote_que_nao_existe_auren"),
    )
    registry = discover_plugins(directory, approval_file=approval, logger=lambda _msg: None)
    try:
        record = next(item for item in registry.records if item.name == "faltante")
        assert not record.valid
        assert "Dependencia ausente" in record.error
        assert dispatcher.validar_registry_handlers() == (True, "")
    finally:
        registry.descarregar()


def test_modulo_do_proprio_auren_ausente_nao_manda_instalar_com_pip(tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(approval, proprio_faltante={"habilitado": True, "aprovado": False})
    directory = _tmp_plugins_with(tmp_path, "proprio_faltante")
    _write_plugin(directory, "proprio_faltante.py", _valid_plugin("proprio_faltante", dependency="core.modulo_que_nao_existe"))
    registry = discover_plugins(directory, approval_file=approval, logger=lambda _msg: None)
    try:
        record = next(item for item in registry.records if item.name == "proprio_faltante")
        assert not record.valid
        assert "Modulo do proprio Auren ausente" in record.error
        assert "pip install core" not in record.error
    finally:
        registry.descarregar()



def test_erro_de_importacao_de_plugin_e_isolado(tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(
        approval,
        quebrado={"habilitado": True, "aprovado": False},
        normal={"habilitado": True, "aprovado": True},
    )
    directory = _tmp_plugins_with(tmp_path, "isolado")
    _write_plugin(
        directory,
        "quebrado.py",
        '''
raise RuntimeError("falha isolada de import")
''',
    )
    _write_plugin(directory, "normal.py", _valid_plugin("normal"))

    registry = discover_plugins(directory, approval_file=approval, logger=lambda _msg: None)
    try:
        quebrado = next(item for item in registry.records if item.name == "quebrado")
        assert not quebrado.valid
        assert "falha isolada de import" in quebrado.error
        assert "normal" in registry.active_names
    finally:
        registry.descarregar()


def test_plugin_desativado_nao_importa_nem_checa_dependencia(monkeypatch, tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(
        approval,
        desligado={"habilitado": False, "aprovado": False},
    )
    directory = _tmp_plugins_with(tmp_path, "desligado")
    _write_plugin(
        directory,
        "desligado.py",
        _valid_plugin("desligado", dependency="pacote_que_nao_existe_auren"),
    )
    original_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda _name: (_ for _ in ()).throw(AssertionError("find_spec nao deveria rodar para plugin desligado")),
    )
    registry = discover_plugins(directory, approval_file=approval, logger=lambda _msg: None)
    try:
        record = next(item for item in registry.records if item.name == "desligado")
        assert not record.valid
        assert record.enabled is False
        assert "desativado" in record.error
        assert importlib.util.find_spec is not original_find_spec
    finally:
        registry.descarregar()


def test_descoberta_nao_executa_handler_plugin(tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(approval, efeito={"habilitado": True, "aprovado": True})
    directory = _tmp_plugins_with(tmp_path, "efeito")
    _write_plugin(
        directory,
        "efeito.py",
        _valid_plugin("efeito").replace(
            'def executar(argumentos):',
            'def executar(argumentos):\n    Path("marcador").write_text("executado")',
        ).replace(
            "from core.tool_result import ToolResult",
            "from pathlib import Path\nfrom core.tool_result import ToolResult",
        ),
    )
    registry = discover_plugins(directory, approval_file=approval, logger=lambda _msg: None)
    marker = Path("marcador")
    marker.unlink(missing_ok=True)
    try:
        assert not marker.exists()
        resultado = dispatcher.executar_ferramenta(
            SimpleNamespace(name="efeito", arguments="{}"),
            PermissionManager(),
            None,
        )
        assert resultado.ok
        assert marker.exists()
    finally:
        marker.unlink(missing_ok=True)
        registry.descarregar()


def test_registry_handlers_inclui_plugin_e_so_dispatcher_executa(monkeypatch, tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(approval, caminho_unico={"habilitado": True, "aprovado": True})
    directory = _tmp_plugins_with(tmp_path, "caminho_unico")
    _write_plugin(directory, "caminho_unico.py", _valid_plugin("caminho_unico"))
    registry = discover_plugins(directory, approval_file=approval, logger=lambda _msg: None)
    try:
        assert dispatcher.validar_registry_handlers() == (True, "")
        assert "caminho_unico" in dispatcher.PLUGIN_TOOL_NAMES
        assert "caminho_unico" in dispatcher.TOOL_HANDLERS
        # O plugin nao aparece em fast_paths; o unico acionamento funcional e o Dispatcher.
        source = (ROOT / "tools" / "fast_paths.py").read_text(encoding="utf-8")
        assert "PLUGIN_TOOL_NAMES" not in source
        assert "plugins." not in source
    finally:
        registry.descarregar()


def test_ligar_desligar_funciona_sem_reiniciar(tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(approval, alternavel={"habilitado": False, "aprovado": True})
    directory = _tmp_plugins_with(tmp_path, "alternavel")
    _write_plugin(directory, "alternavel.py", _valid_plugin("alternavel"))

    registry = discover_plugins(directory, approval_file=approval, logger=lambda _msg: None)
    try:
        assert "alternavel" not in dispatcher.TOOL_HANDLERS
        _write_approval(approval, alternavel={"habilitado": True, "aprovado": True})
        registry.recarregar()
        assert "alternavel" in dispatcher.TOOL_HANDLERS
        _write_approval(approval, alternavel={"habilitado": False, "aprovado": True})
        registry.recarregar()
        assert "alternavel" not in dispatcher.TOOL_HANDLERS
    finally:
        registry.descarregar()


def test_capability_do_plugin_nao_pode_definir_permissao(tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(approval, sem_permissao={"habilitado": True, "aprovado": False})
    directory = _tmp_plugins_with(tmp_path, "sem_permissao")
    body = _valid_plugin("sem_permissao").replace(
        '"resolver": "plugin",',
        '"resolver": "plugin",\n    "politica_confirmacao": "auto",',
    )
    _write_plugin(directory, "sem_permissao.py", body)
    registry = discover_plugins(directory, approval_file=approval, logger=lambda _msg: None)
    try:
        record = next(item for item in registry.records if item.name == "sem_permissao")
        assert not record.valid
        assert "nao pode escolher permissao" in record.error
    finally:
        registry.descarregar()



def test_prompt_usa_capacidade_de_plugin_do_registry(monkeypatch, tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(approval, prompt_plugin={"habilitado": True, "aprovado": False})
    monkeypatch.setenv("AUREN_PLUGINS_APPROVAL_FILE", str(approval))
    directory = _tmp_plugins_with(tmp_path, "prompt_plugin")
    _write_plugin(directory, "prompt_plugin.py", _valid_plugin("prompt_plugin"))

    registry = discover_plugins(directory, approval_file=approval, logger=lambda _msg: None)
    try:
        from core.prompt import gerar_instrucoes
        prompt = gerar_instrucoes()
        assert "plugin.prompt_plugin" in prompt
        assert "prompt_plugin" in prompt
        assert "CONFIRM ate aprovacao local" in prompt
    finally:
        registry.descarregar()




def test_tool_do_plugin_usa_contrato_dinamico(monkeypatch, tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(approval, contrato_plugin={"habilitado": True, "aprovado": True})
    directory = _tmp_plugins_with(tmp_path, "contrato_plugin")
    _write_plugin(
        directory,
        "contrato_plugin.py",
        _valid_plugin("contrato_plugin").replace(
            '"properties": {},',
            '"properties": {"modo": {"type": "string", "enum": ["a", "b"]}},',
        ).replace(
            '"required": [],',
            '"required": ["modo"],',
        ),
    )
    registry = discover_plugins(directory, approval_file=approval, logger=lambda _msg: None)
    try:
        resultado = dispatcher.executar_ferramenta(
            SimpleNamespace(name="contrato_plugin", arguments=json.dumps({"modo": "a"})),
            PermissionManager(),
            None,
        )
        assert resultado.ok
        ruim = dispatcher.executar_ferramenta(
            SimpleNamespace(name="contrato_plugin", arguments=json.dumps({"modo": "c"})),
            PermissionManager(),
            None,
        )
        assert not ruim.ok and ruim.error_code == "contract_error"
    finally:
        registry.descarregar()


def test_plugin_invalid_result_vira_toolresult_de_falha(monkeypatch, tmp_path):
    approval = tmp_path / "aprovacoes.json"
    _write_approval(approval, retorno_invalido={"habilitado": True, "aprovado": True})
    directory = _tmp_plugins_with(tmp_path, "retorno_invalido")
    body = _valid_plugin("retorno_invalido").replace(
        'return ToolResult.success("teste", tool_name=TOOL["name"])',
        'return "texto legado"',
    )
    _write_plugin(directory, "retorno_invalido.py", body)
    registry = discover_plugins(directory, approval_file=approval, logger=lambda _msg: None)
    try:
        resultado = dispatcher.executar_ferramenta(
            SimpleNamespace(name="retorno_invalido", arguments="{}"),
            PermissionManager(),
            None,
        )
        assert not resultado.ok
        assert resultado.error_code == "plugin_invalid_result"
    finally:
        registry.descarregar()


def _tmp_plugins_with(tmp_path: Path, name: str) -> Path:
    directory = tmp_path / f"plugins_{name}"
    directory.mkdir()
    return directory
