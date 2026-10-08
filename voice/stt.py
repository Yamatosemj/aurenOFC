from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VOICE_DIR = PROJECT_ROOT / "data" / "voice"
ASR_DIR = VOICE_DIR / "asr" / "parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx-int8"
ASR_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_REPO = "calneymgp/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx-int8"
DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_GAIN_TARGET_RMS = 0.035
DEFAULT_GAIN_MAX = 8.0


def _normalizar_nivel_fala(waveform: Any, *, target_rms: float = DEFAULT_GAIN_TARGET_RMS, max_gain: float = DEFAULT_GAIN_MAX) -> Any:
    """Eleva apenas sinais de fala muito baixos, sem permitir ganho destrutivo."""
    import numpy as np

    audio = _normalizar_onda(waveform)
    if audio.size == 0:
        return audio

    rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float64)))))
    peak = float(np.max(np.abs(audio)))
    if rms <= 0.0 or peak <= 0.0 or target_rms <= 0.0 or max_gain <= 1.0:
        return audio

    gain = min(float(max_gain), max(1.0, float(target_rms) / rms))
    if peak * gain > 0.95:
        gain = min(gain, 0.95 / peak)
    return (audio * np.float32(max(1.0, gain))).astype(np.float32, copy=False)


def _normalizar_onda(waveform: Any) -> Any:
    import numpy as np

    audio = np.asarray(waveform, dtype=np.float32)
    if audio.ndim == 0:
        audio = audio.reshape(1)
    elif audio.ndim > 1:
        audio = np.mean(audio, axis=-1)
    return np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0).reshape(-1)


