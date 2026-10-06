from __future__ import annotations

from core.harness_session import _garantir_sessao_chat


class _Session:
    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id


def test_existing_session_is_reused_and_rebound_to_current_context():
    session = _Session("chat-existing")
    created = []
    current = []

    result = _garantir_sessao_chat(
        session,
        criar_sessao=lambda: created.append(True),
        definir_sessao_atual=current.append,
    )

    assert result == (session, False, "chat-existing")
    assert created == []
    assert current == [session]


def test_missing_session_is_created_and_marked_as_started_here():
    created_session = _Session("chat-new")
    created = []
    current = []

    result = _garantir_sessao_chat(
        None,
        criar_sessao=lambda: created.append(created_session) or created_session,
        definir_sessao_atual=current.append,
    )

    assert result == (created_session, True, "chat-new")
    assert created == [created_session]
    assert current == [created_session]


def test_session_creator_is_called_only_when_session_is_missing():
    session = _Session("chat-existing")
    calls = []

    _garantir_sessao_chat(
        session,
        criar_sessao=lambda: calls.append("created") or _Session("wrong"),
        definir_sessao_atual=lambda _: None,
    )

    assert calls == []
