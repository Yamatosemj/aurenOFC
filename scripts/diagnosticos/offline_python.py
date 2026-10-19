"""Run Python with no model credentials and outbound Python sockets blocked.

Loopback remains available for HTTP fixture tests. The guard is inherited by
Python children; this is a test guard, not an OS sandbox for arbitrary binaries.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

GUARD = '''import socket
_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
def _allowed(address):
    return isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1", "localhost"}
def connect(self, address):
    if not _allowed(address):
        raise OSError("Offline validation: outbound network blocked")
    return _connect(self, address)
def connect_ex(self, address):
    if not _allowed(address):
        raise OSError("Offline validation: outbound network blocked")
    return _connect_ex(self, address)
socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
'''

def main():
    root = Path(__file__).resolve().parents[2]
    env = {k: v for k, v in os.environ.items()
           if not any(s in k.upper() for s in ("API_KEY", "ACCESS_TOKEN", "AUTH_TOKEN"))}
    env["AUREN_TEST_MODE"] = "1"
    reports = root.parent / ".auren-offline-temp"
    reports.mkdir(exist_ok=True)
    # AppData is intentionally protected by file policy; fixtures live outside it.
    with tempfile.TemporaryDirectory(prefix="auren-offline-", dir=reports) as folder:
        env["TMP"] = env["TEMP"] = env["PYTEST_DEBUG_TEMPROOT"] = folder
        Path(folder, "sitecustomize.py").write_text(GUARD, encoding="utf-8")
        env["PYTHONPATH"] = os.pathsep.join((folder, str(root), env.get("PYTHONPATH", "")))
        return subprocess.call([sys.executable, *sys.argv[1:]], cwd=root, env=env)

if __name__ == "__main__":
    raise SystemExit(main())
