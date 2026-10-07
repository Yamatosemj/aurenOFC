from __future__ import annotations

import json
import logging
import os
import platform
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger("auren.voice.audio")

DEFAULT_LABEL = "Sistema padrão"
DEFAULT_VALUE = ""

_RATES = {"input": 16_000, "output": 24_000}
_PROBE_SECONDS = {"input": 0.35, "output": 0.60}
_PREFERRED_APIS = {
    "Windows": ("directsound", "mme", "wasapi"),
    "Darwin": ("core audio",),
    "Linux": ("pulse", "pipewire", "jack", "alsa"),
}
_PSEUDO_DEVICES = (
    "sound mapper",
    "primary sound",
    "sysdefault",
    "default",
    "dmix",
    "dsnoop",
    "surround",
    "samplerate",
    "speexrate",
    "upmix",
    "vdownmix",
    "null",
)

_cache: dict[str, list[str]] | None = None
_cache_lock = threading.Lock()
_chosen_api: dict[str, str | None] = {"input": None, "output": None}
_probe_results: dict[tuple[str | None, str], bool] = {}


def _config_path() -> Path:
    if os.name == "nt":
        root = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.getenv("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return root / "Auren" / "audio_devices.json"


def _valid_kind(kind: str) -> str:
    if kind not in {"input", "output"}:
        raise ValueError("kind deve ser 'input' ou 'output'")
    return kind


def _normalizar_nome(nome: Any) -> str:
    return str(nome or "").strip()


def _nome_chave(nome: str) -> str:
    return nome.casefold()


def _is_pseudo(nome: str) -> bool:
    low = _normalizar_nome(nome).casefold()
    return any(token in low for token in _PSEUDO_DEVICES)


def _obter_sounddevice() -> Any:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("sounddevice ausente. Rode INSTALAR_VOZ.bat.") from exc
    return sd


def _carregar_config() -> dict[str, str]:
    path = _config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        _LOGGER.warning("Configuração de áudio inválida em %s: %s; usando padrão", path, exc)
        return {}
    if not isinstance(data, dict):
        _LOGGER.warning("Configuração de áudio não é um objeto JSON; usando padrão")
        return {}
    return {
        "input": _normalizar_nome(data.get("input")),
        "output": _normalizar_nome(data.get("output")),
    }


def carregar_escolha(kind: str) -> str:
    """Lê o nome salvo para uma direção de áudio.
    Retorna vazio quando a escolha é o padrão do sistema ou não existe.
    O custo é uma leitura pequena de JSON no armazenamento local."""
    kind = _valid_kind(kind)
    return _carregar_config().get(kind, "")


def salvar_escolha(kind: str, nome: str | None) -> Path:
    """Persiste o nome escolhido para uma direção de áudio.
    A gravação é atômica e nomes vazios significam retorno ao padrão do sistema.
    O custo é uma escrita pequena de JSON no armazenamento local."""
    kind = _valid_kind(kind)
    config = _carregar_config()
    config[kind] = _normalizar_nome(nome)
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="audio_devices_", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "input": config.get("input", ""),
                    "output": config.get("output", ""),
                },
                fh,
                ensure_ascii=False,
                indent=2,
            )
            fh.write("\n")
        Path(tmp_name).replace(path)
    finally:
        try:
            Path(tmp_name).unlink()
        except FileNotFoundError:
            pass
    return path


def _hostapis(sd: Any) -> list[str]:
    try:
        return [str(item.get("name", "")) for item in sd.query_hostapis()]
    except Exception:
        return []


def _api_name(dev: dict[str, Any], apis: list[str]) -> str:
    index = dev.get("hostapi")
    if isinstance(index, int) and 0 <= index < len(apis):
        return apis[index].casefold()
    return ""


def _display_name(name: str, devices: list[dict[str, Any]]) -> str:
    if len(name) < 30:
        return name
    best = name
    for dev in devices:
        other = _normalizar_nome(dev.get("name"))
        if len(other) > len(best) and other.startswith(name):
            best = other
    return best


