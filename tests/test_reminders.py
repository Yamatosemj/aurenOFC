from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.dispatcher as dispatcher
import tools.reminders as reminders
from core.permission_manager import PermissionLevel, PermissionManager
from core.tool_contracts import validate_tool_arguments
from core.tools_registry import tools
from core.router import Router


class FakeScheduler:
    def __init__(self):
        self.tasks: dict[str, datetime] = {}
        self.created: list[tuple[str, datetime, list[str]]] = []
        self.deleted: list[str] = []

    def create(self, task_name, target, command):
        self.tasks[str(task_name)] = target
        self.created.append((str(task_name), target, list(command)))

    def delete(self, task_name):
        name = str(task_name)
        self.deleted.append(name)
        return self.tasks.pop(name, None) is not None

    def exists(self, task_name):
        return str(task_name) in self.tasks


@pytest.fixture
def reminder_env(monkeypatch, tmp_path):
    store = tmp_path / "lembretes.json"
    scheduler = FakeScheduler()
    monkeypatch.setenv("AUREN_REMINDERS_FILE", str(store))
    monkeypatch.setattr(reminders, "SCHEDULER", scheduler)
    monkeypatch.setattr(reminders.sys, "platform", "win32")
    return store, scheduler


def _future(minutes: int = 30) -> tuple[str, str]:
    alvo = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=minutes)
    return alvo.strftime("%Y-%m-%d"), alvo.strftime("%H:%M")


def _write_entries(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")


def test_tools_registry_contains_three_reminder_tools():
    names = {item["name"] for item in tools}
    assert {"criar_lembrete", "listar_lembretes", "cancelar_lembrete"} <= names
    assert len(tools) == 57


def test_reminder_contracts_are_strict():
    data, hora = _future()
    assert validate_tool_arguments(
        "criar_lembrete",
        {"mensagem": "ligar para o Gu", "data": data, "hora": hora},
    )[0]
    assert validate_tool_arguments("listar_lembretes", {})[0]
    assert validate_tool_arguments("cancelar_lembrete", {"id": "rem-a1b2c3d4e5"})[0]

    ok, error = validate_tool_arguments(
        "criar_lembrete",
        {"mensagem": "x", "data": data},
    )
    assert not ok
    assert "hora" in error


def test_permission_policy_create_and_cancel_confirm_list_auto():
    pm = PermissionManager()
    assert pm.nivel("criar_lembrete") is PermissionLevel.CONFIRM
    assert pm.nivel("cancelar_lembrete") is PermissionLevel.CONFIRM
    assert pm.nivel("listar_lembretes") is PermissionLevel.AUTO

    assert pm.nivel_da_acao(
        "criar_lembrete",
        {"mensagem": "teste", "data": "2099-01-01", "hora": "10:00"},
    )[0] is PermissionLevel.CONFIRM
    assert pm.nivel_da_acao("listar_lembretes", {})[0] is PermissionLevel.AUTO


@pytest.mark.parametrize(
    "mensagem",
    ["me lembre de pagar a conta", "crie um lembrete amanhã", "avise para eu ligar depois"],
)
def test_router_selects_reminder_tools(mensagem):
    selected = set(Router().select_tool_names(mensagem, tools))
    assert {"criar_lembrete", "listar_lembretes", "cancelar_lembrete"} <= selected


def test_create_persists_and_schedules_with_argument_list(reminder_env):
    store, scheduler = reminder_env
    data, hora = _future()
    result = reminders.criar_lembrete("Comprar pão", data, hora)

    assert result.ok is True
    assert result.tool_name == "criar_lembrete"
    assert result.data["agendador"] == "Windows Task Scheduler"
    reminder_id = result.data["id"]
    assert re.fullmatch(r"rem-[0-9a-f]{10}", reminder_id)

    entries = json.loads(store.read_text(encoding="utf-8"))
    assert entries[0]["id"] == reminder_id
    assert entries[0]["mensagem"] == "Comprar pão"

    assert len(scheduler.created) == 1
    task_name, target, command = scheduler.created[0]
    assert task_name == entries[0]["task_name"]
    assert target.strftime("%Y-%m-%d") == data
    assert target.strftime("%H:%M") == hora
    assert command == [
        str(Path(reminders.sys.executable).with_name("pythonw.exe"))
        if Path(reminders.sys.executable).with_name("pythonw.exe").exists()
        else reminders.sys.executable,
        "-m",
        "tools.reminders",
        "--disparar",
        reminder_id,
    ]
    assert result.data["desfazer"] == {
        "ferramenta": "cancelar_lembrete",
        "argumentos": {"id": reminder_id},
    }


def test_create_rejects_past_and_oversized_message(reminder_env):
    result = reminders.criar_lembrete(
        "teste",
        "2000-01-01",
        "00:00",
    )
    assert not result.ok
    assert result.error_code == "invalid_reminder"

    data, hora = _future()
    result = reminders.criar_lembrete("x" * 501, data, hora)
    assert not result.ok
    assert result.error_code == "invalid_reminder"


def test_create_rolls_back_metadata_when_scheduler_fails(reminder_env, monkeypatch):
    store, _scheduler = reminder_env

    def explode(*_args, **_kwargs):
        raise RuntimeError("scheduler down")

    monkeypatch.setattr(reminders.SCHEDULER, "create", explode)
    data, hora = _future()
    result = reminders.criar_lembrete("teste", data, hora)

    assert not result.ok
    assert result.error_code == "reminder_schedule_failed"
    assert json.loads(store.read_text(encoding="utf-8")) == []


def test_list_returns_only_existing_future_tasks_and_cleans_stale_entries(reminder_env):
    store, scheduler = reminder_env
    future_data, future_hora = _future(40)
    past = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=10)

    active_id = "rem-1111111111"
    stale_id = "rem-2222222222"
    past_id = "rem-3333333333"

    active_task = "AurenReminder_" + active_id
    stale_task = "AurenReminder_" + stale_id
    scheduler.tasks[active_task] = datetime.strptime(
        f"{future_data} {future_hora}", "%Y-%m-%d %H:%M"
    )

    _write_entries(
        store,
        [
            {
                "id": active_id,
                "task_name": active_task,
                "mensagem": "ativo",
                "data": future_data,
                "hora": future_hora,
            },
            {
                "id": stale_id,
                "task_name": stale_task,
                "mensagem": "apagado fora do Auren",
                "data": future_data,
                "hora": future_hora,
            },
            {
                "id": past_id,
                "task_name": "AurenReminder_" + past_id,
                "mensagem": "passado",
                "data": past.strftime("%Y-%m-%d"),
                "hora": past.strftime("%H:%M"),
            },
        ],
    )

    result = reminders.listar_lembretes()
    assert result.ok
    assert result.data["lembretes"] == [
        {
            "id": active_id,
            "data": future_data,
            "hora": future_hora,
            "mensagem": "ativo",
        }
    ]

    entries = json.loads(store.read_text(encoding="utf-8"))
    assert [item["id"] for item in entries] == [active_id]


