"""An additional restriction; never grants permission or approval."""
from contextvars import ContextVar

current_scope = ContextVar('auren_execution_scope', default=None)
current_session_guard = ContextVar('auren_session_guard', default=None)


def session_allows():
    guard = current_session_guard.get()
    try:
        return guard is None or guard() is True
    except Exception:
        return False


def scope_allows(item):
    if not session_allows():
        return False
    guard = current_scope.get()
    if guard is None:
        return True
    try:
        return guard(item) is True
    except Exception:
        return False