def _usable(idx: int, kind: str, sd: Any) -> bool:
    stream = None
    rate = _RATES[kind]
    try:
        if kind == "input":
            stream = sd.InputStream(
                samplerate=rate,
                channels=1,
                dtype="int16",
                blocksize=1024,
                device=idx,
                callback=lambda *_args: None,
            )
        else:
            stream = sd.RawOutputStream(
                samplerate=rate,
                channels=1,
                dtype="int16",
                blocksize=1024,
                device=idx,
            )
        stream.start()
        return True
    except Exception:
        return False
    finally:
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass


def _probe_enabled() -> bool:
    return os.getenv("AUREN_AUDIO_PROBE", "1").strip().casefold() not in {
        "0",
        "false",
        "nao",
        "não",
        "off",
    }


def _transport_works(
    idx: int,
    kind: str,
    api_key: str | None,
    sd: Any,
) -> bool:
    key = (api_key, kind)
    cached = _probe_results.get(key)
    if cached is not None:
        return cached

    if not _probe_enabled():
        _probe_results[key] = True
        return True

    ok = False
    rate = _RATES[kind]
    seconds = _PROBE_SECONDS[kind]
    stream = None
    try:
        if kind == "output":
            stream = sd.RawOutputStream(
                samplerate=rate,
                channels=1,
                dtype="int16",
                blocksize=1024,
                device=idx,
            )
            stream.start()
            started = time.monotonic()
            stream.write(bytes(int(rate * seconds) * 2))
            elapsed = time.monotonic() - started
            ok = elapsed >= seconds * 0.5
            if not ok:
                _LOGGER.warning(
                    "Áudio de saída foi aceito pelo host API, mas não consumiu os dados "
                    "(%.0f ms para %.0f ms); ignorando essa API",
                    elapsed * 1000,
                    seconds * 1000,
                )
        else:
            frames = 0

            def _callback(_indata: Any, count: int, *_args: Any) -> None:
                nonlocal frames
                frames += int(count)

            stream = sd.InputStream(
                samplerate=rate,
                channels=1,
                dtype="int16",
                blocksize=1024,
                device=idx,
                callback=_callback,
            )
            stream.start()
            time.sleep(seconds)
            ok = frames > rate * seconds * 0.3
            if not ok:
                _LOGGER.warning(
                    "Áudio de entrada entregou poucos frames (%d em %.0f ms); ignorando essa API",
                    frames,
                    seconds * 1000,
                )
    except Exception as exc:
        _LOGGER.warning("Sonda de transporte de áudio (%s) falhou: %s", kind, exc)
        ok = False
    finally:
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

    _probe_results[key] = ok
    return ok


def _query() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"input": [], "output": []}
    sd = _obter_sounddevice()
    devices = list(sd.query_devices())
    apis = _hostapis(sd)
    preferred = _PREFERRED_APIS.get(platform.system(), ())

    def collect(api_filter: str | None, kind: str) -> list[tuple[int, str]]:
        channel_key = "max_input_channels" if kind == "input" else "max_output_channels"
        found: list[tuple[int, str]] = []
        seen: set[str] = set()
        for idx, dev in enumerate(devices):
            name = _normalizar_nome(dev.get("name"))
            key = _nome_chave(name)
            if not name or _is_pseudo(name) or key in seen:
                continue
            if int(dev.get(channel_key, 0) or 0) <= 0:
                continue
            if api_filter is not None and api_filter not in _api_name(dev, apis):
                continue
            if not _usable(idx, kind, sd):
                continue
            seen.add(key)
            found.append((idx, name))
        return found

    for kind in ("input", "output"):
        for api_filter in list(preferred) + [None]:
            found = collect(api_filter, kind)
            if not found:
                continue
            if not _transport_works(found[0][0], kind, api_filter, sd):
                continue
            _chosen_api[kind] = api_filter
            result[kind] = [_display_name(name, devices) for _idx, name in found]
            break

    return result


