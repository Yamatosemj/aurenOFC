from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from jsonschema import Draft202012Validator


TASK_SPEC_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://auren.local/schemas/taskspec-v1.json",
    "title": "Auren TaskSpec v1",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "version",
        "tipo",
        "objetivo",
        "complexidade",
        "parametros",
        "restricoes",
        "requer_confirmacao",
        "dados_exatos",
    ],
    "properties": {
        "version": {"const": "1"},
        "tipo": {
            "type": "string",
            "enum": ["execucao", "esclarecimento"],
        },
        "objetivo": {
            "type": "string",
            "minLength": 1,
            "maxLength": 500,
        },
        "complexidade": {
            "type": "string",
            "enum": ["simples", "complexa", "nao_definida"],
        },
        "parametros": {
            "type": "object",
            "additionalProperties": True,
        },
        "restricoes": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "string",
                "minLength": 1,
                "maxLength": 300,
            },
        },
        "requer_confirmacao": {"type": "boolean"},
        "dados_exatos": {
            "type": "object",
            "additionalProperties": True,
        },
        "pergunta": {
            "type": "string",
            "minLength": 1,
            "maxLength": 300,
        },
    },
    "allOf": [
        {
            "if": {
                "properties": {
                    "tipo": {"const": "esclarecimento"}
                },
                "required": ["tipo"],
            },
            "then": {"required": ["pergunta"]},
        },
        {
            "if": {
                "properties": {
                    "tipo": {"const": "execucao"}
                },
                "required": ["tipo"],
            },
            "then": {
                "not": {"required": ["pergunta"]},
            },
        },
    ],
}

MAX_TASKSPEC_VALIDATION_ATTEMPTS = 2
MAX_CAPABILITY_CLARIFICATION_ROUNDS = 2


@dataclass(frozen=True)
class TaskSpecValidationResult:
    valid: bool
    errors: tuple[str, ...]
    attempt: int
    max_attempts: int = MAX_TASKSPEC_VALIDATION_ATTEMPTS

    @property
    def should_retry(self) -> bool:
        return (not self.valid) and self.attempt < self.max_attempts


# Falhar cedo se o contrato do schema for alterado de forma invalida.
_VALIDATOR = Draft202012Validator(TASK_SPEC_SCHEMA)


def validate_task_spec(
    payload: Any,
    *,
    attempt: int = 1,
    max_attempts: int = MAX_TASKSPEC_VALIDATION_ATTEMPTS,
) -> TaskSpecValidationResult:
    """Valida um TaskSpec v1 sem decidir como a tarefa sera executada."""
    attempt = max(1, int(attempt))
    max_attempts = max(1, int(max_attempts))

    if not isinstance(payload, Mapping):
        return TaskSpecValidationResult(
            valid=False,
            errors=("TaskSpec deve ser um objeto JSON.",),
            attempt=attempt,
            max_attempts=max_attempts,
        )

    erros = tuple(
        _format_validation_error(error)
        for error in sorted(_VALIDATOR.iter_errors(payload), key=lambda item: list(item.path))
    )

    return TaskSpecValidationResult(
        valid=not erros,
        errors=erros,
        attempt=attempt,
        max_attempts=max_attempts,
    )


def _format_validation_error(error: Any) -> str:
    caminho = ".".join(str(part) for part in error.path)
    prefixo = f"{caminho}: " if caminho else ""
    return f"{prefixo}{error.message}"


def pode_tentar_novamente_validator(attempt: int) -> bool:
    return int(attempt) < MAX_TASKSPEC_VALIDATION_ATTEMPTS


def pode_esclarecer_capability(round_number: int) -> bool:
    return int(round_number) < MAX_CAPABILITY_CLARIFICATION_ROUNDS
