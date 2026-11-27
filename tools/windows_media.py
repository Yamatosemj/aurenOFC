"""Pausa verificavel de uma unica sessao GSMTC do Windows.

O modulo e importavel fora do Windows: PyWinRT so e carregado ao executar a
ferramenta. Nao ha fallback para teclas globais.
"""

from __future__ import annotations

import asyncio
import os
import time

from core.tool_result import ToolResult


# Valores da enum GlobalSystemMediaTransportControlsSessionPlaybackStatus.
_PLAYING = 4
_PAUSED = 5
_CHANGING = 2
_REQUEST_TIMEOUT_SECONDS = 2.0
_VERIFY_TIMEOUT_SECONDS = 0.75
_VERIFY_INTERVAL_SECONDS = 0.05
_TOOL = "controle_midia_windows"


def _is_windows() -> bool:
    return os.name == "nt"


def _result_failure(message: str, code: str, **data: object) -> ToolResult:
    return ToolResult.failure(message, error_code=code, data={"estado": "falha", **data}, tool_name=_TOOL)


def _result_unknown(message: str, **data: object) -> ToolResult:
    return ToolResult.failure(
        message,
        error_code="media_state_unknown",
        data={"estado": "desconhecido", **data},
        tool_name=_TOOL,
    )


def _status(session: object) -> int:
    return int(session.get_playback_info().playback_status)


def _status_label(state: int | None) -> str:
    return {_PLAYING: "reproduzindo", _PAUSED: "pausada", _CHANGING: "em_transicao"}.get(state, "desconhecido")


async def _pause_with_manager(manager: object) -> ToolResult:
    """Seleciona uma instancia inequivoca; usa somente TryPauseAsync nela."""
    try:
        sessions = tuple(manager.get_sessions())
    except Exception:
        return _result_unknown("Nao foi possivel consultar as sessoes de midia.", etapa="listar_sessoes")

    if not sessions:
        return _result_failure("Nenhuma sessao de midia disponivel.", "media_session_absent")

    playing = []
    paused = []
    changing = False
    try:
        for session in sessions:
            state = _status(session)
            if state == _PLAYING:
                playing.append(session)
            elif state == _PAUSED:
                paused.append(session)
            elif state == _CHANGING or state not in {0, 1, 3}:
                changing = True
    except Exception:
        return _result_unknown("Nao foi possivel consultar o estado de todas as sessoes.", etapa="estado_inicial")

    if len(playing) > 1:
        return _result_failure("Mais de uma sessao esta reproduzindo; destino ambiguo.", "media_session_ambiguous")
    if changing:
        return _result_unknown("Ha sessao com estado de reproducao desconhecido ou em transicao.", etapa="selecao")
    if not playing:
        if len(paused) > 1:
            return _result_failure("Mais de uma sessao esta pausada; destino ambiguo.", "media_session_ambiguous")
        if len(paused) == 1:
            return ToolResult.success(
                "A midia ja estava pausada.",
                data={"estado": "ja_pausada", "antes": "pausada", "depois": "pausada", "comando_enviado": False},
                tool_name=_TOOL,
            )
        return _result_failure("Nenhuma sessao esta reproduzindo ou pausada.", "media_not_playing")

    session = playing[0]
    try:
        info = session.get_playback_info()
        before = int(info.playback_status)
        if before == _PAUSED:
            return ToolResult.success(
                "A midia ja estava pausada.",
                data={"estado": "ja_pausada", "antes": "pausada", "depois": "pausada", "comando_enviado": False},
                tool_name=_TOOL,
            )
        if before != _PLAYING:
            return _result_unknown("O estado da sessao mudou antes da pausa.", antes="reproduzindo", depois="desconhecido", comando_enviado=False)
        if not info.controls.is_pause_enabled:
            return _result_failure("A sessao nao oferece pausa explicita.", "media_pause_unavailable", antes="reproduzindo", comando_enviado=False)
        app_id = str(session.source_app_user_model_id or "")
    except Exception:
        return _result_unknown("Nao foi possivel verificar a sessao antes da pausa.", antes="reproduzindo", comando_enviado=False)

    try:
        accepted = await asyncio.wait_for(session.try_pause_async(), timeout=_REQUEST_TIMEOUT_SECONDS)
    except Exception:
        try:
            after = _status(session)
        except Exception:
            after = None
        return _result_unknown("A requisicao de pausa terminou sem resultado confiavel.", antes="reproduzindo", depois=_status_label(after), comando_enviado=True, aplicativo=app_id)
    if not accepted:
        try:
            after = _status(session)
        except Exception:
            return _result_unknown("A sessao recusou a pausa e o estado posterior nao esta disponivel.", antes="reproduzindo", comando_enviado=True, aplicativo=app_id)
        if after != _PLAYING:
            return _result_unknown("A sessao recusou a pausa, mas o estado mudou.", antes="reproduzindo", depois=_status_label(after), comando_enviado=True, aplicativo=app_id)
        return _result_failure("A sessao recusou a pausa.", "media_pause_rejected", antes="reproduzindo", depois="reproduzindo", comando_enviado=True, aplicativo=app_id)

    deadline = time.monotonic() + _VERIFY_TIMEOUT_SECONDS
    while True:
        try:
            after = _status(session)
        except Exception:
            return _result_unknown("Nao foi possivel verificar o estado apos a pausa.", antes="reproduzindo", comando_enviado=True, aplicativo=app_id)
        if after == _PAUSED:
            return ToolResult.success(
                "Pausa confirmada pelo estado da sessao de midia.",
                data={"estado": "pausa_confirmada", "antes": "reproduzindo", "depois": "pausada", "comando_enviado": True, "aplicativo": app_id},
                tool_name=_TOOL,
            )
        if after not in {_PLAYING, _CHANGING}:
            return _result_unknown("A sessao mudou para outro estado apos o pedido de pausa.", antes="reproduzindo", depois="desconhecido", comando_enviado=True, aplicativo=app_id)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return _result_unknown("A pausa foi aceita, mas o estado pausado nao foi confirmado.", antes="reproduzindo", depois="reproduzindo" if after == _PLAYING else "em_transicao", comando_enviado=True, aplicativo=app_id)
        await asyncio.sleep(min(_VERIFY_INTERVAL_SECONDS, remaining))


async def _pause() -> ToolResult:
    try:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
    except ImportError:
        return _result_failure("API GSMTC indisponivel neste ambiente.", "media_backend_unavailable")
    try:
        manager = await asyncio.wait_for(
            GlobalSystemMediaTransportControlsSessionManager.request_async(),
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    except Exception:
        return _result_failure("Nao foi possivel obter o gerenciador de sessoes de midia.", "media_backend_unavailable")
    return await _pause_with_manager(manager)


def pausar_midia_windows() -> ToolResult:
    if not _is_windows():
        return _result_failure("Pausa GSMTC disponivel somente no Windows.", "media_platform_unsupported")
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        return _result_unknown("Nao foi possivel iniciar a consulta de midia neste contexto.", comando_enviado=False)
    try:
        return asyncio.run(_pause())
    except Exception:
        return _result_unknown("A consulta de midia terminou sem resultado confiavel.", comando_enviado=None)
