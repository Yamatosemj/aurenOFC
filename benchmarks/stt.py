"""STT evaluation with no microphone, implicit downloads or credential discovery.

Default CLI only inventories pending cases. Cloud adapters require an injected
client and explicit authorization; the CLI deliberately cannot call paid APIs.
"""
from __future__ import annotations

import argparse
from array import array
from dataclasses import dataclass
import hashlib
from importlib import metadata
import io
import json
import math
from pathlib import Path
import platform
import random
import statistics
import sys
import time
import unicodedata
import wave


PRICE_DATE = "2026-10-21"
MODELS = {"groq": "whisper-large-v3-turbo", "openai": "gpt-4o-mini-transcribe"}


def normalize(text):
    """NFC, casefold, punctuation to spaces; accents/digits/fillers retained."""
    text = unicodedata.normalize("NFC", text).casefold()
    return " ".join("".join(" " if unicodedata.category(c).startswith("P")
                            else c for c in text).split())


def distance(reference, hypothesis):
    row = list(range(len(hypothesis) + 1))
    for i, left in enumerate(reference, 1):
        new = [i]
        for j, right in enumerate(hypothesis, 1):
            new.append(min(new[-1] + 1, row[j] + 1, row[j-1] + (left != right)))
        row = new
    return row[-1]


def score(reference, hypothesis):
    ref, hyp = normalize(reference), normalize(hypothesis)
    words, chars = ref.split(), list(ref.replace(" ", ""))
    we = distance(words, hyp.split())
    ce = distance(chars, list(hyp.replace(" ", "")))
    return {"word_errors": we, "reference_words": len(words),
            "char_errors": ce, "reference_chars": len(chars),
            "wer": we / len(words) if words else None,
            "cer": ce / len(chars) if chars else None,
            "exact_normalized": ref == hyp}


def estimated_cost(engine, seconds):
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Invalid audio duration")
    if engine == "groq":
        return max(10.0, seconds) * 0.04 / 3600
    if engine == "openai":
        return seconds * 0.003 / 60  # Published estimate, not actual token billing.
    if engine in {"parakeet", "faster-whisper"}:
        return 0.0  # API only, excludes energy/hardware.
    raise ValueError("Unknown engine")


@dataclass(frozen=True)
class Audio:
    samples: tuple[float, ...]
    sample_rate: int

    @property
    def seconds(self):
        return len(self.samples) / self.sample_rate


