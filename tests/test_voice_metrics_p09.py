"""Regressoes offline da telemetria observacional de voz P09."""

import json
import time
from types import SimpleNamespace

import pytest

from core.task_trace import TaskTraceStore
from voice.main import _falar_interrompivel, _processar_e_falar
from voice.metrics import VoiceInteractionMetrics
from voice.tts import LocalKokoroTTS


def test_voice_metrics_distinguishes_zero_missing_failure_and_cancel(tmp_path):
    metrics = VoiceInteractionMetrics(channel="ptt")
    metrics.record("capture", 10.0, 10.0)
    metrics.record("asr", 10.0, 11.0, status="failed")
    metrics.statuses["tts_first_chunk"] = "cancelled"
    metrics.speech_end_at = 11.0
    assert metrics.interval_ms() is None
    path = tmp_path / "voice.jsonl"
    metrics.persist(path=path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["stages_ms"]["capture"] == 0.0
    assert data["stages_status"]["capture"] == "completed"
    assert data["stages_ms"]["asr"] == 1000.0
    assert data["stages_status"]["asr"] == "failed"
    assert data["stages_ms"]["tts_first_chunk"] is None
    assert data["stages_status"]["tts_first_chunk"] == "cancelled"
    assert data["speech_end_to_audio_delivery_ms"] is None
    assert data["task_id"] is None


def test_voice_metrics_attach_to_existing_task_without_schema_migration(tmp_path):
    store = TaskTraceStore(tmp_path / "trace.sqlite3")
    trace = store.start_task(task_id="task-voice", chat_id="chat", objective="teste")
    trace.finish(status="completed", total_ms=10)
    metrics = VoiceInteractionMetrics(channel="ptt", task_id="task-voice", task_status="completed")
    metrics.record("capture", 1.0, 1.5)
    metrics.record("asr", 1.5, 1.7)
    metrics.record("task", 1.7, 1.8)
    metrics.record("tts_first_chunk", 1.8, 1.9)
    metrics.record("audio_delivery", 1.9, 1.9)
    metrics.speech_end_at = 1.4
    metrics.delivery_at = 1.9
    metrics.persist(path=tmp_path / "voice.jsonl", trace_store=store)

    row = store.get_task("task-voice")
    assert row["asr_ms"] == pytest.approx(200)
    assert row["tts_ms"] == pytest.approx(100)
    assert row["total_ms"] == 10  # intervalo de voz nao altera duracao da tarefa
    spans = store.get_spans("task-voice")
    assert [span["name"] for span in spans] == [
        "capture", "asr", "task", "tts_first_chunk", "audio_delivery", "speech_end_to_audio_delivery"]
    assert spans[-1]["category"] == "voice_interval"
    assert spans[-1]["duration_ms"] == pytest.approx(500)
    assert json.loads(spans[-1]["metadata_json"])["delivery_kind"] == "first_output_write_attempt"
    assert all(metrics.interaction_id == json.loads(span["metadata_json"])["interaction_id"] for span in spans)


def test_voice_metrics_unavailable_span_is_not_zero_sample(tmp_path):
    store = TaskTraceStore(tmp_path / "trace.sqlite3")
    trace = store.start_task(task_id="failed", chat_id=None, objective="falha")
    trace.finish(status="failed")
    metrics = VoiceInteractionMetrics(channel="ptt", task_id="failed", task_status="failed")
    metrics.statuses["asr"] = "failed"
    metrics.persist(path=tmp_path / "voice.jsonl", trace_store=store)
    span = next(span for span in store.get_spans("failed") if span["name"] == "asr")
    assert span["duration_ms"] == 0.0
    assert json.loads(span["metadata_json"])["duration_available"] is False
    assert json.loads(span["metadata_json"])["stage_status"] == "failed"
    assert store.get_task("failed")["asr_ms"] == 0.0  # campo legado; span e autoritativo


def test_waiting_task_resumed_by_second_voice_interaction_keeps_totals_and_span_order(tmp_path):
    store = TaskTraceStore(tmp_path / "waiting.sqlite3")
    trace = store.start_task(task_id="same-task", chat_id="chat", objective="pedido")
    trace.record_stage("contexto inicial", 10.0, category="context")

    first = VoiceInteractionMetrics(channel="ptt", task_id=trace.task_id, task_status="waiting")
    first.record("asr", 1.0, 1.2)
    first.record("tts_first_chunk", 1.2, 1.3)
    first.persist(path=tmp_path / "voice.jsonl", trace_store=store)
    assert store.get_task(trace.task_id)["status"] is None

    # O Harness conserva o mesmo TaskTrace em WAITING e o retoma na resposta.
    trace.record_stage("contexto retomado", 5.0, category="context")
    trace.record_tool("ferramenta", 20.0, success=True)
    trace.finish(status="completed", total_ms=100.0)

    second = VoiceInteractionMetrics(channel="ptt", task_id=trace.task_id, task_status="completed")
    second.record("asr", 2.0, 2.4)
    second.record("tts_first_chunk", 2.4, 2.55)
    second.persist(path=tmp_path / "voice.jsonl", trace_store=store)
    # Reprocessar o mesmo envelope nao pode somar spans nem contadores novamente.
    store.record_voice_interaction(trace.task_id, second.payload())

    row = store.get_task(trace.task_id)
    assert row["status"] == "completed"
    assert row["context_ms"] == pytest.approx(15)
    assert row["tool_calls"] == 1
    assert row["asr_ms"] == pytest.approx(600)
    assert row["tts_ms"] == pytest.approx(250)
    spans = store.get_spans(trace.task_id)
    sequences = [span["sequence"] for span in spans]
    assert sequences == list(range(1, len(spans) + 1))
    assert [span["name"] for span in spans if span["category"] == "context"] == [
        "contexto inicial", "contexto retomado"]
    assert [json.loads(span["metadata_json"])["interaction_id"]
            for span in spans if span["category"] == "voice_interval"] == [
                first.interaction_id, second.interaction_id]


def test_voice_pipeline_links_task_and_measures_first_chunk_not_audibility(monkeypatch):
    from voice import main as voice_main

    class FakeHarness:
        def processar_mensagem(self, message):
            assert message == "olá"
            return False, SimpleNamespace(output_text="resposta")

        def current_task(self):
            return SimpleNamespace(task_id="task-1", state=SimpleNamespace(value="completed"), steps=[])

    class FakeRecorder:
        def definir_saida_ativa(self, _active):
            pass

        def limpar_pre_roll(self):
            pass

        def pediu_saida(self):
            return False

        def hotkey_pressionada(self):
            return False

    class FakeTTS:
        def falar(self, _text, *, cancel_event, on_audio_start, on_synthesis_ready):
            assert not cancel_event.is_set()
            on_synthesis_ready()
            on_audio_start()

    monkeypatch.setattr(voice_main.auren, "mostrar_uso", lambda: None)
    metrics = VoiceInteractionMetrics(channel="ptt", speech_end_at=time.perf_counter() - 0.01)
    sair, _ = _processar_e_falar(harness=FakeHarness(), tts=FakeTTS(), recorder=FakeRecorder(),
                                mensagem="olá", texto_recebido_em=time.perf_counter(), metrics=metrics)
    assert sair is False
    assert metrics.task_id == "task-1"
    assert metrics.task_status == "completed"
    assert metrics.durations_ms["task"] is not None
    assert metrics.durations_ms["tts_first_chunk"] is not None
    assert metrics.interval_ms() is not None
    assert metrics.payload()["delivery_kind"] == "first_output_write_attempt"


def test_tts_callbacks_mark_ready_then_first_write_attempt():
    events = []

    class FakeModel:
        async def create_stream(self, *_args, **_kwargs):
            yield [0.1], 22050

    class FakeStream:
        def start(self):
            events.append("stream_start")

        def write(self, _audio):
            events.append("write")

        def stop(self):
            pass

        def close(self):
            pass

    class FakeSoundDevice:
        def OutputStream(self, **_kwargs):
            return FakeStream()

    tts = LocalKokoroTTS(model=FakeModel(), sounddevice_module=FakeSoundDevice())
    tts.falar("olá", on_synthesis_ready=lambda: events.append("ready"),
              on_audio_start=lambda: events.append("delivery_attempt"))
    assert events == ["ready", "stream_start", "delivery_attempt", "write"]


def test_tts_cancel_before_first_chunk_has_no_delivery_interval():
    calls = []

    class FakeRecorder:
        def definir_saida_ativa(self, active):
            calls.append(active)

        def limpar_pre_roll(self):
            calls.append("clear")

        def pediu_saida(self):
            return False

        def hotkey_pressionada(self):
            return True

    class FakeTTS:
        def falar(self, _text, *, cancel_event, on_audio_start, on_synthesis_ready):
            del on_audio_start, on_synthesis_ready
            assert cancel_event.wait(1.0)

    metrics = VoiceInteractionMetrics(channel="ptt", speech_end_at=time.perf_counter())
    interrupted, exiting, latency = _falar_interrompivel(FakeTTS(), FakeRecorder(), "resposta", metrics=metrics)
    assert (interrupted, exiting, latency) == (True, False, None)
    assert metrics.statuses["tts_first_chunk"] == "cancelled"
    assert metrics.durations_ms["tts_first_chunk"] is None
    assert metrics.interval_ms() is None
    assert calls == [True, False, "clear"]


def test_tts_interruption_after_delivery_keeps_completed_stage_measurements():
    from threading import Event

    delivered = Event()

    class FakeRecorder:
        def definir_saida_ativa(self, _active):
            pass

        def limpar_pre_roll(self):
            pass

        def pediu_saida(self):
            return False

        def hotkey_pressionada(self):
            return delivered.is_set()

    class FakeTTS:
        def falar(self, _text, *, cancel_event, on_audio_start, on_synthesis_ready):
            on_synthesis_ready()
            on_audio_start()
            delivered.set()
            assert cancel_event.wait(1.0)

    metrics = VoiceInteractionMetrics(channel="ptt", speech_end_at=time.perf_counter())
    interrupted, exiting, _ = _falar_interrompivel(FakeTTS(), FakeRecorder(), "resposta", metrics=metrics)
    assert (interrupted, exiting) == (True, False)
    assert metrics.statuses["tts_first_chunk"] == "completed"
    assert metrics.statuses["audio_delivery"] == "completed"
    assert metrics.durations_ms["tts_first_chunk"] is not None
    assert metrics.durations_ms["audio_delivery"] == 0.0
    assert metrics.interval_ms() is not None
    assert metrics.payload()["audio_output_status"] == "cancelled"


def test_tts_failure_marks_failed_without_invented_delivery():
    class FakeRecorder:
        def definir_saida_ativa(self, _active):
            pass

        def limpar_pre_roll(self):
            pass

        def pediu_saida(self):
            return False

        def hotkey_pressionada(self):
            return False

    class FakeTTS:
        def falar(self, *_args, **_kwargs):
            raise RuntimeError("offline")

    metrics = VoiceInteractionMetrics(channel="ptt", speech_end_at=time.perf_counter())
    with pytest.raises(RuntimeError, match="offline"):
        _falar_interrompivel(FakeTTS(), FakeRecorder(), "resposta", metrics=metrics)
    assert metrics.statuses["tts_first_chunk"] == "failed"
    assert metrics.statuses["audio_delivery"] == "failed"
    assert metrics.interval_ms() is None
