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


def test_skill_library_is_empty_or_loads_valid_skill(tmp_path: Path):
    skill_dir = tmp_path / "teste"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: teste\ndescription: faz um teste\n---\nUse esta skill.", encoding="utf-8")
    skills = SkillLibrary(tmp_path).discover()
    assert len(skills) == 1
    assert skills[0].name == "teste"


def test_agent_plans_and_reflects_without_second_brain():
    from agent.orchestrator import AgentOrchestrator
    from core.tool_result import ToolResult

    agent = AgentOrchestrator()
    plan = agent.begin("abra o Chrome e depois pesquise o projeto")
    assert plan.complexity in {"multi_step", "complex"}
    verification, reflection = agent.observe("abrir_programa", ToolResult.success("Chrome aberto"))
    assert verification.ok is True
    assert "etapas" in reflection.guidance.lower() or "passo" in reflection.guidance.lower()


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
        "---\nname: navegador\ndescription: ajuda com navegador e pesquisa\n---\nUse como referencia para tarefas de navegador.",
        encoding="utf-8",
    )
    library = SkillLibrary(root)
    installed = library.install(source)
    assert installed.name == "navegador"
    matched = library.match("pesquise no navegador", limit=1)
    assert [s.name for s in matched] == ["navegador"]
    assert "Skills locais relevantes" in library.prompt_context("pesquise no navegador")
