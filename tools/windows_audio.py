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

def obter_audio_windows():
    if os.name != "nt":
        return "Controle de audio so esta disponivel no Windows."

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
        estado = "ativado" if bool(mute.value) else "desativado"
        return f"Volume atual: {percentual}%. Mudo: {estado}."
    except Exception as erro:
        return f"Nao consegui consultar o audio do Windows: {erro}"

def definir_volume_windows(percentual):
    if os.name != "nt":
        return "Controle de audio so esta disponivel no Windows."

    try:
        percentual = int(percentual)
    except (TypeError, ValueError):
        return ToolResult.failure(
            "Volume invalido. Informe uma porcentagem inteira de 0 a 100.",
            error_code="volume_invalid",
        )

    if not 0 <= percentual <= 100:
        return ToolResult.failure(
            "Volume invalido. Informe uma porcentagem inteira de 0 a 100.",
            error_code="volume_invalid",
        )

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
        return f"Volume definido para {percentual}%."
    except Exception as erro:
        return f"Nao consegui definir o volume: {erro}"

def definir_mudo_windows(ativado):
    if os.name != "nt":
        return "Controle de audio so esta disponivel no Windows."

    if not isinstance(ativado, bool):
        return ToolResult.failure(
            "O estado do mudo deve ser verdadeiro ou falso.",
            error_code="mute_state_invalid",
        )

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
        return f"Mudo {'ativado' if ativado else 'desativado'}."
    except Exception as erro:
        return f"Nao consegui alterar o mudo: {erro}"

