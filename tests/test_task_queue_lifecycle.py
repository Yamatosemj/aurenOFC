
import threading
import time
import pytest

from agent.ari_native.task_queue import AgentTaskQueue


def test_duplicate_task_id_is_rejected(tmp_path):
    q = AgentTaskQueue(max_workers=1)
    gate = threading.Event()
    q.submit("first", lambda cancel: gate.wait(2), task_id="same")
    with pytest.raises(ValueError):
        q.submit("second", lambda cancel: None, task_id="same")
    gate.set()
    assert q.shutdown(cancel_pending=False) == "stopped"


def test_cancel_pending_shutdown_produces_results():
    q = AgentTaskQueue(max_workers=1)
    gate = threading.Event()
    running = q.submit("running", lambda cancel: gate.wait(2), task_id="running")
    pending = q.submit("pending", lambda cancel: "should-not-run", task_id="pending")
    deadline = time.time() + 2
    while time.time() < deadline and q.status(running) != "running":
        time.sleep(0.01)
    state = q.shutdown(cancel_pending=True, timeout=0.05)
    assert state in {"timed_out", "stopped"}
    assert q.result(pending) is not None
    assert q.result(pending).status == "cancelled"
    gate.set()
    assert q.shutdown(timeout=2) == "stopped"


def test_graceful_shutdown_drains_pending():
    q = AgentTaskQueue(max_workers=1)
    ran = []
    q.submit("a", lambda cancel: ran.append("a"), task_id="a", priority=1)
    q.submit("b", lambda cancel: ran.append("b"), task_id="b", priority=2)
    assert q.shutdown(cancel_pending=False, timeout=2) == "stopped"
    assert ran == ["a", "b"]
    assert q.result("a").status == "completed"
    assert q.result("b").status == "completed"


def test_shutdown_timeout_is_observable_and_submit_is_blocked():
    q = AgentTaskQueue(max_workers=1)
    gate = threading.Event()
    q.submit("blocked", lambda cancel: gate.wait(2), task_id="blocked")
    deadline = time.time() + 2
    while time.time() < deadline and q.status("blocked") != "running":
        time.sleep(0.01)
    assert q.shutdown(timeout=0.01) == "timed_out"
    assert q.shutdown_state == "timed_out"
    assert q.alive_workers >= 1
    with pytest.raises(RuntimeError):
        q.submit("new", lambda cancel: None, task_id="new")
    gate.set()
    assert q.shutdown(timeout=2) == "stopped"


def test_worker_survives_normal_exception():
    q = AgentTaskQueue(max_workers=1)
    q.submit("bad", lambda cancel: (_ for _ in ()).throw(RuntimeError("boom")), task_id="bad")
    q.submit("good", lambda cancel: "ok", task_id="good")
    deadline = time.time() + 2
    while time.time() < deadline and q.result("good") is None:
        time.sleep(0.01)
    assert q.result("bad").status == "failed"
    assert q.result("good").status == "completed"
    assert q.shutdown(cancel_pending=False) == "stopped"
