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
    "encoder-model.int8.onnx": ("89e33f4b8c5186a7034947f07e41af36b853ab638c5a16be37d55774722b8fc5", 879_746_906),
    "decoder_joint-model.int8.onnx": ("4150d4d86c89dfee7a9a0d6d7ab2e8d756ba31ffe92ca0242fa93707febc33ac", 53_592_358),
    "nemo128.onnx": ("a9fde1486ebfcc08f328d75ad4610c67835fea58c73ba57e3209a6f6cf019e9f", 139_764),
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

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _verify_model_files(cls, model_dir: Path) -> list[str]:
        invalid: list[str] = []
        for name in (
            "config.json",
            "encoder-model.int8.onnx",
            "decoder_joint-model.int8.onnx",
            "nemo128.onnx",
            "vocab.txt",
        ):
            if not (model_dir / name).is_file():
                invalid.append(f"ausente:{name}")

        for name, (expected_hash, expected_size) in ASR_EXPECTED.items():
            path = model_dir / name
            if not path.is_file():
                continue
            try:
                if path.stat().st_size != expected_size:
                    invalid.append(f"tamanho:{name}")
                    continue
                if cls._sha256(path) != expected_hash:
                    invalid.append(f"sha256:{name}")
            except OSError:
                invalid.append(f"indisponivel:{name}")
        return invalid

    def _download_model(self) -> Path:
        """Garante cache do modelo em revision imutavel e com integridade verificada."""
        self.model_dir.mkdir(parents=True, exist_ok=True)

        required = (
            "config.json",
            "encoder-model.int8.onnx",
            "decoder_joint-model.int8.onnx",
            "nemo128.onnx",
            "vocab.txt",
        )
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise RuntimeError(
                "hugging-face-hub ausente. Rode INSTALAR_VOZ.bat."
            ) from exc

        invalid = self._verify_model_files(self.model_dir)
        if invalid:
            for name in required:
                try:
                    (self.model_dir / name).unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    pass

            print(
                "Primeiro uso do ASR ou cache invalido: baixando Parakeet "
                f"PT-BR TAGARELA INT8 em revision {ASR_REVISION}..."
            )
            try:
                snapshot_download(
                    repo_id=self.repo_id,
                    revision=ASR_REVISION,
                    local_dir=str(self.model_dir),
                    allow_patterns=list(required),
                    force_download=True,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Falha ao baixar o ASR Parakeet local: {exc}"
                ) from exc

        invalid = self._verify_model_files(self.model_dir)
        if invalid:
            raise RuntimeError(
                "Integridade do cache ASR invalida apos o download: "
                + ", ".join(invalid)
            )

        aliases = {
            "encoder-model.onnx": "encoder-model.int8.onnx",
            "decoder_joint-model.onnx": "decoder_joint-model.int8.onnx",
        }
        for alias_name, source_name in aliases.items():
            alias = self.model_dir / alias_name
            source = self.model_dir / source_name
            if alias.exists():
                try:
                    if alias.stat().st_size == source.stat().st_size:
                        continue
                except OSError:
                    pass
                try:
                    alias.unlink()
                except OSError:
                    pass
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
