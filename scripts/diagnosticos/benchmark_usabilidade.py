"""Offline local overhead benchmark; provider latency is deliberately excluded."""
import argparse
import gc
import json
from pathlib import Path
from statistics import median
import tempfile
import time
from types import SimpleNamespace

from core.harness import AurenHarness
from core.orchestrator import AurenOrchestrator
from core.router import Router
from core.session import SessionContextManager
from core.task_manager import TaskManager
from core.task_trace import TaskTraceStore, _percentile
from core.tools_registry import tools
from memory.store import PersistentMemoryStore


def stats(values):
    return {"n": len(values), "median": round(median(values), 3),
            "p95": round(_percentile(values, 95), 3)}


def run(samples):
    result = {"kind": "offline_fake_provider_real_sqlite_no_api", "samples": samples, "cases": {}}
    with tempfile.TemporaryDirectory(prefix="auren-benchmark-") as folder:
        root = Path(folder)
        for case, objective in {"saudacao": "Olá!", "conversa": "Como posso organizar melhor minhas ideias?",
                                "pergunta": "Explique o que é uma metáfora."}.items():
            durations, contexts, calls, tool_counts, payloads = [], [], [], [], []
            class Provider:
                def create_response(self, entrada, **kwargs):
                    calls.append(1)
                    tool_counts.append(len(kwargs["tools"]))
                    payloads.append(len(json.dumps({"input": entrada, "tools": kwargs["tools"]}, ensure_ascii=False)))
                    return SimpleNamespace(output=[], output_text="Resposta fictícia para medir o processamento local.")
            orch = AurenOrchestrator(provider=Provider(), router=Router())
            trace = TaskTraceStore(root / (case + "-traces.db"))
            harness = AurenHarness(criar_resposta=lambda entrada, rid=None, effort="none", choice=None: orch.create_response(
                entrada, response_id=rid, reasoning_effort=effort, tool_choice=choice),
                executar_ferramenta=lambda _: (_ for _ in ()).throw(AssertionError("No tools expected")),
                obter_chamadas=lambda r: r.output, mostrar_uso=lambda: None,
                comando_rapido=lambda _: (False, ""), iniciar_tarefa=lambda: None,
                apos_tarefa=None, fechar=lambda: None, trace_store=trace,
                task_manager=TaskManager(db_path=root / (case + "-tasks.db")),
                context=SessionContextManager(store=PersistentMemoryStore(root / (case + "-memory.db"))))
            try:
                for _ in range(samples):
                    started = time.perf_counter()
                    harness.processar_mensagem(objective)
                    durations.append((time.perf_counter()-started)*1000)
                    contexts.append(trace.get_task(harness.current_task().task_id)["context_ms"])
                result["cases"][case] = {"total_ms": stats(durations), "context_ms": stats(contexts),
                    "model_calls": len(calls), "tools_per_call": stats(tool_counts), "payload_chars": stats(payloads),
                    "last_status": harness.current_task().state.value}
            finally:
                harness.shutdown()
                gc.collect()
        gc.collect()
    result["ambiguous_tools"] = len(Router().select_tools("faça isso", tools))
    from tests.benchmark_app_discovery import benchmark
    result['simulated_executable_scan'] = benchmark(samples, stats)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(run(args.samples), ensure_ascii=False, indent=2), encoding="utf-8")
