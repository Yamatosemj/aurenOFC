"""Selecao de acao: o Router e o dono unico (core/router.py).

Cobre: pedidos conhecidos -> ferramenta certa; pedidos que nao sao ferramentas;
atalhos locais; e a garantia de que nao ha dois mecanismos ativos decidindo.
Nenhum teste chama API ou executa ferramenta real.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.dispatcher as dispatcher
import tools.fast_paths as fast_paths
from core.capability_audio_runtime import ENV_FLAG, try_execute
from core.local_decision import ESCOLHAS_EXECUTADAS_LOCALMENTE, SITES_CONHECIDOS
from core.orchestrator import AurenOrchestrator
from core.router import Router, get_router
from core.tool_result import ToolResult
from core.tools_registry import tools

ALL_TOOLS = [item["name"] for item in tools]


class _Permissoes:
    def __init__(self, negar: bool = False) -> None:
        self.negar = negar
        self.autorizadas: list[tuple[str, dict]] = []

    def autorizar(self, nome, args):
        self.autorizadas.append((nome, dict(args)))
        return (False, "bloqueado no teste") if self.negar else (True, "")

    def registrar_resultado(self, ok, nome, args):
        pass


def _executar(permissoes):
    """Mesmo caminho do runtime: atalho -> Dispatcher (contrato -> permissao -> handler)."""
    return lambda item: dispatcher.executar_ferramenta(item, permissoes, None)


def _stub_ferramentas(monkeypatch) -> list[tuple[str, dict]]:
    """Troca os HANDLERS do Dispatcher por registradores (contrato e permissao continuam reais)."""
    chamadas: list[tuple[str, dict]] = []
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "obter_status_windows", lambda args, mem, ctx: chamadas.append(("obter_status_windows", {})) or "status ok")
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "abrir_nova_aba", lambda args, mem, ctx: chamadas.append(("abrir_nova_aba", {"url": args["url"]})) or "Abri uma nova aba.")
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "navegar_navegador", lambda args, mem, ctx: chamadas.append(("navegar_navegador", {"url": args["url"]})) or f"Naveguei para {args['url']}")
    return chamadas


# ----------------------------------------------------- 1) pedidos conhecidos -> ferramenta certa
LOCAL_CASES = [
    ("que horas são?", [("obter_status_windows", {})]),
    ("quanta RAM está sendo usada", [("obter_status_windows", {})]),
    ("abra duas abas", [("abrir_nova_aba", {"url": ""})] * 2),
    ("abra o YouTube", [("navegar_navegador", {"url": SITES_CONHECIDOS["youtube"]})]),
    ("abra o discord", [("navegar_navegador", {"url": SITES_CONHECIDOS["discord"]})]),
    ("abra https://example.com/x?y=1", [("navegar_navegador", {"url": "https://example.com/x?y=1"})]),
    ("abra o exemplo.com.br", [("navegar_navegador", {"url": "exemplo.com.br"})]),
]


def test_atalhos_locais_executam_a_ferramenta_correta(monkeypatch):
    for frase, esperado in LOCAL_CASES:
        chamadas = _stub_ferramentas(monkeypatch)
        tratado, resposta = fast_paths.comando_rapido(frase, _executar(_Permissoes()))
        assert tratado is True, frase
        assert resposta, frase
        assert chamadas == esperado, frase


MODEL_CASES = [
    ("volume 40%", "definir_volume_windows"),
    ("maximize a janela do Notepad", "maximizar_janela_windows"),
    ("mova a janela do Bloco de Notas para 100,100", "mover_janela_windows"),
    ("leia a área de transferência", "ler_area_transferencia_windows"),
    ("liste os processos do Windows", "listar_processos_windows"),
    ("procure o arquivo meu documento pdf", "buscar_arquivo"),
    ("pesquise Create Aeronautics no YouTube", "navegar_navegador"),
    ("clique no mouse em x=500 y=300", "clicar_mouse_windows"),
    ("inspecione a interface da janela AUREN_UIA_TESTE procurando Campo de Teste", "inspecionar_interface_windows"),
    ("toque uma playlist no Spotify", "controle_midia_windows"),
    ("salve na memória que minha playlist de trabalho é X", "salvar_memoria_persistente"),
]


def test_pedidos_conhecidos_sem_atalho_chegam_ao_modelo_com_a_ferramenta_certa(monkeypatch):
    for frase, ferramenta in MODEL_CASES:
        chamadas = _stub_ferramentas(monkeypatch)
        assert fast_paths.comando_rapido(frase, _executar(_Permissoes())) == (False, ""), frase  # nenhum atalho rouba o pedido
        assert chamadas == [], frase
        assert ferramenta in Router().select_tool_names(frase, tools), frase


def test_pedidos_que_nao_sao_ferramentas_seguem_normalmente(monkeypatch):
    for frase in ("o que você acha disso?", "qual é a capital da França?", "me explique o que é uma API", "obrigado!", ""):
        chamadas = _stub_ferramentas(monkeypatch)
        router = Router()
        assert router.decidir_local(frase).choice == "unknown_or_complex", frase
        assert fast_paths.comando_rapido(frase, _executar(_Permissoes())) == (False, ""), frase
        assert chamadas == [], frase
        assert router.select_tool_names(frase, tools) == ALL_TOOLS, frase  # fallback: modelo decide com o registry completo
        assert router.last_domains == [], frase


def test_atalhos_preservam_politicas_do_executor(monkeypatch):
    chamadas = _stub_ferramentas(monkeypatch)
    assert fast_paths.comando_rapido("abra 11 abas", _executar(_Permissoes())) == (True, "Quantidade de abas invalida. Use entre 1 e 10.")
    assert fast_paths.comando_rapido("abra 0 abas", _executar(_Permissoes())) == (True, "Quantidade de abas invalida. Use entre 1 e 10.")
    permissoes = _Permissoes(negar=True)
    assert fast_paths.comando_rapido("abra o youtube", _executar(permissoes)) == (True, "ACAO NAO EXECUTADA: bloqueado no teste")
    assert fast_paths.comando_rapido("abra duas abas", _executar(permissoes)) == (True, "ACAO NAO EXECUTADA: bloqueado no teste")
    assert chamadas == []  # negado antes de executar
    assert [nome for nome, _ in permissoes.autorizadas] == ["navegar_navegador", "abrir_nova_aba"]


def test_escolhas_sem_executor_local_continuam_indo_ao_modelo(monkeypatch):
    """control_media / set_volume / set_mute sao decididas pelo Router mas nao viram atalho (comportamento atual)."""
    router = Router()
    for frase, escolha in (("pausa", "control_media"), ("proxima", "control_media"),
                           ("coloque o volume em 40", "set_volume"), ("ative o mudo", "set_mute")):
        chamadas = _stub_ferramentas(monkeypatch)
        assert router.decidir_local(frase).choice == escolha
        assert escolha not in ESCOLHAS_EXECUTADAS_LOCALMENTE
        assert fast_paths.comando_rapido(frase, _executar(_Permissoes())) == (False, "")
        assert chamadas == []


# ----------------------------------------------------- 2) um unico mecanismo de decisao
MATRIZ = [frase for frase, _ in LOCAL_CASES] + [frase for frase, _ in MODEL_CASES] + [
    "abra 11 abas", "pausa", "coloque o volume em 40", "ative o mudo", "abra o chrome", "o que você acha disso?",
    "abra o youtube e pesquise algo", "que horas são em Tóquio", "próxima música", "qual está o volume?",
]


def test_atalho_so_acontece_quando_o_router_decide_e_na_ferramenta_que_o_router_oferece(monkeypatch):
    router = get_router()
    for frase in MATRIZ:
        chamadas = _stub_ferramentas(monkeypatch)
        escolha = router.decidir_local(frase).choice
        tratado, _ = fast_paths.comando_rapido(frase, _executar(_Permissoes()))
        # Executa localmente <=> o Router escolheu uma acao executavel localmente.
        assert tratado == (escolha in ESCOLHAS_EXECUTADAS_LOCALMENTE), frase
        # E a ferramenta executada tambem esta no toolset que o mesmo Router daria ao modelo.
        oferecidas = set(Router().select_tool_names(frase, tools))
        for nome, _args in chamadas:
            assert nome in oferecidas, (frase, nome)


def test_runtime_usa_uma_unica_instancia_de_router():
    provider = SimpleNamespace(create_response=lambda *a, **k: None, name="fake")
    assert AurenOrchestrator(provider=provider).router is get_router()
    assert AurenOrchestrator(provider=provider).router is AurenOrchestrator(provider=provider).router


def test_experimento_de_audio_nao_compete_com_atalhos_locais(monkeypatch):
    """Com a flag ligada, uma frase nunca e resolvida ao mesmo tempo pelo audio e por um atalho executavel."""
    monkeypatch.setenv(ENV_FLAG, "1")
    router = get_router()
    for frase in MATRIZ + ["volume 40%", "mudo", "play pause", "música anterior"]:
        chamou = []
        tratado_audio, _msg, _meta = try_execute(
            frase, executar_ferramenta=lambda item: chamou.append(item) or ToolResult.success("ok", tool_name=item.name)
        )
        if tratado_audio:
            assert router.decidir_local(frase).choice not in ESCOLHAS_EXECUTADAS_LOCALMENTE, frase
            assert json.loads(chamou[0].arguments) is not None


def _fontes_de_runtime() -> dict[str, str]:
    excluir_prefixos = ("tests/", "data/", "medir_", "testar_", "testes_auren", ".venv/")
    fontes = {}
    for caminho in ROOT.rglob("*.py"):
        rel = caminho.relative_to(ROOT).as_posix()
        if rel.startswith(excluir_prefixos):
            continue
        fontes[rel] = caminho.read_text(encoding="utf-8")
    return fontes


def test_fast_paths_nao_tem_regras_proprias_de_decisao():
    arvore = ast.parse((ROOT / "tools" / "fast_paths.py").read_text(encoding="utf-8"))
    importados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados.update(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom):
            importados.add(no.module or "")
    assert "re" not in importados
    assert "core.router" in importados
    assert "core.local_decision" in importados  # so para SITES_CONHECIDOS (dado), nao para decidir
    codigo = (ROOT / "tools" / "fast_paths.py").read_text(encoding="utf-8")
    assert "LocalDecisionEngine" not in codigo
    assert "fullmatch" not in codigo and "re.search" not in codigo


def test_regras_locais_so_sao_usadas_pelo_router_em_runtime():
    usam = {rel for rel, src in _fontes_de_runtime().items() if "LocalDecisionEngine" in src}
    assert usam == {"core/local_decision.py", "core/router.py"}


def test_capability_e_taskspec_nao_estao_no_caminho_ativo():
    """CapabilityResolver/IntentResolver/TaskSpec so existem atras da flag experimental de audio."""
    permitidos = {
        "core/capability_resolver.py", "core/intent_resolver.py", "core/task_spec.py", "core/capabilities.py",
        "core/capability_audio_runtime.py", "core/capability_audio_experiment.py", "core/router.py",
        # Ferramenta manual de diagnostico, fora do caminho de execucao do Auren.
        "scripts/diagnosticos/testar_spotify_desktop_runtime.py",
    }
    marcas = ("CapabilityResolver", "IntentResolver", "validate_task_spec", "route_task_spec")
    usam = {rel for rel, src in _fontes_de_runtime().items() if any(m in src for m in marcas)}
    assert usam <= permitidos, usam - permitidos
    # O unico ponto de entrada a partir do fluxo principal e a flag, desligada por padrao.
    auren_src = (ROOT / "auren.py").read_text(encoding="utf-8")
    assert "_try_experimental_audio(" in auren_src
    ok, _msg, meta = try_execute("volume 40%", executar_ferramenta=lambda item: ToolResult.success("x"))
    assert ok is False and meta["reason"] == "flag_disabled"
