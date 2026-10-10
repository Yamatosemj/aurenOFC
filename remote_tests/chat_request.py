"""Owner-only chat command validation for the Auren Windows runner.

Only a comment on an open same-repository PR with an exact SHA may run the
default no-API pytest suite. The GitHub event is data, not shell source.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen

_COMMAND = re.compile(r"\AAUREN_TESTE_V1 pytest ([a-f0-9]{40})\Z")
_REPOSITORY = "Yamatosemj/aurenOFC"
_OWNER = "Yamatosemj"


def parse_command(body: str) -> str:
    match = _COMMAND.fullmatch(body)
    if match is None:
        raise ValueError("Comando invalido: somente AUREN_TESTE_V1 pytest <sha completo>")
    return match.group(1)


def validate_event(event: dict, *, actor: str, repo: str, attempt: str) -> tuple[int, str]:
    if repo != _REPOSITORY or event.get("repository", {}).get("full_name") != _REPOSITORY:
        raise ValueError("Repositorio inesperado")
    if event.get("repository", {}).get("private") is not True:
        raise ValueError("O repositorio precisa ser privado")
    if actor != _OWNER or event.get("sender", {}).get("login") != _OWNER:
        raise ValueError("Somente o proprietario pode solicitar testes")
    if event.get("comment", {}).get("user", {}).get("login") != _OWNER:
        raise ValueError("Comentario nao pertence ao proprietario")
    if event.get("action") != "created" or attempt != "1":
        raise ValueError("Apenas comentarios novos, sem repeticao do job")
    issue = event.get("issue") or {}
    if not isinstance(issue.get("pull_request"), dict):
        raise ValueError("O comentario precisa estar em uma PR")
    number = issue.get("number")
    if type(number) is not int or not (1 <= number <= 999999):
        raise ValueError("Numero da PR invalido")
    sha = parse_command(event.get("comment", {}).get("body", ""))
    return number, sha


def validate_pull_request(pr: dict, *, number: int, sha: str) -> None:
    if pr.get("number") != number or pr.get("state") != "open" or pr.get("draft"):
        raise ValueError("PR inexistente, fechada ou draft")
    if pr.get("base", {}).get("ref") != "main" or pr.get("base", {}).get("repo", {}).get("full_name") != _REPOSITORY:
        raise ValueError("PR nao aponta para a main deste projeto")
    head = pr.get("head", {})
    if head.get("repo", {}).get("full_name") != _REPOSITORY:
        raise ValueError("PR de fork nao pode executar no Windows pessoal")
    if head.get("sha") != sha:
        raise ValueError("O SHA solicitado nao corresponde ao HEAD atual da PR")


def main() -> int:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    number, sha = validate_event(
        event,
        actor=os.environ["GITHUB_ACTOR"],
        repo=os.environ["GITHUB_REPOSITORY"],
        attempt=os.environ["GITHUB_RUN_ATTEMPT"],
    )
    token = os.environ["GH_TOKEN"]
    request = Request(
        f"https://api.github.com/repos/{_REPOSITORY}/pulls/{number}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=20) as response:
        pr = json.load(response)
    validate_pull_request(pr, number=number, sha=sha)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as result:
        result.write(f"pr_number={number}\npr_sha={sha}\n")
    print(f"Pedido validado: PR #{number}, SHA {sha}, suite pytest sem API")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