def _resample_linear(audio: Any, sample_rate: int, target_rate: int) -> Any:
    import numpy as np

    source = _normalizar_onda(audio)
    sr = int(sample_rate)
    target = int(target_rate)

    if source.size == 0 or sr <= 0 or target <= 0 or sr == target:
        return source

    target_length = max(1, int(round(source.size * target / sr)))
    if target_length == source.size:
        return source

    # Para reducoes inteiras comuns de 48/32 kHz para 16 kHz, a media por
    # bloco evita aliases grosseiros sem adicionar uma dependencia DSP.
    if sr % target == 0 and sr > target:
        factor = sr // target
        usable = (source.size // factor) * factor
        if usable >= factor:
            return (
                source[:usable]
                .reshape(-1, factor)
                .mean(axis=1, dtype=np.float32)
                .astype(np.float32, copy=False)
            )

    old_positions = np.linspace(0.0, 1.0, source.size, dtype=np.float64)
    new_positions = np.linspace(0.0, 1.0, target_length, dtype=np.float64)
    return np.interp(new_positions, old_positions, source).astype(
        np.float32,
        copy=False,
    )


def _normalizar_resultado(resultado: Any) -> str:
    if isinstance(resultado, str):
        texto = resultado
    elif isinstance(resultado, (list, tuple)):
        partes: list[str] = []
        for item in resultado:
            texto_item = getattr(item, "text", None)
            if texto_item:
                partes.append(str(texto_item))
            elif isinstance(item, dict) and item.get("text"):
                partes.append(str(item["text"]))
        texto = " ".join(partes)
    else:
        texto = str(getattr(resultado, "text", resultado))

    return " ".join(texto.split()).strip()


class LocalPortugueseASR:
    """ASR local em português brasileiro via Parakeet TDT + ONNX Runtime."""

    def __init__(
        self,
        *,
        repo_id: str | None = None,
        model_dir: str | Path | None = None,
        model: Any | None = None,
        language: str = "pt",
        target_sample_rate: int | None = None,
    ) -> None:
        self.repo_id = repo_id or os.getenv("AUREN_ASR_MODEL", DEFAULT_REPO)
        self.model_dir = Path(model_dir or ASR_DIR)
        self.language = language
        self.target_sample_rate = int(
            target_sample_rate
            or os.getenv("AUREN_ASR_SAMPLE_RATE", DEFAULT_SAMPLE_RATE)
        )
        if self.target_sample_rate <= 0:
            raise ValueError("target_sample_rate deve ser maior que zero.")

        self._model = model
        self._runtime = "onnxruntime-cpu"
        self._inference_lock = Lock()

    def _download_model(self) -> Path:
        """Garante o cache local completo do modelo INT8 oficial."""
        self.model_dir.mkdir(parents=True, exist_ok=True)

        required = (
            "config.json",
            "encoder-model.int8.onnx",
            "decoder_joint-model.int8.onnx",
            "nemo128.onnx",
            "vocab.txt",
        )
        if not all((self.model_dir / name).exists() for name in required):
            try:
                from huggingface_hub import snapshot_download
            except ImportError as exc:
                raise RuntimeError(
                    "hugging-face-hub ausente. Rode INSTALAR_VOZ.bat."
                ) from exc

            print(
                "Primeiro uso do ASR: baixando Parakeet PT-BR TAGARELA INT8 "
                f"({self.repo_id})..."
            )
            try:
                snapshot_download(
                    repo_id=self.repo_id,
                    local_dir=str(self.model_dir),
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Falha ao baixar o ASR Parakeet local: {exc}"
                ) from exc

            missing = [name for name in required if not (self.model_dir / name).exists()]
            if missing:
                raise RuntimeError(
                    "Download do ASR terminou, mas faltam arquivos do modelo: "
                    + ", ".join(missing)
                )

        aliases = {
            "encoder-model.onnx": "encoder-model.int8.onnx",
            "decoder_joint-model.onnx": "decoder_joint-model.int8.onnx",
        }
        for alias_name, source_name in aliases.items():
            alias = self.model_dir / alias_name
            source = self.model_dir / source_name
            if alias.exists():
                continue
            try:
                os.link(source, alias)
            except OSError:
                try:
                    import shutil

                    shutil.copy2(source, alias)
                except Exception as exc:
                    raise RuntimeError(
                        f"Nao foi possivel preparar o alias do modelo '{alias_name}': {exc}"
                    ) from exc
            print(f"ASR: alias de compatibilidade pronto: {alias_name}")

        return self.model_dir

    def _ensure_model(self) -> None:
        if self._model is not None:
            return

        try:
            import onnx_asr
        except ImportError as exc:
            raise RuntimeError(
                "onnx-asr ausente. Rode INSTALAR_VOZ.bat."
            ) from exc

        model_dir = self._download_model()
        try:
            print(
                "Carregando Parakeet PT-BR TAGARELA INT8 local "
                f"de {model_dir}..."
            )
            self._model = onnx_asr.load_model(
                "nemo-conformer-tdt",
                path=str(model_dir),
            )
        except Exception as exc:
            raise RuntimeError(f"Falha ao carregar o ASR Parakeet local: {exc}") from exc

    def precarregar(self) -> None:
        """Aquece o modelo explicitamente sem transcrever audio."""

        with self._inference_lock:
            self._ensure_model()

    @property
    def runtime(self) -> str:
        return self._runtime

    def preparar_audio(self, audio: Any, sample_rate: int | None = None) -> tuple[Any, int]:
        if audio is None:
            return [], self.target_sample_rate

        waveform = getattr(audio, "samples", audio)
        sr = int(sample_rate or getattr(audio, "sample_rate", self.target_sample_rate))
        return _resample_linear(waveform, sr, self.target_sample_rate), self.target_sample_rate

    def transcrever(self, audio: Any, sample_rate: int | None = None) -> str:
        waveform, sr = self.preparar_audio(audio, sample_rate)
        if getattr(waveform, "size", len(waveform) if hasattr(waveform, "__len__") else 0) == 0:
            return ""

        try:
            duration = float(len(waveform)) / float(sr)
        except Exception as exc:
            raise RuntimeError(f"Audio invalido para transcricao local: {exc}") from exc
        if duration < 0.08:
            return ""

        try:
            with self._inference_lock:
                self._ensure_model()
                try:
                    resultado = self._model.recognize(
                        waveform,
                        sample_rate=sr,
                        language=self.language,
                        channel="mean",
                    )
                except TypeError:
                    resultado = self._model.recognize(
                        waveform,
                        sample_rate=sr,
                    )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Falha na transcricao local PT-BR: {exc}") from exc

        return _normalizar_resultado(resultado)


# Compatibilidade temporaria para codigo legado da V2.
LocalWhisper = LocalPortugueseASR
