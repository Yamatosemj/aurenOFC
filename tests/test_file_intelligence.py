from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.capabilities import CAPABILITY_REGISTRY
from core.permission_manager import PermissionLevel, PermissionManager
from core.tool_contracts import capability_for_tool, validate_tool_arguments
from core.tool_result import ToolResult
import tools.dispatcher as dispatcher
import tools.file_intelligence as file_intelligence
import tools.files as files
from tools.file_intelligence import READ_MAX_CHARS, _history, _parse_zone_identifier, inspect_file, read_file


def _args(path: Path) -> dict:
    return {"caminho": str(path), "procurar_copias": False, "limite_copias": 5}

@pytest.fixture(autouse=True)
def _allowed_test_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Mantem os testes existentes dentro de uma raiz permitida ficticia."""
    monkeypatch.setattr(file_intelligence, "_read_allowed_roots", lambda: [tmp_path.resolve()])
    original_sensitive = file_intelligence._has_sensitive_path_component

    def ignore_runner_appdata(path: Path) -> bool:
        try:
            relativo = Path(path).resolve().relative_to(tmp_path.resolve())
        except ValueError:
            relativo = Path(path)
        return original_sensitive(relativo)

    monkeypatch.setattr(
        file_intelligence,
        "_has_sensitive_path_component",
        ignore_runner_appdata,
    )


def test_inspect_existing_file_metadata_and_hash(tmp_path: Path):
    path = tmp_path / "relatorio.txt"
    path.write_text("abc", encoding="utf-8")
    result = inspect_file(str(path))
    assert result.ok
    info = result.data["file_info"]
    assert info["nome"] == "relatorio.txt"
    assert info["extensao"] == ".txt"
    assert info["tamanho_bytes"] == 3
    assert info["tamanho_humano"] == "3 B"
    assert info["sha256"] == hashlib.sha256(b"abc").hexdigest()
    assert info["tipo_detectado"] == "Texto simples"
    assert info["datas"]["modificacao"] is not None
    assert info["estado"]["existe"] is True


def test_inspect_state_attributes_are_explicit(tmp_path: Path):
    path = tmp_path / "atributos.txt"
    path.write_text("x", encoding="utf-8")
    result = inspect_file(str(path))
    assert result.ok
    state = result.data["file_info"]["estado"]
    assert {"existe", "acessivel", "somente_leitura", "oculto", "diretorio", "link_simbolico", "atalho", "permissoes", "proprietario"} <= set(state)
    assert state["diretorio"] is False
    assert state["link_simbolico"] is False


def test_inspect_missing_file_is_structured_failure(tmp_path: Path):
    result = inspect_file(str(tmp_path / "nao-existe.txt"))
    assert not result.ok
    assert result.error_code == "file_not_found"
    assert result.data["existe"] is False


def test_inspect_empty_file(tmp_path: Path):
    path = tmp_path / "vazio.txt"
    path.write_bytes(b"")
    result = inspect_file(str(path))
    assert result.ok
    assert result.data["file_info"]["tamanho_bytes"] == 0
    assert result.data["file_info"]["sha256"] == hashlib.sha256(b"").hexdigest()


def test_inspect_json_type_is_content_validated(tmp_path: Path):
    path = tmp_path / "dados.json"
    path.write_text(json.dumps({"a": 1}), encoding="utf-8")
    result = inspect_file(str(path))
    assert result.ok
    assert result.data["file_info"]["tipo_detectado"] == "JSON"
    assert "validado" in result.data["file_info"]["evidencia_tipo"]


def test_inspect_pdf_signature_does_not_claim_read_support(tmp_path: Path):
    path = tmp_path / "arquivo.bin"
    path.write_bytes(b"%PDF-1.7\n%fake")
    result = inspect_file(str(path))
    assert result.ok
    assert result.data["file_info"]["tipo_detectado"] == "PDF"
    assert "leitura de conteudo" in result.data["limitacoes"]["pdf"]


def test_inspect_origin_is_unknown_without_windows_zone_data(tmp_path: Path):
    path = tmp_path / "origem.txt"
    path.write_text("x", encoding="utf-8")
    result = inspect_file(str(path))
    assert result.ok
    assert result.data["origem"]["status"] == "desconhecido"
    assert result.data["origem"]["url_origem"] is None


def test_zone_identifier_parser_extracts_confirmed_evidence():
    parsed = _parse_zone_identifier(
        "[ZoneTransfer]\nZoneId=3\nHostUrl=https://example.com/a.txt\nReferrerUrl=https://example.com/\n"
    )
    assert parsed == {
        "zone_id": 3,
        "host_url": "https://example.com/a.txt",
        "referrer_url": "https://example.com/",
    }


def test_zone_identifier_parser_without_metadata_stays_unknown():
    assert _parse_zone_identifier(None) == {"zone_id": None, "host_url": None, "referrer_url": None}


def test_history_unavailable_without_hash(tmp_path: Path):
    path = tmp_path / "sem-hash.txt"
    path.write_text("x", encoding="utf-8")
    history = _history(path, None, 5)
    assert history.status == "desconhecido"
    assert history.copias_confirmadas == ()
    assert history.trajetoria_completa == "desconhecida"


def test_inspect_copy_with_same_hash_is_confirmed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    original = tmp_path / "origem.txt"
    copy = tmp_path / "sub" / "copia.txt"
    copy.parent.mkdir()
    original.write_text("mesmo", encoding="utf-8")
    copy.write_text("mesmo", encoding="utf-8")
    monkeypatch.setattr("tools.file_intelligence._copy_search_roots", lambda: [tmp_path])
    result = inspect_file(str(original), procurar_copias=True, limite_copias=5)
    assert result.ok
    history = result.data["historico"]
    assert str(copy.resolve()) in history["copias_confirmadas"]
    assert "SHA-256" in history["relacao"]
    assert history["trajetoria_completa"] == "desconhecida"


def test_inspect_different_content_is_not_a_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    original = tmp_path / "origem.txt"
    other = tmp_path / "outra.txt"
    original.write_text("um", encoding="utf-8")
    other.write_text("dois", encoding="utf-8")
    monkeypatch.setattr("tools.file_intelligence._copy_search_roots", lambda: [tmp_path])
    result = inspect_file(str(original), procurar_copias=True, limite_copias=5)
    assert result.ok
    assert result.data["historico"]["copias_confirmadas"] == ()
    assert result.data["historico"]["relacao"].startswith("nenhuma copia")


@pytest.mark.parametrize(
    ("suffix", "content"),
    [
        (".txt", "texto simples"),
        (".md", "# titulo\ncorpo"),
        (".json", '{"nome": "Auren"}'),
        (".csv", "nome,idade\nVictor,19\n"),
    ],
)
def test_read_supported_formats(tmp_path: Path, suffix: str, content: str):
    path = tmp_path / f"arquivo{suffix}"
    path.write_text(content, encoding="utf-8")
    result = read_file(str(path), 0, 200)
    assert result.ok
    assert result.data["file_content"]["conteudo"] == content
    assert result.data["file_content"]["truncado"] is False


def test_read_file_marks_content_as_untrusted(tmp_path: Path):
    path = tmp_path / "nao-confiavel.txt"
    path.write_text("conteudo externo", encoding="utf-8")

    result = read_file(str(path), 0, 200)

    assert result.ok is True
    assert result.conteudo_nao_confiavel is True
    assert "conteudo_nao_confiavel" in result.for_model()


def test_read_utf8_preserves_accents(tmp_path: Path):
    path = tmp_path / "acentos.txt"
    expected = "ação, café, coração"
    path.write_text(expected, encoding="utf-8")
    result = read_file(str(path), 0, 200)
    assert result.ok
    assert result.data["file_content"]["encoding"] == "utf-8"
    assert result.data["file_content"]["conteudo"] == expected


def test_read_empty_file(tmp_path: Path):
    path = tmp_path / "vazio.md"
    path.write_bytes(b"")
    result = read_file(str(path), 0, 200)
    assert result.ok
    assert result.data["file_content"]["vazio"] is True
    assert result.data["file_content"]["conteudo"] == ""


def test_read_large_file_is_bounded_and_returns_continuation(tmp_path: Path):
    path = tmp_path / "grande.txt"
    path.write_text("x" * (READ_MAX_CHARS + 500), encoding="utf-8")
    result = read_file(str(path), 0, READ_MAX_CHARS)
    assert result.ok
    content = result.data["file_content"]
    assert len(content["conteudo"]) == READ_MAX_CHARS
    assert content["truncado"] is True
    assert content["proximo_inicio"] == READ_MAX_CHARS


def test_read_supports_offset_for_future_continuation(tmp_path: Path):
    path = tmp_path / "offset.txt"
    path.write_text("0123456789", encoding="utf-8")
    result = read_file(str(path), 4, 3)
    assert result.ok
    assert result.data["file_content"]["conteudo"] == "456"
    assert result.data["proxima_leitura"]["inicio"] == 7


def test_read_unsupported_format(tmp_path: Path):
    path = tmp_path / "arquivo.pdf"
    path.write_bytes(b"%PDF-1.7")
    result = read_file(str(path))
    assert not result.ok
    assert result.error_code == "unsupported_format"


def test_read_error_is_not_reported_as_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "erro.txt"
    path.write_text("x", encoding="utf-8")
    monkeypatch.setattr("tools.file_intelligence._read_text_range", lambda *args: (_ for _ in ()).throw(OSError("bloqueado")))
    result = read_file(str(path))
    assert not result.ok
    assert result.error_code == "read_error"


def test_dispatcher_inspect_returns_tool_result(tmp_path: Path):
    path = tmp_path / "dispatcher.txt"
    path.write_text("ok", encoding="utf-8")
    result = dispatcher.executar_ferramenta(
        SimpleNamespace(name="inspecionar_arquivo", arguments=json.dumps(_args(path))),
        PermissionManager(max_actions=10),
        None,
    )
    assert isinstance(result, ToolResult)
    assert result.ok is True
    assert result.tool_name == "inspecionar_arquivo"


def test_dispatcher_read_returns_tool_result(tmp_path: Path):
    path = tmp_path / "dispatcher.txt"
    path.write_text("ok", encoding="utf-8")
    result = dispatcher.executar_ferramenta(
        SimpleNamespace(
            name="ler_arquivo",
            arguments=json.dumps({"caminho": str(path), "inicio": 0, "limite_caracteres": 100}),
        ),
        PermissionManager(max_actions=10),
        None,
    )
    assert isinstance(result, ToolResult)
    assert result.ok is True
    assert result.tool_name == "ler_arquivo"
    assert result.data["file_content"]["conteudo"] == "ok"


def test_file_capabilities_have_contract_and_auto_permission():
    assert capability_for_tool("buscar_arquivo") == "file.search"
    assert capability_for_tool("inspecionar_arquivo") == "file.inspect"
    assert capability_for_tool("ler_arquivo") == "file.read"
    manager = PermissionManager(max_actions=10)
    assert manager.nivel("inspecionar_arquivo") == PermissionLevel.AUTO
    assert manager.nivel("ler_arquivo") == PermissionLevel.AUTO
    assert manager.conta_para_limite("inspecionar_arquivo") is False
    assert manager.conta_para_limite("ler_arquivo") is False


def test_new_tools_have_valid_contract_samples():
    assert validate_tool_arguments(
        "inspecionar_arquivo",
        {"caminho": "C:\\temp\\a.txt", "procurar_copias": False, "limite_copias": 5},
    )[0]
    assert validate_tool_arguments(
        "ler_arquivo",
        {"caminho": "C:\\temp\\a.txt", "inicio": 0, "limite_caracteres": 100},
    )[0]


def test_router_includes_file_intelligence_tools():
    from core.router import Router
    available = [
        {"name": "buscar_arquivo"},
        {"name": "inspecionar_arquivo"},
        {"name": "ler_arquivo"},
        {"name": "abrir_programa"},
        {"name": "obter_status_windows"},
    ]
    selected = {item["name"] for item in Router().select_tools("leia este arquivo", available)}
    assert {"buscar_arquivo", "inspecionar_arquivo", "ler_arquivo"} <= selected


def test_capability_registry_exposes_file_inspection_and_read():
    assert CAPABILITY_REGISTRY.get("inspecionar_arquivo") is not None
    assert CAPABILITY_REGISTRY.get("ler_arquivo") is not None
    assert CAPABILITY_REGISTRY.get("inspecionar_arquivo").tools == ("inspecionar_arquivo",)
    assert CAPABILITY_REGISTRY.get("ler_arquivo").tools == ("ler_arquivo",)



def test_requested_trusted_root_names_are_recognized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    profile = tmp_path / "perfil"
    profile.mkdir()
    monkeypatch.setenv("USERPROFILE", str(profile))
    monkeypatch.delenv("OneDrive", raising=False)
    monkeypatch.delenv("OneDriveConsumer", raising=False)
    monkeypatch.delenv("OneDriveCommercial", raising=False)

    real_read_allowed_roots = file_intelligence._read_allowed_roots
    monkeypatch.setattr(file_intelligence, "_read_allowed_roots", real_read_allowed_roots)

    for root_name in ("Downloads", "Desktop", "Documents"):
        root = profile / root_name
        root.mkdir()
        path = root / "arquivo.txt"
        path.write_text("ok", encoding="utf-8")
        result = read_file(str(path))
        assert result.ok is True


def test_read_and_inspect_outside_allowlist_require_confirmation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    allowed = tmp_path / "Desktop"
    allowed.mkdir()
    outside = tmp_path.parent / "arquivo-fora.txt"
    outside.write_text("segredo", encoding="utf-8")
    monkeypatch.setattr(file_intelligence, "_read_allowed_roots", lambda: [allowed.resolve()])

    read_result = read_file(str(outside))
    inspect_result = inspect_file(str(outside))

    assert read_result.ok is False
    assert read_result.error_code == "path_confirmation_required"
    assert inspect_result.ok is False
    assert inspect_result.error_code == "path_confirmation_required"


def test_parent_traversal_is_resolved_before_allowlist_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    allowed = tmp_path / "Desktop"
    nested = allowed / "nested"
    nested.mkdir(parents=True)
    outside = tmp_path / "fora.txt"
    outside.write_text("fora", encoding="utf-8")
    monkeypatch.setattr(file_intelligence, "_read_allowed_roots", lambda: [allowed.resolve()])

    traversal = nested / ".." / ".." / "fora.txt"
    result = read_file(str(traversal))

    assert result.ok is False
    assert result.error_code == "path_confirmation_required"
    assert str(outside.resolve()) == result.data["caminho"]


def test_symlink_to_outside_is_not_covered_by_allowed_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    allowed = tmp_path / "Desktop"
    target_dir = tmp_path / "fora"
    allowed.mkdir()
    target_dir.mkdir()
    target = target_dir / "segredo.txt"
    target.write_text("nao ler automaticamente", encoding="utf-8")
    link = allowed / "atalho.txt"
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.skip(f"ambiente nao permite criar symlink: {exc}")

    monkeypatch.setattr(file_intelligence, "_read_allowed_roots", lambda: [allowed.resolve()])
    result = read_file(str(link))

    assert result.ok is False
    assert result.error_code == "path_confirmation_required"
    assert result.data["caminho"] == str(target.resolve())


def test_browser_profile_folder_is_blocked_even_inside_onedrive_like_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    allowed = tmp_path / "OneDrive"
    profile = allowed / "Google" / "Chrome" / "User Data" / "Default" / "History"
    profile.parent.mkdir(parents=True)
    profile.write_text("historico", encoding="utf-8")
    monkeypatch.setattr(file_intelligence, "_read_allowed_roots", lambda: [allowed.resolve()])

    result = read_file(str(profile))

    assert result.ok is False
    assert result.error_code == "sensitive_path_blocked"


def test_sensitive_folder_is_blocked_even_inside_allowed_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    allowed = tmp_path / "Desktop"
    sensitive = allowed / "AppData" / "config.txt"
    sensitive.parent.mkdir(parents=True)
    sensitive.write_text("credencial", encoding="utf-8")
    monkeypatch.setattr(file_intelligence, "_read_allowed_roots", lambda: [allowed.resolve()])

    read_result = read_file(str(sensitive))
    inspect_result = inspect_file(str(sensitive))

    assert read_result.ok is False
    assert read_result.error_code == "sensitive_path_blocked"
    assert inspect_result.ok is False
    assert inspect_result.error_code == "sensitive_path_blocked"


class _RecordingConfirmationChannel:
    def __init__(self, approved: bool):
        self.approved = approved
        self.requests = []

    def confirmar(self, request):
        self.requests.append(request)
        return self.approved


def test_permission_manager_confirms_file_path_outside_allowlist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    allowed = tmp_path / "Desktop"
    allowed.mkdir()
    outside = tmp_path.parent / "fora-permissao.txt"
    outside.write_text("x", encoding="utf-8")
    monkeypatch.setattr(file_intelligence, "_read_allowed_roots", lambda: [allowed.resolve()])

    channel = _RecordingConfirmationChannel(True)
    manager = PermissionManager(confirmation_channel=channel)
    permitido, motivo = manager.autorizar(
        "ler_arquivo",
        {"caminho": str(outside), "inicio": 0, "limite_caracteres": 100},
    )

    assert permitido is True
    assert motivo == "Usuario confirmou a acao."
    assert len(channel.requests) == 1
    assert channel.requests[0].tool_name == "ler_arquivo"
    assert "fora das raizes locais permitidas" in channel.requests[0].reason


def test_permission_manager_denies_outside_allowlist_when_user_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    allowed = tmp_path / "Desktop"
    allowed.mkdir()
    outside = tmp_path.parent / "fora-negada.txt"
    outside.write_text("nao ler", encoding="utf-8")
    monkeypatch.setattr(file_intelligence, "_read_allowed_roots", lambda: [allowed.resolve()])

    channel = _RecordingConfirmationChannel(False)
    manager = PermissionManager(confirmation_channel=channel)
    permitido, motivo = manager.autorizar(
        "ler_arquivo",
        {"caminho": str(outside), "inicio": 0, "limite_caracteres": 100},
    )

    assert permitido is False
    assert motivo == "Usuario negou a acao."
    assert len(channel.requests) == 1
    assert "fora das raizes locais permitidas" in channel.requests[0].reason


def test_permission_manager_blocks_sensitive_file_path_without_confirmation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    allowed = tmp_path / "Desktop"
    sensitive = allowed / ".ssh" / "config.txt"
    sensitive.parent.mkdir(parents=True)
    sensitive.write_text("chave", encoding="utf-8")
    monkeypatch.setattr(file_intelligence, "_read_allowed_roots", lambda: [allowed.resolve()])

    channel = _RecordingConfirmationChannel(True)
    manager = PermissionManager(confirmation_channel=channel)
    permitido, motivo = manager.autorizar(
        "inspecionar_arquivo",
        {"caminho": str(sensitive), "procurar_copias": False, "limite_copias": 5},
    )

    assert permitido is False
    assert "sensivel" in motivo
    assert channel.requests == []


def test_dispatcher_confirmed_path_is_really_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    allowed = tmp_path / "Desktop"
    allowed.mkdir()
    outside = tmp_path.parent / "fora-dispatcher.txt"
    outside.write_text("conteudo confirmado", encoding="utf-8")
    monkeypatch.setattr(file_intelligence, "_read_allowed_roots", lambda: [allowed.resolve()])

    channel = _RecordingConfirmationChannel(True)
    manager = PermissionManager(confirmation_channel=channel)
    result = dispatcher.executar_ferramenta(
        SimpleNamespace(
            name="ler_arquivo",
            arguments=json.dumps({"caminho": str(outside), "inicio": 0, "limite_caracteres": 100}),
        ),
        manager,
        None,
    )

    assert result.ok is True
    assert result.data["file_content"]["conteudo"] == "conteudo confirmado"
    assert len(channel.requests) == 1


def test_dispatcher_does_not_bypass_sensitive_path_with_confirmation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    allowed = tmp_path / "Desktop"
    sensitive = allowed / ".aws" / "credentials.txt"
    sensitive.parent.mkdir(parents=True)
    sensitive.write_text("access_key", encoding="utf-8")
    monkeypatch.setattr(file_intelligence, "_read_allowed_roots", lambda: [allowed.resolve()])

    channel = _RecordingConfirmationChannel(True)
    manager = PermissionManager(confirmation_channel=channel)
    result = dispatcher.executar_ferramenta(
        SimpleNamespace(
            name="ler_arquivo",
            arguments=json.dumps({"caminho": str(sensitive), "inicio": 0, "limite_caracteres": 100}),
        ),
        manager,
        None,
    )

    assert result.ok is False
    assert result.error_code == "permission_denied"
    assert channel.requests == []


def test_one_drive_root_itself_is_not_an_implicit_read_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    profile = tmp_path / "perfil"
    onedrive = profile / "OneDrive"
    onedrive.mkdir(parents=True)
    arquivo = onedrive / "Privado" / "arquivo.txt"
    arquivo.parent.mkdir()
    arquivo.write_text("privado", encoding="utf-8")

    monkeypatch.setenv("USERPROFILE", str(profile))
    monkeypatch.setenv("OneDrive", str(onedrive))
    monkeypatch.delenv("OneDriveConsumer", raising=False)
    monkeypatch.delenv("OneDriveCommercial", raising=False)

    result = read_file(str(arquivo))

    assert result.ok is False
    assert result.error_code == "path_confirmation_required"


def test_same_file_identity_detects_metadata_change(tmp_path: Path):
    path = tmp_path / "arquivo.txt"
    path.write_text("abc", encoding="utf-8")
    before = path.stat()
    path.write_text("abcd", encoding="utf-8")
    after = path.stat()

    assert file_intelligence._same_file_identity(before, after) is False


def test_inspect_large_file_skips_sha256_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    allowed = tmp_path / "Desktop"
    allowed.mkdir()
    path = allowed / "grande.txt"
    with path.open("wb") as handle:
        handle.truncate(file_intelligence.MAX_HASH_BYTES + 1)

    monkeypatch.setattr(file_intelligence, "_read_allowed_roots", lambda: [allowed.resolve()])

    def fail_sha256(_path):
        raise AssertionError("SHA-256 nao deveria ser calculado para arquivo gigante sem procurar copias.")

    monkeypatch.setattr(file_intelligence, "_sha256", fail_sha256)

    result = inspect_file(str(path), procurar_copias=False)

    assert result.ok is True
    assert result.data["file_info"]["sha256"] is None
    assert "SHA-256 omitido" in " ".join(result.data.get("observacoes", []))


def test_inspect_rejects_changed_file_identity(monkeypatch, tmp_path: Path):
    allowed = tmp_path / "Desktop"
    allowed.mkdir()
    path = allowed / "mutavel.txt"
    path.write_text("abc", encoding="utf-8")

    monkeypatch.setattr(file_intelligence, "_read_allowed_roots", lambda: [allowed.resolve()])
    monkeypatch.setattr(file_intelligence, "_same_file_identity", lambda _before, _after: False)

    result = inspect_file(str(path), procurar_copias=False)

    assert result.ok is False
    assert result.error_code == "path_changed_during_inspect"


def test_read_rejects_changed_file_identity(monkeypatch, tmp_path: Path):
    allowed = tmp_path / "Desktop"
    allowed.mkdir()
    path = allowed / "mutavel.txt"
    path.write_text("conteudo", encoding="utf-8")

    monkeypatch.setattr(file_intelligence, "_read_allowed_roots", lambda: [allowed.resolve()])
    monkeypatch.setattr(file_intelligence, "_same_file_identity", lambda _before, _after: False)

    result = read_file(str(path), 0, 100)

    assert result.ok is False
    assert result.error_code == "path_changed_during_read"


def test_busca_arquivo_ignora_symlink_para_fora_da_raiz(tmp_path, monkeypatch):
    allowed = tmp_path / "Desktop"
    allowed.mkdir()
    outside = tmp_path / "privado.txt"
    outside.write_text("segredo fora", encoding="utf-8")
    link = allowed / "atalho.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink nao disponivel neste ambiente")

    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    resultado = files.buscar_arquivo("atalho")

    assert "atalho.txt" not in resultado
    assert "privado.txt" not in resultado
