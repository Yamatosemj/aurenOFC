"""The chat-to-Windows request never permits arbitrary commands or SHAs."""
from __future__ import annotations

from pathlib import Path
import pytest

from remote_tests.chat_request import parse_command, validate_event, validate_pull_request


SHA = "a" * 40


def event_for(body=f"AUREN_TESTE_V1 pytest {SHA}"):
    return {
        "action": "created",
        "repository": {"full_name": "Yamatosemj/aurenOFC", "private": True},
        "sender": {"login": "Yamatosemj"},
        "comment": {"user": {"login": "Yamatosemj"}, "body": body},
        "issue": {"number": 108, "pull_request": {"url": "https://api.github.com/repos/Yamatosemj/aurenOFC/pulls/108"}},
    }


def pr_for():
    repo = {"full_name": "Yamatosemj/aurenOFC"}
    return {
        "number": 108, "state": "open", "draft": False,
        "base": {"ref": "main", "repo": repo},
        "head": {"sha": SHA, "repo": repo},
    }


def test_valid_owner_request_pins_pr_head():
    assert parse_command(f"AUREN_TESTE_V1 pytest {SHA}") == SHA
    assert validate_event(event_for(), actor="Yamatosemj", repo="Yamatosemj/aurenOFC", attempt="1") == (108, SHA)
    validate_pull_request(pr_for(), number=108, sha=SHA)


@pytest.mark.parametrize("bad", [
    "AUREN_TESTE_V1 pytest main",
    "AUREN_TESTE_V1 ALL " + SHA,
    "AUREN_TESTE_V1 pytest " + SHA + "\nwhoami",
    "AUREN_TESTE_V1 pytest " + "A" * 40,
    "AUREN_TESTE_V1 pytest " + SHA + " ",
    "AUREN_TESTE_V1 pytest " + SHA + " && echo hello",
    "AUREN_TESTE_V1 update " + SHA,
])
def test_reject_nonexact_commands(bad):
    with pytest.raises(ValueError):
        parse_command(bad)


@pytest.mark.parametrize("variant", ["other_author", "public", "replay", "not_pr", "other_repo"])
def test_reject_unauthorized_events(variant):
    e = event_for()
    attempt = "1"
    if variant == "other_author":
        e["comment"]["user"]["login"] = "someone-else"
    elif variant == "public":
        e["repository"]["private"] = False
    elif variant == "replay":
        attempt = "2"
    elif variant == "not_pr":
        del e["issue"]["pull_request"]
    elif variant == "other_repo":
        e["repository"]["full_name"] = "someone-else/aurenOFC"
    with pytest.raises(ValueError):
        validate_event(e, actor="Yamatosemj", repo="Yamatosemj/aurenOFC", attempt=attempt)


@pytest.mark.parametrize("variant", ["changed_sha", "fork", "closed", "draft", "other_base"])
def test_reject_untrusted_prs(variant):
    pr = pr_for()
    if variant == "changed_sha":
        pr["head"]["sha"] = "b" * 40
    elif variant == "fork":
        pr["head"]["repo"] = {"full_name": "someone-else/fork"}
    elif variant == "closed":
        pr["state"] = "closed"
    elif variant == "draft":
        pr["draft"] = True
    elif variant == "other_base":
        pr["base"]["ref"] = "dev"
    with pytest.raises(ValueError):
        validate_pull_request(pr, number=108, sha=SHA)


def test_workflow_is_owner_only_pytest_only_and_pins_trusted_execution():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/auren-chat-tests.yml").read_text(encoding="utf-8")
    assert "  issue_comment:" in workflow
    assert "github.actor == github.repository_owner" in workflow
    assert "github.triggering_actor == github.repository_owner" in workflow
    assert "github.event.repository.private == true" in workflow
    assert "auren-isolated" in workflow
    assert "448a1f87a672278471d1d8dcc08a2a621e10b77c" in workflow
    assert "Remove-Item Env:OPENAI_API_KEY" in workflow
    assert "pr-checkout" in workflow
    assert "--camada pytest" in workflow
    assert "actions/upload-artifact@" in workflow
    assert "workflow_dispatch:" not in workflow
