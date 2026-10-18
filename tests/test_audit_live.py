import json
from types import SimpleNamespace

import pytest

from core.harness import AurenHarness
from core.harness_followup import resolver_continuacao
from core.tool_result import from_legacy
from tools import applications


def test_liv001_exact_path_has_priority_over_fuzzy_application(tmp_path, monkeypatch):
    target = tmp_path / "run-ficticio" / "EditorFicticio.exe"
    target.parent.mkdir()
    target.write_bytes(b"nao e executavel real")
    discovered, launches = [], []
    monkeypatch.setattr(applications, "encontrar_aplicativo", lambda name:
                        discovered.append(name) or {"Name": "Run", "AppID": "falso"})
    monkeypatch.setattr(applications.subprocess, "Popen", lambda cmd, **kw:
                        launches.append(cmd) or SimpleNamespace(pid=742))
    result = from_legacy(applications.abrir_programa(str(target)))
    assert not discovered
    assert launches == [[str(target.resolve())]]
    assert result.ok
    assert result.data["caminho"] == str(target.resolve())
    assert "solicit" in result.message.lower()


def test_liv001_missing_explicit_path_never_opens_another_app(tmp_path, monkeypatch):
    launched = []
    monkeypatch.setattr(applications, "encontrar_aplicativo", lambda name: {"Name": "Run", "AppID": "falso"})
    monkeypatch.setattr(applications.subprocess, "Popen", lambda *a, **kw: launched.append(a))
    result = from_legacy(applications.abrir_programa(str(tmp_path / "missing.exe")))
    assert not result.ok
    assert not launched


@pytest.mark.parametrize("goal,tool", [
    ("maximize a janela ALFA sem listar outras janelas", "listar_janelas_windows"),
    ("Na janela ALFA preencha o segundo campo", "consultar_memoria_persistente"),
    ("Não feche outras janelas; maximize ALFA", "listar_janelas_windows"),
])
def test_liv002_observation_is_not_completion_of_action(goal, tool):
    assert not AurenHarness._pode_encerrar_localmente(goal, [{
        "ferramenta": tool, "sucesso": True, "argumentos": "{}", "resultado": "observacao ficticia"}])


@pytest.mark.parametrize("goal", [
    "Defina a janela ALFA: maximize, restaure, mova para 150 200 e redimensione para 560 360",
    "Defina a janela ALFA maximizando, restaurando, movendo e redimensionando",
])
def test_liv007_first_mutation_does_not_complete_composed_goal(goal):
    assert not AurenHarness._pode_encerrar_localmente(goal, [{
        "ferramenta": "maximizar_janela_windows", "sucesso": True,
        "argumentos": '{"alvo":"ALFA"}', "resultado": "maximizada"}])


def test_liv005_question_survives_restriction_at_start():
    harness = object.__new__(AurenHarness)
    harness._pergunta_pendente = None
    goal = "Não feche outras abas; abra a página fictícia"
    harness._guardar_esclarecimento(goal, "Qual cor devo escolher?")
    effective, status = resolver_continuacao(harness._pergunta_pendente, "AZUL_FICTICIO")
    assert goal in effective
    assert "AZUL_FICTICIO" in effective
    assert "Pergunta pendente" in effective
    assert status == "normal"
