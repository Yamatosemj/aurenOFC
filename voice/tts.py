from __future__ import annotations

import asyncio
import os
from pathlib import Path
from threading import Event, Lock
from typing import Any
from urllib.request import urlopen

from agent.ari_native.audio_manager import output_session
from voice.audio_devices import carregar_escolha, resolver_dispositivo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TTS_DIR = PROJECT_ROOT / "data" / "voice" / "tts" / "kokoro"
MODEL_PATH = TTS_DIR / "kokoro-v1.0.onnx"
VOICES_PATH = TTS_DIR / "voices-v1.0.bin"

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin"


class LocalKokoroTTS:
    """TTS local via Kokoro ONNX, com streaming de audio."""

    DEFAULT_VOICE = "pm_alex"
    DEFAULT_LANG = "pt-br"

    def __init__(
        self,
        *,
        voice: str | None = None,
        lang: str | None = None,
        speed: float | None = None,
        model: Any | None = None,
        sounddevice_module: Any | None = None,
    ) -> None:
        self.voice = voice or os.getenv("AUREN_TTS_VOICE", self.DEFAULT_VOICE)
        self.lang = lang or os.getenv("AUREN_TTS_LANG", self.DEFAULT_LANG)
        self.speed = float(speed or os.getenv("AUREN_TTS_SPEED", "1.05"))
        self._model = model
        self._sd = sounddevice_module
        self._lock = Lock()

    def _load_sounddevice(self) -> Any:
        if self._sd is None:
            try:
                import sounddevice as sd
            except ImportError as exc:
                raise RuntimeError("sounddevice ausente. Rode INSTALAR_VOZ.bat.") from exc
            self._sd = sd
        return self._sd

    @staticmethod
    def _download(url: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        print(f"Baixando modelo de voz local: {target.name}", flush=True)

        if partial.exists():
            try:
                partial.unlink()
            except OSError:
                pass

        try:
            with urlopen(url, timeout=120) as response:
                total = int(response.headers.get("Content-Length") or 0)
                downloaded = 0
                last_report = -1

                with partial.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        downloaded += len(chunk)

                        if total > 0:
                            percent = int(downloaded * 100 / total)
                            if percent != last_report and (percent == 100 or percent % 5 == 0):
                                done_mb = downloaded / (1024 * 1024)
                                total_mb = total / (1024 * 1024)
                                print(
                                    f"  {percent:3d}% | {done_mb:,.1f} / {total_mb:,.1f} MB",
                                    flush=True,
                                )
                                last_report = percent
                        else:
                            done_mb = downloaded / (1024 * 1024)
                            if downloaded == len(chunk) or downloaded // (10 * 1024 * 1024) != (downloaded - len(chunk)) // (10 * 1024 * 1024):
                                print(f"  baixados: {done_mb:,.1f} MB", flush=True)

            partial.replace(target)
            print(f"Download concluído: {target.name}", flush=True)
        except Exception:
            try:
                partial.unlink()
            except OSError:
                pass
            raise

    def _ensure_files(self) -> None:
        if not MODEL_PATH.exists():
            self._download(MODEL_URL, MODEL_PATH)
        if not VOICES_PATH.exists():
            self._download(VOICES_URL, VOICES_PATH)

    def _ensure_model(self) -> None:
        if self._model is not None:
            return

        try:
            from kokoro_onnx import Kokoro
        except ImportError as exc:
            raise RuntimeError("kokoro-onnx ausente. Rode INSTALAR_VOZ.bat.") from exc

        self._ensure_files()
        try:
            self._model = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
        except Exception as exc:
            raise RuntimeError(f"Falha ao carregar o Kokoro local: {exc}") from exc

    def falar(self, texto: str, *, cancel_event: Event | None = None, on_audio_start: Any | None = None) -> None:
        mensagem = str(texto or "").strip()
        if not mensagem:
            return

        self._ensure_model()
        sd = self._load_sounddevice()
        saved_name = carregar_escolha("output")
        device_index = resolver_dispositivo(saved_name, "output")

        async def _play() -> None:
            stream = None
            try:
                async for samples, sample_rate in self._model.create_stream(
                    mensagem,
                    voice=self.voice,
                    speed=self.speed,
                    lang=self.lang,
                ):
                    if cancel_event is not None and cancel_event.is_set():
                        break

                    import numpy as np

                    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
                    if audio.size == 0:
                        continue
                    if stream is None:
                        stream = sd.OutputStream(
                            samplerate=int(sample_rate),
                            channels=1,
                            dtype="float32",
                            latency="low",
                            device=device_index,
                        )
                        stream.start()
                        if on_audio_start is not None:
                            on_audio_start()
                    stream.write(audio)
            finally:
                if stream is not None:
                    stream.stop()
                    stream.close()

        try:
            with self._lock:
                with output_session():
                    asyncio.run(_play())
        except Exception as exc:
            raise RuntimeError(f"Falha na sintese Kokoro local: {exc}") from exc

# Compatibilidade temporaria para codigo legado da V2.
WindowsTTS = LocalKokoroTTS
