from core import harness
from core import harness_runtime


def test_harness_runtime_symbols_are_reexported_for_compatibility():
    public_names = (
        "SessionContext",
        "start_chat_session",
        "end_chat_session",
        "current_chat_id",
        "current_chat_log_path",
    )

    for name in public_names:
        assert getattr(harness, name) is getattr(harness_runtime, name)


def test_harness_runtime_owns_session_and_log_implementations():
    for name in (
        "_create_chat_session",
        "_write_one_log_file",
        "_prepare_log_details",
        "_write_log",
    ):
        assert getattr(harness, name) is getattr(harness_runtime, name)
        assert getattr(harness, name).__module__ == "core.harness_runtime"


def test_harness_runtime_owns_session_context_and_log_lock():
    assert harness._CURRENT_SESSION is harness_runtime._CURRENT_SESSION
    assert harness._LOG_LOCK is harness_runtime._LOG_LOCK
