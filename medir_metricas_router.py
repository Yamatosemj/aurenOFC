from __future__ import annotations

"""Agrega as metricas comportamentais reais registradas pelo Auren.

O script nao chama a API e nao executa ferramentas. Ele apenas le os chat.logs
produzidos pelo runtime instrumentado.

Uso:
    py medir_metricas_router.py
    py medir_metricas_router.py logs/chats/<chat_id>/chat/chat.log
"""

import json
import re
import sys
from pathlib import Path
from statistics import mean
from typing import Any

TS = r"\[\d{4}-\d{2}-\d{2}T[^\]\n]+\]"
TASK_RE = re.compile(rf"(?ms)^{TS} TASK_START\n.*?(?=^{TS} TASK_START\n|^{TS} CHAT_END\n|\Z)")
RESPONSE_RE = re.compile(rf"(?ms)^{TS} (?:MODEL_ROUND_RESPONSE|INTENT_VERIFICATION_RESULT)\n(.*?)(?=^{TS} [A-Z_]+\n|\Z)")
FAST_RE = re.compile(rf"(?ms)^{TS} TASK_FAST_PATH\n.*?(?=^{TS} [A-Z_]+\n|\Z)")
LOCAL_RE = re.compile(rf"(?m)^{TS} TASK_LOCAL_COMPLETION\b")
TASK_END_RE = re.compile(rf"(?ms)^(?P<ts>{TS}) TASK_END\n(?P<body>.*?)(?=^{TS} [A-Z_]+\n|\Z)")
FLOAT_RE = re.compile(r"^  latencia_ms: ([0-9]+(?:\.[0-9]+)?)$", re.M)
JSON_FIELD_RE = re.compile(r"^  (uso|router): (.+)$", re.M)

PRICE_INPUT = 0.20 / 1_000_000
PRICE_CACHE = 0.02 / 1_000_000
PRICE_CACHE_WRITE = 0.25 / 1_000_000
PRICE_OUTPUT = 1.20 / 1_000_000


def find_log(argv: list[str]) -> Path:
    if len(argv) > 1:
        return Path(argv[1])
    logs = sorted(
        Path("logs/chats").glob("*/chat/chat.log"),
        key=lambda p: p.stat().st_mtime,
    )
    if not logs:
        raise SystemExit("Nenhum chat.log encontrado em logs/chats.")
    return logs[-1]


