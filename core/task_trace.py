from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

from core.usage import calcular_custo_estimado


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACE_DB_PATH = PROJECT_ROOT / "data" / "traces" / "auren_trace.sqlite3"
SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _hash_objective(objective: str) -> str:
    return hashlib.sha256(str(objective or "").encode("utf-8")).hexdigest()


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile / 100.0
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


class TaskTraceStore:
    """Persistencia observacional separada do banco de memoria do Auren."""

    def __init__(self, db_path: str | Path = DEFAULT_TRACE_DB_PATH) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        self._ensure_schema(connection)
        return connection

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"Versao do trace nao suportada: {version}")
        if version == 0:
            connection.executescript(
                """
                CREATE TABLE task_traces (
                    task_id TEXT PRIMARY KEY, chat_id TEXT, task_type TEXT NOT NULL DEFAULT 'unknown',
                    objective_chars INTEGER NOT NULL DEFAULT 0, objective_hash TEXT NOT NULL,
                    started_at TEXT NOT NULL, finished_at TEXT, status TEXT, total_ms REAL,
                    context_ms REAL NOT NULL DEFAULT 0, fast_path_ms REAL NOT NULL DEFAULT 0,
                    model_rounds INTEGER NOT NULL DEFAULT 0, model_ms REAL NOT NULL DEFAULT 0,
                    tool_calls INTEGER NOT NULL DEFAULT 0, tool_successes INTEGER NOT NULL DEFAULT 0,
                    tool_failures INTEGER NOT NULL DEFAULT 0, tool_ms REAL NOT NULL DEFAULT 0,
                    asr_ms REAL NOT NULL DEFAULT 0, tts_ms REAL NOT NULL DEFAULT 0,
                    input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
                    cached_tokens INTEGER NOT NULL DEFAULT 0, cache_write_tokens INTEGER NOT NULL DEFAULT 0,
                    cost_usd REAL NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE task_trace_spans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                    category TEXT NOT NULL, name TEXT NOT NULL, started_at TEXT NOT NULL,
                    duration_ms REAL NOT NULL, success INTEGER, metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (task_id) REFERENCES task_traces(task_id)
                );
                CREATE INDEX idx_task_trace_spans_task ON task_trace_spans(task_id);
                CREATE INDEX idx_task_traces_started ON task_traces(started_at);
                CREATE INDEX idx_task_traces_type ON task_traces(task_type);
                PRAGMA user_version = 1;
                """
            )
        connection.commit()

    def start_task(self, *, task_id: str, chat_id: str | None, objective: str,
                   started_at: str | None = None, started_perf: float | None = None) -> "TaskTrace":
        trace = TaskTrace(
            store=self, task_id=str(task_id), chat_id=str(chat_id) if chat_id else None,
            objective_chars=len(str(objective or "")), objective_hash=_hash_objective(objective),
            started_at=started_at or _now_iso(),
            started_perf=float(started_perf) if started_perf is not None else time.perf_counter(),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO task_traces (task_id,chat_id,objective_chars,objective_hash,started_at) VALUES (?,?,?,?,?)",
                (trace.task_id, trace.chat_id, trace.objective_chars, trace.objective_hash, trace.started_at),
            )
            connection.commit()
        return trace

    def record_late_stage(self, *, task_id: str, category: str, duration_ms: float,
                           metadata: dict[str, Any] | None = None) -> None:
        """Persiste etapa que terminou depois do fechamento logico da tarefa."""
        if category not in {"asr", "tts"}:
            raise ValueError("etapa tardia deve ser 'asr' ou 'tts'.")
        duration = max(0.0, float(duration_ms))
        with self._connect() as connection:
            sequence = int(connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM task_trace_spans WHERE task_id=?",
                (str(task_id),),
            ).fetchone()[0])
            started = datetime.fromtimestamp(
                time.time() - duration / 1000.0
            ).astimezone().isoformat(timespec="milliseconds")
            connection.execute(
                "INSERT INTO task_trace_spans "
                "(task_id,sequence,category,name,started_at,duration_ms,success,metadata_json) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (str(task_id), sequence, category, category, started, duration, 1,
                 json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":"))),
            )
            connection.execute(
                f"UPDATE task_traces SET {category}_ms = {category}_ms + ? WHERE task_id=?",
                (duration, str(task_id)),
            )
            connection.commit()
    def record_span(self, *, task_id: str, sequence: int, category: str, name: str,
                    started_at: str, duration_ms: float, success: bool | None = None,
                    metadata: dict[str, Any] | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO task_trace_spans (task_id,sequence,category,name,started_at,duration_ms,success,metadata_json) VALUES (?,?,?,?,?,?,?,?)",
                (task_id, int(sequence), str(category), str(name), str(started_at), max(0.0, float(duration_ms)),
                 None if success is None else int(bool(success)),
                 json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":"))),
            )
            connection.commit()

    def finish_task(self, *, task_id: str, summary: dict[str, Any]) -> None:
        fields = (
            "task_type", "finished_at", "status", "total_ms", "context_ms", "fast_path_ms",
            "model_rounds", "model_ms", "tool_calls", "tool_successes", "tool_failures", "tool_ms",
            "asr_ms", "tts_ms", "input_tokens", "output_tokens", "cached_tokens", "cache_write_tokens",
            "cost_usd", "error",
        )
        values = [summary.get(field, "") if field in {"task_type", "finished_at", "status", "error"} else float(summary.get(field) or 0) for field in fields]
        for index in (6, 8, 9, 10, 16, 17):
            values[index] = int(values[index])
        with self._connect() as connection:
            connection.execute(
                "UPDATE task_traces SET " + ", ".join(f"{field}=?" for field in fields) + " WHERE task_id=?",
                (*values, task_id),
            )
            connection.commit()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM task_traces WHERE task_id=?", (str(task_id),)).fetchone()
        return dict(row) if row is not None else None

    def get_spans(self, task_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT sequence,category,name,started_at,duration_ms,success,metadata_json FROM task_trace_spans WHERE task_id=? ORDER BY sequence,id",
                (str(task_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def report(self, *, limit: int = 500) -> dict[str, Any]:
        if limit < 1:
            raise ValueError("limit deve ser maior que zero.")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT task_type,total_ms,model_ms,tool_ms,cost_usd FROM task_traces ORDER BY started_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        groups: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            groups.setdefault(str(row["task_type"] or "unknown"), []).append(row)
        result = {}
        for task_type, items in groups.items():
            total = [float(x["total_ms"] or 0) for x in items]
            model = [float(x["model_ms"] or 0) for x in items]
            tool = [float(x["tool_ms"] or 0) for x in items]
            cost = [float(x["cost_usd"] or 0) for x in items]
            result[task_type] = {
                "tasks": len(items),
                "median_total_ms": median(total) if total else 0.0, "p95_total_ms": _percentile(total, 95),
                "median_model_ms": median(model) if model else 0.0, "p95_model_ms": _percentile(model, 95),
                "median_tool_ms": median(tool) if tool else 0.0, "p95_tool_ms": _percentile(tool, 95),
                "median_cost_usd": median(cost) if cost else 0.0, "p95_cost_usd": _percentile(cost, 95),
            }
        return {"tasks_considered": len(rows), "by_type": result}


@dataclass
class TaskTrace:
    store: TaskTraceStore
    task_id: str
    chat_id: str | None
    objective_chars: int
    objective_hash: str
    started_at: str
    started_perf: float
    task_type: str = "unknown"
    sequence: int = 0
    context_ms: float = 0.0
    fast_path_ms: float = 0.0
    model_rounds: int = 0
    model_ms: float = 0.0
    tool_calls: int = 0
    tool_successes: int = 0
    tool_failures: int = 0
    tool_ms: float = 0.0
    asr_ms: float = 0.0
    tts_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    _finished: bool = field(default=False, init=False, repr=False)

    def _span(self, category: str, name: str, duration_ms: float, *, success: bool | None = True, metadata: dict[str, Any] | None = None) -> None:
        if self._finished:
            return
        duration = max(0.0, float(duration_ms))
        self.sequence += 1
        started = datetime.fromtimestamp(time.time() - duration / 1000.0).astimezone().isoformat(timespec="milliseconds")
        try:
            self.store.record_span(task_id=self.task_id, sequence=self.sequence, category=category, name=name,
                                  started_at=started, duration_ms=duration, success=success, metadata=metadata)
        except Exception:
            pass

    def record_stage(self, name: str, duration_ms: float, *, category: str | None = None,
                     success: bool | None = True, metadata: dict[str, Any] | None = None) -> None:
        stage = str(category or name)
        duration = max(0.0, float(duration_ms))
        self._span(stage, name, duration, success=success, metadata=metadata)
        if stage == "context": self.context_ms += duration
        elif stage == "fast_path": self.fast_path_ms += duration; self.task_type = "fast_path"
        elif stage == "asr": self.asr_ms += duration
        elif stage == "tts": self.tts_ms += duration

    def record_model(self, rodada: int, duration_ms: float, usage: dict[str, int] | None = None) -> None:
        metrics = usage if isinstance(usage, dict) else {}
        values = {key: max(0, int(metrics.get(key) or 0)) for key in ("input_tokens", "output_tokens", "cached_tokens", "cache_write_tokens")}
        self.model_rounds += 1
        self.model_ms += max(0.0, float(duration_ms))
        self.input_tokens += values["input_tokens"]
        self.output_tokens += values["output_tokens"]
        self.cached_tokens += values["cached_tokens"]
        self.cache_write_tokens += values["cache_write_tokens"]
        self.cost_usd += calcular_custo_estimado(values)
        self.task_type = "agentic"
        self._span("model", f"round_{int(rodada)}", duration_ms, metadata=values)

    def record_tool(self, tool_name: str, duration_ms: float, *, success: bool) -> None:
        duration = max(0.0, float(duration_ms))
        self.tool_calls += 1
        self.tool_ms += duration
        if success: self.tool_successes += 1
        else: self.tool_failures += 1
        self.task_type = "agentic"
        self._span("tool", str(tool_name), duration, success=success)

    def finish(self, *, status: str, error: str = "", total_ms: float | None = None) -> None:
        if self._finished:
            return
        self._finished = True
        total = max(0.0, float(total_ms)) if total_ms is not None else max(0.0, (time.perf_counter() - self.started_perf) * 1000.0)
        self.store.finish_task(task_id=self.task_id, summary={
            "task_type": self.task_type, "finished_at": _now_iso(), "status": status, "total_ms": total,
            "context_ms": self.context_ms, "fast_path_ms": self.fast_path_ms, "model_rounds": self.model_rounds,
            "model_ms": self.model_ms, "tool_calls": self.tool_calls, "tool_successes": self.tool_successes,
            "tool_failures": self.tool_failures, "tool_ms": self.tool_ms, "asr_ms": self.asr_ms, "tts_ms": self.tts_ms,
            "input_tokens": self.input_tokens, "output_tokens": self.output_tokens, "cached_tokens": self.cached_tokens,
            "cache_write_tokens": self.cache_write_tokens, "cost_usd": self.cost_usd, "error": error,
        })


__all__ = ["DEFAULT_TRACE_DB_PATH", "SCHEMA_VERSION", "TaskTrace", "TaskTraceStore"]