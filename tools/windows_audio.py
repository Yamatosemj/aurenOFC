from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from core.tool_result import ToolResult


_AUDIO_CLSID_MMDEVICE_ENUMERATOR = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"

_AUDIO_IID_MMDEVICE_ENUMERATOR = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"

_AUDIO_IID_ENDPOINT_VOLUME = "{5CDF2C82-841E-4546-9722-0CF74078229A}"

_AUDIO_CLSCTX_ALL = 0x17

_AUDIO_E_RENDER = 0

_AUDIO_E_CONSOLE = 0

_AUDIO_HRESULT_S_OK = 0x00000000

_AUDIO_HRESULT_S_FALSE = 0x00000001

_AUDIO_COM_RELEASE_INDEX = 2

_AUDIO_ENDPOINT_METHOD_SET_MASTER_VOLUME_SCALAR = 7

_AUDIO_ENDPOINT_METHOD_GET_MASTER_VOLUME_SCALAR = 9

_AUDIO_ENDPOINT_METHOD_SET_MUTE = 14

_AUDIO_ENDPOINT_METHOD_GET_MUTE = 15

def _audio_guid(texto):
    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", wintypes.BYTE * 8),
        ]

    guid = GUID()
    ole32 = ctypes.windll.ole32
    ole32.CLSIDFromString.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(GUID)]
    ole32.CLSIDFromString.restype = wintypes.LONG
    hr = ole32.CLSIDFromString(texto, ctypes.byref(guid))
    if hr != 0:
        raise OSError(f"CLSIDFromString falhou: HRESULT=0x{hr & 0xFFFFFFFF:08X}")
    return guid

def _audio_com_call(interface_ptr, index, restype, argtypes, *args):
    if not interface_ptr:
        raise OSError("Interface COM de audio invalida.")

    func_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
    vtable = ctypes.cast(
        interface_ptr,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
    ).contents
    func = func_type(
        restype,
        ctypes.c_void_p,
        *argtypes,
    )(vtable[index])
    return func(interface_ptr, *args)

def _audio_release(interface_ptr):
    if not interface_ptr:
        return
    try:
        _audio_com_call(
            interface_ptr,
            _AUDIO_COM_RELEASE_INDEX,
            ctypes.c_long,
            [],
        )
    except Exception:
        pass

