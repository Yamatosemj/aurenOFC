"""Conversation regressions; no API, personal files, or desktop effects."""
from types import SimpleNamespace

import pytest

from core.harness import AurenHarness
from core.harness_followup import PerguntaPendente, resolver_continuacao


def harness_with_answers(*answers):
    answers = iter(answers)
    return AurenHarness(
        criar_resposta=lambda *a, **k: SimpleNamespace(output=[], output_text=next(answers), usage=None),
        executar_ferramenta=lambda c: pytest.fail("Unexpected tool execution"),
        mostrar_uso=lambda: None, obter_chamadas=lambda r: [],
        comando_rapido=lambda _: (False, ""), iniciar_tarefa=lambda: None,
        apos_tarefa=None, fechar=lambda: None,
    )


@pytest.mark.parametrize("goal,answer", [
    ("ola auren", "Olá! Como posso ajudar?"),
    ("bom dia", "Bom dia! Em que posso ajudar?"),
    ("obrigado", "De nada! Precisa de mais alguma coisa?"),
    ("vamos conversar", "Claro! Sobre o que quer conversar?"),
])
def test_social_question_does_not_capture_next_request(goal, answer):
    h = harness_with_answers(answer)
    h.processar_mensagem(goal)
    assert h._pergunta_pendente is None
    request = "auren, crie um timer de 10 minutos"
    assert resolver_continuacao(h._pergunta_pendente, request) == (request, "normal")


@pytest.mark.parametrize("command", [
    "auren, crie um timer de 10 minutos", "Me lembre de estudar amanhã às 14h",
    "Cancele meu timer", "Adie esse lembrete em 10 minutos", "Crie uma pasta ficticia",
])
def test_new_command_replaces_pending_clarification(command):
    pending = PerguntaPendente("abra o arquivo ficticio", "Qual arquivo?")
    assert resolver_continuacao(pending, command) == (command, "normal")


@pytest.mark.parametrize("answer", ["AZUL_FICTICIO", "amanhã às 14h", "pasta ficticia"])
def test_actual_short_clarification_is_preserved(answer):
    h = harness_with_answers("Qual cor devo escolher?")
    h.processar_mensagem("Escolha uma cor para o exemplo ficticio")
    assert h._pergunta_pendente is not None
    resolved, status = resolver_continuacao(h._pergunta_pendente, answer)
    assert "Esclarecimento do usuario: " + answer in resolved
    assert status == "normal"


def test_open_invitation_after_real_task_is_not_a_clarification():
    h = harness_with_answers("A soma é quatro. Posso ajudar em mais alguma coisa?")
    h.processar_mensagem("Quanto é dois mais dois?")
    assert h._pergunta_pendente is None


def test_old_social_pending_question_is_ignored_too():
    pending = PerguntaPendente("ola auren", "Como posso ajudar?")
    assert resolver_continuacao(pending, "sim") == ("sim", "sem_pendencia")


def test_clarification_is_consumed_once_and_does_not_authorize_tools():
    h = harness_with_answers("Qual cor devo escolher?", "Escolhi azul.")
    h.processar_mensagem("Escolha uma cor para o exemplo ficticio")
    h.processar_mensagem("AZUL_FICTICIO")
    assert h._pergunta_pendente is None
    assert h._confirmacao_esclarecimento is None
