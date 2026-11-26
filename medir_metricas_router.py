from __future__ import annotations

"""Agrega as metricas comportamentais reais registradas pelo Auren.

O script nao chama a API e nao executa ferramentas. Ele apenas le os chat.logs
produzidos pelo runtime instrumentado.

Uso:
    py medir_metricas_router.py
    py medir_metricas_router.py logs/chats/<chat_id>/chat/chat.log
    py medir_metricas_router.py <chat.log> <auren_trace.sqlite3>

Custos completos sao lidos do trace SQLite v2 em modo somente leitura. O log
isolado nao permite identificar modelo efetivo nem todas as chamadas externas.
"""

import json
import math
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from core.task_trace import DEFAULT_TRACE_DB_PATH

TS = r"\[\d{4}-\d{2}-\d{2}T[^\]\n]+\]"
TASK_RE = re.compile(rf"(?ms)^{TS} TASK_START\n.*?(?=^{TS} TASK_START\n|^{TS} CHAT_END\n|\Z)")
RESPONSE_RE = re.compile(rf"(?ms)^{TS} MODEL_ROUND_RESPONSE\n(.*?)(?=^{TS} [A-Z_]+\n|\Z)")
FAST_RE = re.compile(rf"(?ms)^{TS} TASK_FAST_PATH\n.*?(?=^{TS} [A-Z_]+\n|\Z)")
LOCAL_RE = re.compile(rf"(?m)^{TS} TASK_LOCAL_COMPLETION\b")
TASK_END_RE = re.compile(rf"(?m)^(?P<ts>{TS}) TASK_END\n(?P<body>.*?)(?=^{TS} [A-Z_]+\n|\Z)")
FLOAT_RE = re.compile(r"^  latencia_ms: ([0-9]+(?:\.[0-9]+)?)$", re.M)
JSON_FIELD_RE = re.compile(r"^  (uso|router): (.+)$", re.M)

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
        tokens = {
            key: sum(row[key] for row in responses)
            for key in ("input_tokens", "output_tokens", "cached_tokens", "cache_write_tokens")
        }
        tasks.append(
            {
                "task_id": task_id,
                "fast_path": fast,
                "local_completion": local,
                "status": task_end.strip().splitlines()[-1].strip() if task_end.strip() else "",
                "model_rounds": len(responses),
                "tokens": tokens,
                "custo_estimado_usd": None,
                "custo_status": "unavailable",
                "latencia_ms_total": sum(r["latencia_ms"] or 0.0 for r in responses),
            }
        )
    return tasks


def _trace_costs(tasks: list[dict[str, Any]], path: str | Path | None) -> None:
    """Le apenas traces v2 finalizados; nao cria nem migra bancos historicos."""
    if path is None or not Path(path).is_file():
        return
    try:
        uri = Path(path).resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            if connection.execute("PRAGMA user_version").fetchone()[0] != 2:
                return
            connection.row_factory = sqlite3.Row
            task_ids = Counter(task["task_id"] for task in tasks)
            updates: list[tuple[dict[str, Any], float, str]] = []
            for task in tasks:
                if not task["task_id"] or task_ids[task["task_id"]] != 1:
                    continue
                row = connection.execute(
                    "SELECT cost_usd,cost_status,finished_at,model_rounds,input_tokens,output_tokens,"
                    "cached_tokens,cache_write_tokens FROM task_traces WHERE task_id=?",
                    (task["task_id"],),
                ).fetchone()
                if row is None or row["finished_at"] is None or row["cost_status"] not in {"estimated", "zero"}:
                    continue
                # O trace deve cobrir todas as rodadas e ao menos os tokens vistos no log.
                # Pode conter tokens adicionais de verificacoes semanticas nao logadas aqui.
                if row["model_rounds"] != task["model_rounds"] or any(
                    row[key] < task["tokens"][key] for key in task["tokens"]
                ):
                    continue
                amount = float(row["cost_usd"])
                if not math.isfinite(amount) or amount < 0 or (row["cost_status"] == "zero" and amount != 0):
                    continue
                updates.append((task, amount, row["cost_status"]))
            for task, amount, status in updates:
                task["custo_estimado_usd"] = amount
                task["custo_status"] = status
    except (OSError, sqlite3.Error, TypeError, ValueError):
        # O diagnostico de roteamento continua util mesmo sem trace compativel.
        return


def aggregate(text: str, *, trace_db_path: str | Path | None = None) -> dict[str, Any]:
    responses = parse_responses(text)
    tasks = parse_tasks(text)
    _trace_costs(tasks, trace_db_path)
    routed = [r for r in responses if r.get("router")]
    tool_sizes = [int(r["router"].get("ferramentas", 0)) for r in routed if r["router"].get("ferramentas")]
    fallback = sum(1 for r in routed if bool(r["router"].get("fallback_45")))
    latencies = [r["latencia_ms"] for r in responses if r["latencia_ms"] is not None]
    model_tasks = [t for t in tasks if t["model_rounds"] > 0]

    totals = {
        key: sum(r[key] for r in responses)
        for key in ("input_tokens", "output_tokens", "cached_tokens", "cache_write_tokens")
    }
    costs_available = bool(tasks) and all(t["custo_estimado_usd"] is not None for t in tasks)
    total_cost = sum(t["custo_estimado_usd"] for t in tasks) if costs_available else None
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
        "tarefas_custo_disponivel": sum(t["custo_estimado_usd"] is not None for t in tasks),
        "custo_estimado_total_usd": total_cost,
        "custo_estimado_medio_por_tarefa_usd": (total_cost / len(tasks)) if costs_available else None,
        "tarefas": tasks,
    }


def main() -> int:
    path = find_log(sys.argv)
    text = path.read_text(encoding="utf-8", errors="replace")
    trace_db_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_TRACE_DB_PATH
    result = aggregate(text, trace_db_path=trace_db_path)

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
