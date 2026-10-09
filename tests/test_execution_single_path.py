"""Execucao de ferramentas: o Dispatcher e o caminho unico.

seleção -> Dispatcher -> contrato/validacao -> permissao -> handler -> resultado

Nenhum teste chama API, navegador, Windows ou arquivos reais: os HANDLERS do
Dispatcher sao trocados por registradores; contrato e permissao sao os reais.
"""
from __future__ import annotations

import ast
import builtins
import json
import pytest
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.dispatcher as dispatcher
import tools.fast_paths as fast_paths
from core.permission_manager import PermissionLevel, PermissionManager
from core.tool_result import ToolResult
from core.tools_registry import tools


def _item(nome, argumentos, bruto=None):
    return SimpleNamespace(
        name=nome,
        arguments=bruto if bruto is not None else json.dumps(argumentos),
        call_id=f"t-{nome}",
    )


def _handler(chamadas, nome, retorno="ok"):
    def handler(args, memory_store, context):
        chamadas.append((nome, dict(args)))
        if isinstance(retorno, Exception):
            raise retorno
        return retorno
    return handler


def _executar(pm):
    return lambda item: dispatcher.executar_ferramenta(item, pm, None)


# ------------------------------------------------------------ 1) caminho do Dispatcher
def test_ferramenta_valida_executa_e_devolve_toolresult(monkeypatch):
    chamadas = []
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "obter_status_windows", _handler(chamadas, "obter_status_windows", "status ok"))
    r = dispatcher.executar_ferramenta(_item("obter_status_windows", {}), PermissionManager(), None)
    assert isinstance(r, ToolResult) and r.ok and r.message == "status ok"
    assert chamadas == [("obter_status_windows", {})]


def test_ferramenta_inexistente_falha_de_forma_controlada():
    r = dispatcher.executar_ferramenta(_item("nao_existe", {}), PermissionManager(), None)
    assert r.ok is False and r.error_code == "unknown_tool"


def test_argumentos_invalidos_falham_sem_chamar_o_handler(monkeypatch):
    chamadas = []
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "navegar_navegador", _handler(chamadas, "navegar_navegador"))
    pm = PermissionManager()
    casos = [
        (_item("navegar_navegador", None, bruto="{nao e json"), "invalid_json_arguments"),
        (_item("navegar_navegador", None, bruto="[1, 2]"), "invalid_arguments"),
        (_item("navegar_navegador", {"url": "https://a.com"}), "contract_error"),  # falta 'modo'
        (_item("navegar_navegador", {"url": "https://a.com", "modo": "visivel", "extra": 1}), "contract_error"),
        (_item("navegar_navegador", {"url": 123, "modo": "visivel"}), "contract_error"),
    ]
    for item, codigo in casos:
        r = dispatcher.executar_ferramenta(item, pm, None)
        assert r.ok is False and r.error_code == codigo, (item.arguments, r)
    assert chamadas == []


def test_permissao_negada_bloqueia_a_execucao(monkeypatch):
    chamadas = []
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "navegar_navegador", _handler(chamadas, "navegar_navegador"))
    pm = PermissionManager()
    pm.policy["browser.navigation"] = PermissionLevel.BLOCKED
    r = dispatcher.executar_ferramenta(_item("navegar_navegador", {"url": "https://a.com", "modo": "visivel"}), pm, None)
    assert r.ok is False and r.error_code == "permission_denied" and r.message.startswith("ACAO NAO EXECUTADA:")
    assert chamadas == []


def test_confirmacao_aprovada_executa_e_negada_nao_executa(monkeypatch):
    chamadas = []
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "encerrar_processo_windows", _handler(chamadas, "encerrar_processo_windows"))
    item = _item("encerrar_processo_windows", {"pid": 4321, "nome": ""})

    monkeypatch.setattr(builtins, "input", lambda *_: "n")
    r = dispatcher.executar_ferramenta(item, PermissionManager(), None)
    assert r.ok is False and r.error_code == "permission_denied" and "negou" in r.message.lower()
    assert chamadas == []

    monkeypatch.setattr(builtins, "input", lambda *_: "s")
    r = dispatcher.executar_ferramenta(item, PermissionManager(), None)
    assert r.ok is True
    assert chamadas == [("encerrar_processo_windows", {"pid": 4321, "nome": ""})]


def test_erro_do_handler_nao_derruba_o_processo(monkeypatch):
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "obter_status_windows", _handler([], "x", RuntimeError("boom")))
    r = dispatcher.executar_ferramenta(_item("obter_status_windows", {}), PermissionManager(), None)
    assert r.ok is False and r.error_code == "exception" and "boom" in r.message


def test_erro_operacional_conhecido_do_handler_e_convertido(monkeypatch):
    monkeypatch.setitem(
        dispatcher.TOOL_HANDLERS,
        "obter_status_windows",
        _handler([], "x", ValueError("entrada invalida")),
    )
    r = dispatcher.executar_ferramenta(_item("obter_status_windows", {}), PermissionManager(), None)
    assert r.ok is False and r.error_code == "exception" and "entrada invalida" in r.message


