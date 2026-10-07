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
from voice.confirmation import VoiceConfirmationChannel  # noqa: E402
from voice.input import PushToTalkRecorder  # noqa: E402
from voice.speech_response import SpeechResponseFormatter  # noqa: E402
from voice.stt import LocalPortugueseASR  # noqa: E402
from voice.tts import LocalKokoroTTS  # noqa: E402
from core.harness import AurenHarness  # noqa: E402
from core.confirmation import TIMEOUT_SECONDS  # noqa: E402


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
    """Mantem o push-to-talk disponivel enquanto o chat textual esta aberto."""

    def _worker() -> None:
        while not stop_event.is_set():
            try:
                audio = recorder.capturar()
            except Exception as exc:
                fila.put(("erro", exc))
                return

            if stop_event.is_set():
                return

            # ESC faz o recorder devolver None; o loop principal decide encerrar.
            fila.put(("audio", audio))

    thread = Thread(target=_worker, name="auren-voice-input", daemon=True)
    thread.start()
    return thread


def _falar_interrompivel(
    tts: LocalKokoroTTS,
    recorder: PushToTalkRecorder,
    texto: str,
    texto_recebido_em: float | None = None,
) -> tuple[bool, bool, float | None, float]:
    """Fala em segundo plano e retorna estado, latência inicial e duração total do TTS."""
    cancel_event = Event()
    erro: list[BaseException] = []
    inicio_voz: list[float | None] = [None]

    def _marcar_inicio_voz() -> None:
        if inicio_voz[0] is None:
            inicio_voz[0] = time.perf_counter()

    def _worker() -> None:
        try:
            tts.falar(texto, cancel_event=cancel_event, on_audio_start=_marcar_inicio_voz)
        except BaseException as exc:  # propaga o erro no thread principal
            erro.append(exc)

    inicio_tts = time.perf_counter()
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
    tts_ms = max(0.0, (time.perf_counter() - inicio_tts) * 1000.0)

    if erro:
        exc = erro[0]
        if isinstance(exc, RuntimeError):
            raise exc
        raise RuntimeError(str(exc)) from exc

    latencia = None
    if texto_recebido_em is not None and inicio_voz[0] is not None:
        latencia = max(0.0, inicio_voz[0] - texto_recebido_em)
    return interrompido, sair, latencia, tts_ms


def _novo_harness(confirmation_channel: VoiceConfirmationChannel | None = None) -> AurenHarness:
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
    """Processa uma mensagem, mostra a resposta e fala a mesma resposta."""
    try:
        tratado, resposta = harness.processar_mensagem(mensagem)
    except Exception as exc:
        print(f"Auren: erro ao processar a tarefa: {exc}")
        try:
            tts.falar("Tive um problema ao executar essa tarefa.")
        except Exception:
            pass
        return False, None

    texto = resposta if tratado else getattr(resposta, "output_text", str(resposta))
    texto = str(texto or "").strip()
    snapshot = harness.current_task()
    # Fast path/local completion pode ser enriquecido pela formatacao
    # especifica de ferramenta; respostas finais do modelo ficam com
    # o texto natural do proprio modelo, apenas limpo/encurtado.
    fala = SpeechResponseFormatter.formatar(
        objetivo=mensagem,
        texto=texto,
        snapshot=snapshot if tratado or snapshot and snapshot.steps else None,
    )

    print(f"Auren: {fala}")
    try:
        interrompido, sair, latencia, tts_ms = _falar_interrompivel(
            tts,
            recorder,
            fala,
            texto_recebido_em,
        )
    except RuntimeError as exc:
        print(f"Auren voz: TTS indisponível: {exc}")
        interrompido, sair, latencia, tts_ms = False, False, None, 0.0

    harness.registrar_etapa_voz("tts", tts_ms)
    if latencia is not None:
        print(f"Latência texto → voz: {latencia:.3f}s")

    if sair:
        print("Auren: Até mais.")
        return True, latencia

    if interrompido:
        # F8 tambem serve como barge-in: interrompe a fala do Auren
        # e deixa o usuario continuar falando sem precisar esperar o TTS.
        print("Auren voz: fala interrompida.")

    auren.mostrar_uso()
    return False, latencia


def main() -> int:
    recorder = PushToTalkRecorder(hotkey="f8")
    stt = LocalPortugueseASR()
    tts = LocalKokoroTTS()
    fila_texto: Queue = Queue()
    fila_audio: Queue = Queue()
    stop_event = Event()
    confirmation_channel = VoiceConfirmationChannel(
        tts=tts,
        stt=stt,
        audio_queue=fila_audio,
        timeout=TIMEOUT_SECONDS,
    )
    harness = _novo_harness(confirmation_channel)

    print("Auren Voice Engine V3 online.")
    print("F8 = segurar para falar | ESC = encerrar")
    print("Texto = digite a mensagem e pressione Enter")
    print("ASR: Parakeet TDT 0.6B pt-BR TAGARELA (ONNX INT8 local)")
    print("TTS: Kokoro ONNX local")
    print("O primeiro uso baixa os modelos e os deixa em cache local.")
    _iniciar_leitor_texto(fila_texto, stop_event)
    _iniciar_captura_de_voz(recorder, fila_audio, stop_event)

    try:
        while True:
            if recorder.pediu_saida():
                print("Auren: Até mais.")
                return 0

            # Primeiro verificamos texto para deixar o modo silencioso responsivo.
            try:
                entrada_texto = fila_texto.get_nowait()
            except Empty:
                entrada_texto = None

            if entrada_texto is not None:
                if entrada_texto is _INPUT_EOF:
                    print("Auren: Até mais.")
                    return 0

                if isinstance(entrada_texto, tuple) and entrada_texto:
                    tipo, valor = entrada_texto[0], entrada_texto[1] if len(entrada_texto) > 1 else None
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

            # Depois verificamos o resultado do push-to-talk.
            try:
                tipo_audio, audio = fila_audio.get(timeout=0.05)
            except Empty:
                continue

            if tipo_audio == "erro":
                print(f"Auren voz: {audio}")
                return 2

            if recorder.pediu_saida():
                print("Auren: Até mais.")
                return 0

            if audio is None:
                continue

            texto_recebido_em = time.perf_counter()
            inicio_asr = texto_recebido_em
            try:
                mensagem = stt.transcrever(audio)
            except RuntimeError as exc:
                harness.registrar_etapa_voz("asr", (time.perf_counter() - inicio_asr) * 1000.0)
                print(f"Auren voz: {exc}")
                return 3
            else:
                harness.registrar_etapa_voz("asr", (time.perf_counter() - inicio_asr) * 1000.0)

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
