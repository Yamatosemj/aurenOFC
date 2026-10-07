from __future__ import annotations

from types import SimpleNamespace

from core.harness_completion import _finalizar_resposta_sucesso


class _TaskManager:
    def __init__(self, snapshot=None):
        self.completed = []
        self.snapshot = snapshot

    def complete(self, texto, *, task_id):
        self.completed.append((texto, task_id))

    def current_snapshot(self):
        return self.snapshot


def _resposta(texto):
    return SimpleNamespace(output_text=texto, output=[])


def test_finaliza_resposta_preserva_resposta_e_completa_tarefa():
    resposta = _resposta("resposta final")
    manager = _TaskManager(SimpleNamespace(state=SimpleNamespace(value="completed")))
    saved = []
    turns = []
    logs = []

    resultado = _finalizar_resposta_sucesso(
        "objetivo",
        [],
        resposta,
        apos_tarefa=None,
        task_id="task-1",
        salvar_estrategia=lambda *args: saved.append(args),
        task_manager=manager,
        registrar_turno=lambda *args: turns.append(args),
        write_log=lambda *args, **kwargs: logs.append((args, kwargs)),
        criar_resposta=_resposta,
    )

    assert resultado is resposta
    assert saved == [("objetivo", [], "resposta final", True)]
    assert manager.completed == [("resposta final", "task-1")]
    assert turns == [("assistant", "resposta final")]
    assert logs == [
        (("TASK_STATE",), {"task_id": "task-1", "estado": "completed"})
    ]


def test_finaliza_resposta_anexa_extra_de_apos_tarefa():
    resposta = _resposta("resposta")
    historico = [{"ferramenta": "abrir", "resultado": "ok"}]
    manager = _TaskManager(SimpleNamespace(state=SimpleNamespace(value="completed")))
    callback_calls = []

    resultado = _finalizar_resposta_sucesso(
        "objetivo",
        historico,
        resposta,
        apos_tarefa=lambda objetivo, historico: (
            callback_calls.append((objetivo, historico)) or " | memoria salva"
        ),
        task_id="task-2",
        salvar_estrategia=lambda objetivo, historico, texto, sucesso: callback_calls.append(
            ("save", objetivo, historico, texto, sucesso)
        ),
        task_manager=manager,
        registrar_turno=lambda papel, texto: callback_calls.append(("turn", papel, texto)),
        write_log=lambda *args, **kwargs: callback_calls.append(("log", args, kwargs)),
        criar_resposta=_resposta,
    )

    assert resultado.output_text == "resposta | memoria salva"
    assert callback_calls[0] == ("objetivo", historico)
    assert callback_calls[1] == ("save", "objetivo", historico, "resposta | memoria salva", True)
    assert manager.completed == [("resposta | memoria salva", "task-2")]


def test_erro_de_apos_tarefa_apenas_registra_memoria_e_conclui():
    resposta = _resposta("resposta")
    historico = [{"ferramenta": "abrir", "resultado": "ok"}]
    manager = _TaskManager(None)
    logs = []

    def falhar(*_args):
        raise RuntimeError("memoria indisponivel")

    _finalizar_resposta_sucesso(
        "objetivo",
        historico,
        resposta,
        apos_tarefa=falhar,
        task_id="task-3",
        salvar_estrategia=lambda *args: None,
        task_manager=manager,
        registrar_turno=lambda *args: None,
        write_log=lambda *args, **kwargs: logs.append((args, kwargs)),
        criar_resposta=_resposta,
    )

    assert logs == [
        (
            ("MEMORY_ERROR",),
            {"task_id": "task-3", "erro": "memoria indisponivel"},
        ),
        (
            ("TASK_STATE",),
            {"task_id": "task-3", "estado": "completed"},
        ),
    ]
    assert manager.completed == [("resposta", "task-3")]
