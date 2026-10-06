from __future__ import annotations

import ast
import inspect
import importlib
from datetime import datetime, timezone
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def fail(msg: str) -> None:
    raise AssertionError(msg)


def main() -> int:
    checks = []

    # 1) Import every internal module without needing the OpenAI client.
    modules = [
        "config",
        "auren",
        "main",
        "core.prompt",
        "core.response",
        "core.router",
        "core.orchestrator",
        "brains.base",
        "brains.fast",
        "brains.deep",
        "providers.openai_provider",
        "core.tools_registry",
        "core.usage",
        "core.utils",
        "core.harness",
        "core.permission_manager",
        "tools.applications",
        "tools.browser",
        "tools.dispatcher",
        "tools.fast_paths",
        "tools.files",
        "tools.memory",
        "tools.windows",
        "memory.store",
    ]
    for name in modules:
        importlib.import_module(name)
    checks.append("imports internos")

    import auren
    from core.tools_registry import tools
    from core.tool_contracts import DEFAULT_TOOL_CONTRACTS
    from core.permission_manager import PermissionManager

    assert auren.AUREN_VERSION == 46
    assert auren.MODEL == "gpt-5.6-luna"
    assert auren.CACHE_KEY == "auren-v46"
    checks.append("versao/cache/modelo")
    assert auren.ARCHITECTURE_NAME == "V46 ARI NATIVE SURGERY"
    checks.append("nome da nova arquitetura")

    from core.orchestrator import AurenOrchestrator
    from core.router import Router
    from brains.fast import FastBrain
    from brains.deep import DeepBrain
    from providers.openai_provider import OpenAIProvider
    orchestrator = AurenOrchestrator()
    assert isinstance(orchestrator.router, Router)
    assert isinstance(orchestrator.brains["fast"], FastBrain)
    assert isinstance(orchestrator.brains["deep"], DeepBrain)
    assert isinstance(orchestrator.provider, OpenAIProvider)
    assert orchestrator.router.route("teste") == "fast"
    checks.append("Orchestrator + Router + Fast/Deep Brain + Provider")


    names = [item["name"] for item in tools]
    assert len(names) == 45 and len(set(names)) == 45
    DEFAULT_TOOL_CONTRACTS.validate_registry()
    assert set(DEFAULT_TOOL_CONTRACTS.names()) == set(names)
    assert all(callable(getattr(auren, n, None)) for n in names)
    checks.append("45 ferramentas expostas + contratos genericos")

    from tools.dispatcher import TOOL_HANDLERS, validar_registry_handlers
    handlers_ok, handlers_error = validar_registry_handlers()
    assert handlers_ok, handlers_error
    assert len(TOOL_HANDLERS) == 45
    checks.append("registry de handlers cobre as 45 ferramentas")

    pm = PermissionManager(max_actions=10)
    policy = set(pm.policy)
    required_capabilities = set(DEFAULT_TOOL_CONTRACTS.capabilities().values())
    assert required_capabilities <= policy, sorted(required_capabilities - policy)
    assert not (policy & set(names)), "politica ainda contem nomes de ferramentas"
    assert all(pm.nivel(name) != pm.nivel("nao_existe") for name in names if name != "nao_existe")
    checks.append("politica central por capacidade cobre todas as capacidades")

    # Compare facade signatures contra o contrato histórico congelado da V43 original.
    from tests.v43_api_signatures import V43_SIGNATURES
    original_signatures = V43_SIGNATURES
    for name in names:
        # A V46 pode adicionar novas ferramentas sem alterar as assinaturas congeladas da V43.
        if name not in original_signatures:
            continue
        expected = original_signatures[name]
        actual = str(inspect.signature(getattr(auren, name)))
        # Normalize a leading annotation-free signature comparison by parsing both.
        expected_args = ast.unparse(ast.parse(f"def _({expected}):\n    pass").body[0].args)
        actual_args = ast.unparse(ast.parse(f"def _{actual}:\n    pass").body[0].args)
        assert expected_args == actual_args, f"assinatura mudou em {name}: {expected_args!r} != {actual_args!r}"
    checks.append("assinaturas das ferramentas preservadas")

    # Memory behavior and credential blocking.
    import tempfile
    from memory.store import PersistentMemoryStore
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "memory.sqlite3"
        store = PersistentMemoryStore(p)
        assert store.salvar("chave teste", "valor teste")["ok"]
        assert store.consultar("chave teste")["total"] == 1
        store2 = PersistentMemoryStore(p)
        assert store2.consultar("chave teste")["memorias"][0]["valor"] == "valor teste"
        assert not store2.salvar("credencial de teste", "token secreto")["ok"]
        assert store2.esquecer("chave teste")["ok"]
        assert store2.consultar("chave teste")["total"] == 0
    checks.append("memoria persistente")

    # Regression checks for small V43 maintenance bugs.
    import json
    import tempfile
    import tools.applications as applications
    from core import harness as harness_module

    # 1) applications.py must have a real shutil import and its fallback path
    # must be callable when Windows app/shortcut/executable discovery fails.
    original_finders = (applications.encontrar_aplicativo, applications.procurar_atalho, applications.procurar_executavel)
    original_which = applications.shutil.which
    try:
        applications.encontrar_aplicativo = lambda _nome: None
        applications.procurar_atalho = lambda _nome: None
        applications.procurar_executavel = lambda _nome: None
        applications.shutil.which = lambda _programa: None
        fallback_result = applications.abrir_programa("__auren_programa_que_nao_existe__")
        assert "Nao encontrei o programa" in fallback_result
    finally:
        applications.encontrar_aplicativo, applications.procurar_atalho, applications.procurar_executavel = original_finders
        applications.shutil.which = original_which
    checks.append("applications fallback + import shutil")

    # 2) Empates de relevancia devem respeitar recencia.
    from datetime import timedelta
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "memory.sqlite3"
        store = PersistentMemoryStore(p)
        agora = datetime.now(timezone.utc)
        with store._lock, store._conexao() as con:
            for indice in range(6):
                ts = (agora - timedelta(seconds=indice)).isoformat(timespec="seconds")
                con.execute(
                    "INSERT INTO memorias (chave, valor, categoria, criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?)",
                    (f"memoria {indice}", "mesmo assunto", "geral", ts, ts),
                )
            con.commit()
        memorias = store.consultar("mesmo assunto", 3)["memorias"]
        assert [m["chave"] for m in memorias] == ["memoria 0", "memoria 1", "memoria 2"]
    checks.append("memoria ordena empates por recencia")

    # 3) Usage metadata must stay numeric in the canonical log so the cost
    # meter can read it. Sensitive keys remain redacted separately.
    uso = {
        "input_tokens": 111,
        "output_tokens": 22,
        "cached_tokens": 333,
        "cache_write_tokens": 4,
    }
    compacto = harness_module._compact_json({"uso": uso})
    assert json.loads(compacto)["uso"] == uso
    from medir_custo_modelo import TOKEN_RE
    capturados = dict(TOKEN_RE.findall(compacto))
    assert {k: int(v) for k, v in capturados.items()} == uso
    checks.append("log de uso preserva os 4 contadores de tokens")

    # Tool dispatcher and safe non-Windows guards.
    from types import SimpleNamespace
    from tools.dispatcher import executar_ferramenta
    from core.tool_result import ToolResult
    import auren as facade
    for name, args in [
        ("obter_status_windows", {}),
        ("obter_audio_windows", {}),
        ("ler_area_transferencia_windows", {}),
        ("listar_processos_windows", {}),
    ]:
        pm2 = PermissionManager(max_actions=10)
        item = SimpleNamespace(name=name, arguments="{}")
        facade.permission_manager = pm2
        result = executar_ferramenta(item, pm2, facade.memory_store)
        assert isinstance(result, ToolResult) and result.message
    checks.append("dispatcher + guardas fora do Windows")

    print("VERIFICACAO MODULAR V46: PASS")
    for check in checks:
        print(f"[PASS] {check}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
