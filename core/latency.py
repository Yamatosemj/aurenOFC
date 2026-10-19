"""Content-free, task-local spans. Instrumentation never authorizes an action."""
from contextlib import contextmanager
from contextvars import ContextVar
import time


_observer = ContextVar("auren_latency_observer", default=None)


@contextmanager
def observe(callback):
    token = _observer.set(callback)
    try:
        yield
    finally:
        _observer.reset(token)


@contextmanager
def measure(stage):
    """Stage names must be static code labels, never targets or arguments."""
    started = time.perf_counter()
    success, error_type = True, ""
    try:
        yield
    except Exception as exc:
        success, error_type = False, type(exc).__name__
        raise
    finally:
        callback = _observer.get()
        if callback is not None:
            try:
                callback(stage, (time.perf_counter() - started) * 1000,
                         success, error_type)
            except Exception:
                pass  # A trace failure must not change execution or permissions.
