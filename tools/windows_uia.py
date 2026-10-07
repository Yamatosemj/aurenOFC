from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from queue import Empty, Queue

from tools.windows_window import _encontrar_janela_windows, _user32

_UI_AUTOMATION_WORKER_SCRIPT = Path(__file__).with_name("windows_uia_worker.ps1")
_UI_AUTOMATION_WORKER = None
_UI_AUTOMATION_WORKER_RESPONSES = None
_UI_AUTOMATION_WORKER_READER = None
_UI_AUTOMATION_WORKER_LOCK = threading.RLock()




def _ui_automation_hwnd_int(hwnd):
    """Converte HWND para inteiro de forma segura em diferentes versoes do ctypes."""
    valor = getattr(hwnd, "value", hwnd)
    try:
        return int(valor or 0)
    except (TypeError, ValueError):
        return 0

def _ui_automation_janela(alvo):
    """Resolve a janela alvo e retorna (hwnd, titulo, erro)."""
    if os.name != "nt":
        return None, None, "Automacao de interface do Windows so esta disponivel no Windows."
    user32 = _user32()
    if user32 is None:
        return None, None, "Nao consegui acessar a API de janelas do Windows."
    pedido = str(alvo or "").strip()
    if pedido:
        encontrado = _encontrar_janela_windows(pedido)
        if not encontrado:
            return None, None, f"Nao encontrei uma janela correspondente a '{pedido}'."
        return encontrado[0], encontrado[1], None
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None, None, "Nao encontrei uma janela em primeiro plano."
    tamanho = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(max(1, tamanho + 1))
    user32.GetWindowTextW(hwnd, buffer, max(1, tamanho + 1))
    titulo = buffer.value.strip() or f"HWND {_ui_automation_hwnd_int(hwnd)}"
    return hwnd, titulo, None

def _encerrar_ui_automation_worker() -> None:
    global _UI_AUTOMATION_WORKER
    global _UI_AUTOMATION_WORKER_RESPONSES
    global _UI_AUTOMATION_WORKER_READER

    processo = _UI_AUTOMATION_WORKER
    _UI_AUTOMATION_WORKER = None
    _UI_AUTOMATION_WORKER_RESPONSES = None
    _UI_AUTOMATION_WORKER_READER = None

    if processo is None:
        return

    try:
        if processo.stdin is not None:
            processo.stdin.close()
    except Exception:
        pass

    try:
        processo.terminate()
        processo.wait(timeout=2)
    except Exception:
        try:
            processo.kill()
        except Exception:
            pass


