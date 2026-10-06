from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medir_metricas_router import aggregate, parse_responses


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
