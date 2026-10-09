"""Run tests from a temporary PR checkout under the *trusted* Windows watchdog.

This file must be loaded from the pinned remote-control branch, never from a PR.
It is not a sandbox: executing Python from a PR grants the runner account's
permissions. Explicit owner-triggered approval and Windows isolation still matter.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import tempfile

from windows_watchdog import supervise

LAYERS = {"pytest", "L0", "L1", "L2", "L4", "L5", "ALL"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--camada", choices=sorted(LAYERS), default="pytest")
    args = parser.parse_args()

    project = args.project.resolve(strict=True)
    output = args.output.resolve()
    if not (project / ".git").exists() or not (project / "auren.py").is_file():
        raise SystemExit("PR checkout not found; refusing execution")
    if project == output or project in output.parents:
        raise SystemExit("Report directory must be outside the PR checkout")
    output.mkdir(parents=True, exist_ok=True)
    if args.camada != "pytest" and not (project / "testes_auren_live.py").is_file():
        raise SystemExit("Live tester not found in PR")

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    api.CreateMutexW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    mutex = api.CreateMutexW(None, True, "Local\\AurenAuthorizedLiveTests")
    if not mutex:
        raise SystemExit("Could not acquire shared Auren test mutex")
    if ctypes.get_last_error() == 183:
        api.CloseHandle(mutex)
        raise SystemExit("Auren live or PR test already in progress")
    try:
        if args.camada in {"L4", "L5", "ALL"} and not os.getenv("OPENAI_API_KEY"):
            result = {"reason": "missing_api_key", "exit_code": 125}
        else:
            if args.camada == "pytest":
                downloads = Path.home() / "Downloads"
                if not downloads.is_dir():
                    raise RuntimeError("Downloads directory not present for safe pytest tmp data")
                with tempfile.TemporaryDirectory(prefix="auren-pr-pytest-", dir=downloads) as tmp:
                    command = [sys.executable, "-u", "-m", "pytest", "tests", "-q",
                               "-ra", "--tb=short", "--basetemp", tmp,
                               "--junitxml", str(output / "pytest.xml")]
                    result = supervise(
                        command, cwd=project, log_path=output / "pr-test.log",
                        wall_seconds=1200, idle_seconds=120,
                        stop_file=Path(os.environ["USERPROFILE"]) / "auren-remote" / "STOP-LIVE",
                    )
            else:
                layers = "L0,L1,L2,L4,L5" if args.camada == "ALL" else args.camada
                result = supervise(
                    [sys.executable, "-u", str(project / "testes_auren_live.py"),
                     "--camada", layers],
                    cwd=project, log_path=output / "pr-test.log",
                    wall_seconds=1200, idle_seconds=120,
                    stop_file=Path(os.environ["USERPROFILE"]) / "auren-remote" / "STOP-LIVE",
                )
        result["camada"] = args.camada
        (output / "pr-result.json").write_text(
            json.dumps({k: v for k, v in result.items() if k != "pid"}, indent=2),
            encoding="utf-8",
        )
        print(f"PR test: {result['reason']}; exit={result['exit_code']}", flush=True)
        return result["exit_code"] if result["exit_code"] in {0, 1, 124, 125, 130} else 1
    finally:
        api.CloseHandle(mutex)


if __name__ == "__main__":
    raise SystemExit(main())