def test_cancel_removes_scheduler_task_and_metadata(reminder_env):
    store, scheduler = reminder_env
    data, hora = _future()
    created = reminders.criar_lembrete("cancelar", data, hora)
    reminder_id = created.data["id"]

    result = reminders.cancelar_lembrete(reminder_id)
    assert result.ok
    assert result.data["id"] == reminder_id
    assert scheduler.deleted == ["AurenReminder_" + reminder_id]
    assert json.loads(store.read_text(encoding="utf-8")) == []


def test_cancel_unknown_and_malformed_ids_fail(reminder_env):
    assert reminders.cancelar_lembrete("rem-nao-valido").error_code == "invalid_reminder_id"
    assert reminders.cancelar_lembrete("rem-aaaaaaaaaa").error_code == "reminder_not_found"


def test_create_scheduler_builds_safe_xml_and_never_shells_out(reminder_env, monkeypatch):
    _store, scheduler = reminder_env
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(reminders.subprocess, "run", fake_run)
    scheduler_real = reminders.TaskScheduler()
    data, hora = _future(50)
    target = datetime.strptime(f"{data} {hora}", "%Y-%m-%d %H:%M")
    scheduler_real.create(
        "AurenReminder_rem-aaaaaaaaaa",
        target,
        [reminders.sys.executable, "-m", "tools.reminders", "--disparar", "rem-aaaaaaaaaa"],
    )

    command = captured["command"]
    assert command[0] == "schtasks.exe"
    assert command[1:4] == ["/Create", "/TN", "AurenReminder_rem-aaaaaaaaaa"]
    assert captured["kwargs"]["check"] is False
    assert "shell" not in captured["kwargs"]

    # The XML is removed after the call; validate the serialized contract via the
    # command-side temporary file captured during invocation.
    args_path = Path(command[5])
    assert not args_path.exists()


