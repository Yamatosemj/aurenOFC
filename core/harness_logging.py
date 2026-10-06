"""Mecanicas de redacao e serializacao usadas pelo log do Harness."""
from __future__ import annotations

import json
import re
from typing import Any


SENSITIVE_KEYS = {
    "senha", "password", "passcode", "pin", "cpf",
    "cartao", "cartão", "card", "cvv", "cvc", "codigo", "token",
    "codigo_de_verificacao", "verification_code", "authorization",
}

# Contadores de uso sao metadados do log, nao segredos de entrada. A funcao
# publica _redact_value() preserva esses numeros para os testes e para quem
# reutilizar o helper; o redator do log os mascara especificamente ao salvar.
USAGE_KEYS = {
    "input_tokens", "output_tokens", "cached_tokens", "cache_write_tokens",
}

# Campos de texto que podem carregar conteudo digitado pelo usuario, valores
# privados ou dados de formularios. O valor nunca deve aparecer cru no log.
TEXT_SENSITIVE_KEYS = {
    "texto", "text", "conteudo", "content", "valor",
}

@dataclass(frozen=True)
class SessionContext:
    chat_id: str
    log_file: Path

    @property
    def log_root(self) -> Path:
        return self.log_file.parent.parent


_CURRENT_SESSION: contextvars.ContextVar[SessionContext | None] = contextvars.ContextVar(
    "auren_current_session", default=None
)
_LOG_LOCK = threading.RLock()


def _runtime_redaction_values() -> set[str]:
    values = getattr(_redact_free_text, "_values", None)
    if values is None:
        values = set()
        setattr(_redact_free_text, "_values", values)
    return values


def _register_redaction_value(value: Any) -> None:
    if value is None:
        return
    text = str(value)
    if len(text) >= 3:
        _runtime_redaction_values().add(text)


def _redact_free_text(text: str) -> str:
    """Redige segredos conhecidos e tokens de segredo em texto livre."""
    bruto = str(text).replace("\x00", " ")

    for segredo in sorted(_runtime_redaction_values(), key=len, reverse=True):
        if segredo:
            bruto = bruto.replace(segredo, "[REDACTED]")

    # Cobre credenciais escritas em texto livre.
    bruto = re.sub(
        r"(?i)\b(?:senha|password|passcode|pin|token|cvv|cvc|cpf)\s*[:=]\s*[^\s,;]+",
        lambda match: re.sub(r"(?i)([:=]\s*).*$", r"\1[REDACTED]", match.group(0)),
        bruto,
    )
    return bruto


def _redact_value(value: Any, *, _key: str | None = None) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            key_norm = str(key).strip().lower()
            if key_norm in USAGE_KEYS:
                result[key] = _redact_value(item, _key=key_norm)
            elif key_norm in SENSITIVE_KEYS or any(term in key_norm for term in SENSITIVE_KEYS):
                _register_redaction_value(item)
                result[key] = "[REDACTED]"
            elif key_norm in TEXT_SENSITIVE_KEYS:
                _register_redaction_value(item)
                result[key] = "[REDACTED]"
            else:
                result[key] = _redact_value(item, _key=key_norm)
        return result
    if isinstance(value, list):
        return [_redact_value(item, _key=_key) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item, _key=_key) for item in value)
    if isinstance(value, str):
        return _redact_free_text(value)
    return value


def _register_sensitive_values_from_object(value: Any) -> None:
    """Registra recursivamente textos sensiveis antes de persistir um evento."""
    if isinstance(value, dict):
        for key, item in value.items():
            key_norm = str(key).strip().lower()
            if key_norm in USAGE_KEYS:
                _register_sensitive_values_from_object(item)
            elif key_norm in SENSITIVE_KEYS or any(term in key_norm for term in SENSITIVE_KEYS) or key_norm in TEXT_SENSITIVE_KEYS:
                _register_redaction_value(item)
            else:
                _register_sensitive_values_from_object(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _register_sensitive_values_from_object(item)


def _register_sensitive_values_from_json_text(value: Any) -> None:
    if not isinstance(value, str):
        return
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return
    _register_sensitive_values_from_object(parsed)


def _register_redaction_values_from_objective(objetivo: str) -> None:
    """Detecta valores digitados em objetivos antes do TASK_START ser gravado.

    Isso evita uma janela de tempo em que o valor aparece no log antes da chamada
    de ferramenta que normalmente revelaria que aquele campo e sensivel.
    """
    texto = str(objetivo or "").strip()
    if not texto:
        return

    patterns = (
        # Ex.: coloque ABC na minha area de transferencia
        r"(?is)\bcoloque\s+(.+?)\s+na\s+minha\s+area\s+de\s+transferencia\b",
        # Ex.: preencha o campo X ... com ABC
        r"(?is)\bpreencha\b.*?\bcom\s+(.+?)\s*$",
        # Ex.: digite ABC em ... / escreva ABC no ...
        r"(?is)\b(?:digite|escreva|insira)\s+(.+?)\s+(?:em|no|na)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, texto)
        if match:
            _register_redaction_value(match.group(1).strip())
            return


def _compact_json(value: Any, limit: int = 1800) -> str:
    try:
        redigido = _redact_value(value)
        text = json.dumps(redigido, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(_redact_value(value))

    text = _redact_free_text(text).replace("\x00", " ").strip()
    if len(text) > limit:
        return text[:limit] + "...[truncated]"
    return text
