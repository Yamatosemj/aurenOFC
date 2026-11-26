"""Metricas observacionais de uma interacao de voz; nenhum audio ou texto e salvo."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4


DEFAULT_VOICE_METRICS_PATH = Path(__file__).resolve().parents[1] / "logs" / "voice" / "metrics.jsonl"
STAGES = ("capture", "asr", "task", "tts_first_chunk", "audio_delivery")


@dataclass
class VoiceInteractionMetrics:
    channel: str
    interaction_id: str = field(default_factory=lambda: uuid4().hex)
    task_id: str | None = None
    task_status: str | None = None
    audio_output_status: str = "unavailable"
    speech_end_at: float | None = None
    delivery_at: float | None = None
    durations_ms: dict[str, float | None] = field(default_factory=lambda: {name: None for name in STAGES})
    statuses: dict[str, str] = field(default_factory=lambda: {name: "unavailable" for name in STAGES})

    def record(self, stage: str, start: float | None, end: float | None, *, status: str = "completed") -> None:
        if stage not in self.durations_ms:
            raise ValueError(f"Etapa de voz desconhecida: {stage}")
        if start is not None and end is not None and end >= start:
            self.durations_ms[stage] = (end - start) * 1000.0
            self.statuses[stage] = status
        else:
            self.statuses[stage] = "unavailable" if status == "completed" else status

    def interval_ms(self) -> float | None:
        if self.speech_end_at is None or self.delivery_at is None or self.delivery_at < self.speech_end_at:
            return None
        return (self.delivery_at - self.speech_end_at) * 1000.0

    def payload(self) -> dict[str, Any]:
        return {
            "interaction_id": self.interaction_id,
            "channel": self.channel,
            "task_id": self.task_id,
            "task_status": self.task_status,
            "audio_output_status": self.audio_output_status,
            "stages_ms": dict(self.durations_ms),
            "stages_status": dict(self.statuses),
            "speech_end_to_audio_delivery_ms": self.interval_ms(),
            "speech_end_source": "ptt_release" if self.speech_end_at is not None else None,
            "delivery_kind": "first_output_write_attempt" if self.delivery_at is not None else None,
        }

    def persist(self, *, path: Path = DEFAULT_VOICE_METRICS_PATH, trace_store: Any = None) -> None:
        """Uma linha por interacao; falha da coleta nao altera o assistente."""
        data = self.payload()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            pass
        if self.task_id and trace_store is not None:
            try:
                trace_store.record_voice_interaction(self.task_id, data)
            except Exception:
                pass
