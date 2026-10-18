"""An additional restriction; never grants permission or approval."""
from contextvars import ContextVar

current_scope = ContextVar('auren_execution_scope', default=None)


def scope_allows(item):
    guard = current_scope.get()
    if guard is None:
        return True
    try:
        return guard(item) is True
    except Exception:
        return False
