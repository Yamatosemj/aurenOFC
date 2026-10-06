import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.task_spec import (
    MAX_CAPABILITY_CLARIFICATION_ROUNDS,
    MAX_TASKSPEC_VALIDATION_ATTEMPTS,
    pode_esclarecer_capability,
    pode_tentar_novamente_validator,
    validate_task_spec,
)


def base_spec(**overrides):
    payload = {
        "version": "1",
        "tipo": "execucao",
        "objetivo": "Abrir o YouTube",
        "complexidade": "simples",
        "parametros": {},
        "restricoes": [],
        "requer_confirmacao": False,
        "dados_exatos": {"destino": "YouTube"},
    }
    payload.update(overrides)
    return payload


def test_valid_execution_taskspec_is_accepted():
    result = validate_task_spec(base_spec())
    assert result.valid is True
    assert result.errors == ()
    assert result.should_retry is False


def test_clarification_taskspec_requires_question():
    result = validate_task_spec(base_spec(tipo="esclarecimento", objetivo="Falta o site"))
    assert result.valid is False
    assert any("'pergunta' is a required property" in error for error in result.errors)


def test_clarification_taskspec_with_question_is_valid():
    result = validate_task_spec(
        base_spec(
            tipo="esclarecimento",
            objetivo="Falta o site",
            pergunta="Qual site você quer que eu abra?",
        )
    )
    assert result.valid is True


def test_execution_taskspec_rejects_question_field():
    result = validate_task_spec(
        base_spec(pergunta="Qual programa?")
    )
    assert result.valid is False


def test_invalid_complexity_is_rejected():
    result = validate_task_spec(base_spec(complexidade="muito_complexa"))
    assert result.valid is False


def test_unknown_fields_are_rejected():
    result = validate_task_spec(base_spec(ferramenta="abrir_programa"))
    assert result.valid is False


def test_validator_allows_retry_only_until_second_attempt():
    assert MAX_TASKSPEC_VALIDATION_ATTEMPTS == 2
    assert pode_tentar_novamente_validator(1) is True
    assert pode_tentar_novamente_validator(2) is False


def test_capability_clarification_has_two_round_budget():
    assert MAX_CAPABILITY_CLARIFICATION_ROUNDS == 2
    assert pode_esclarecer_capability(0) is True
    assert pode_esclarecer_capability(1) is True
    assert pode_esclarecer_capability(2) is False