def read_wav(path):
    with wave.open(str(path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
            raise ValueError("Corpus must be mono PCM16 WAV at 16000 Hz")
        if source.getnframes() > 60 * 16000:
            raise ValueError("Clips must be at most 60 seconds")
        raw = array("h", source.readframes(source.getnframes()))
    if sys.byteorder != "little":
        raw.byteswap()
    if not raw:
        raise ValueError("Empty audio")
    return Audio(tuple(x / 32768 for x in raw), 16000)


def wav_bytes(audio):
    pcm = array("h", (max(-32768, min(32767, round(x * 32768))) for x in audio.samples))
    if sys.byteorder != "little":
        pcm.byteswap()
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(audio.sample_rate)
        target.writeframes(pcm.tobytes())
    return output.getvalue()


def add_noise(audio, snr_db=15.0, seed=0):
    """Deterministic white-noise condition; not a substitute for real room noise."""
    rng = random.Random(seed)
    noise = [rng.gauss(0, 1) for _ in audio.samples]
    signal_power = statistics.fmean(x*x for x in audio.samples)
    noise_power = statistics.fmean(x*x for x in noise)
    gain = math.sqrt(signal_power / (10 ** (snr_db / 10) * noise_power))
    values = tuple(x + gain*n for x, n in zip(audio.samples, noise))
    if any(abs(x) >= 1 for x in values):
        raise ValueError("Noise would clip: lower source level before benchmark")
    return Audio(values, audio.sample_rate)


class FasterWhisper:
    name = "faster-whisper"

    def __init__(self, model_dir, threads=4):
        self.path = Path(model_dir)
        self.threads = threads

    def start(self):
        if not self.path.is_dir() or not (self.path / "model.bin").is_file():
            raise ValueError("Explicit existing CTranslate2 model directory required")
        from faster_whisper import WhisperModel
        self.model = WhisperModel(str(self.path), device="cpu", compute_type="int8",
                                  cpu_threads=self.threads, num_workers=1,
                                  local_files_only=True)

    def transcribe(self, audio):
        import numpy as np
        segments, _ = self.model.transcribe(np.asarray(audio.samples, dtype=np.float32),
            language="pt", task="transcribe", beam_size=5, temperature=0,
            vad_filter=False, condition_on_previous_text=False)
        # Iteration is the inference, not just creation of the generator.
        return " ".join(segment.text.strip() for segment in segments).strip()


class Parakeet:
    name = "parakeet"

    def __init__(self, model_dir):
        self.path = Path(model_dir)

    def start(self):
        required = ("config.json", "encoder-model.onnx", "decoder_joint-model.onnx",
                    "nemo128.onnx", "vocab.txt")
        if not all((self.path / f).is_file() for f in required):
            raise ValueError("Complete explicit Parakeet directory/aliases required; no download")
        import onnx_asr
        from voice.stt import LocalPortugueseASR
        model = onnx_asr.load_model("nemo-conformer-tdt", path=str(self.path))
        self.model = LocalPortugueseASR(model=model)

    def transcribe(self, audio):
        return self.model.transcrever(audio.samples, audio.sample_rate)


class Cloud:
    """Injected SDK-shaped client. No keys, client creation or network at import.

    A future authorized caller supplies a dedicated client with finite timeout
    and retries disabled. A fake client is sufficient for all offline tests.
    """
    def __init__(self, engine, client, *, authorized=False, budget_usd=0):
        if engine not in MODELS or not math.isfinite(budget_usd) or budget_usd < 0:
            raise ValueError("Invalid cloud configuration")
        self.name, self.client = engine, client
        self.authorized, self.remaining = authorized, budget_usd

    def start(self):
        if not self.authorized:
            raise PermissionError("Cloud transcription not authorized")

    def transcribe(self, audio):
        self.start()
        cost = estimated_cost(self.name, audio.seconds)
        if cost > self.remaining:
            raise PermissionError("Evaluation budget exhausted")
        # Reserve even when the provider fails; no hidden retry/refund.
        self.remaining -= cost
        result = self.client.audio.transcriptions.create(
            model=MODELS[self.name], file=("evaluation.wav", wav_bytes(audio), "audio/wav"),
            language="pt", response_format="json", temperature=0)
        text = result.get("text") if isinstance(result, dict) else getattr(result, "text", None)
        if not isinstance(text, str):
            raise ValueError("Invalid transcription response")
        return text.strip()


def corpus_entries(manifest):
    entries = json.loads(Path(manifest).read_text(encoding="utf-8"))
    seen = set()
    for case in entries:
        if case["id"] in seen or not normalize(case["reference"]) or not case["tags"]:
            raise ValueError("Duplicate ID or missing reference/tags")
        seen.add(case["id"])
    return entries


def permitted_audio(case, root):
    if case.get("permission") != "approved" or not case.get("source") or not case.get("license"):
        raise PermissionError("Audio provenance/permission missing")
    root = Path(root).resolve()
    path = (root / case["audio"]).resolve()
    if not path.is_relative_to(root):
        raise PermissionError("Audio must remain inside the supplied corpus root")
    if path.stat().st_size > 2_000_000:
        raise ValueError("PCM16 evaluation clip exceeds 2 MB")
    if hashlib.sha256(path.read_bytes()).hexdigest() != case.get("sha256"):
        raise ValueError("Audio SHA256 mismatch")
    return path


def evaluate(adapter, entries, audio_root, *, repetitions=3, clock=time.perf_counter,
             simulated=False):
    if not 1 <= repetitions <= 100:
        raise ValueError("repetitions must be 1..100")
    prepared, rows = [], []
    # Validate corpus before initializing any engine.
    for case in entries:
        if not case.get("audio"):
            rows.append({"id": case["id"], "status": "pending_audio"})
            continue
        prepared.append((case, permitted_audio(case, audio_root)))
    startup = None
    if prepared:
        t = clock()
        adapter.start()
        startup = (clock() - t) * 1000
    first = True
    for case, path in prepared:
        for iteration in range(repetitions):
            t = clock()
            audio = read_wav(path)
            if case.get("noise_snr_db") is not None:
                audio = add_noise(audio, case["noise_snr_db"], case.get("seed", 0))
            prepared_at = clock()
            text = adapter.transcribe(audio)
            ready_at = clock()
            # Conversion to final consumable text included in delivery time.
            text = " ".join(text.split())
            delivered_at = clock()
            rows.append({"id": case["id"], "tags": case["tags"], "iteration": iteration,
                "status": "simulated" if simulated else "measured",
                "first_inference": first, "audio_sha256": case["sha256"],
                "hypothesis": text, "audio_seconds": audio.seconds,
                "prepare_ms": (prepared_at-t)*1000,
                "transcribe_ms": (ready_at-prepared_at)*1000,
                "delivery_ms": (delivered_at-ready_at)*1000,
                "audio_ready_to_text_ms": (delivered_at-t)*1000,
                "rtf": (ready_at-prepared_at)/audio.seconds,
                "capture_ms": None, "queue_ms": None,
                "cost_usd_estimate": estimated_cost(adapter.name, audio.seconds),
                **score(case["reference"], text)})
            first = False
    measured = [r for r in rows if r["status"] in {"measured", "simulated"}]
    warm = [r["audio_ready_to_text_ms"] for r in measured if not r["first_inference"]]
    def percentile(values, fraction):
        return sorted(values)[max(0, math.ceil(len(values)*fraction)-1)] if values else None
    we, rw = sum(r["word_errors"] for r in measured), sum(r["reference_words"] for r in measured)
    ce, rc = sum(r["char_errors"] for r in measured), sum(r["reference_chars"] for r in measured)
    versions = {}
    for package in ("numpy", "faster-whisper", "ctranslate2", "onnx-asr", "onnxruntime", "openai"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return {"engine": adapter.name, "simulated": simulated, "startup_ms": startup,
        "startup_scope": "imports/load only; fresh process required for cold OS cache",
        "warm_p50_ms": statistics.median(warm) if warm else None,
        "warm_p95_ms": percentile(warm, .95), "micro_wer": we/rw if rw else None,
        "micro_cer": ce/rc if rc else None, "price_date": PRICE_DATE,
        "python": platform.python_version(), "platform": platform.platform(), "packages": versions,
        "capture_and_queue_measured": False, "rows": rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--engine", choices=["plan", "parakeet", "faster-whisper"], default="plan")
    parser.add_argument("--audio-root", type=Path)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--model-revision", help="Immutable source revision of manually provisioned model")
    parser.add_argument("--allow-local-audio", action="store_true")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    entries = corpus_entries(args.manifest)
    if args.engine == "plan":
        result = {"status": "pending_real_audio_and_engines", "price_date": PRICE_DATE,
            "rows": [{"id": c["id"], "tags": c["tags"], "status": "pending",
                      "wer": None, "cer": None, "latency_ms": None} for c in entries]}
    else:
        if (not args.allow_local_audio or args.audio_root is None or args.model_dir is None
                or not args.model_revision):
            parser.error("Local inference requires --allow-local-audio, --audio-root, --model-dir and --model-revision")
        adapter = (Parakeet(args.model_dir) if args.engine == "parakeet" else
                   FasterWhisper(args.model_dir, args.threads))
        result = evaluate(adapter, entries, args.audio_root, repetitions=args.repetitions)
        result["configuration"] = {"model_revision_declared": args.model_revision,
            "threads": args.threads if args.engine == "faster-whisper" else "runtime-default",
            "compute_type": "int8", "beam_size": 5 if args.engine == "faster-whisper" else None,
            "language": "pt", "shared_vad": False, "repetitions": args.repetitions}
    # Preserve existing evidence rather than silently overwriting it.
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
