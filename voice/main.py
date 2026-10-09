from __future__ import annotations

import sys
import time
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import auren  # noqa: E402
from core.harness import AurenHarness  # noqa: E402
from voice.confirmation import VoiceConfirmationChannel  # noqa: E402
from voice.input import PushToTalkRecorder  # noqa: E402
from voice.speech_response import SpeechResponseFormatter  # noqa: E402
from voice.stt import LocalPortugueseASR  # noqa: E402
from voice.tts import LocalKokoroTTS  # noqa: E402


_INPUT_EOF = object()


def _iniciar_leitor_texto(fila: Queue, stop_event: Event) -> Thread:
    """Mantem uma entrada textual paralela ao push-to-talk.

    O texto entra na mesma fila de processamento usada pela voz, portanto nao
    existe um segundo "chat" nem um segundo fluxo de raciocinio.
    """

    def _worker() -> None:
        while not stop_event.is_set():
            try:
                mensagem = input("Voce (texto): ")
            except EOFError:
                fila.put(_INPUT_EOF)
                return
            except Exception as exc:
                fila.put(("erro", exc))
                return

            fila.put(("texto", mensagem))

    thread = Thread(target=_worker, name="auren-text-input", daemon=True)
    thread.start()
    return thread


def _iniciar_captura_de_voz(
    recorder: PushToTalkRecorder,
    fila: Queue,
    stop_event: Event,
) -> Thread:
    """Mantem o PTT disponivel e recupera erros de captura sem derrubar o processo."""

    def _worker() -> None:
        while not stop_event.is_set():
            try:
                audio = recorder.capturar()
            except Exception as exc:
                print(f"Auren voz: captura indisponivel: {exc}")
                fila.put(("erro_captura", exc))
                stop_event.wait(1.0)
                continue

            if stop_event.is_set():
                return

            fila.put(("audio", audio))

    thread = Thread(target=_worker, name="auren-voice-input", daemon=True)
    thread.start()
    return thread

def _iniciar_precarregamento_stt(stt: LocalPortugueseASR, stop_event: Event) -> Thread:
    """Carrega o ASR fora do loop principal para reduzir a latencia da primeira fala."""

    def _worker() -> None:
        try:
            stt.precarregar()
            if not stop_event.is_set():
                print("Auren voz: ASR local pronto.")
        except Exception as exc:
            if not stop_event.is_set():
                print(f"Auren voz: nao foi possivel aquecer o ASR agora: {exc}")

    thread = Thread(target=_worker, name="auren-stt-warmup", daemon=True)
    thread.start()
    return thread

def _falar_interrompivel(
    tts: LocalKokoroTTS,
    recorder: PushToTalkRecorder,
    texto: str,
    texto_recebido_em: float | None = None,
) -> tuple[bool, bool, float | None]:
    """Fala em segundo plano para permitir ESC ou Ctrl direito + Shift direito interromper a fala."""

    cancel_event = Event()
    erro: list[BaseException] = []
    inicio_voz: list[float | None] = [None]

    def _marcar_inicio_voz() -> None:
        if inicio_voz[0] is None:
            inicio_voz[0] = time.perf_counter()

    def _worker() -> None:
        try:
            tts.falar(
                texto,
                cancel_event=cancel_event,
                on_audio_start=_marcar_inicio_voz,
            )
        except BaseException as exc:
            erro.append(exc)

    # Enquanto o TTS fala, nao deixamos a janela de pre-roll acumular a propria
    # voz. Isso evita que a proxima fala comece contaminada sem implementar
    # Echo Guard nesta tarefa.
    recorder.definir_saida_ativa(True)
    try:
        thread = Thread(target=_worker, name="auren-tts", daemon=True)
        thread.start()

        interrompido = False
        sair = False
        while thread.is_alive():
            if recorder.pediu_saida():
                sair = True
                cancel_event.set()
                break
            if recorder.hotkey_pressionada():
                interrompido = True
                cancel_event.set()
                break
            time.sleep(0.02)

        thread.join()
    finally:
        recorder.definir_saida_ativa(False)
        recorder.limpar_pre_roll()

    if erro:
        exc = erro[0]
        if isinstance(exc, RuntimeError):
            raise exc
        raise RuntimeError(str(exc)) from exc

    latencia = None
    if texto_recebido_em is not None and inicio_voz[0] is not None:
        latencia = max(0.0, inicio_voz[0] - texto_recebido_em)
    return interrompido, sair, latencia


def _novo_harness(
    confirmation_channel: VoiceConfirmationChannel | None = None,
) -> AurenHarness:
    # Mesma montagem do texto: mesmo Session/Context, memoria, metricas e callbacks.
    if confirmation_channel is None:
        return auren.criar_harness()
    return auren.criar_harness(confirmation_channel=confirmation_channel)