def prefetch() -> None:
    """Precarrega os dispositivos de áudio em uma thread de fundo.
    O resultado fica em cache para evitar latência no início do uso da voz.
    O custo é uma thread curta de enumeração e sondagem do backend de áudio."""
    def _work() -> None:
        global _cache
        try:
            result = _query()
        except Exception as exc:
            _LOGGER.warning("Enumeração de dispositivos de áudio falhou: %s", exc)
            result = {"input": [], "output": []}
        with _cache_lock:
            _cache = result

    threading.Thread(target=_work, name="auren-audio-devices", daemon=True).start()


def listar_dispositivos(kind: str, refresh: bool = False) -> list[str]:
    """Lista nomes únicos de dispositivos utilizáveis para uma direção.
    Usa a cache aquecida pelo boot e reconsulta quando ela não existe ou é forçada.
    O custo da consulta é proporcional ao número de endpoints expostos pelo backend."""
    global _cache
    kind = _valid_kind(kind)
    with _cache_lock:
        cached = None if refresh else _cache
    if cached is None:
        result = _query()
        with _cache_lock:
            _cache = result
            cached = result
    return list(cached.get(kind, []))


def _matching_candidate(
    wanted: str,
    candidates: list[tuple[int, str]],
) -> int | None:
    exact = None
    partial = None
    wanted_key = _nome_chave(wanted)
    for idx, dev_name in candidates:
        dev_key = _nome_chave(dev_name)
        if dev_key == wanted_key:
            exact = idx
            break
        prefix_len = min(24, len(wanted), len(dev_name))
        if prefix_len > 0 and (
            dev_key.startswith(wanted_key[:prefix_len])
            or wanted_key.startswith(dev_key[:prefix_len])
        ):
            if partial is None:
                partial = idx
    return exact if exact is not None else partial


def resolver_dispositivo(nome: str, kind: str) -> int | None:
    """Resolve um nome salvo para o índice atual do sounddevice.
    Valida abertura real e retorna None para padrão do sistema ou dispositivo indisponível.
    O custo é uma enumeração atual e, quando necessário, uma abertura curta de teste."""
    kind = _valid_kind(kind)
    wanted = _normalizar_nome(nome)
    if not wanted or wanted.casefold() == DEFAULT_LABEL.casefold():
        return None

    try:
        sd = _obter_sounddevice()
        devices = list(sd.query_devices())
        apis = _hostapis(sd)
        listar_dispositivos(kind)

        chosen = _chosen_api.get(kind)
        orders: list[str | None] = ([chosen] if chosen is not None else [])
        orders.extend(api for api in _PREFERRED_APIS.get(platform.system(), ()) if api != chosen)
        orders.append(None)

        channel_key = "max_input_channels" if kind == "input" else "max_output_channels"
        for api_filter in orders:
            candidates: list[tuple[int, str]] = []
            for idx, dev in enumerate(devices):
                if int(dev.get(channel_key, 0) or 0) <= 0:
                    continue
                if api_filter is not None and api_filter not in _api_name(dev, apis):
                    continue
                dev_name = _normalizar_nome(dev.get("name"))
                if not dev_name or _is_pseudo(dev_name):
                    continue
                candidates.append((idx, dev_name))

            idx = _matching_candidate(wanted, candidates)
            if idx is not None and _usable(idx, kind, sd):
                return idx

        _LOGGER.warning(
            "Dispositivo %s salvo como '%s' sumiu ou não abre a %d Hz; usando padrão do sistema",
            kind,
            wanted,
            _RATES[kind],
        )
        return None
    except Exception as exc:
        _LOGGER.warning(
            "Não foi possível resolver o dispositivo %s '%s': %s; usando padrão do sistema",
            kind,
            wanted,
            exc,
        )
        return None


def estado_dispositivos() -> dict[str, str]:
    """Lê as escolhas atuais de entrada e saída para exibição.
    O retorno usa apenas nomes persistidos, sem expor índices voláteis do backend.
    O custo é uma leitura pequena de JSON local."""
    return _carregar_config()
