from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any, Callable

from core.capability_resolver import CapabilityResolver
from core.task_spec import validate_task_spec
from core.tool_result import ToolResult


ENV_FLAG = "AUREN_EXPERIMENT_CAPABILITY_AUDIO"
CAPABILITY_ID = "controlar_audio"

_TOOL_BY_ACTION: dict[str, str] = {
    "consultar": "obter_audio_windows",
    "volume": "definir_volume_windows",
    "mudo": "definir_mudo_windows",
    "mudo_off": "definir_mudo_windows",
    "play_pause": "controle_midia_windows",
    "proxima": "controle_midia_windows",
    "anterior": "controle_midia_windows",
}


def enabled() -> bool:
    return os.getenv(ENV_FLAG, "0").strip().lower() in {"1", "true", "sim", "yes", "on"}


def make_task_spec(phrase: str) -> dict[str, Any]:
    return {
        "version": "1",
        "tipo": "execucao",
        "objetivo": str(phrase or "").strip(),
        "complexidade": "simples",
        "parametros": {},
        "restricoes": [],
        "requer_confirmacao": False,
        "dados_exatos": {},
    }


def _tool_call_for_resolution(capability_id: str, params: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    if capability_id != CAPABILITY_ID:
        return None

    action = str(params.get("acao") or "").strip().lower()
    tool_name = _TOOL_BY_ACTION.get(action)
    if not tool_name:
        return None

    if action == "consultar":
        return tool_name, {}

    if action == "volume":
        percentual = params.get("percentual")
        if isinstance(percentual, bool) or not isinstance(percentual, int):
            return None
        return tool_name, {"percentual": percentual}

    if action == "mudo":
        return tool_name, {"ativado": True}

    if action == "mudo_off":
        return tool_name, {"ativado": False}

    if action in {"play_pause", "proxima", "anterior"}:
        return tool_name, {"acao": action}

    return None


def try_execute(
    phrase: str,
    *,
    executar_ferramenta: Callable[[Any], ToolResult],
) -> tuple[bool, str, dict[str, Any]]:
    """Tenta o caminho experimental local e nunca assume o fluxo normal se não resolver."""
    if not enabled():
        return False, "", {"enabled": False, "reason": "flag_disabled"}

    task_spec = make_task_spec(phrase)
    validation = validate_task_spec(task_spec)
    if not validation.valid:
        return False, "", {"enabled": True, "reason": "invalid_taskspec", "errors": validation.errors}

    try:
        resolution = CapabilityResolver().resolve(task_spec)
    except Exception as exc:
        return False, "", {"enabled": True, "reason": "resolver_exception", "error": str(exc)}

    metadata = {
        "enabled": True,
        "status": resolution.status,
        "route": resolution.route,
        "capability_id": resolution.capability_id,
        "params": dict(resolution.params),
        "reason_code": resolution.reason_code,
    }

    if (
        resolution.status != "resolved"
        or resolution.route != "local"
        or resolution.capability_id != CAPABILITY_ID
    ):
        metadata["reason"] = "not_resolved_audio_local"
        return False, "", metadata

    tool_call = _tool_call_for_resolution(resolution.capability_id, dict(resolution.params))
    if tool_call is None:
        metadata["reason"] = "unsupported_audio_action"
        return False, "", metadata

    tool_name, arguments = tool_call
    item = SimpleNamespace(
        name=tool_name,
        arguments=json.dumps(arguments, ensure_ascii=False),
        call_id=f"capability-audio-{tool_name}",
    )

    try:
        result = executar_ferramenta(item)
    except Exception as exc:
        metadata["reason"] = "execution_exception"
        metadata["error"] = str(exc)
        return False, "", metadata

    if not isinstance(result, ToolResult):
        metadata["reason"] = "unexpected_result_type"
        return False, "", metadata

    metadata.update(
        {
            "executed": True,
            "tool": tool_name,
            "tool_ok": result.ok,
            "error_code": result.error_code,
        }
    )

    if result.ok:
        return True, result.message, metadata

    # Um erro local não impede o caminho normal de tentar resolver o pedido.
    metadata["reason"] = "local_tool_failed"
    return False, "", metadata
