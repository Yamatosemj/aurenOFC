from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.capability_resolver import CapabilityResolver
from core.router import Router
from core.tools_registry import tools as TOOL_REGISTRY


@dataclass(frozen=True)
class AudioExperimentCase:
    phrase: str
    expected_action: str
    expected_params: dict[str, Any]


CASES: tuple[AudioExperimentCase, ...] = (
    AudioExperimentCase("volume 40%", "volume", {"percentual": 40}),
    AudioExperimentCase("coloca o som em 40%", "volume", {"percentual": 40}),
    AudioExperimentCase("aumenta o volume pra 25", "volume", {"percentual": 25}),
    AudioExperimentCase("deixa o áudio em 60%", "volume", {"percentual": 60}),
    AudioExperimentCase("coloque o volume em 35", "volume", {"percentual": 35}),
    AudioExperimentCase("coloque no mudo", "mudo", {}),
    AudioExperimentCase("silencia o som", "mudo", {}),
    AudioExperimentCase("tira o mudo", "mudo_off", {}),
    AudioExperimentCase("pausa a música", "play_pause", {}),
    AudioExperimentCase("próxima música", "proxima", {}),
    AudioExperimentCase("música anterior", "anterior", {}),
    AudioExperimentCase("qual está o volume?", "consultar", {}),
)


def make_task_spec(phrase: str) -> dict[str, Any]:
    return {
        "version": "1",
        "tipo": "execucao",
        "objetivo": phrase,
        "complexidade": "simples",
        "parametros": {},
        "restricoes": [],
        "requer_confirmacao": False,
        "dados_exatos": {},
    }


def _baseline_router(phrase: str) -> dict[str, Any]:
    router = Router()
    names = router.select_tool_names(phrase, TOOL_REGISTRY)
    return {
        "domains": list(router.last_domains),
        "tool_count": len(names),
        "fallback_45": len(names) == len(TOOL_REGISTRY),
        "tools": names,
    }


def _registry_resolution(phrase: str) -> dict[str, Any]:
    result = CapabilityResolver().resolve(make_task_spec(phrase))
    return {
        "status": result.status,
        "route": result.route,
        "capability_id": result.capability_id,
        "params": dict(result.params),
        "reason_code": result.reason_code,
    }


def _expected_tool(action: str) -> str:
    return {
        "volume": "definir_volume_windows",
        "mudo": "definir_mudo_windows",
        "mudo_off": "definir_mudo_windows",
        "play_pause": "controle_midia_windows",
        "proxima": "controle_midia_windows",
        "anterior": "controle_midia_windows",
        "consultar": "obter_audio_windows",
    }[action]


def _normalize_expected_params(case: AudioExperimentCase, resolved: dict[str, Any]) -> dict[str, Any]:
    params = dict(resolved.get("params") or {})
    if case.expected_action == "mudo":
        params["ativado"] = True
    elif case.expected_action == "mudo_off":
        params["ativado"] = False
    elif case.expected_action in {"play_pause", "proxima", "anterior"}:
        params["acao"] = case.expected_action
    return params


def run_experiment() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    registry_resolved = 0
    registry_local = 0
    registry_correct = 0
    baseline_fallback = 0
    baseline_tool_total = 0

    for case in CASES:
        baseline = _baseline_router(case.phrase)
        registry = _registry_resolution(case.phrase)
        baseline_tool_total += int(baseline["tool_count"])
        baseline_fallback += int(baseline["fallback_45"])

        expected_tool = _expected_tool(case.expected_action)
        registry_is_resolved = registry["status"] == "resolved"
        registry_is_local = registry["route"] == "local"
        registry_matches = registry_is_resolved and registry.get("capability_id") == "controlar_audio"
        if registry_is_resolved:
            registry_resolved += 1
        if registry_is_local:
            registry_local += 1
        if registry_matches and registry["params"].get("acao") in {case.expected_action, "volume", "mudo"}:
            registry_correct += 1
        if case.expected_action == "consultar" and registry_matches and registry_is_resolved:
            registry_correct += 0

        row = {
            "phrase": case.phrase,
            "expected_action": case.expected_action,
            "expected_tool": expected_tool,
            "baseline": baseline,
            "registry": registry,
            "registry_target_tool": expected_tool,
            "registry_target_params": _normalize_expected_params(case, registry),
        }
        rows.append(row)

    # Recalcula correção com validação direta de ação/parametros, mantendo o
    # cálculo explícito e auditável.
    registry_correct = 0
    for case, row in zip(CASES, rows):
        reg = row["registry"]
        if reg["status"] != "resolved" or reg["route"] != "local" or reg["capability_id"] != "controlar_audio":
            continue
        params = reg["params"]
        action = params.get("acao")
        if case.expected_action == "volume":
            if action == "volume" and params.get("percentual") == case.expected_params["percentual"]:
                registry_correct += 1
        elif case.expected_action == "mudo":
            if action == "mudo":
                registry_correct += 1
        elif case.expected_action == "mudo_off":
            if action == "mudo_off":
                registry_correct += 1
        elif case.expected_action in {"play_pause", "proxima", "anterior"}:
            if action == case.expected_action:
                registry_correct += 1
        elif case.expected_action == "consultar":
            if action == "consultar":
                registry_correct += 1

    total = len(CASES)
    return {
        "cases": rows,
        "summary": {
            "cases": total,
            "baseline_fallback_45": baseline_fallback,
            "baseline_fallback_pct": (baseline_fallback / total) * 100.0,
            "baseline_toolset_avg": baseline_tool_total / total,
            "registry_resolved": registry_resolved,
            "registry_resolved_pct": (registry_resolved / total) * 100.0,
            "registry_local": registry_local,
            "registry_local_pct": (registry_local / total) * 100.0,
            "registry_functionally_correct": registry_correct,
            "registry_functionally_correct_pct": (registry_correct / total) * 100.0,
            "model_calls_registry": 0,
            "input_tokens_registry": 0,
            "output_tokens_registry": 0,
        },
        "notes": [
            "Experimento somente de resolução; nao altera o fluxo principal do Auren.",
            "O Router legado continua sendo a baseline oficial.",
            "A rota Registry-local nao executa ferramentas reais neste primeiro experimento.",
        ],
    }


if __name__ == "__main__":
    import json
    from pathlib import Path

    result = run_experiment()
    path = Path(__file__).resolve().parent / "RELATORIOS" / "EXPERIMENTO_CAPABILITY_AUDIO_V43.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"JSON salvo em: {path}")
