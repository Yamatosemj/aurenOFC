from __future__ import annotations

import json
import hashlib
from typing import Any

from core.harness_logging import _redact_value


def _identidade_da_chamada(item: Any) -> str:
    raw = getattr(item, "arguments", "")
    try:
        raw = json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        raw = str(raw)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _texto_seguro(valor: Any, limite: int) -> str:
    texto = str(valor if valor is not None else "")
    texto = texto.replace("\x00", " ")
    texto = texto.strip()

    if len(texto) <= limite:
        return texto

    try:
        payload = json.loads(texto)
    except (TypeError, ValueError):
        payload = None
    if isinstance(payload, dict):
        data = payload.get("dados")
        content = data.get("file_content") if isinstance(data, dict) else None
        if isinstance(content, dict) and isinstance(content.get("conteudo"), str):
            original = content["conteudo"]
            low, high = 0, len(original)
            best = None
            while low <= high:
                size = (low + high) // 2
                content["conteudo"] = original[:size]
                content["truncado"] = True
                content["proximo_inicio"] = int(content.get("inicio") or 0) + size
                data["proxima_leitura"] = {"inicio": content["proximo_inicio"]}
                candidate = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                if len(candidate) <= limite:
                    best = candidate
                    low = size + 1
                else:
                    high = size - 1
            if best is not None:
                return best
        # Manter um objeto valido e sinalizar omissao quando nao cabe estrutura.
        summary = {"ok": payload.get("ok"), "resultado_truncado": True,
                   "mensagem": str(payload.get("mensagem") or "")[:max(0, limite // 3)]}
        compact = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
        return compact if len(compact) <= limite else "{}"

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
