from types import SimpleNamespace

import pytest

from core.task_manager import TaskState
from voice.speech_response import SpeechResponseFormatter


@pytest.mark.parametrize('state,success', [
    (TaskState.FAILED, False), (TaskState.CANCELLED, True),
    (TaskState.RUNNING, True), (TaskState.COMPLETED, False),
    (TaskState.COMPLETED, None),
])
def test_aud027_preserves_final_response_without_confirmed_success(state, success):
    text = 'Não foi possível concluir a tarefa.'
    snapshot = SimpleNamespace(state=state, objective='Maximize a janela', result=text,
        steps=(SimpleNamespace(tool='maximizar_janela_windows', success=success,
                               result='Não consegui maximizar a janela.'),))
    assert SpeechResponseFormatter.formatar(objetivo=snapshot.objective,
        texto=text, snapshot=snapshot) == text


def test_aud027_completed_success_can_be_shortened():
    snapshot = SimpleNamespace(state=TaskState.COMPLETED, objective='Maximize a janela',
        result='Janela maximizada com sucesso.',
        steps=(SimpleNamespace(tool='maximizar_janela_windows', success=True,
                               result='Janela maximizada com sucesso.'),))
    assert SpeechResponseFormatter.formatar(objetivo=snapshot.objective,
        texto=snapshot.result, snapshot=snapshot) == 'Janela maximizada.'
