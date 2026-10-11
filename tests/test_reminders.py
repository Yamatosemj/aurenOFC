"""Persistencia, horarios e avisos de lembretes (sem API externa)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from queue import Queue
from types import SimpleNamespace

import pytest

from core.permission_manager import PermissionLevel, PermissionManager
from core.router import Router
from core.tool_contracts import capability_for_tool
from tools import reminders
from tools.dispatcher import executar_ferramenta
from ui.chrome_server import LocalChromeApp


TZ = timezone(timedelta(hours=-3))


@pytest.fixture
def clock():
    return [datetime(2026, 10, 11, 13, 30, tzinfo=TZ)]


@pytest.fixture
def store(tmp_path, clock):
    return reminders.ReminderStore(tmp_path / "reminders.sqlite3", clock=lambda: clock[0])


def test_criar_consultar_persistir_e_nao_duplicar_alerta(store, clock):
    one = store.criar("beber agua", "hoje as 13:40")
    assert one["horario"].startswith("2026-10-11T13:40:00")
    assert store.listar()[0]["id"] == one["id"]
    reopened = reminders.ReminderStore(store.path, clock=lambda: clock[0])
    assert reopened.listar()[0]["texto"] == "beber agua"

    clock[0] += timedelta(minutes=9)
    assert reopened.retirar_vencidos() == []
    clock[0] += timedelta(minutes=1)
    assert [x["id"] for x in reopened.retirar_vencidos()] == [one["id"]]
    assert store.retirar_vencidos() == []
    assert store.listar(status="notificado")[0]["id"] == one["id"]


def test_relativos_amanha_adiamento_e_falhas(store, clock):
    one = store.criar("consulta", "em 10 minutos")
    two = store.criar("cafe", "amanha 08:00")
    assert one["horario"].startswith("2026-10-11T13:40")
    assert two["horario"].startswith("2026-10-12T08:00")
    assert store.alterar(one["id"], "adiar", 15)["horario"].startswith("2026-10-11T13:45")
    assert store.alterar(one["id"], "concluir")["status"] == "concluido"
    assert store.alterar(two["id"], "cancelar")["status"] == "cancelado"
    assert store.listar(status="ativos") == []
    with pytest.raises(ValueError, match="passou"):
        store.criar("antigo", "hoje 13:00")
    with pytest.raises(ValueError):
        store.criar("invalido", "hoje 44:00")
    with pytest.raises(ValueError):
        store.criar("muito longo", "em 0 minutos")
    with pytest.raises(ValueError):
        store.alterar(one["id"], "adiar", 10)


def test_permissions_router_e_dispatcher_usam_um_unico_caminho(monkeypatch, store):
    monkeypatch.setattr(reminders, "get_reminder_store", lambda: store)
    pm = PermissionManager(max_actions=10)
    assert capability_for_tool("criar_lembrete") == "reminder.write"
    assert pm.nivel("criar_lembrete") == PermissionLevel.AUTO
    assert pm.nivel("listar_lembretes") == PermissionLevel.AUTO

    def call(name, args):
        return executar_ferramenta(
            SimpleNamespace(name=name, arguments=json.dumps(args)),
            pm,
            None,
        )

    result = call("criar_lembrete", {"texto": "tomar agua", "quando": "em 15 minutos"})
    assert result.ok and result.data["id"] == 1
    listed = call("listar_lembretes", {"status": "ativos", "limite": 20})
    assert listed.ok and len(listed.data["lembretes"]) == 1
    changed = call("gerenciar_lembrete", {"id": 1, "acao": "concluir", "minutos": 0})
    assert changed.ok
    assert not call("criar_lembrete", {"texto": "x"}).ok  # contrato antes do handler


def test_chrome_notifica_mesmo_desligado_sem_chamar_modelo(store, clock):
    class FakeWorker:
        def __init__(self):
            self.events = Queue()
            self.closed = False
            self.messages = []

        def start(self): pass
        def activate(self): pass
        def submit(self, msg):
            self.messages.append(msg)
            return True
        def go_off(self): pass
        def close(self):
            self.closed = True

    fake = FakeWorker()
    app = LocalChromeApp(worker=fake, reminder_store=store)
    try:
        store.criar("agua", "em 10 minutos")
        clock[0] += timedelta(minutes=10)
        app.poll_due_reminders()
        events = app.snapshot()["events"]
        matches = [x for x in events if x["kind"] == "reminder_due"]
        assert len(matches) == 1
        assert matches[0]["text"] == "agua"
        assert matches[0]["payload"]["id"] == 1
        assert app.snapshot()["mode"] == "off"
        app.poll_due_reminders()
        assert len([x for x in app.snapshot()["events"] if x["kind"] == "reminder_due"]) == 1
        assert fake.messages == []  # sem chamadas ao modelo
    finally:
        app.shutdown()
