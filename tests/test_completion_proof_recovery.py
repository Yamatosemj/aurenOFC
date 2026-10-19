from types import SimpleNamespace
import pytest
from core.task_verification import validate_completion, CompletionPending, CompletionValidationFailure


def snapshot():
    return SimpleNamespace(plan=SimpleNamespace(steps=[SimpleNamespace(index=1)]),steps=[
        SimpleNamespace(tool='navegar_navegador',success=True),
        SimpleNamespace(tool='obter_contexto_navegador',success=True)])


def test_omitted_post_read_reference_stays_pending_and_never_becomes_success():
    result={'summary':'done','answer_status':'verified','steps':[{'index':1,'status':'verified','evidence':[1]}]}
    with pytest.raises(CompletionPending) as error:validate_completion(result,snapshot())
    assert error.value.code=='completion_effect_unverified'
    assert 'Leituras posteriores existentes: [2]' in str(error.value)
    assert result['steps'][0]['evidence']==[1]  # No invented automatic repair.
    result['steps'][0]['evidence']=[1,2]
    assert validate_completion(result,snapshot()) is result


def test_nonexistent_reference_remains_invalid_not_recoverably_accepted():
    result={'summary':'done','answer_status':'verified','steps':[{'index':1,'status':'verified','evidence':[999]}]}
    with pytest.raises(CompletionValidationFailure):validate_completion(result,snapshot())
