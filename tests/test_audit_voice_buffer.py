from voice.input import AudioCaptureConfig, PushToTalkRecorder


def test_aud008_callback_bounds_audio_even_while_hotkey_remains_pressed():
    recorder = PushToTalkRecorder(config=AudioCaptureConfig(max_seconds=1,
        pre_roll_seconds=0), sounddevice_module=object(), keyboard_module=object())
    recorder._preparar_buffer(100)
    recorder._registrar_inicio()
    for _ in range(100):
        recorder._callback([0.1] * 30, 30, None, None)
    frames = recorder._registrar_fim()
    assert sum(len(frame) for frame in frames) == 100


def test_aud008_preroll_is_included_in_recording_limit():
    recorder = PushToTalkRecorder(config=AudioCaptureConfig(max_seconds=1,
        pre_roll_seconds=2), sounddevice_module=object(), keyboard_module=object())
    recorder._preparar_buffer(100)
    recorder._callback([0.1] * 150, 150, None, None)
    recorder._registrar_inicio()
    recorder._callback([0.1] * 30, 30, None, None)
    assert sum(len(frame) for frame in recorder._registrar_fim()) == 100
