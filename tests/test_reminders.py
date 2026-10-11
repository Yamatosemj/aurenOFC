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


def test_horarios_falados_com_h_e_minutos_opcionais(store):
    horarios = {
        "amanhã às 8h": "2026-10-12T08:00",
        "amanha as 08": "2026-10-12T08:00",
        "hoje às 13h40": "2026-10-11T13:40",
        "hoje as 13:40": "2026-10-11T13:40",
        "hoje às 14h": "2026-10-11T14:00",
        "hoje 14:30": "2026-10-11T14:30",
    }
    for quando, expected in horarios.items():
        assert store.criar("teste", quando)["horario"].startswith(expected)



def test_fuso_diferente_nao_esconde_lembrete_vencido_com_limite_1(store, clock):
    # O ISO da primeira linha ordena antes da segunda como texto,
    # mas o seu instante UTC ocorre depois. LIMIT nao pode ocultar atrasos.
    store.criar("futuro em outro fuso", "2026-10-11T12:00:00-05:00")
    due = store.criar("vencido", "em 1 minuto")
    clock[0] += timedelta(minutes=1)
    found = store.retirar_vencidos(limite=1)
    assert [r["id"] for r in found] == [due["id"]]
    assert [r["texto"] for r in store.listar(status="pendente")] == ["futuro em outro fuso"]


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
        assert app.snapshot()["alerts"][0]["id"] == 1
        # Antes do navegador confirmar, o aviso segue pendente mesmo apos
        # desligar/reiniciar o processo e o banco ser reaberto.
        restored = reminders.ReminderStore(store.path, clock=lambda: clock[0])
        assert restored.avisos_nao_entregues()[0]["texto"] == "agua"
        assert app.confirmar_aviso(1) == {"recorded": True}
        assert app.snapshot()["alerts"] == []
        assert app.confirmar_aviso(1) == {"recorded": True}  # ACK idempotente
    finally:
        app.shutdown()


def test_reagendamento_reabre_avisos_sem_duplicar_entrega(store, clock):
    reminder = store.criar("medicacao", "em 2 minutos")
    clock[0] += timedelta(minutes=2)
    assert len(store.retirar_vencidos()) == 1
    assert len(store.avisos_nao_entregues()) == 1
    assert store.confirmar_aviso(reminder["id"])
    assert store.avisos_nao_entregues() == []
    store.alterar(reminder["id"], "adiar", minutos=3)
    clock[0] += timedelta(minutes=3)
    assert [a["id"] for a in store.retirar_vencidos()] == [reminder["id"]]
    assert [a["id"] for a in store.avisos_nao_entregues()] == [reminder["id"]]
    assert store.retirar_vencidos() == []


def test_cancelamento_antes_do_ack_remove_alerta(store, clock):
    reminder = store.criar("agua", "em 1 minuto")
    clock[0] += timedelta(minutes=1)
    assert len(store.retirar_vencidos()) == 1
    store.alterar(reminder["id"], "cancelar")
    assert store.avisos_nao_entregues() == []
    assert store.confirmar_aviso(reminder["id"]) is False
    with pytest.raises(ValueError):
        store.confirmar_aviso(True)


def test_migracao_sqlite_preserva_lembretes_antigos(tmp_path, clock):
    import sqlite3
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute("""CREATE TABLE lembretes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, texto TEXT NOT NULL,
            horario TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pendente',
            criado_em TEXT NOT NULL, atualizado_em TEXT NOT NULL
        )""")
        con.execute("""INSERT INTO lembretes(texto, horario, status, criado_em, atualizado_em)
                       VALUES (?, ?, ?, ?, ?)""", (
                           "lembrete antigo", "2026-10-11T13:25:00-03:00",
                           "notificado", "2026-10-11T13:00:00-03:00",
                           "2026-10-11T13:25:00-03:00",
                       ))
    store = reminders.ReminderStore(path, clock=lambda: clock[0])
    assert [a["texto"] for a in store.avisos_nao_entregues()] == ["lembrete antigo"]
    assert store.confirmar_aviso(1)
    assert store.avisos_nao_entregues() == []


def test_http_ack_requer_token_e_so_confirma_id_valido(store, clock):
    from http.client import HTTPConnection
    from threading import Thread
    from ui.chrome_server import ChromeServer

    class FakeWorker:
        def __init__(self):
            self.events = Queue()
        def start(self): pass
        def close(self): pass
        def go_off(self): pass

    fake = FakeWorker()
    app = LocalChromeApp(worker=fake, reminder_store=store)
    server = ChromeServer(app)
    runner = Thread(target=server.serve_forever, daemon=True)
    runner.start()
    try:
        store.criar("revisar projeto", "em 1 minuto")
        clock[0] += timedelta(minutes=1)
        app.poll_due_reminders()
        def post(body, token):
            con = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                con.request("POST", "/api/reminders/ack", body=json.dumps(body),
                            headers={"Content-Type": "application/json",
                                     "X-Auren-Token": token})
                resp = con.getresponse()
                code, data = resp.status, json.loads(resp.read())
                return code, data
            finally:
                con.close()
        assert post({"id": 1}, "token-invalido")[0] == 403
        assert post({"id": True}, app.token)[0] == 400
        assert post({"id": 999}, app.token)[0] == 400
        assert len(store.avisos_nao_entregues()) == 1
        assert post({"id": 1}, app.token) == (200, {"recorded": True})
        assert store.avisos_nao_entregues() == []
        assert post({"id": 1}, app.token) == (200, {"recorded": True})
    finally:
        server.shutdown()
        server.server_close()
        app.shutdown()
        runner.join(timeout=3)
