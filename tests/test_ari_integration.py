from __future__ import annotations

from pathlib import Path

from core.local_decision import LocalDecisionEngine
from memory.store import PersistentMemoryStore
from skills.loader import SkillLibrary


def test_local_decision_abstains_on_complex_request():
    result = LocalDecisionEngine().choice("abra o Chrome, procure meu projeto e me diga o que encontrou")
    assert result.choice == "unknown_or_complex"
    assert not result.confident


def test_local_decision_recognizes_safe_exact_commands():
    result = LocalDecisionEngine().choice("que horas sao")
    assert result.choice == "get_system_status"
    assert result.confident
    assert result.latency_ms >= 0


def test_memory_conversation_and_strategy(tmp_path: Path):
    store = PersistentMemoryStore(tmp_path / "m.db")
    assert store.registrar_conversa("c1", "user", "eu gosto de respostas curtas")["ok"]
    found = store.buscar_conversas("respostas curtas")
    assert found["total"] == 1
    assert store.salvar_estrategia("abrir site", ["navegar_navegador"], "feito", True)["ok"]
    strategies = store.buscar_estrategias("abrir site")
    assert strategies["total"] == 1


def test_agent_plans_without_second_brain():
    from agent.orchestrator import AgentOrchestrator

    agent = AgentOrchestrator()
    plan = agent.begin("abra o Chrome e depois pesquise o projeto")
    assert plan.complexity in {"multi_step", "complex"}
    assert len(plan.steps) >= 2


def test_screen_tool_is_registered_with_read_only_contract():
    from core.tools_registry import tools
    from core.tool_contracts import capability_for_tool
    from tools.dispatcher import TOOL_HANDLERS

    names = {item["name"] for item in tools}
    assert "capturar_tela_windows" in names
    assert "capturar_tela_windows" in TOOL_HANDLERS
    assert capability_for_tool("capturar_tela_windows") == "windows.screen.read"


def test_skill_matching_and_prompt_context(tmp_path: Path):
    from skills.loader import SkillLibrary

    root = tmp_path / "skills"
    source = tmp_path / "source_skill"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---
name: navegador
description: ajuda com navegador e pesquisa
---
Use como referencia para tarefas de navegador.",
        encoding="utf-8",
    )
    library = SkillLibrary(root)
    installed = library.install(source)
    assert installed.name == "navegador"
    matched = library.match("pesquise no navegador", limit=1)
    assert [s.name for s in matched] == ["navegador"]
    assert "Skills locais relevantes" in library.prompt_context("pesquise no navegador")