def _parse_json_field(block: str, field: str) -> dict[str, Any]:
    for name, value in JSON_FIELD_RE.findall(block):
        if name != field:
            continue
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def parse_responses(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for match in RESPONSE_RE.finditer(text):
        block = match.group(1)
        if "INTENT_VERIFICATION_RESULT" in match.group(0) and not re.search(r"^  uso:", block, re.M):
            continue
        usage = _parse_json_field(block, "uso")
        router = _parse_json_field(block, "router")
        round_match = re.search(r"^  rodada: (\d+)$", block, re.M)
        task_match = re.search(r"^  task_id: (.+)$", block, re.M)
        latency_match = FLOAT_RE.search(block)
        rows.append(
            {
                "task_id": (task_match.group(1).strip() if task_match else ""),
                "rodada": int(round_match.group(1)) if round_match else 0,
                "latencia_ms": float(latency_match.group(1)) if latency_match else None,
                "input_tokens": int(usage.get("input_tokens", 0) or 0),
                "output_tokens": int(usage.get("output_tokens", 0) or 0),
                "cached_tokens": int(usage.get("cached_tokens", 0) or 0),
                "cache_write_tokens": int(usage.get("cache_write_tokens", 0) or 0),
                "router": router,
            }
        )
    return rows


def parse_tasks(text: str) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for block_match in TASK_RE.finditer(text):
        block = block_match.group(0)
        task_id_match = re.search(r"^  task_id: (.+)$", block, re.M)
        task_id = task_id_match.group(1).strip() if task_id_match else ""
        responses = [row for row in parse_responses(block) if row["task_id"] == task_id]
        fast = bool(FAST_RE.search(block))
        local = bool(LOCAL_RE.search(block))
        task_end_match = next(TASK_END_RE.finditer(block), None)
        task_end = task_end_match.group("body") if task_end_match else ""
        status = re.search(r"^  (?:status|estado):\s*([^\n]+)", task_end, re.M)
        tokens = {
            key: sum(row[key] for row in responses)
            for key in ("input_tokens", "output_tokens", "cached_tokens", "cache_write_tokens")
        }
        cost = (
            max(0, tokens["input_tokens"] - tokens["cached_tokens"] - tokens["cache_write_tokens"]) * PRICE_INPUT
            + tokens["cached_tokens"] * PRICE_CACHE
            + tokens["cache_write_tokens"] * PRICE_CACHE_WRITE
            + tokens["output_tokens"] * PRICE_OUTPUT
        )
        tasks.append(
            {
                "task_id": task_id,
                "fast_path": fast,
                "local_completion": local,
                "status": status.group(1).strip() if status else "",
                "model_rounds": len(responses),
                "tokens": tokens,
                "custo_estimado_usd": cost,
                "latencia_ms_total": sum(r["latencia_ms"] or 0.0 for r in responses),
            }
        )
    return tasks


def aggregate(text: str) -> dict[str, Any]:
    responses = parse_responses(text)
    tasks = parse_tasks(text)
    routed = [r for r in responses if r.get("router")]
    tool_sizes = [int(r["router"].get("ferramentas", 0)) for r in routed if r["router"].get("ferramentas")]
    fallback = sum(1 for r in routed if bool(r["router"].get("fallback_45")))
    latencies = [r["latencia_ms"] for r in responses if r["latencia_ms"] is not None]
    model_tasks = [t for t in tasks if t["model_rounds"] > 0]

    totals = {
        key: sum(r[key] for r in responses)
        for key in ("input_tokens", "output_tokens", "cached_tokens", "cache_write_tokens")
    }
    total_cost = sum(t["custo_estimado_usd"] for t in tasks)
    local_tasks = sum(1 for t in model_tasks if t["local_completion"])
    fast_tasks = sum(1 for t in tasks if t["fast_path"])

    return {
        "tarefas_totais": len(tasks),
        "tarefas_fast_path": fast_tasks,
        "tarefas_com_modelo": len(model_tasks),
        "rodadas_modelo": len(responses),
        "toolsets_medio": mean(tool_sizes) if tool_sizes else 0.0,
        "toolsets_min": min(tool_sizes) if tool_sizes else 0,
        "toolsets_max": max(tool_sizes) if tool_sizes else 0,
        "fallback_45_model_rounds": fallback,
        "fallback_45_pct_model_rounds": (fallback / len(routed) * 100.0) if routed else 0.0,
        "conclusao_local_tarefas_modelo": local_tasks,
        "conclusao_local_pct_tarefas_modelo": (local_tasks / len(model_tasks) * 100.0) if model_tasks else 0.0,
        "rodadas_medias_por_tarefa_com_modelo": mean(t["model_rounds"] for t in model_tasks) if model_tasks else 0.0,
        "latencia_media_por_rodada_ms": mean(latencies) if latencies else 0.0,
        "latencia_total_modelo_ms": sum(latencies),
        "tokens": totals,
        "tokens_input_medio_por_tarefa_com_modelo": (totals["input_tokens"] / len(model_tasks)) if model_tasks else 0.0,
        "tokens_output_medio_por_tarefa_com_modelo": (totals["output_tokens"] / len(model_tasks)) if model_tasks else 0.0,
        "custo_estimado_total_usd": total_cost,
        "custo_estimado_medio_por_tarefa_usd": (total_cost / len(tasks)) if tasks else 0.0,
        "tarefas": tasks,
    }


def main() -> int:
    path = find_log(sys.argv)
    text = path.read_text(encoding="utf-8", errors="replace")
    result = aggregate(text)

    out_dir = Path("logs/testes")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "METRICAS_ROUTER_V43_OURO_LIMPO.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Log: {path}")
    for key, value in result.items():
        if key != "tarefas":
            print(f"{key}: {value}")
    print(f"JSON salvo em: {out_dir / 'METRICAS_ROUTER_V43_OURO_LIMPO.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
