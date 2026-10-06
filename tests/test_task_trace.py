from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.harness import AurenHarness
from core.task_manager import TaskManager, TaskState
from core.task_trace import TaskTraceStore


def test_trace_store_persists_spans_and_report(tmp_path: Path) -> None:
    store = TaskTraceStore(tmp_path / "trace.sqlite3")
    trace = store.start_task(
        task_id="task-1",
        chat_id="chat-1",
        objective="abra o navegador",
        started_at="2026-10-06T16:00:00-03:00",
    )

    trace.record_stage("contexto", 12.0, category="context")
    trace.record_model(
        1,
        120.0,
        {
            "input_tokens": 1000,
            "output_tokens": 200,
            "cached_tokens": 100,
            "cache_write_tokens": 0,
        },
    )
    trace.record_tool("abrir_programa", 45.0, success=True)
    trace.finish(status="completed", total_ms=190.0)

    row = store.get_task("task-1")
    assert row is not None
    assert row["status"] == "completed"
    assert row["task_type"] == "agentic"
    assert row["model_rounds"] == 1
    assert row["tool_calls"] == 1
    assert row["tool_successes"] == 1
    assert row["tool_failures"] == 0
    assert row["input_tokens"] == 1000
    assert row["output_tokens"] == 200
    assert row["cached_tokens"] == 100
    assert row["cost_usd"] > 0

    spans = store.get_spans("task-1")
    assert [span["category"] for span in spans] == ["context", "model", "tool"]

    report = store.report()
    group = report["by_type"]["agentic"]
    assert group["tasks"] == 1
    assert group["median_total_ms"] == 190.0
    assert group["p95_total_ms"] == 190.0


def test_harness_records_real_task_trace(tmp_path: Path) -> None:
    class FakeResponse:
        def __init__(self, output, output_text="", usage=None):
            self.output = output
            self.output_text = output_text
            self.usage = usage

    call = SimpleNamespace(
        type="function_call",
        name="abrir_programa",
        arguments='{"programa":"Notepad"}',
        call_id="call-trace-1",
    )
    response_usage = SimpleNamespace(
        input_tokens=900,
        output_tokens=120,
        input_tokens_details=SimpleNamespace(
            cached_tokens=100,
            cache_write_tokens=0,
        ),
    )
    responses = [
        FakeResponse([call], usage=response_usage),
        FakeResponse([], "Concluido.", usage=response_usage),
    ]

    manager = TaskManager()
    store = TaskTraceStore(tmp_path / "harness-trace.sqlite3")

    harness = AurenHarness(
        criar_resposta=lambda *_args, **_kwargs: responses.pop(0),
        executar_ferramenta=lambda _item: "Notepad aberto",
        mostrar_uso=lambda: None,
        obter_chamadas=lambda response: [
            item for item in response.output if item.type == "function_call"
        ],
        comando_rapido=lambda _mensagem: (False, ""),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        task_manager=manager,
        trace_store=store,
        max_model_rounds=3,
    )

    tratado, resposta = harness.processar_mensagem("abra o Notepad")
    assert tratado is False
    assert resposta.output_text == "Concluido."

    snapshot = harness.current_task()
    assert snapshot is not None
    assert snapshot.state is TaskState.COMPLETED

    row = store.get_task(snapshot.task_id)
    assert row is not None
    assert row["status"] == "completed"
    assert row["task_type"] == "agentic"
    assert row["model_rounds"] == 2
    assert row["tool_calls"] == 1
    assert row["tool_successes"] == 1
    assert row["input_tokens"] == 1800
    assert row["output_tokens"] == 240
    assert row["total_ms"] >= row["model_ms"]
    assert row["total_ms"] >= row["tool_ms"]
    assert row["objective_hash"]

    spans = store.get_spans(snapshot.task_id)
    assert any(span["category"] == "context" for span in spans)
    assert sum(span["category"] == "model" for span in spans) == 2
    assert any(span["category"] == "tool" and span["name"] == "abrir_programa" for span in spans)