def _iniciar_ui_automation_worker():
    global _UI_AUTOMATION_WORKER
    global _UI_AUTOMATION_WORKER_RESPONSES
    global _UI_AUTOMATION_WORKER_READER

    if _UI_AUTOMATION_WORKER is not None and _UI_AUTOMATION_WORKER.poll() is None:
        return _UI_AUTOMATION_WORKER, _UI_AUTOMATION_WORKER_RESPONSES

    if not _UI_AUTOMATION_WORKER_SCRIPT.is_file():
        return None, None

    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        return None, None

    respostas: Queue[dict] = Queue()
    try:
        processo = subprocess.Popen(
            [
                powershell,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-STA",
                "-File",
                str(_UI_AUTOMATION_WORKER_SCRIPT),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except Exception:
        return None, None

    if processo.stdin is None or processo.stdout is None:
        try:
            processo.terminate()
        except Exception:
            pass
        return None, None

    def _reader() -> None:
        try:
            for linha in processo.stdout:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    objeto = json.loads(linha)
                except json.JSONDecodeError:
                    continue
                if isinstance(objeto, dict):
                    respostas.put(objeto)
        finally:
            respostas.put({"__worker_encerrou__": True})

    leitor = threading.Thread(
        target=_reader,
        name="auren-uia-worker-reader",
        daemon=True,
    )
    leitor.start()

    _UI_AUTOMATION_WORKER = processo
    _UI_AUTOMATION_WORKER_RESPONSES = respostas
    _UI_AUTOMATION_WORKER_READER = leitor
    return processo, respostas


def _executar_ui_automation(operacao, dados):
    """Executa UIA em worker persistente via stdin/stdout, sem temp files ou bypass."""
    if os.name != "nt":
        return {
            "ok": False,
            "erro": "Automacao de interface do Windows so esta disponivel no Windows.",
        }

    payload = {"operacao": operacao, **(dados or {})}

    with _UI_AUTOMATION_WORKER_LOCK:
        processo, respostas = _iniciar_ui_automation_worker()
        if processo is None or respostas is None:
            return {"ok": False, "erro": "Nao consegui iniciar o worker de UI Automation."}

        try:
            mensagem = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            processo.stdin.write(mensagem + "\n")
            processo.stdin.flush()

            limite = time.monotonic() + 20.0
            while True:
                restante = limite - time.monotonic()
                if restante <= 0:
                    raise TimeoutError(
                        "A operacao de UI Automation excedeu o limite de 20 segundos."
                    )

                try:
                    resultado = respostas.get(timeout=min(0.5, restante))
                except Empty:
                    if processo.poll() is not None:
                        raise RuntimeError(
                            "O worker de UI Automation encerrou inesperadamente."
                        )
                    continue

                if resultado.get("__worker_encerrou__"):
                    raise RuntimeError(
                        "O worker de UI Automation encerrou inesperadamente."
                    )

                if isinstance(resultado, dict):
                    return resultado

        except (BrokenPipeError, OSError, RuntimeError, TimeoutError) as erro:
            _encerrar_ui_automation_worker()
            return {"ok": False, "erro": str(erro)}


def inspecionar_interface_windows(alvo_janela="", foco="", max_itens=40):
    """Inspeciona controles visiveis da janela usando UI Automation."""
    hwnd, titulo, erro = _ui_automation_janela(alvo_janela)
    if erro:
        return erro
    try:
        max_itens = max(1, min(80, int(max_itens)))
    except (TypeError, ValueError):
        return "Quantidade maxima de itens invalida."
    resultado = _executar_ui_automation("inspecionar", {"hwnd": _ui_automation_hwnd_int(hwnd), "foco": str(foco or ""), "max_itens": max_itens})
    if not resultado.get("ok"):
        return f"Nao consegui inspecionar a interface de '{titulo}': {resultado.get('erro', 'erro desconhecido')}"
    controles = resultado.get("controles") or []
    linhas = [
        f"Janela: {titulo}",
        f"Controles encontrados na arvore: {resultado.get('total', 0)}",
        f"Controles exibidos: {len(controles)}",
    ]
    for controle in controles:
        nome = controle.get("nome") or "[sem nome]"
        tipo = controle.get("tipo") or "[sem tipo]"
        automation_id = controle.get("automation_id") or "[sem AutomationId]"
        padroes = ", ".join(controle.get("padroes") or []) or "nenhum"
        linha = f"{controle.get('indice','?')}. {nome} | tipo={tipo} | id={automation_id} | habilitado={controle.get('habilitado')} | protegido={controle.get('protegido')} | padroes={padroes}"
        if controle.get("estado"):
            linha += f" | estado={controle['estado']}"
        if controle.get("texto"):
            linha += f" | texto={str(controle['texto'])[:240]}"
        linhas.append(linha)
    if foco and not controles:
        linhas.append(f"Nenhum controle correspondeu a '{foco}'.")
    return "\n".join(linhas)

def _executar_acao_ui_windows(operacao, alvo_janela, alvo, indice, texto=None, permitir_protegido=False):
    hwnd, titulo, erro = _ui_automation_janela(alvo_janela)
    if erro:
        return erro
    try:
        indice = int(indice)
        if indice < 1:
            return "O indice do elemento deve comecar em 1."
    except (TypeError, ValueError):
        return "Indice de elemento invalido."
    dados = {"hwnd": _ui_automation_hwnd_int(hwnd), "alvo": str(alvo or ""), "indice": indice}
    if texto is not None:
        dados["texto"] = str(texto)
    if operacao == "preencher":
        dados["permitir_protegido"] = bool(permitir_protegido)
    resultado = _executar_ui_automation(operacao, dados)
    if not resultado.get("ok"):
        verbos = {"clicar": "clicar", "preencher": "preencher", "alternar": "alternar", "selecionar": "selecionar"}
        return f"Nao consegui {verbos.get(operacao, operacao)} '{alvo}' na janela '{titulo}': {resultado.get('erro', 'erro desconhecido')}"
    if operacao == "preencher" and resultado.get("confirmado") is False:
        nome_real = resultado.get("nome") or alvo
        automation_id = resultado.get("automation_id") or "[sem AutomationId]"
        protegido = resultado.get("protegido")
        return (f"Preenchimento nao confirmado em '{nome_real}' (automation_id={automation_id}; protegido={protegido}) "
                f"na janela '{titulo}'. O controle nao confirmou o valor solicitado.")
    return str(resultado.get("resultado") or "Acao concluida.")

def clicar_elemento_windows(alvo_janela="", alvo="", indice=1):
    return _executar_acao_ui_windows("clicar", alvo_janela, alvo, indice)

def preencher_elemento_windows(alvo_janela="", alvo="", texto="", indice=1, permitir_protegido=False):
    return _executar_acao_ui_windows("preencher", alvo_janela, alvo, indice, texto, permitir_protegido)

def alternar_elemento_windows(alvo_janela="", alvo="", indice=1):
    return _executar_acao_ui_windows("alternar", alvo_janela, alvo, indice)

def selecionar_elemento_windows(alvo_janela="", alvo="", indice=1):
    return _executar_acao_ui_windows("selecionar", alvo_janela, alvo, indice)

