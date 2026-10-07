from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from threading import Event, Lock, Thread

from agent.ari_native.audio_manager import output_session
from typing import Any
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TTS_DIR = PROJECT_ROOT / "data" / "voice" / "tts" / "kokoro"
MODEL_PATH = TTS_DIR / "kokoro-v1.0.onnx"
VOICES_PATH = TTS_DIR / "voices-v1.0.bin"

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin"

TTS_EXPECTED = {
    MODEL_PATH.name: ("beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a", 325_505_369),
    VOICES_PATH.name: ("bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d", 28_214_398),
}


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

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _verify_file(cls, path: Path) -> None:
        esperado = TTS_EXPECTED.get(path.name)
        if esperado is None:
            raise RuntimeError(f"Modelo TTS sem manifest de integridade: {path.name}")
        expected_hash, expected_size = esperado
        if not path.is_file():
            raise RuntimeError(f"Arquivo TTS ausente: {path.name}")
        if path.stat().st_size != expected_size:
            try:
                path.unlink()
            except OSError:
                pass
            raise RuntimeError(
                f"Arquivo TTS com tamanho inesperado: {path.name}. "
                "O cache foi invalidado; execute novamente para baixar o artefato correto."
            )
        if cls._sha256(path) != expected_hash:
            try:
                path.unlink()
            except OSError:
                pass
            raise RuntimeError(
                f"SHA-256 invalido para o arquivo TTS {path.name}; cache invalidado."
            )

    def _ensure_files(self) -> None:
        for url, path in ((MODEL_URL, MODEL_PATH), (VOICES_URL, VOICES_PATH)):
            if path.exists():
                try:
                    self._verify_file(path)
                    continue
                except RuntimeError:
                    pass
                try:
                    path.unlink()
                except OSError:
                    pass
            self._download(url, path)
            self._verify_file(path)

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

        async def _play() -> None:
            stream = None
            try:
                stream = None
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
                    try:
                        asyncio.get_running_loop()
                    except RuntimeError:
                        asyncio.run(_play())
                    else:
                        erro = []
                        def executar_em_thread():
                            try:
                                asyncio.run(_play())
                            except BaseException as exc:
                                erro.append(exc)

                        thread = Thread(target=executar_em_thread, name="auren-kokoro", daemon=True)
                        thread.start()
                        thread.join()
                        if erro:
                            raise erro[0]
        except Exception as exc:
            raise RuntimeError(f"Falha na sintese Kokoro local: {exc}") from exc

# Compatibilidade temporaria para codigo legado da V2.
WindowsTTS = LocalKokoroTTS
