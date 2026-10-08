from __future__ import annotations

import ctypes
import html
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from core.tool_result import ToolResult


_ID_RE = re.compile(r"^rem-[0-9a-f]{10}$")
_MESSAGE_LIMIT = 500
_DATE_FORMAT = "%Y-%m-%d"
_TIME_FORMAT = "%H:%M"
_TOOL_CREATE = "criar_lembrete"
_TOOL_LIST = "listar_lembretes"
_TOOL_CANCEL = "cancelar_lembrete"


_STORE_LOCK = threading.RLock()


def _is_windows() -> bool:
    return sys.platform == "win32"


def _store_path() -> Path:
    configured = os.getenv("AUREN_REMINDERS_FILE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    appdata = os.getenv("APPDATA", "").strip()
    if appdata:
        return Path(appdata) / "Auren" / "lembretes.json"

    return Path(__file__).resolve().parents[1] / "data" / "reminders" / "lembretes.json"


def _load_entries() -> list[dict[str, Any]]:
    path = _store_path()
    if not path.exists():
        return []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []

    if not isinstance(raw, list):
        return []

    entries: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if not _ID_RE.fullmatch(str(item.get("id", ""))):
            continue
        if not isinstance(item.get("task_name"), str):
            continue
        if not isinstance(item.get("mensagem"), str):
            continue
        entries.append(dict(item))
    return entries


def _save_entries(entries: Sequence[dict[str, Any]]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    payload = json.dumps(list(entries), ensure_ascii=False, indent=2) + "\n"
    try:
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _gerar_id() -> str:
    return f"rem-{secrets.token_hex(5)}"


def _task_name(reminder_id: str) -> str:
    """Deriva o nome exato da tarefa a partir do ID validado do lembrete.
    A derivacao elimina metadata externa como autoridade para escolher outra tarefa.
    Custo: O(1), sem acesso ao sistema."""
    return f"AurenReminder_{reminder_id}"


def _validar_mensagem(mensagem: Any) -> str:
    texto = " ".join(str(mensagem or "").split()).strip()
    if not texto:
        raise ValueError("A mensagem do lembrete nao pode ser vazia.")
    if len(texto) > _MESSAGE_LIMIT:
        raise ValueError(
            f"A mensagem do lembrete excede o limite de {_MESSAGE_LIMIT} caracteres."
        )
    return texto


def _parse_target(data: Any, hora: Any) -> datetime:
    data_texto = str(data or "").strip()
    hora_texto = str(hora or "").strip()

    try:
        alvo = datetime.strptime(
            f"{data_texto} {hora_texto}",
            f"{_DATE_FORMAT} {_TIME_FORMAT}",
        )
    except ValueError as exc:
        raise ValueError(
            "Data ou hora invalidas. Use data YYYY-MM-DD e hora HH:MM."
        ) from exc

    if alvo <= datetime.now():
        raise ValueError("O lembrete precisa estar no futuro.")
    return alvo


def _python_command(reminder_id: str) -> list[str]:
    python_exe = Path(sys.executable)
    pythonw = python_exe.with_name("pythonw.exe")
    executable = pythonw if pythonw.exists() else python_exe
    return [
        str(executable),
        "-m",
        "tools.reminders",
        "--disparar",
        reminder_id,
    ]


def _task_xml(task_name: str, target: datetime, command: Sequence[str]) -> str:
    if len(command) < 1:
        raise ValueError("Comando do lembrete ausente.")

    executable = html.escape(str(command[0]), quote=False)
    arguments = html.escape(
        subprocess.list2cmdline([str(value) for value in command[1:]]),
        quote=False,
    )
    working_directory = html.escape(
        str(Path(__file__).resolve().parents[1]),
        quote=False,
    )

    return f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Auren reminder {html.escape(task_name)}</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>{target.strftime("%Y-%m-%dT%H:%M:%S")}</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT2M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{executable}</Command>
      <Arguments>{arguments}</Arguments>
      <WorkingDirectory>{working_directory}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
'''


def _run_schtasks(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    command = ["schtasks.exe", *[str(value) for value in arguments]]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class TaskScheduler:
    """Adaptador pequeno para o Agendador de Tarefas do Windows.

    O adaptador monta comandos seguros como listas e usa XML para preservar
    data/hora sem depender da localizacao do Windows.
    """

    def create(self, task_name: str, target: datetime, command: Sequence[str]) -> None:
        """Cria uma tarefa ONCE para disparar o runner do lembrete no horario pedido.
        O sistema de tarefas passa a ser a agenda persistente, mesmo sem o Auren aberto.
        Custo: uma escrita de XML temporario e uma chamada ao schtasks.exe."""
        if not _is_windows():
            raise RuntimeError("Lembretes do Windows exigem um sistema Windows.")

        xml_path = _store_path().with_name(
            f".{task_name}.{uuid.uuid4().hex}.xml"
        )
        xml_path.parent.mkdir(parents=True, exist_ok=True)
        xml_path.write_text(
            _task_xml(task_name, target, command),
            encoding="utf-16",
        )
        try:
            result = _run_schtasks([
                "/Create",
                "/TN",
                task_name,
                "/XML",
                str(xml_path),
                "/F",
            ])
        finally:
            xml_path.unlink(missing_ok=True)

        if result.returncode != 0:
            detalhe = (result.stderr or result.stdout or "erro desconhecido").strip()
            raise RuntimeError(
                f"O Agendador de Tarefas recusou o lembrete: {detalhe[:500]}"
            )

    def delete(self, task_name: str) -> bool:
        """Exclui uma tarefa pelo nome exato e retorna se ela existia.
        Erros de inexistencia sao tratados como estado ja cancelado, sem repetir trabalho.
        Custo: uma chamada ao schtasks.exe."""
        if not _is_windows():
            raise RuntimeError("Lembretes do Windows exigem um sistema Windows.")

        result = _run_schtasks([
            "/Delete",
            "/TN",
            task_name,
            "/F",
        ])
        if result.returncode == 0:
            return True

        detalhe = (result.stderr or result.stdout or "").lower()
        if any(token in detalhe for token in (
            "cannot find",
            "nao foi possivel encontrar",
            "não foi possível encontrar",
            "does not exist",
            "nao existe",
            "não existe",
        )):
            return False

        raise RuntimeError(
            f"Nao foi possivel cancelar a tarefa: {(result.stderr or result.stdout or 'erro desconhecido').strip()[:500]}"
        )

    def exists(self, task_name: str) -> bool:
        """Consulta se a tarefa exata ainda existe no Agendador do Windows.
        Falhas desconhecidas nao sao confundidas com ausencia, evitando apagar metadata por engano.
        Custo: uma chamada ao schtasks.exe por lembrete consultado."""
        if not _is_windows():
            raise RuntimeError("Lembretes do Windows exigem um sistema Windows.")

        result = _run_schtasks([
            "/Query",
            "/TN",
            task_name,
        ])
        if result.returncode == 0:
            return True

        detalhe = (result.stderr or result.stdout or "").lower()
        if any(token in detalhe for token in (
            "cannot find",
            "nao pode encontrar",
            "não pode encontrar",
            "does not exist",
            "nao existe",
            "não existe",
            "the system cannot find",
            "o sistema nao pode encontrar",
            "o sistema não pode encontrar",
        )):
            return False

        raise RuntimeError(
            f"Nao foi possivel consultar a tarefa: {(result.stderr or result.stdout or 'erro desconhecido').strip()[:500]}"
        )


SCHEDULER = TaskScheduler()


def _criar_entrada(
    reminder_id: str,
    task_name: str,
    mensagem: str,
    alvo: datetime,
) -> dict[str, Any]:
    return {
        "id": reminder_id,
        "task_name": task_name,
        "mensagem": mensagem,
        "data": alvo.strftime(_DATE_FORMAT),
        "hora": alvo.strftime(_TIME_FORMAT),
        "criado_em": datetime.now().isoformat(timespec="seconds"),
    }


def criar_lembrete(mensagem: str, data: str, hora: str) -> ToolResult:
    """Cria um lembrete persistente no Agendador de Tarefas do Windows.
    A entrada fica em metadata local e o sistema dispara o runner mesmo sem o Auren aberto.
    Custo: validacao, uma escrita pequena de JSON e uma criacao no Task Scheduler."""
    try:
        texto = _validar_mensagem(mensagem)
        alvo = _parse_target(data, hora)
    except ValueError as exc:
        return ToolResult.failure(
            str(exc),
            error_code="invalid_reminder",
            tool_name=_TOOL_CREATE,
        )

    reminder_id = _gerar_id()
    task_name = _task_name(reminder_id)
    entry = _criar_entrada(reminder_id, task_name, texto, alvo)

    try:
        with _STORE_LOCK:
            entries = _load_entries()
            entries.append(entry)
            _save_entries(entries)
            try:
                SCHEDULER.create(task_name, alvo, _python_command(reminder_id))
            except Exception:
                _save_entries([item for item in entries if item.get("id") != reminder_id])
                raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return ToolResult.failure(
            f"Nao foi possivel criar o lembrete: {exc}",
            error_code="reminder_schedule_failed",
            tool_name=_TOOL_CREATE,
        )

    return ToolResult.success(
        f"Lembrete criado para {alvo.strftime('%d/%m/%Y às %H:%M')}: {texto}",
        data={
            "id": reminder_id,
            "data": entry["data"],
            "hora": entry["hora"],
            "mensagem": texto,
            "agendador": "Windows Task Scheduler",
            "desfazer": {
                "ferramenta": _TOOL_CANCEL,
                "argumentos": {"id": reminder_id},
            },
        },
        tool_name=_TOOL_CREATE,
    )


def listar_lembretes() -> ToolResult:
    """Lista os lembretes futuros registrados pelo Auren e ainda presentes no Windows.
    Entradas quebradas ou agendamentos removidos sao limpos sem alterar outros lembretes.
    Custo: leitura do JSON e uma consulta ao Task Scheduler por entrada."""
    if not _is_windows():
        return ToolResult.failure(
            "Lembretes do Auren usam o Agendador de Tarefas do Windows.",
            error_code="platform_not_supported",
            tool_name=_TOOL_LIST,
        )

    agora = datetime.now()
    ativos: list[dict[str, Any]] = []
    removidos: set[str] = set()

    try:
        with _STORE_LOCK:
            entries = _load_entries()
            for entry in entries:
                try:
                    alvo = datetime.strptime(
                        f"{entry['data']} {entry['hora']}",
                        f"{_DATE_FORMAT} {_TIME_FORMAT}",
                    )
                except (KeyError, TypeError, ValueError):
                    removidos.add(str(entry.get("id", "")))
                    continue

                if alvo <= agora:
                    removidos.add(str(entry.get("id", "")))
                    continue

                task_name = _task_name(str(entry["id"]))
                try:
                    existe = SCHEDULER.exists(task_name)
                except RuntimeError as exc:
                    return ToolResult.failure(
                        f"Nao foi possivel consultar os lembretes no Agendador do Windows: {exc}",
                        error_code="reminder_scheduler_unavailable",
                        tool_name=_TOOL_LIST,
                    )

                if not existe:
                    removidos.add(str(entry.get("id", "")))
                    continue

                ativos.append({
                    "id": str(entry["id"]),
                    "data": str(entry["data"]),
                    "hora": str(entry["hora"]),
                    "mensagem": str(entry["mensagem"]),
                })

            if removidos:
                _save_entries([
                    entry for entry in entries
                    if str(entry.get("id", "")) not in removidos
                ])
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return ToolResult.failure(
            f"Nao foi possivel listar os lembretes: {exc}",
            error_code="reminder_list_failed",
            tool_name=_TOOL_LIST,
        )

    ativos.sort(key=lambda item: (item["data"], item["hora"], item["id"]))
    if not ativos:
        return ToolResult.success(
            "Nao ha lembretes futuros agendados.",
            data={"lembretes": []},
            tool_name=_TOOL_LIST,
        )

    resumo = "; ".join(
        f"{item['id']} — {item['data']} {item['hora']} — {item['mensagem']}"
        for item in ativos
    )
    return ToolResult.success(
        f"Lembretes futuros: {resumo}",
        data={"lembretes": ativos},
        tool_name=_TOOL_LIST,
    )


def cancelar_lembrete(id: str) -> ToolResult:
    """Cancela um lembrete pelo ID exato e remove sua metadata local.
    A operacao e o desfazer natural da criacao: o agendamento deixa de existir no Windows.
    Custo: leitura pequena de JSON, uma exclusao no Task Scheduler e nova escrita de JSON."""
    reminder_id = str(id or "").strip().lower()
    if not _ID_RE.fullmatch(reminder_id):
        return ToolResult.failure(
            "ID de lembrete invalido. Use o ID retornado ao criar ou listar lembretes.",
            error_code="invalid_reminder_id",
            tool_name=_TOOL_CANCEL,
        )

    try:
        with _STORE_LOCK:
            entries = _load_entries()
            entry = next(
                (item for item in entries if str(item.get("id")) == reminder_id),
                None,
            )
            if entry is None:
                return ToolResult.failure(
                    f"Nao encontrei o lembrete '{reminder_id}'.",
                    error_code="reminder_not_found",
                    tool_name=_TOOL_CANCEL,
                )

            task_name = _task_name(reminder_id)
            SCHEDULER.delete(task_name)
            _save_entries([
                item for item in entries
                if str(item.get("id")) != reminder_id
            ])
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return ToolResult.failure(
            f"Nao foi possivel cancelar o lembrete: {exc}",
            error_code="reminder_cancel_failed",
            tool_name=_TOOL_CANCEL,
        )

    return ToolResult.success(
        f"Lembrete '{reminder_id}' cancelado.",
        data={"id": reminder_id, "desfeito_de": "criar_lembrete"},
        tool_name=_TOOL_CANCEL,
    )


def _notificar_windows(mensagem: str) -> bool:
    try:
        result = subprocess.run(
            ["msg.exe", "*", "/TIME:30", f"Auren: {mensagem}"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0:
            return True
    except OSError:
        pass

    try:
        winsound = __import__("winsound")
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except (ImportError, RuntimeError, OSError):
        pass

    try:
        ctypes.windll.user32.MessageBoxW(
            0,
            str(mensagem),
            "Lembrete Auren",
            0x00000040 | 0x00040000,
        )
        return True
    except (AttributeError, OSError):
        return False


def _disparar_lembrete(reminder_id: str) -> int:
    reminder_id = str(reminder_id or "").strip().lower()
    if not _ID_RE.fullmatch(reminder_id):
        return 2

    try:
        with _STORE_LOCK:
            entries = _load_entries()
            entry = next(
                (item for item in entries if str(item.get("id")) == reminder_id),
                None,
            )
        if entry is None:
            return 0

        sucesso = _notificar_windows(str(entry["mensagem"]))
        if sucesso:
            with _STORE_LOCK:
                SCHEDULER.delete(_task_name(reminder_id))
                _save_entries([
                    item for item in _load_entries()
                    if str(item.get("id")) != reminder_id
                ])
            return 0

        return 1
    except (OSError, RuntimeError, TypeError, ValueError, KeyError):
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Executa somente o runner interno chamado por uma tarefa agendada do Windows.
    O modo exposto aceita apenas o ID do lembrete, recuperando a mensagem do storage local.
    Custo: leitura do JSON e o envio da notificacao no horario programado."""
    argumentos = list(argv if argv is not None else sys.argv[1:])
    if len(argumentos) == 2 and argumentos[0] == "--disparar":
        return _disparar_lembrete(argumentos[1])
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
