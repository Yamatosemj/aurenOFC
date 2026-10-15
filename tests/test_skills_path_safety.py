"""Seguranca das skills: somente caminhos locais contidos e documentos regulares.

Nao usa API, scripts de terceiros ou diretórios do usuario: todas as
provas de instalacao e descoberta usam apenas tmp_path.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from skills.loader import SkillLibrary


def _source(root: Path, name: str = "demo", *, text: str | None = None) -> Path:
    src = root / "fonte"
    src.mkdir(parents=True, exist_ok=True)
    (src / "SKILL.md").write_text(
        text if text is not None else f"---\nname: {name}\ndescription: habilidade de exemplo\n---\n# Guia\nconteudo de teste",
        encoding="utf-8",
    )
    return src


def _symlink(link: Path, destination: Path, *, directory: bool) -> None:
    try:
        link.symlink_to(destination, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Ambiente nao permite criar links simbolicos: {exc}")


def test_install_and_discover_valid_skill_and_safe_reinstall(tmp_path):
    source = _source(tmp_path)
    library = SkillLibrary(tmp_path / "skills")
    first = library.install(source)
    assert first.name == "demo"
    assert first.path == library.root / "demo" / "SKILL.md"
    assert len(library.discover()) == 1
    assert [item.name for item in library.match("guia exemplo")] == ["demo"]
    assert "conteudo de teste" in library.prompt_context("conteudo")

    (source / "SKILL.md").write_text(
        "---\nname: demo\ndescription: revisada\n---\n# Guia\natualizado",
        encoding="utf-8",
    )
    second = library.install(source / "SKILL.md")
    assert second.path.read_text(encoding="utf-8").endswith("atualizado")
    assert len(library.discover()) == 1


@pytest.mark.parametrize("name", [
    "../fora", r"..\fora", "../../fora", "/tmp/fora", r"C:\Windows\Temp",
    r"\\servidor\share", "D:arquivo", "foo/bar", r"foo\bar",
    ".", "..", "", " ", " com espacos", "com espacos ", "trailing.",
    "CON", "NUL.txt", "COM1", "LPT9", "a:ads", "foo?bar",
    "foo|bar", "foo\nbar", "A" * 101,
])
def test_explicit_name_traversal_or_invalid_is_rejected_without_changes(tmp_path, name):
    source = _source(tmp_path)
    root = tmp_path / "skills"
    sentinel = tmp_path / "fora" / "SKILL.md"
    sentinel.parent.mkdir()
    sentinel.write_text("intocavel", encoding="utf-8")
    with pytest.raises(ValueError):
        SkillLibrary(root).install(source, name=name)
    assert sentinel.read_text(encoding="utf-8") == "intocavel"
    assert not root.exists()


@pytest.mark.parametrize("frontmatter_name", [
    "../fora", r"..\fora", "/tmp/fora", r"C:\Users\publico",
    "CON", "foo/bar", "foo:ads",
])
def test_frontmatter_name_rejected_even_if_explicit_name_is_safe(tmp_path, frontmatter_name):
    source = _source(tmp_path, text=f"---\nname: '{frontmatter_name}'\n---\nTexto seguro")
    root = tmp_path / "skills"
    with pytest.raises(ValueError):
        SkillLibrary(root).install(source, name="aceitavel")
    assert not root.exists()


def test_symlinked_destination_directory_cannot_escape_root(tmp_path):
    source = _source(tmp_path)
    root = tmp_path / "skills"
    root.mkdir()
    outside = tmp_path / "fora"
    outside.mkdir()
    secret = outside / "SKILL.md"
    secret.write_text("sentinela", encoding="utf-8")
    _symlink(root / "demo", outside, directory=True)
    with pytest.raises(ValueError):
        SkillLibrary(root).install(source)
    assert secret.read_text(encoding="utf-8") == "sentinela"


def test_symlinked_destination_file_cannot_overwrite_other_file(tmp_path):
    source = _source(tmp_path)
    root = tmp_path / "skills"
    target_dir = root / "demo"
    target_dir.mkdir(parents=True)
    outside = tmp_path / "privado.md"
    outside.write_text("intocavel", encoding="utf-8")
    _symlink(target_dir / "SKILL.md", outside, directory=False)
    with pytest.raises(ValueError):
        SkillLibrary(root).install(source)
    assert outside.read_text(encoding="utf-8") == "intocavel"
    assert SkillLibrary(root).discover() == []


def test_dangling_destination_symlink_is_rejected(tmp_path):
    source = _source(tmp_path)
    root = tmp_path / "skills"
    target_dir = root / "demo"
    target_dir.mkdir(parents=True)
    _symlink(target_dir / "SKILL.md", tmp_path / "missing.md", directory=False)
    with pytest.raises(ValueError):
        SkillLibrary(root).install(source)


def test_discovery_does_not_read_symlink_file_even_inside_root(tmp_path):
    root = tmp_path / "skills"
    source = _source(tmp_path)
    lib = SkillLibrary(root)
    lib.install(source)
    another = root / "alias"
    another.mkdir()
    _symlink(another / "SKILL.md", root / "demo" / "SKILL.md", directory=False)
    found = lib.discover()
    assert [x.name for x in found] == ["demo"]


def test_discovery_ignores_symlink_directory_outside_root(tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text("---\nname: privado\n---\nsegredo", encoding="utf-8")
    _symlink(root / "external", outside, directory=True)
    assert SkillLibrary(root).discover() == []


def test_symlinked_source_skill_is_rejected(tmp_path):
    root = tmp_path / "skills"
    source = tmp_path / "fonte"
    source.mkdir()
    outside = tmp_path / "private.md"
    outside.write_text("---\nname: demo\n---\nconteudo", encoding="utf-8")
    _symlink(source / "SKILL.md", outside, directory=False)
    with pytest.raises(ValueError):
        SkillLibrary(root).install(source)
    assert not root.exists()


def test_symlinked_skill_root_is_rejected(tmp_path):
    source = _source(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "skills"
    _symlink(root, outside, directory=True)
    lib = SkillLibrary(root)
    with pytest.raises(ValueError):
        lib.install(source)
    assert lib.discover() == []
    assert list(outside.iterdir()) == []


def test_discovery_skips_invalid_frontmatter_without_importing_into_context(tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    unsafe = root / "valid-folder"
    unsafe.mkdir()
    (unsafe / "SKILL.md").write_text("---\nname: ../fora\n---\nconteudo", encoding="utf-8")
    lib = SkillLibrary(root)
    assert lib.discover() == []
    assert lib.prompt_context("fora") == ""
