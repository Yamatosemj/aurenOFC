from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _dependency_lines(path: str) -> list[str]:
    return [
        line.strip()
        for line in (REPOSITORY_ROOT / path).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_runtime_requirements_are_exactly_pinned() -> None:
    for path in ("requirements.txt", "requirements-voice.txt"):
        for line in _dependency_lines(path):
            assert "==" in line, f"{path}: dependência sem versão exata: {line}"
            assert all(
                operator not in line for operator in (">=", "<=", "~=", ">", "<")
            ), f"{path}: faixa de versão encontrada: {line}"


def test_runtime_requirements_have_no_duplicate_package_entries() -> None:
    names: dict[str, str] = {}
    for path in ("requirements.txt", "requirements-voice.txt"):
        for line in _dependency_lines(path):
            name = line.split("==", 1)[0].split("[", 1)[0].strip().lower()
            previous = names.get(name)
            if previous is None:
                names[name] = line
                continue
            version = line.split("==", 1)[1]
            previous_version = previous.split("==", 1)[1]
            assert version == previous_version, (
                f"versões conflitantes para {name}: "
                f"{previous} vs {line}"
            )
