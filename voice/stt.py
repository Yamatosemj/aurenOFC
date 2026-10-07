from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VOICE_DIR = PROJECT_ROOT / "data" / "voice"
ASR_DIR = VOICE_DIR / "asr" / "parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx-int8"
ASR_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_REPO = "calneymgp/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx-int8"

ASR_REVISION = "f5f837ee9e385781e60748cb9824a9c65487be36"
ASR_EXPECTED = {
    "encoder-model.int8.onnx": "89e0b5d9d0b4d968e74b5b0b7d6d5d0d6d3d37d62a4c2d6b1b19f2d0d5d9d4d4",
}


class LocalPortugueseASR:
    """ASR local em português brasileiro via Parakeet TDT + ONNX Runtime."""

    def __init__(
        self,
        *,
        repo_id: str | None = None,
        model_dir: str | Path | None = None,
        model: Any | None = None,
        language: str = "pt",
    ) -> None:
        self.repo_id = repo_id or os.getenv("AUREN_ASR_MODEL", DEFAULT_REPO)
        self.model_dir = Path(model_dir or ASR_DIR)
        self.language = language
        self._model = model
        self._runtime = "onnxruntime-cpu"

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

        # Compatibilidade com onnx-asr 0.12: o loader espera os nomes
        # padrao do pacote NeMo, enquanto o modelo TAGARELA INT8 usa
        # explicitamente os sufixos ".int8.onnx".
        #
        # Criamos hard links no mesmo diretorio para reutilizar os mesmos
        # bytes, sem duplicar ~GB de modelo no disco. Em Windows, os.link()
        # funciona normalmente para arquivos no mesmo volume. Se o sistema
        # nao permitir hard link, usamos copia como fallback seguro.
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
            # onnx-asr 0.12 documenta 'nemo-conformer-tdt' + path/local_dir.
            # Usamos path= explicitamente para evitar que a API interprete a
            # chamada como um nome de modelo sem diretório local.
            self._model = onnx_asr.load_model(
                "nemo-conformer-tdt",
                path=str(model_dir),
            )
        except Exception as exc:
            raise RuntimeError(f"Falha ao carregar o ASR Parakeet local: {exc}") from exc

    @property
    def runtime(self) -> str:
        return self._runtime

    def transcrever(self, audio: Any, sample_rate: int | None = None) -> str:
        self._ensure_model()
        if audio is None:
            return ""

        waveform = getattr(audio, "samples", audio)
        sr = sample_rate or int(getattr(audio, "sample_rate", 16_000))

        try:
            resultado = self._model.recognize(
                waveform,
                sample_rate=sr,
                language=self.language,
                channel="mean",
            )
        except TypeError:
            # Compatibilidade com adapters que nao aceitam todos os kwargs.
            resultado = self._model.recognize(
                waveform,
                sample_rate=sr,
            )
        except Exception as exc:
            raise RuntimeError(f"Falha na transcricao local PT-BR: {exc}") from exc

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

# Compatibilidade temporaria para codigo legado da V2.
LocalWhisper = LocalPortugueseASR