def test_excecao_de_programacao_nao_e_silenciosamente_convertida(monkeypatch):
    monkeypatch.setitem(
        dispatcher.TOOL_HANDLERS,
        "obter_status_windows",
        _handler([], "x", AssertionError("invariante quebrada")),
    )
    with pytest.raises(AssertionError, match="invariante quebrada"):
        dispatcher.executar_ferramenta(
            _item("obter_status_windows", {}),
            PermissionManager(),
            None,
        )


def test_principais_ferramentas_do_registry_passam_por_contrato_permissao_e_handler(monkeypatch):
    """Cada tool do registry, com argumentos validos gerados do schema, chega ao handler."""
    assert dispatcher.validar_registry_handlers() == (True, "")
    monkeypatch.setattr(builtins, "input", lambda *_: "s")  # tools com CONFIRM

    def valor(spec):
        if "enum" in spec:
            return spec["enum"][0]
        if "minimum" in spec:
            return spec["minimum"]
        return {"string": "x", "integer": 1, "number": 1, "boolean": True}[spec["type"]]

    pulados = {"preencher_elemento_windows"}  # exige preflight real de UI Automation
    executadas = []
    for tool in tools:
        nome = tool["name"]
        if nome in pulados:
            continue
        chamadas = []
        monkeypatch.setitem(dispatcher.TOOL_HANDLERS, nome, _handler(chamadas, nome))
        props = tool["parameters"].get("properties", {})
        args = {k: valor(props[k]) for k in tool["parameters"].get("required", [])}
        r = dispatcher.executar_ferramenta(_item(nome, args), PermissionManager(max_actions=50), None)
        assert r.ok, (nome, args, r)
        assert len(chamadas) == 1, nome
        executadas.append(nome)
    assert len(executadas) >= len(tools) - len(pulados)


# ------------------------------------------------------------ 1B) plugin nao cria caminho paralelo
def test_plugin_handler_so_roda_quando_o_dispatcher_o_chama(monkeypatch, tmp_path):
    from core.plugin_loader import discover_plugins

    approval = tmp_path / "aprovacoes.json"
    approval.write_text(
        json.dumps({"unico_plugin": {"habilitado": True, "aprovado": True}}),
        encoding="utf-8",
    )
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    marker = tmp_path / "executado.txt"
    plugin = plugins_dir / "unico_plugin.py"
    plugin.write_text(
        f'''
from pathlib import Path
from core.tool_result import ToolResult

DEPENDENCIAS = ("core.tool_result",)

CAPABILITY = {{
    "id": "plugin.unico_plugin",
    "descricao": "Teste do caminho unico.",
    "local": True,
    "deterministica": True,
    "multi_etapa": False,
    "exige_raciocinio": False,
    "resolver": "plugin",
}}

def executar(argumentos):
    Path(r"{marker}").write_text("rodou", encoding="utf-8")
    return ToolResult.success("ok", tool_name=TOOL["name"])

TOOL = {{
    "name": "unico_plugin",
    "description": "Plugin de caminho unico.",
    "parameters": {{"type": "object", "properties": {{}}, "required": [], "additionalProperties": False}},
    "handler": executar,
}}
''',
        encoding="utf-8",
    )

    registry = discover_plugins(plugins_dir, approval_file=approval, logger=lambda _msg: None)
    try:
        assert not marker.exists()
        resultado = dispatcher.executar_ferramenta(
            _item("unico_plugin", {}),
            PermissionManager(),
            None,
        )
        assert resultado.ok
        assert marker.read_text(encoding="utf-8") == "rodou"
    finally:
        registry.descarregar()
        marker.unlink(missing_ok=True)


# ------------------------------------------------------------ 2) atalhos executam PELO Dispatcher
def test_atalho_executa_pelo_dispatcher_com_contrato_e_permissao(monkeypatch):
    chamadas = []
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "navegar_navegador", _handler(chamadas, "navegar_navegador", "Naveguei"))
    autorizadas = []
    pm = PermissionManager()
    original = pm.autorizar
    pm.autorizar = lambda nome, args: autorizadas.append((nome, dict(args))) or original(nome, args)
    assert fast_paths.comando_rapido("abra o youtube", _executar(pm)) == (True, "Naveguei")
    assert chamadas == [("navegar_navegador", {"url": "https://www.youtube.com", "modo": "visivel"})]
    assert autorizadas == [("navegar_navegador", {"url": "https://www.youtube.com", "modo": "visivel"})]


def test_atalho_e_modelo_usam_o_mesmo_caminho_e_os_mesmos_argumentos(monkeypatch):
    """Texto e voz chegam aqui pelo mesmo Harness; o atalho e a chamada do modelo sao indistinguiveis para o Dispatcher."""
    vistos = []
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "navegar_navegador", _handler(vistos, "navegar_navegador", "ok"))
    pm = PermissionManager(max_actions=50)
    assert fast_paths.comando_rapido("abra https://example.com", _executar(pm)) == (True, "ok")        # atalho
    dispatcher.executar_ferramenta(_item("navegar_navegador", {"url": "https://example.com", "modo": "visivel"}), pm, None)  # modelo
    assert vistos[0] == vistos[1]