def _processar_e_falar(
    *,
    harness: AurenHarness,
    tts: LocalKokoroTTS,
    recorder: PushToTalkRecorder,
    mensagem: str,
    texto_recebido_em: float | None,
) -> tuple[bool, float | None]:
    """Processa uma mensagem e fala a mesma resposta pelo canal de voz."""

    try:
        tratado, resposta = harness.processar_mensagem(mensagem)
    except Exception as exc:
        print(f"Auren: erro ao processar a tarefa: {exc}")
        try:
            recorder.definir_saida_ativa(True)
            tts.falar("Tive um problema ao executar essa tarefa.")
        except Exception:
            pass
        finally:
            recorder.definir_saida_ativa(False)
            recorder.limpar_pre_roll()
        return False, None

    texto = resposta if tratado else getattr(resposta, "output_text", str(resposta))
    texto = str(texto or "").strip()
    snapshot = harness.current_task()
    fala = SpeechResponseFormatter.formatar(
        objetivo=mensagem,
        texto=texto,
        snapshot=snapshot if tratado or snapshot and snapshot.steps else None,
    )

    print(f"Auren: {fala}")
    try:
        interrompido, sair, latencia = _falar_interrompivel(
            tts,
            recorder,
            fala,
            texto_recebido_em,
        )
    except RuntimeError as exc:
        print(f"Auren voz: TTS indisponível: {exc}")
        interrompido, sair, latencia = False, False, None

    if latencia is not None:
        print(f"Latência texto → voz: {latencia:.3f}s")

    if sair:
        print("Auren: Até mais.")
        return True, latencia

    if interrompido:
        print("Auren voz: fala interrompida.")

    auren.mostrar_uso()
    return False, latencia


def main() -> int:
    recorder = PushToTalkRecorder(hotkey="right ctrl+right shift")
    stt = LocalPortugueseASR()
    tts = LocalKokoroTTS()
    fila_texto: Queue = Queue()
    fila_audio: Queue = Queue()
    stop_event = Event()
    confirmation_channel = VoiceConfirmationChannel(
        tts=tts,
        stt=stt,
        audio_queue=fila_audio,
        timeout=8.0,
        set_output_active=recorder.definir_saida_ativa,
    )
    harness = _novo_harness(confirmation_channel)

    print("Auren Voice Engine V4 online.")
    print("CTRL DIREITO + SHIFT DIREITO = segurar para falar | ESC = encerrar")
    print("Texto = digite a mensagem e pressione Enter")
    print("ASR: Parakeet TDT 0.6B pt-BR TAGARELA (ONNX INT8 local, entrada 16 kHz)")
    print("Captura: pre-roll + pos-roll + WebRTC VAD local (fallback por energia)")
    print("TTS: Kokoro ONNX local")
    print("O primeiro uso baixa os modelos e os deixa em cache local.")
    _iniciar_precarregamento_stt(stt, stop_event)
    _iniciar_leitor_texto(fila_texto, stop_event)
    _iniciar_captura_de_voz(recorder, fila_audio, stop_event)

    try:
        while True:
            if recorder.pediu_saida():
                print("Auren: Até mais.")
                return 0

            try:
                entrada_texto = fila_texto.get_nowait()
            except Empty:
                entrada_texto = None

            if entrada_texto is not None:
                if entrada_texto is _INPUT_EOF:
                    print("Auren: Até mais.")
                    return 0

                if isinstance(entrada_texto, tuple) and entrada_texto:
                    tipo, valor = (
                        entrada_texto[0],
                        entrada_texto[1] if len(entrada_texto) > 1 else None,
                    )
                else:
                    tipo, valor = "texto", entrada_texto

                if tipo == "erro":
                    print(f"Auren texto: falha na entrada de texto: {valor}")
                    return 4

                mensagem = str(valor or "").strip()
                if mensagem:
                    print(f"Você: {mensagem}")
                    if mensagem.lower() in {"sair", "encerrar", "fechar o auren"}:
                        print("Auren: Até mais.")
                        return 0

                    deve_sair, _ = _processar_e_falar(
                        harness=harness,
                        tts=tts,
                        recorder=recorder,
                        mensagem=mensagem,
                        texto_recebido_em=time.perf_counter(),
                    )
                    if deve_sair:
                        return 0
                continue

            try:
                tipo_audio, audio = fila_audio.get(timeout=0.05)
            except Empty:
                continue

            if tipo_audio == "erro_captura":
                print("Auren voz: a captura sera tentada novamente.")
                continue

            if recorder.pediu_saida():
                print("Auren: Até mais.")
                return 0

            if audio is None:
                continue

            try:
                inicio_stt = time.perf_counter()
                mensagem = stt.transcrever(audio)
                texto_recebido_em = time.perf_counter()
                print(f"Latência ASR: {texto_recebido_em - inicio_stt:.3f}s")
            except RuntimeError as exc:
                print(f"Auren voz: STT indisponível nesta tentativa: {exc}")
                continue
            except Exception as exc:
                print(f"Auren voz: erro inesperado no STT: {exc}")
                continue

            mensagem = mensagem.strip()
            if not mensagem:
                print("Auren voz: não entendi o áudio.")
                continue

            print(f"Você: {mensagem}")
            if mensagem.lower() in {"sair", "encerrar", "fechar o auren"}:
                print("Auren: Até mais.")
                return 0

            deve_sair, _ = _processar_e_falar(
                harness=harness,
                tts=tts,
                recorder=recorder,
                mensagem=mensagem,
                texto_recebido_em=texto_recebido_em,
            )
            if deve_sair:
                return 0

    except KeyboardInterrupt:
        print("\nAuren: Até mais.")
        return 0
    finally:
        stop_event.set()
        try:
            auren.fechar_navegador()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