class _AudioEndpointContext:
    def __enter__(self):
        if os.name != "nt":
            raise OSError("Controle de audio so esta disponivel no Windows.")

        self.ole32 = ctypes.windll.ole32
        self.ole32.CoInitialize.argtypes = [ctypes.c_void_p]
        self.ole32.CoInitialize.restype = ctypes.c_long
        self.ole32.CoUninitialize.argtypes = []
        self.ole32.CoUninitialize.restype = None
        self.ole32.CoCreateInstance.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.ole32.CoCreateInstance.restype = ctypes.c_long

        self.initialized_hr = int(self.ole32.CoInitialize(None))
        if self.initialized_hr not in (_AUDIO_HRESULT_S_OK, _AUDIO_HRESULT_S_FALSE):
            raise OSError(
                f"CoInitialize falhou: HRESULT=0x{self.initialized_hr & 0xFFFFFFFF:08X}"
            )

        self.enumerator = ctypes.c_void_p()
        clsid = _audio_guid(_AUDIO_CLSID_MMDEVICE_ENUMERATOR)
        iid_enumerator = _audio_guid(_AUDIO_IID_MMDEVICE_ENUMERATOR)
        hr = self.ole32.CoCreateInstance(
            ctypes.byref(clsid),
            None,
            _AUDIO_CLSCTX_ALL,
            ctypes.byref(iid_enumerator),
            ctypes.byref(self.enumerator),
        )
        if hr != 0:
            self.close()
            raise OSError(f"CoCreateInstance do enumerador falhou: HRESULT=0x{hr & 0xFFFFFFFF:08X}")

        self.device = ctypes.c_void_p()
        hr = _audio_com_call(
            self.enumerator,
            4,
            ctypes.c_long,
            [wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)],
            _AUDIO_E_RENDER,
            _AUDIO_E_CONSOLE,
            ctypes.byref(self.device),
        )
        if hr != 0:
            self.close()
            raise OSError(f"GetDefaultAudioEndpoint falhou: HRESULT=0x{hr & 0xFFFFFFFF:08X}")

        self.endpoint = ctypes.c_void_p()
        iid_endpoint = _audio_guid(_AUDIO_IID_ENDPOINT_VOLUME)
        hr = _audio_com_call(
            self.device,
            3,
            ctypes.c_long,
            [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
            ctypes.byref(iid_endpoint),
            _AUDIO_CLSCTX_ALL,
            None,
            ctypes.byref(self.endpoint),
        )
        if hr != 0:
            self.close()
            raise OSError(f"Ativacao do endpoint de audio falhou: HRESULT=0x{hr & 0xFFFFFFFF:08X}")

        return self.endpoint

    def close(self):
        _audio_release(getattr(self, "endpoint", None))
        _audio_release(getattr(self, "device", None))
        _audio_release(getattr(self, "enumerator", None))
        if getattr(self, "initialized_hr", None) in (_AUDIO_HRESULT_S_OK, _AUDIO_HRESULT_S_FALSE):
            try:
                self.ole32.CoUninitialize()
            except Exception:
                pass
        self.endpoint = None
        self.device = None
        self.enumerator = None
        self.initialized_hr = None

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

def _audio_hresult_ok(hr, operacao):
    if int(hr) != 0:
        raise OSError(f"{operacao} falhou: HRESULT=0x{int(hr) & 0xFFFFFFFF:08X}")

def obter_audio_windows() -> ToolResult:
    if os.name != "nt":
        return ToolResult.failure(
            "Controle de audio so esta disponivel no Windows.",
            error_code="windows_only",
            tool_name="obter_audio_windows",
        )

    try:
        volume = ctypes.c_float()
        mute = wintypes.BOOL()
        with _AudioEndpointContext() as endpoint:
            hr_volume = _audio_com_call(
                endpoint,
                _AUDIO_ENDPOINT_METHOD_GET_MASTER_VOLUME_SCALAR,
                ctypes.c_long,
                [ctypes.POINTER(ctypes.c_float)],
                ctypes.byref(volume),
            )
            _audio_hresult_ok(hr_volume, "Leitura do volume")
            hr_mute = _audio_com_call(
                endpoint,
                _AUDIO_ENDPOINT_METHOD_GET_MUTE,
                ctypes.c_long,
                [ctypes.POINTER(wintypes.BOOL)],
                ctypes.byref(mute),
            )
            _audio_hresult_ok(hr_mute, "Leitura do mudo")

        percentual = max(0, min(100, round(float(volume.value) * 100)))
        mudo = bool(mute.value)
        estado = "ativado" if mudo else "desativado"
        return ToolResult.success(
            f"Volume atual: {percentual}%. Mudo: {estado}.",
            data={"percentual": percentual, "mudo": mudo},
            tool_name="obter_audio_windows",
        )
    except Exception as erro:
        return ToolResult.failure(
            f"Nao consegui consultar o audio do Windows: {erro}",
            error_code="audio_read_failed",
            tool_name="obter_audio_windows",
        )


def _aplicar_volume_windows(percentual: int) -> ToolResult:
    """Aplica o volume sem registrar outra entrada de undo.
    Esse caminho e usado pelo setter publico e pelo callback de reversao.
    Custo: uma chamada COM ao endpoint de audio do Windows.
    """
    try:
        valor = ctypes.c_float(percentual / 100.0)
        with _AudioEndpointContext() as endpoint:
            hr = _audio_com_call(
                endpoint,
                _AUDIO_ENDPOINT_METHOD_SET_MASTER_VOLUME_SCALAR,
                ctypes.c_long,
                [ctypes.c_float, ctypes.c_void_p],
                valor,
                None,
            )
            _audio_hresult_ok(hr, "Definicao do volume")
        return ToolResult.success(
            f"Volume definido para {percentual}%.",
            tool_name="definir_volume_windows",
        )
    except Exception as erro:
        return ToolResult.failure(
            f"Nao consegui definir o volume: {erro}",
            error_code="volume_set_failed",
            tool_name="definir_volume_windows",
        )


def definir_volume_windows(percentual) -> ToolResult:
    if os.name != "nt":
        return ToolResult.failure(
            "Controle de audio so esta disponivel no Windows.",
            error_code="windows_only",
            tool_name="definir_volume_windows",
        )

    try:
        percentual = int(percentual)
    except (TypeError, ValueError):
        return ToolResult.failure(
            "Volume invalido. Informe uma porcentagem inteira de 0 a 100.",
            error_code="volume_invalid",
            tool_name="definir_volume_windows",
        )

    if not 0 <= percentual <= 100:
        return ToolResult.failure(
            "Volume invalido. Informe uma porcentagem inteira de 0 a 100.",
            error_code="volume_invalid",
            tool_name="definir_volume_windows",
        )

    leitura = obter_audio_windows()
    volume_anterior = None
    if leitura.ok and isinstance(leitura.data, dict):
        valor_anterior = leitura.data.get("percentual")
        if isinstance(valor_anterior, int) and not isinstance(valor_anterior, bool):
            if 0 <= valor_anterior <= 100:
                volume_anterior = valor_anterior

    resultado = _aplicar_volume_windows(percentual)
    if not resultado.ok:
        return ToolResult.failure(
            resultado.message,
            error_code=resultado.error_code or "volume_set_failed",
            data=resultado.data,
            tool_name="definir_volume_windows",
        )

    if volume_anterior is not None and volume_anterior != percentual:
        from core.undo import push_undo
        push_undo(
            f"volume para {percentual}%",
            lambda anterior=volume_anterior: _aplicar_volume_windows(anterior),
        )

    return ToolResult.success(
        resultado.message,
        data=resultado.data,
        tool_name="definir_volume_windows",
    )


def _aplicar_mudo_windows(ativado: bool) -> ToolResult:
    """Aplica o estado de mudo sem criar uma nova entrada de undo.
    Esse caminho e compartilhado pelo setter publico e pelo callback salvo.
    Custo: uma chamada COM ao endpoint de audio do Windows.
    """
    try:
        valor = wintypes.BOOL(1 if ativado else 0)
        with _AudioEndpointContext() as endpoint:
            hr = _audio_com_call(
                endpoint,
                _AUDIO_ENDPOINT_METHOD_SET_MUTE,
                ctypes.c_long,
                [wintypes.BOOL, ctypes.c_void_p],
                valor,
                None,
            )
            _audio_hresult_ok(hr, "Definicao do mudo")
        return ToolResult.success(
            f"Mudo {'ativado' if ativado else 'desativado'}.",
            tool_name="definir_mudo_windows",
        )
    except Exception as erro:
        return ToolResult.failure(
            f"Nao consegui alterar o mudo: {erro}",
            error_code="mute_set_failed",
            tool_name="definir_mudo_windows",
        )


def definir_mudo_windows(ativado) -> ToolResult:
    if os.name != "nt":
        return ToolResult.failure(
            "Controle de audio so esta disponivel no Windows.",
            error_code="windows_only",
            tool_name="definir_mudo_windows",
        )

    if not isinstance(ativado, bool):
        return ToolResult.failure(
            "O estado do mudo deve ser verdadeiro ou falso.",
            error_code="mute_state_invalid",
            tool_name="definir_mudo_windows",
        )

    leitura = obter_audio_windows()
    mudo_anterior = None
    if leitura.ok and isinstance(leitura.data, dict):
        valor_anterior = leitura.data.get("mudo")
        if isinstance(valor_anterior, bool):
            mudo_anterior = valor_anterior

    resultado = _aplicar_mudo_windows(ativado)
    if not resultado.ok:
        return ToolResult.failure(
            resultado.message,
            error_code=resultado.error_code or "mute_set_failed",
            data=resultado.data,
            tool_name="definir_mudo_windows",
        )

    if mudo_anterior is not None and mudo_anterior != ativado:
        from core.undo import push_undo
        push_undo(
            f"mudo {'ativado' if ativado else 'desativado'}",
            lambda anterior=mudo_anterior: _aplicar_mudo_windows(anterior),
        )

    return ToolResult.success(
        resultado.message,
        data=resultado.data,
        tool_name="definir_mudo_windows",
    )
