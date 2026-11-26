from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medir_metricas_router import aggregate, parse_responses
from core.task_trace import TaskTraceStore


def _sample_log() -> str:
    return '''[2026-09-22T16:00:00-03:00] TASK_START\n  task_id: task-1\n  objetivo: volume\n[2026-09-22T16:00:00-03:00] MODEL_ROUND_RESPONSE\n  task_id: task-1\n  rodada: 1\n  uso: {"input_tokens":100,"output_tokens":20,"cached_tokens":10,"cache_write_tokens":0}\n  latencia_ms: 120.500\n  router: {"dominios":["audio"],"ferramentas":7,"fallback_45":false}\n[2026-09-22T16:00:01-03:00] TASK_LOCAL_COMPLETION\n  task_id: task-1\n  rodada: 1\n[2026-09-22T16:00:01-03:00] TASK_END\n  task_id: task-1\n  status: local_completion\n[2026-09-22T16:00:02-03:00] TASK_START\n  task_id: task-2\n  objetivo: ambiguo\n[2026-09-22T16:00:02-03:00] MODEL_ROUND_RESPONSE\n  task_id: task-2\n  rodada: 1\n  uso: {"input_tokens":50,"output_tokens":10,"cached_tokens":0,"cache_write_tokens":0}\n  latencia_ms: 80.000\n  router: {"dominios":[],"ferramentas":44,"fallback_45":true}\n[2026-09-22T16:00:03-03:00] TASK_END\n  task_id: task-2\n  status: completed\n'''


def test_parse_responses_reads_metrics():
    rows = parse_responses(_sample_log())
    assert len(rows) == 2
    assert rows[0]["latencia_ms"] == 120.5
    assert rows[0]["router"]["ferramentas"] == 7


def test_aggregate_calculates_b2_metrics():
    result = aggregate(_sample_log())
    assert result["tarefas_totais"] == 2
    assert result["rodadas_modelo"] == 2
    assert result["fallback_45_model_rounds"] == 1
    assert result["toolsets_medio"] == 25.5
    assert result["conclusao_local_tarefas_modelo"] == 1
    assert result["tokens"]["input_tokens"] == 150
    assert result["tokens"]["output_tokens"] == 30
    assert result["latencia_media_por_rodada_ms"] == 100.25
    assert result["custo_estimado_total_usd"] is None
    assert result["custo_estimado_medio_por_tarefa_usd"] is None
    assert all(task["custo_estimado_usd"] is None for task in result["tarefas"])


def test_router_cost_uses_completed_trace_not_luna_log_rate(tmp_path):
    path = tmp_path / "trace.sqlite3"
    store = TaskTraceStore(path)
    first = store.start_task(task_id="task-1", chat_id=None, objective="volume")
    first.record_model(1, 120.5, {"input_tokens": 100, "output_tokens": 20,
                                  "cached_tokens": 10, "cache_write_tokens": 0}, model="gpt-5.6-terra")
    first.finish(status="completed", total_ms=130)
    second = store.start_task(task_id="task-2", chat_id=None, objective="ambiguo")
    second.record_model(1, 80, {"input_tokens": 50, "output_tokens": 10}, model="gpt-5.6-luna")
    second.finish(status="completed", total_ms=90)

    result = aggregate(_sample_log(), trace_db_path=path)
    assert result["tarefas"][0]["custo_estimado_usd"] == store.get_task("task-1")["cost_usd"]
    assert result["tarefas"][0]["custo_status"] == "estimated"
    assert result["custo_estimado_total_usd"] == sum(
        store.get_task(task_id)["cost_usd"] for task_id in ("task-1", "task-2"))
    assert result["custo_estimado_medio_por_tarefa_usd"] == result["custo_estimado_total_usd"] / 2


def test_router_cost_aggregate_unavailable_if_one_task_partial(tmp_path):
    path = tmp_path / "trace.sqlite3"
    store = TaskTraceStore(path)
    first = store.start_task(task_id="task-1", chat_id=None, objective="volume")
    first.record_model(1, 1, {"input_tokens": 100, "output_tokens": 20,
                              "cached_tokens": 10}, model="gpt-5.6-luna")
    first.finish(status="completed")
    second = store.start_task(task_id="task-2", chat_id=None, objective="ambiguo")
    second.record_model(1, 1, {"input_tokens": 50, "output_tokens": 10}, model="gpt-5.6-luna")
    second.record_provider_call("verification", 1, success=False, usage=None)
    second.finish(status="failed")

    result = aggregate(_sample_log(), trace_db_path=path)
    assert result["tarefas"][0]["custo_estimado_usd"] is not None
    assert result["tarefas"][1]["custo_estimado_usd"] is None
    assert result["tarefas"][1]["custo_status"] == "unavailable"
    assert result["custo_estimado_total_usd"] is None
    assert result["custo_estimado_medio_por_tarefa_usd"] is None


def test_router_cost_zero_requires_trusted_trace_and_legacy_db_is_untouched(tmp_path):
    zero_log = """[2026-09-22T16:00:00-03:00] TASK_START
  task_id: task-1
[2026-09-22T16:00:01-03:00] TASK_FAST_PATH
  task_id: task-1
[2026-09-22T16:00:02-03:00] TASK_END
  task_id: task-1
  status: fast_path
"""
    path = tmp_path / "trace.sqlite3"
    store = TaskTraceStore(path)
    zero = store.start_task(task_id="task-1", chat_id=None, objective="atalho")
    zero.finish(status="completed")
    result = aggregate(zero_log, trace_db_path=path)
    assert result["tarefas"][0]["custo_estimado_usd"] == 0.0
    assert result["tarefas"][0]["custo_status"] == "zero"
    assert result["custo_estimado_total_usd"] == 0.0

    inconsistent = aggregate(_sample_log(), trace_db_path=path)
    assert inconsistent["tarefas"][0]["custo_estimado_usd"] is None
    duplicated = aggregate(zero_log + zero_log, trace_db_path=path)
    assert duplicated["custo_estimado_total_usd"] is None
    assert duplicated["tarefas_custo_disponivel"] == 0

    legacy = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(legacy) as connection:
        connection.execute("CREATE TABLE task_traces (task_id TEXT PRIMARY KEY, cost_usd REAL NOT NULL)")
        connection.execute("INSERT INTO task_traces VALUES ('task-1', 42.0)")
        connection.execute("PRAGMA user_version = 1")
    old = aggregate(zero_log, trace_db_path=legacy)
    assert old["tarefas"][0]["custo_estimado_usd"] is None
    with sqlite3.connect(legacy) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
