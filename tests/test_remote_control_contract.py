"""Contracts for manually dispatched owner-only GitHub/Windows remote control."""
from __future__ import annotations

import ast
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_control_python_parses_without_windows_runtime():
    source = (ROOT / "remote_tests" / "pr_job.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert "from windows_watchdog import supervise" in source
    assert 'wall_seconds=1200, idle_seconds=120' in source
    assert "STOP-LIVE" in source
    assert "AurenAuthorizedLiveTests" in source


def test_remote_control_is_manual_and_pinned_to_control_branch():
    workflow = (ROOT / ".github" / "workflows" / "auren-update-pc.yml").read_text(
        encoding="utf-8"
    )
    assert "  workflow_dispatch:" in workflow
    assert not re.search(r"^  (push|pull_request|schedule|repository_dispatch):", workflow, re.M)
    assert "refs/heads/ci/remote-update-control" in workflow
    assert "github.actor == github.repository_owner" in workflow
    assert "github.triggering_actor == github.repository_owner" in workflow
    assert "github.event.repository.private == true" in workflow
    assert "github.sha" in workflow
    assert "pr_sha" in workflow
    assert "pr-checkout" in workflow
    assert "pull --ff-only origin main" in workflow
    assert "sha_aprovado" in workflow
    assert "Remove-Item Env:OPENAI_API_KEY" in workflow


def test_pr_validation_rejects_unreviewed_forks_and_drafts():
    workflow = (ROOT / ".github" / "workflows" / "auren-update-pc.yml").read_text(
        encoding="utf-8"
    )
    assert 'info.get("draft")' in workflow
    assert 'head.get("repo")' in workflow
    assert 'info.get("base", {}).get("ref") != "main"' in workflow
    assert "sha != " not in workflow  # pinned SHA is validated via exact equality in Windows step
    assert "$actual -ne $env:PR_SHA" in workflow