def test_atalho_respeita_bloqueio_do_dispatcher(monkeypatch):
    chamadas = []
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "navegar_navegador", _handler(chamadas, "navegar_navegador"))
    pm = PermissionManager()
    pm.policy["browser.navigation"] = PermissionLevel.BLOCKED
    tratado, texto = fast_paths.comando_rapido("abra o youtube", _executar(pm))
    assert tratado is True and texto.startswith("ACAO NAO EXECUTADA:")
    assert chamadas == []


def test_atalho_com_excecao_no_handler_nao_propaga_e_conta_como_falha(monkeypatch):
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "navegar_navegador", _handler([], "x", RuntimeError("boom")))
    tratado, texto = fast_paths.comando_rapido("abra o youtube", _executar(PermissionManager()))
    assert tratado is True
    # O Harness classifica falha de atalho por estes marcadores; a excecao nao pode virar "sucesso".
    assert any(m in texto.lower() for m in ("acao nao executada", "nao consegui")), texto
    assert "boom" in texto


def test_atalho_de_abas_para_na_primeira_falha(monkeypatch):
    chamadas = []
    retornos = iter(["Abri uma nova aba.", "Nao consegui abrir a aba."])
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "abrir_nova_aba", lambda a, m, c: chamadas.append(1) or next(retornos))
    tratado, texto = fast_paths.comando_rapido("abra tres abas", _executar(PermissionManager()))
    assert tratado is True and texto == "Nao consegui abrir a aba." and len(chamadas) == 2


def test_atalho_de_abas_bem_sucedido_mantem_o_formato(monkeypatch):
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "abrir_nova_aba", lambda a, m, c: "Abri uma nova aba.")
    assert fast_paths.comando_rapido("abra duas abas", _executar(PermissionManager())) == (True, "Abri 2 novas abas.\nAbri uma nova aba.")


# ------------------------------------------------------------ 3) guardas estruturais
def _modulos_importados(rel):
    arvore = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    mods = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            mods.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom):
            base = no.module or ""
            mods.add(base)
            mods.update(f"{base}.{a.name}" for a in no.names)
    return mods


def test_fast_paths_nao_toca_ferramentas_nem_permissoes_diretamente():
    mods = _modulos_importados("tools/fast_paths.py")
    proibidos = {"tools.browser", "tools.windows", "tools.applications", "tools.files", "tools.dispatcher",
                 "core.permission_manager"}
    assert not (mods & proibidos), mods & proibidos
    codigo = (ROOT / "tools" / "fast_paths.py").read_text(encoding="utf-8")
    assert ".autorizar(" not in codigo and ".registrar_resultado(" not in codigo


def test_caminhos_criticos_nao_usam_except_exception_generico():
    for rel in ("core/permission_manager.py", "tools/dispatcher.py"):
        arvore = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        genericos = [
            no
            for no in ast.walk(arvore)
            if isinstance(no, ast.ExceptHandler)
            and isinstance(no.type, ast.Name)
            and no.type.id == "Exception"
        ]
        assert not genericos, rel


def test_so_o_dispatcher_importa_os_modulos_de_ferramenta_no_runtime():
    """Fora de tools/ (e dos facades de compatibilidade), ninguem importa as ferramentas para executa-las."""
    permitidos = {"auren.py", "core/facade.py"}  # re-export de compatibilidade V43, nao e caminho de execucao
    alvo = {"tools.browser", "tools.windows", "tools.applications", "tools.files"}
    excluir = ("tests/", "data/", "medir_", "testar_", "testes_auren", ".venv/", "tools/")
    for caminho in ROOT.rglob("*.py"):
        rel = caminho.relative_to(ROOT).as_posix()
        if rel.startswith(excluir) or rel in permitidos:
            continue
        mods = _modulos_importados(rel)
        assert not (mods & alvo), (rel, mods & alvo)
    # E dentro de tools/, apenas o Dispatcher monta handlers sobre elas.
    for rel in ("tools/fast_paths.py", "tools/memory.py"):
        assert not (_modulos_importados(rel) & alvo), rel


def test_texto_e_voz_montam_o_mesmo_harness():
    voz = (ROOT / "voice" / "main.py").read_text(encoding="utf-8")
    assert "auren.criar_harness()" in voz
    assert not any(m.startswith("tools.") for m in _modulos_importados("voice/main.py"))
    facade = (ROOT / "auren.py").read_text(encoding="utf-8")
    # O harness recebe, e so recebe, estes dois pontos de execucao.
    assert "executar_ferramenta=executar_ferramenta" in facade
    assert "comando_rapido=comando_rapido" in facade
    assert "_comando_rapido(mensagem, executar_ferramenta)" in facade