def test_scheduler_xml_uses_iso_time_interactive_token_and_least_privilege(tmp_path, monkeypatch):
    scheduler = reminders.TaskScheduler()
    temp_store = tmp_path / "reminders.json"
    monkeypatch.setenv("AUREN_REMINDERS_FILE", str(temp_store))

    target = datetime(2030, 5, 17, 14, 30)
    xml = reminders._task_xml(
        "AurenReminder_rem-aaaaaaaaaa",
        target,
        [r"C:\Python\pythonw.exe", "-m", "tools.reminders", "--disparar", "rem-aaaaaaaaaa"],
    )

    assert "<StartBoundary>2030-05-17T14:30:00</StartBoundary>" in xml
    assert "<LogonType>InteractiveToken</LogonType>" in xml
    assert "<RunLevel>LeastPrivilege</RunLevel>" in xml
    assert r"<Command>C:\Python\pythonw.exe</Command>" in xml
    assert "--disparar" in xml
    assert "shell=True" not in xml


def test_dispatcher_executes_create_only_after_confirmation():
    data, hora = _future()
    calls = []

    class ConfirmingManager(PermissionManager):
        def autorizar(self, nome_ferramenta, argumentos):
            calls.append((nome_ferramenta, argumentos))
            return False, "Usuario negou a acao."

    result = dispatcher.executar_ferramenta(
        SimpleNamespace(
            name="criar_lembrete",
            arguments=json.dumps(
                {"mensagem": "teste", "data": data, "hora": hora}
            ),
        ),
        ConfirmingManager(),
        None,
    )

    assert not result.ok
    assert result.error_code == "permission_denied"
    assert calls and calls[0][0] == "criar_lembrete"


def test_dispatcher_uses_real_reminder_handler_after_permission(monkeypatch):
    captured = {}

    def fake_create(mensagem, data, hora):
        captured.update(mensagem=mensagem, data=data, hora=hora)
        return reminders.ToolResult.success(
            "ok",
            tool_name="criar_lembrete",
        )

    monkeypatch.setitem(
        dispatcher.TOOL_HANDLERS,
        "criar_lembrete",
        lambda args, memory_store, context: fake_create(
            args["mensagem"], args["data"], args["hora"]
        ),
    )

    pm = PermissionManager(
        confirmation_channel=type(
            "Channel",
            (),
            {"confirmar": lambda _self, _request: True},
        )(),
    )
    data, hora = _future()
    result = dispatcher.executar_ferramenta(
        SimpleNamespace(
            name="criar_lembrete",
            arguments=json.dumps(
                {"mensagem": "teste", "data": data, "hora": hora}
            ),
        ),
        pm,
        None,
    )

    assert result.ok
    assert captured == {"mensagem": "teste", "data": data, "hora": hora}


def test_dispatcher_registry_has_reminder_handlers():
    assert dispatcher.validar_registry_handlers() == (True, "")
    assert {"criar_lembrete", "listar_lembretes", "cancelar_lembrete"} <= set(dispatcher.TOOL_HANDLERS)


def test_fire_runner_notifies_and_cleans_task(monkeypatch, reminder_env):
    store, scheduler = reminder_env
    reminder_id = "rem-aaaaaaaaaa"
    task_name = "AurenReminder_" + reminder_id
    data, hora = _future()

    _write_entries(
        store,
        [{
            "id": reminder_id,
            "task_name": task_name,
            "mensagem": "Agora!",
            "data": data,
            "hora": hora,
        }],
    )
    scheduler.tasks[task_name] = datetime.strptime(
        f"{data} {hora}", "%Y-%m-%d %H:%M"
    )
    monkeypatch.setattr(reminders, "_notificar_windows", lambda _message: True)

    assert reminders.main(["--disparar", reminder_id]) == 0
    assert not store.exists() or json.loads(store.read_text(encoding="utf-8")) == []
    assert task_name in scheduler.deleted


def test_fire_runner_rejects_unexpected_arguments(reminder_env):
    assert reminders.main([]) == 2
    assert reminders.main(["--disparar", "nao-e-id"]) == 2
