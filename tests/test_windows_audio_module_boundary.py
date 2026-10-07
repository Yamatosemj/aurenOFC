import tools.windows as windows
import tools.windows_audio as windows_audio


def test_windows_audio_controls_live_in_dedicated_module():
    assert windows.obter_audio_windows is windows_audio.obter_audio_windows
    assert windows.definir_volume_windows is windows_audio.definir_volume_windows
    assert windows.definir_mudo_windows is windows_audio.definir_mudo_windows
    assert windows.obter_audio_windows.__module__ == "tools.windows_audio"
    assert windows.definir_volume_windows.__module__ == "tools.windows_audio"
    assert windows.definir_mudo_windows.__module__ == "tools.windows_audio"


def test_windows_module_no_longer_owns_audio_endpoint_context():
    assert not hasattr(windows, "_AudioEndpointContext")
    assert hasattr(windows_audio, "_AudioEndpointContext")
