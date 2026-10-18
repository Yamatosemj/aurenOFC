from queue import Queue
from threading import Event
from types import SimpleNamespace

from core.harness import AurenHarness
from agent.ari_native.task_queue import AgentTaskQueue
from voice.input import PushToTalkRecorder
from voice import main as voice_main


def test_aud024_voice_exit_closes_harness_and_bounds_queues(monkeypatch):
    queues = []
    closed = []

    def queue_factory(*args, **kwargs):
        queue = Queue(*args, **kwargs)
        queues.append(queue)
        return queue

    monkeypatch.setattr(voice_main, 'Queue', queue_factory)
    monkeypatch.setattr(voice_main, 'PushToTalkRecorder', lambda **kwargs: SimpleNamespace(
        pediu_saida=lambda: True, definir_saida_ativa=lambda active: None,
        solicitar_parada=lambda: closed.append('recorder')))
    monkeypatch.setattr(voice_main, 'LocalPortugueseASR', lambda: object())
    monkeypatch.setattr(voice_main, 'LocalKokoroTTS', lambda: object())
    monkeypatch.setattr(voice_main, '_novo_harness', lambda channel: SimpleNamespace(
        shutdown=lambda **kwargs: closed.append('harness')))
    monkeypatch.setattr(voice_main, '_iniciar_leitor_texto', lambda *args: None)
    monkeypatch.setattr(voice_main, '_iniciar_captura_de_voz', lambda *args: None)
    monkeypatch.setattr(voice_main, '_iniciar_precarregamento_stt', lambda *args: None)
    monkeypatch.setattr(voice_main.auren, 'fechar_navegador', lambda: closed.append('browser'))
    assert voice_main.main() == 0
    assert 'harness' in closed
    assert 'recorder' in closed
    assert all(queue.maxsize > 0 for queue in queues)


def test_aud024_interrupted_tts_has_bounded_join(monkeypatch):
    joined = []

    class Thread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            pass

        def is_alive(self):
            return True

        def join(self, timeout=None):
            assert timeout is not None and 0 <= timeout <= 2
            joined.append(timeout)

    monkeypatch.setattr(voice_main, 'Thread', Thread)
    recorder = SimpleNamespace(pediu_saida=lambda: True, hotkey_pressionada=lambda: False,
        definir_saida_ativa=lambda active: None, limpar_pre_roll=lambda: None)
    _, exit_requested, _ = voice_main._falar_interrompivel(object(), recorder, 'teste')
    assert exit_requested and joined


def test_aud024_shutdown_ends_session_even_when_resource_close_fails():
    events = []
    harness = AurenHarness.__new__(AurenHarness)
    harness.cancel_current_task = lambda: events.append('cancel')
    harness._background_queue = SimpleNamespace(shutdown=lambda **kwargs: events.append('queue') or 'stopped')
    harness.fechar = lambda: (_ for _ in ()).throw(RuntimeError('fake close error'))
    harness._encerrar_sessao_chat = lambda state: events.append(state)
    try:
        harness.shutdown(timeout=0.01)
    except RuntimeError:
        pass
    assert events == ['cancel', 'queue', 'closed']


def test_aud024_full_audio_queue_preserves_queued_confirmation_data():
    queue = Queue(maxsize=2)
    queue.put(('audio', 'first fictional clip'))
    queue.put(('audio', 'second fictional clip'))
    voice_main._enfileirar_audio(queue, ('audio', 'overflow fictional clip'))
    assert queue.qsize() == 2
    assert queue.get_nowait() == ('audio', 'first fictional clip')


def test_aud024_shutdown_signals_capture_without_loading_hardware():
    recorder = PushToTalkRecorder(sounddevice_module=object(), keyboard_module=object())
    recorder.solicitar_parada()
    assert recorder.pediu_saida()


def test_aud024_blocked_memory_writer_has_observable_shutdown_timeout():
    started, release = Event(), Event()
    queue = AgentTaskQueue()
    def writer(cancel):
        started.set()
        release.wait(2)
    queue.submit('fictional memory', writer)
    assert started.wait(1)
    harness = AurenHarness.__new__(AurenHarness)
    harness.cancel_current_task = lambda: None
    harness._background_queue = queue
    harness.fechar = lambda: None
    ended = []
    harness._encerrar_sessao_chat = ended.append
    try:
        assert harness.shutdown(timeout=0.01) == 'timed_out'
        assert ended == ['closed']
    finally:
        release.set()
        assert queue.shutdown(cancel_pending=False, timeout=1) == 'stopped'
