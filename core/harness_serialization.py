from __future__ import annotations

import json
from typing import Any

from core.harness_logging import _redact_value


def _texto_seguro(valor: Any, limite: int) -> str:
    texto = str(valor if valor is not None else "")
    texto = texto.replace("\x00", " ")
    texto = texto.strip()

    if len(texto) <= limite:
        return texto

    return texto[:limite] + "\n[resultado truncado pelo harness]"


def _argumentos_da_chamada(item: Any) -> str:
    argumentos = getattr(item, "arguments", "")

    try:
        dados = json.loads(argumentos)
    except (TypeError, json.JSONDecodeError):
        return str(argumentos)

    try:
        return json.dumps(
            _redact_value(dados),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return str(_redact_value(dados))
