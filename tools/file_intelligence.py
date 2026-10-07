from __future__ import annotations

import csv
import hashlib
import json
import mimetypes
import os
import stat
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from core.tool_result import ToolResult


SUPPORTED_READ_EXTENSIONS = frozenset({".txt", ".md", ".json", ".csv"})
READ_MAX_CHARS = 20_000
MAX_READ_OFFSET = 1_000_000
MAX_COPY_SCAN_FILES = 20_000
MAX_HASH_BYTES = 256 * 1024 * 1024
COPY_SEARCH_ROOT_NAMES = ("Downloads", "Desktop", "Documents")
ONEDRIVE_ALLOWED_SUBROOT_NAMES = ("Downloads", "Desktop", "Documents", "Área de Trabalho", "Documentos")


@dataclass(frozen=True)
class FileInfo:
    nome: str
    extensao: str
    tipo_detectado: str
    evidencia_tipo: str
    mime_type: str | None
    caminho: str
    tamanho_bytes: int
    tamanho_humano: str
    sha256: str | None
    datas: Mapping[str, str | None]
    estado: Mapping[str, Any]


@dataclass(frozen=True)
class FileOriginEvidence:
    status: str
    marcacao_zona_internet: str
    zone_id: int | None
    url_origem: str | None
    referrer_url: str | None
    aplicativo_origem: str | None
    autor: str | None
    empresa: str | None
    fabricante_software: str | None
    observacoes: tuple[str, ...] = ()


@dataclass(frozen=True)
class FileHistoryEvidence:
    status: str
    escopo_varredura: str
    copias_confirmadas: tuple[str, ...]
    relacao: str
    trajetoria_completa: str
    varredura_limitada: bool = False


@dataclass(frozen=True)
class FileContent:
    formato: str
    encoding: str
    inicio: int
    limite_caracteres: int
    conteudo: str
    vazio: bool
    truncado: bool
    proximo_inicio: int | None


def _same_file_identity(before: os.stat_result, after: os.stat_result) -> bool:
    before_identity = (
        getattr(before, "st_dev", None),
        getattr(before, "st_ino", None),
        getattr(before, "st_size", None),
        getattr(before, "st_mtime_ns", None),
    )
    after_identity = (
        getattr(after, "st_dev", None),
        getattr(after, "st_ino", None),
        getattr(after, "st_size", None),
        getattr(after, "st_mtime_ns", None),
    )
    if before_identity[:2] != (None, None) and after_identity[:2] != (None, None):
        if before_identity[:2] != after_identity[:2]:
            return False
    return before_identity[2:] == after_identity[2:]

def _human_size(size: int) -> str:
    value = float(max(0, size))
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def _format_timestamp(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return None


def _readable_probe(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            handle.read(1)
        return True
    except (OSError, PermissionError):
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_sample(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def _detect_encoding(path: Path) -> str:
    with path.open("rb") as handle:
        sample = handle.read(128 * 1024)
    if not sample:
        return "utf-8"
    _, encoding = _decode_sample(sample)
    return encoding


def _detect_type(path: Path) -> tuple[str, str, str | None]:
    extension = path.suffix.lower()
    mime = mimetypes.guess_type(path.name, strict=False)[0]
    if extension == ".md" and not mime:
        mime = "text/markdown"
    if extension == ".csv" and not mime:
        mime = "text/csv"

    if extension == ".json":
        try:
            if path.stat().st_size <= 1_000_000:
                text = path.read_text(encoding=_detect_encoding(path), errors="strict")
                json.loads(text)
                return "JSON", "extensao+conteudo_validado", "application/json"
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        return "JSON", "extensao", mime or "application/json"
    if extension == ".csv":
        try:
            sample = path.read_text(encoding=_detect_encoding(path), errors="strict")[:16_384]
            if sample.strip():
                csv.Sniffer().sniff(sample)
                return "CSV", "extensao+estrutura_csv", "text/csv"
        except (OSError, UnicodeDecodeError, csv.Error):
            pass
        return "CSV", "extensao", "text/csv"
    if extension == ".md":
        return "Markdown", "extensao", mime or "text/markdown"
    if extension == ".txt":
        return "Texto simples", "extensao", mime or "text/plain"

    try:
        with path.open("rb") as handle:
            signature = handle.read(16)
    except OSError:
        return "desconhecido", "nao_disponivel", mime

    if signature.startswith(b"%PDF-"):
        return "PDF", "assinatura_binaria", "application/pdf"
    if signature.startswith(b"PK\x03\x04"):
        return "ZIP/contêiner", "assinatura_binaria", mime or "application/zip"
    if signature.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG", "assinatura_binaria", "image/png"
    if signature.startswith(b"\xff\xd8\xff"):
        return "JPEG", "assinatura_binaria", "image/jpeg"
    if signature.startswith((b"GIF87a", b"GIF89a")):
        return "GIF", "assinatura_binaria", "image/gif"
    return "desconhecido", "assinatura_nao_reconhecida", mime


def _hidden_attribute(path: Path) -> bool | None:
    if os.name != "nt":
        return None
    try:
        import ctypes
        value = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if value == 0xFFFFFFFF:
            return None
        return bool(value & 0x2)
    except Exception:
        return None


def _owner(path: Path, file_stat: os.stat_result) -> str | None:
    if os.name == "nt":
        return None
    try:
        import pwd
        return pwd.getpwuid(file_stat.st_uid).pw_name
    except Exception:
        return None


def _state(path: Path, file_stat: os.stat_result, readable: bool) -> dict[str, Any]:
    return {
        "existe": True,
        "acessivel": readable,
        "somente_leitura": not bool(file_stat.st_mode & stat.S_IWRITE),
        "oculto": _hidden_attribute(path),
        "diretorio": False,
        "link_simbolico": path.is_symlink(),
        "atalho": None,
        "permissoes": oct(stat.S_IMODE(file_stat.st_mode)) if os.name != "nt" else None,
        "proprietario": _owner(path, file_stat),
    }


def _zone_identifier_text(path: Path) -> str | None:
    if os.name != "nt":
        return None
    try:
        with open(f"{path}:Zone.Identifier", "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(16 * 1024)
    except (OSError, PermissionError):
        return None


def _parse_zone_identifier(text_value: str | None) -> dict[str, Any]:
    result = {"zone_id": None, "host_url": None, "referrer_url": None}
    if not text_value:
        return result
    for raw_line in text_value.splitlines():
        line = raw_line.strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if key.strip() == "ZoneId":
            try:
                result["zone_id"] = int(value)
            except ValueError:
                pass
        elif key.strip() == "HostUrl":
            result["host_url"] = value or None
        elif key.strip() == "ReferrerUrl":
            result["referrer_url"] = value or None
    return result


def _origin(path: Path) -> FileOriginEvidence:
    zone = _parse_zone_identifier(_zone_identifier_text(path))
    zone_id = zone["zone_id"]
    internet_marked = "desconhecido"
    if zone_id is not None:
        internet_marked = "confirmado" if zone_id in {3, 4} else "nao_confirmado"

    observations = []
    if os.name != "nt":
        observations.append("Zone.Identifier so pode ser consultado no Windows.")
    if zone_id is None:
        observations.append("Nenhum Zone.Identifier acessivel foi encontrado.")
        status = "desconhecido"
    elif zone_id in {3, 4}:
        observations.append("Zone.Identifier indica origem em zona da Internet/Intranet.")
        status = "confirmado"
    else:
        observations.append(
            "Zone.Identifier foi encontrado, mas o ZoneId nao corresponde a uma zona "
            "tratada como origem da Internet/Intranet."
        )
        status = "nao_confirmado"

    return FileOriginEvidence(
        status=status,
        marcacao_zona_internet=internet_marked,
        zone_id=zone_id,
        url_origem=zone.get("host_url"),
        referrer_url=zone.get("referrer_url"),
        aplicativo_origem=None,
        autor=None,
        empresa=None,
        fabricante_software=None,
        observacoes=tuple(observations),
    )


def _copy_search_roots() -> list[Path]:
    roots: list[Path] = []
    userprofile_value = os.environ.get("USERPROFILE", "").strip()
    if userprofile_value:
        userprofile = Path(userprofile_value).expanduser()
        roots.extend(userprofile / name for name in COPY_SEARCH_ROOT_NAMES)

    for env_name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        value = os.environ.get(env_name, "").strip()
        if not value:
            continue
        root = Path(value)
        roots.extend(
            root / name
            for name in (
                "Downloads",
                "Desktop",
                "Área de Trabalho",
                "Documents",
                "Documentos",
            )
        )

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            if not root.exists() or not root.is_dir():
                continue
            key = str(root.resolve()).lower()
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _history(path: Path, digest: str | None, limit: int) -> FileHistoryEvidence:
    roots = _copy_search_roots()
    scope = ", ".join(str(root) for root in roots) if roots else "nenhuma raiz local de busca disponivel"
    if not digest:
        return FileHistoryEvidence(
            status="desconhecido",
            escopo_varredura=scope,
            copias_confirmadas=(),
            relacao="nao comparavel sem SHA-256",
            trajetoria_completa="desconhecida",
        )

    try:
        canonical_self = str(path.resolve()).lower()
        source_size = path.stat().st_size
    except OSError:
        canonical_self = str(path).lower()
        source_size = -1

    found: list[str] = []
    scanned = 0
    limited = False
    seen_paths: set[str] = set()
    for root in roots:
        if limited:
            break
        try:
            walker = os.walk(root, followlinks=False)
            for current, directories, filenames in walker:
                directories[:] = [d for d in directories if not Path(current, d).is_symlink()]
                for filename in filenames:
                    if scanned >= MAX_COPY_SCAN_FILES:
                        limited = True
                        break
                    candidate = Path(current) / filename
                    try:
                        key = str(candidate.resolve()).lower()
                    except OSError:
                        key = str(candidate).lower()
                    if key in seen_paths or key == canonical_self:
                        continue
                    seen_paths.add(key)
                    try:
                        candidate_stat = candidate.stat()
                    except OSError:
                        continue
                    scanned += 1
                    if candidate_stat.st_size != source_size:
                        continue
                    try:
                        if _sha256(candidate) == digest:
                            found.append(str(candidate.resolve()))
                            if len(found) >= limit:
                                return FileHistoryEvidence(
                                    status="confirmado",
                                    escopo_varredura=scope,
                                    copias_confirmadas=tuple(found),
                                    relacao="mesmo SHA-256; relacao confirmada por hash",
                                    trajetoria_completa="desconhecida",
                                )
                    except OSError:
                        continue
                if limited:
                    break
        except OSError:
            continue

    return FileHistoryEvidence(
        status="desconhecido" if limited else "confirmado",
        escopo_varredura=scope,
        copias_confirmadas=tuple(found),
        relacao=(
            "mesmo SHA-256; relacao confirmada por hash"
            if found
            else "nenhuma copia confirmada no escopo consultado"
        ),
        trajetoria_completa="desconhecida",
        varredura_limitada=limited,
    )




ALLOWED_READ_ROOT_NAMES = (
    "Downloads",
    "Desktop",
    "Documents",
    "Documentos",
    "Área de Trabalho",
)
SENSITIVE_PATH_COMPONENTS = frozenset({
    "appdata",
    ".ssh",
    ".aws",
})
_BROWSER_PROFILE_PATHS = (
    ("google", "chrome", "user data"),
    ("microsoft", "edge", "user data"),
    ("bravesoftware", "brave-browser", "user data"),
    ("chromium", "user data"),
    ("vivaldi", "user data"),
    ("opera software", "opera stable"),
    ("mozilla", "firefox", "profiles"),
)


@dataclass(frozen=True)
class FileReadPathPolicy:
    status: str
    motivo: str
    caminho_resolvido: str
    raiz_permitida: str | None


def _is_reparse_point(path: Path) -> bool:
    try:
        file_stat = path.lstat()
    except OSError:
        return True
    if path.is_symlink():
        return True
    atributos = int(getattr(file_stat, "st_file_attributes", 0) or 0)
    flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return bool(atributos & flag)

def _read_allowed_roots() -> list[Path]:
    roots: list[Path] = []
    profile_value = os.environ.get("USERPROFILE", "").strip()
    if profile_value:
        profile = Path(profile_value).expanduser()
    else:
        profile = Path.home()

    roots.extend(
        profile / name
        for name in (
            *ALLOWED_READ_ROOT_NAMES,
        )
    )

    onedrive_values = [
        os.environ.get(name, "").strip()
        for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")
    ]
    for value in onedrive_values:
        if value:
            raiz = Path(value).expanduser()
            roots.extend(raiz / nome for nome in ONEDRIVE_ALLOWED_SUBROOT_NAMES)

    # Em instalações comuns do Windows, o OneDrive pode existir mesmo quando
    # a variável de ambiente não foi propagada ao processo.
    raiz_padrao = profile / "OneDrive"
    roots.extend(raiz_padrao / nome for nome in ONEDRIVE_ALLOWED_SUBROOT_NAMES)

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            resolved = root.expanduser().resolve(strict=False)
        except OSError:
            resolved = root.expanduser().absolute()
        key = str(resolved).casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(resolved)
    return unique


def _path_is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _has_sensitive_path_component(path: Path) -> bool:
    parts = tuple(part.casefold() for part in path.parts)
    if any(part in SENSITIVE_PATH_COMPONENTS for part in parts):
        return True
    for pattern in _BROWSER_PROFILE_PATHS:
        size = len(pattern)
        if any(parts[index:index + size] == pattern for index in range(0, len(parts) - size + 1)):
            return True
    return False


def _onedrive_roots() -> list[Path]:
    roots: list[Path] = []
    profile_value = os.environ.get("USERPROFILE", "").strip()
    profile = Path(profile_value).expanduser() if profile_value else Path.home()
    for env_name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        value = os.environ.get(env_name, "").strip()
        if value:
            roots.append(Path(value).expanduser().resolve(strict=False))
    roots.append((profile / "OneDrive").resolve(strict=False))
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique

def _classify_read_path(path: Path) -> FileReadPathPolicy:
    """Classifica o caminho ja resolvido antes de qualquer leitura de conteudo."""
    if _has_sensitive_path_component(path):
        return FileReadPathPolicy(
            status="blocked",
            motivo="O caminho esta em uma pasta sensivel protegida (AppData, .ssh, .aws ou perfil de navegador).",
            caminho_resolvido=str(path),
            raiz_permitida=None,
        )

    for onedrive_root in _onedrive_roots():
        if not _path_is_relative_to(path, onedrive_root):
            continue
        allowed_one_drive_subroots = [
            onedrive_root / nome
            for nome in ONEDRIVE_ALLOWED_SUBROOT_NAMES
        ]
        if not any(_path_is_relative_to(path, subroot) for subroot in allowed_one_drive_subroots):
            return FileReadPathPolicy(
                status="confirm",
                motivo="O caminho esta dentro da raiz OneDrive, mas fora das subpastas explicitamente permitidas.",
                caminho_resolvido=str(path),
                raiz_permitida=None,
            )
    for root in _read_allowed_roots():
        if _path_is_relative_to(path, root):
            return FileReadPathPolicy(
                status="allowed",
                motivo="O caminho esta dentro de uma raiz local explicitamente permitida.",
                caminho_resolvido=str(path),
                raiz_permitida=str(root),
            )

    return FileReadPathPolicy(
        status="confirm",
        motivo="O caminho esta fora das raizes locais permitidas e exige confirmacao do usuario.",
        caminho_resolvido=str(path),
        raiz_permitida=None,
    )

def _resolve_path(value: str) -> Path:
    return Path(str(value or "").strip()).expanduser().resolve(strict=False)


def _absolute_unresolved_path(value: str | Path) -> Path:
    """Normaliza um caminho sem seguir links para permitir a inspeção de reparse points.\n    A função torna caminhos relativos absolutos e preserva a cadeia de diretórios sem resolver symlinks.\n    Custo: O(tamanho do caminho) em memória e tempo.\n    """
    raw = Path(str(value or "").strip()).expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    return Path(os.path.abspath(os.path.normpath(str(raw))))


def _existing_reparse_prefix(path: Path) -> Path | None:
    """Localiza um symlink, junction ou outro reparse point existente no caminho.\n    A inspeção para no primeiro componente inexistente e nunca segue o alvo de um link.\n    Custo: O(n) nos componentes existentes do caminho.\n    """
    current = Path(path.anchor) if path.anchor else Path()
    anchor_parts = Path(path.anchor).parts if path.anchor else ()
    for part in path.parts[len(anchor_parts):]:
        current = current / part
        try:
            current.lstat()
        except FileNotFoundError:
            break
        except OSError:
            return current
        if _is_reparse_point(current):
            return current
    return None


def _classify_write_path(value: str | Path) -> FileReadPathPolicy:
    """Classifica um caminho de escrita usando a allowlist e bloqueando reparse traversal.\n    Diferente da leitura, qualquer caminho fora das raízes permitidas é bloqueado para impedir confirmação que libere uma escrita.\n    Custo: O(n) nos componentes existentes do caminho, mais a classificação normal da allowlist.\n    """
    raw = str(value or "").strip()
    if not raw:
        return FileReadPathPolicy(
            status="blocked",
            motivo="O caminho e obrigatorio para operacoes de arquivo.",
            caminho_resolvido="",
            raiz_permitida=None,
        )

    absoluto = _absolute_unresolved_path(raw)
    reparse = _existing_reparse_prefix(absoluto)
    if reparse is not None:
        return FileReadPathPolicy(
            status="blocked",
            motivo=(
                "Operacao de arquivo bloqueada: o caminho atravessa um "
                "link simbolico, junction ou outro reparse point."
            ),
            caminho_resolvido=str(absoluto),
            raiz_permitida=None,
        )

    resolvido = absoluto.resolve(strict=False)
    leitura = _classify_read_path(resolvido)
    if leitura.status == "allowed":
        return leitura
    if leitura.status == "blocked":
        return leitura
    return FileReadPathPolicy(
        status="blocked",
        motivo=(
            "Operacoes de escrita so podem atuar dentro das pastas explicitamente "
            "permitidas; o caminho informado esta fora da allowlist."
        ),
        caminho_resolvido=str(resolvido),
        raiz_permitida=None,
    )


def _rename_destination(caminho: str | Path, novo_nome: str) -> Path:
    """Monta o destino de renome sem permitir que o novo nome escape da pasta de origem.\n    O nome deve ser um unico componente de arquivo e nao pode conter separadores, curingas ou caracteres de controle.\n    Custo: O(tamanho do novo nome) em tempo e O(1) em espaço adicional.\n    """
    nome = str(novo_nome or "").strip()
    if not nome or nome in {".", ".."}:
        raise ValueError("novo_nome deve conter um nome de arquivo valido")
    if Path(nome).name != nome or "/" in nome or "\\\\" in nome:
        raise ValueError("novo_nome deve ser um unico componente de arquivo")
    invalidos = set('<>:"/\\\\|?*')
    if any(ord(ch) < 32 or ch in invalidos for ch in nome):
        raise ValueError("novo_nome contem caracteres invalidos para o Windows")
    origem = _absolute_unresolved_path(caminho)
    return origem.with_name(nome)


def inspect_file(caminho: str, procurar_copias: bool = False, limite_copias: int = 5, *, caminho_confirmado: str | None = None) -> ToolResult:
    tool_name = "inspecionar_arquivo"
    raw = str(caminho or "").strip()
    if not raw:
        return ToolResult.failure("O caminho do arquivo e obrigatorio.", error_code="invalid_path", tool_name=tool_name)

    path = _resolve_path(raw)
    path_policy = _classify_read_path(path)
    if path_policy.status == "blocked":
        return ToolResult.failure(
            f"Leitura bloqueada por politica de caminho: {path}",
            error_code="sensitive_path_blocked",
            data={"caminho": str(path), "motivo": path_policy.motivo},
            tool_name=tool_name,
        )
    if path_policy.status == "confirm" and caminho_confirmado != path_policy.caminho_resolvido:
        return ToolResult.failure(
            f"Confirmacao necessaria para ler este caminho: {path}",
            error_code="path_confirmation_required",
            data={"caminho": str(path), "motivo": path_policy.motivo},
            tool_name=tool_name,
        )
    try:
        path.lstat()
    except FileNotFoundError:
        return ToolResult.failure(
            f"Arquivo nao encontrado: {path}",
            error_code="file_not_found",
            data={"caminho": str(path), "existe": False},
            tool_name=tool_name,
        )
    except OSError as exc:
        return ToolResult.failure(
            f"Nao foi possivel acessar o estado do arquivo: {exc}",
            error_code="file_inaccessible",
            data={"caminho": str(path), "existe": None},
            tool_name=tool_name,
        )

    if path.is_symlink() and not path.exists():
        return ToolResult.failure(
            f"O link simbolico existe, mas o alvo nao esta disponivel: {path}",
            error_code="file_not_found",
            data={"caminho": str(path), "existe": True, "link_simbolico": True, "alvo_existe": False},
            tool_name=tool_name,
        )

    if not path.is_file():
        return ToolResult.failure(
            f"O caminho informado nao e um arquivo regular: {path}",
            error_code="not_a_file",
            data={"caminho": str(path), "existe": True, "diretorio": path.is_dir()},
            tool_name=tool_name,
        )

    try:
        file_stat = path.stat()
    except OSError as exc:
        return ToolResult.failure(
            f"Nao foi possivel ler os metadados do arquivo: {exc}",
            error_code="file_inaccessible",
            data={"caminho": str(path), "existe": True},
            tool_name=tool_name,
        )

    readable = _readable_probe(path)
    detected_type, type_evidence, mime = _detect_type(path)
    digest = None
    hash_error = None
    if readable and (procurar_copias or file_stat.st_size <= MAX_HASH_BYTES):
        try:
            digest = _sha256(path)
        except (OSError, PermissionError) as exc:
            hash_error = str(exc)
    elif readable:
        hash_error = f"SHA-256 omitido para arquivo maior que {MAX_HASH_BYTES} bytes."

    info = FileInfo(
        nome=path.name,
        extensao=path.suffix.lower(),
        tipo_detectado=detected_type,
        evidencia_tipo=type_evidence,
        mime_type=mime,
        caminho=str(path),
        tamanho_bytes=file_stat.st_size,
        tamanho_humano=_human_size(file_stat.st_size),
        sha256=digest,
        datas={
            "criacao": _format_timestamp(file_stat.st_ctime) if os.name == "nt" else None,
            "modificacao": _format_timestamp(file_stat.st_mtime),
            "ultimo_acesso": _format_timestamp(file_stat.st_atime),
        },
        estado=_state(path, file_stat, readable),
    )
    origin = _origin(path)
    history = (
        _history(path, digest, max(1, min(int(limite_copias), 20)))
        if procurar_copias
        else FileHistoryEvidence(
            status="desconhecido",
            escopo_varredura="nao consultado",
            copias_confirmadas=(),
            relacao="nao consultado",
            trajetoria_completa="desconhecida",
        )
    )

    try:
        current_stat = path.stat()
    except OSError as exc:
        return ToolResult.failure(
            f"Nao foi possivel confirmar a estabilidade do arquivo: {exc}",
            error_code="path_changed_during_inspect",
            data={"caminho": str(path)},
            tool_name=tool_name,
        )
    if not _same_file_identity(file_stat, current_stat):
        return ToolResult.failure(
            "O arquivo mudou durante a inspeção e o resultado foi descartado.",
            error_code="path_changed_during_inspect",
            data={"caminho": str(path)},
            tool_name=tool_name,
        )
    data = {
        "file_info": asdict(info),
        "origem": asdict(origin),
        "historico": asdict(history),
        "limitacoes": {
            "formatos_leitura": sorted(SUPPORTED_READ_EXTENSIONS),
            "pdf": "tipo pode ser detectado por assinatura; leitura de conteudo nao implementada",
            "docx": "nao implementado",
            "xlsx": "nao implementado",
            "ocr": "nao implementado",
        },
    }
    if hash_error:
        data.setdefault("observacoes", []).append(str(hash_error))
    if os.name != "nt":
        data.setdefault("observacoes", []).append("Data de criacao do Windows e Zone.Identifier nao estao disponiveis neste ambiente.")

    return ToolResult.success(f"Arquivo inspecionado: {path.name}.", data=data, tool_name=tool_name)


def _read_text_range(path: Path, encoding: str, start: int, limit: int) -> tuple[str, bool]:
    with path.open("r", encoding=encoding, errors="strict", newline=None) as handle:
        remaining = start
        while remaining > 0:
            chunk = handle.read(min(64 * 1024, remaining))
            if not chunk:
                return "", False
            remaining -= len(chunk)
        content = handle.read(limit)
        return content, bool(handle.read(1))


def read_file(caminho: str, inicio: int = 0, limite_caracteres: int = 12_000, *, caminho_confirmado: str | None = None) -> ToolResult:
    tool_name = "ler_arquivo"
    raw = str(caminho or "").strip()
    if not raw:
        return ToolResult.failure("O caminho do arquivo e obrigatorio.", error_code="invalid_path", tool_name=tool_name)
    if not 0 <= inicio <= MAX_READ_OFFSET:
        return ToolResult.failure(
            f"Inicio fora do limite permitido: 0..{MAX_READ_OFFSET}.",
            error_code="invalid_offset",
            tool_name=tool_name,
        )
    if not 1 <= limite_caracteres <= READ_MAX_CHARS:
        return ToolResult.failure(
            f"Limite de caracteres fora do intervalo permitido: 1..{READ_MAX_CHARS}.",
            error_code="invalid_read_limit",
            tool_name=tool_name,
        )

    path = _resolve_path(raw)
    path_policy = _classify_read_path(path)
    if path_policy.status == "blocked":
        return ToolResult.failure(
            f"Leitura bloqueada por politica de caminho: {path}",
            error_code="sensitive_path_blocked",
            data={"caminho": str(path), "motivo": path_policy.motivo},
            tool_name=tool_name,
        )
    if path_policy.status == "confirm" and caminho_confirmado != path_policy.caminho_resolvido:
        return ToolResult.failure(
            f"Confirmacao necessaria para ler este caminho: {path}",
            error_code="path_confirmation_required",
            data={"caminho": str(path), "motivo": path_policy.motivo},
            tool_name=tool_name,
        )
    try:
        path_stat = path.stat()
    except FileNotFoundError:
        return ToolResult.failure(
            f"Arquivo nao encontrado: {path}",
            error_code="file_not_found",
            data={"caminho": str(path), "existe": False},
            tool_name=tool_name,
        )
    except OSError as exc:
        return ToolResult.failure(
            f"Nao foi possivel acessar o arquivo: {exc}",
            error_code="file_inaccessible",
            data={"caminho": str(path)},
            tool_name=tool_name,
        )

    if not path.is_file():
        return ToolResult.failure(
            f"O caminho informado nao e um arquivo regular: {path}",
            error_code="not_a_file",
            tool_name=tool_name,
        )

    extension = path.suffix.lower()
    if extension not in SUPPORTED_READ_EXTENSIONS:
        return ToolResult.failure(
            f"Formato nao suportado para leitura de conteudo: {extension or 'sem extensao'}.",
            error_code="unsupported_format",
            data={"caminho": str(path), "extensao": extension, "formatos_suportados": sorted(SUPPORTED_READ_EXTENSIONS)},
            tool_name=tool_name,
        )

    encoding = None
    try:
        encoding = _detect_encoding(path)
        content, truncated = _read_text_range(path, encoding, inicio, limite_caracteres)
    except UnicodeDecodeError as exc:
        return ToolResult.failure(
            f"Nao consegui decodificar o arquivo com seguranca: {exc}",
            error_code="encoding_error",
            data={"caminho": str(path), "encoding_tentado": encoding},
            tool_name=tool_name,
        )
    except (OSError, PermissionError) as exc:
        return ToolResult.failure(
            f"Falha de leitura do arquivo: {exc}",
            error_code="read_error",
            data={"caminho": str(path)},
            tool_name=tool_name,
        )

    try:
        current_stat = path.stat()
    except OSError as exc:
        return ToolResult.failure(
            f"Nao foi possivel confirmar a estabilidade do arquivo apos a leitura: {exc}",
            error_code="path_changed_during_read",
            data={"caminho": str(path)},
            tool_name=tool_name,
        )
    if not _same_file_identity(path_stat, current_stat):
        return ToolResult.failure(
            "O arquivo mudou durante a leitura e o resultado foi descartado.",
            error_code="path_changed_during_read",
            data={"caminho": str(path)},
            tool_name=tool_name,
        )
    result = FileContent(
        formato=extension.lstrip("."),
        encoding=encoding or "unknown",
        inicio=inicio,
        limite_caracteres=limite_caracteres,
        conteudo=content,
        vazio=path_stat.st_size == 0,
        truncado=truncated,
        proximo_inicio=(inicio + len(content)) if truncated else None,
    )
    return ToolResult.success(
        f"Conteudo lido de {path.name}." if content else f"O arquivo {path.name} esta vazio ou o inicio solicitado esta alem do conteudo.",
        data={
            "file_content": asdict(result),
            "arquivo": {"nome": path.name, "caminho": str(path), "tamanho_bytes": path_stat.st_size},
            "proxima_leitura": {"inicio": inicio + len(content)} if truncated else None,
        },
        tool_name=tool_name,
        conteudo_nao_confiavel=True,
    )


__all__ = [
    "FileInfo",
    "FileOriginEvidence",
    "FileHistoryEvidence",
    "FileContent",
    "SUPPORTED_READ_EXTENSIONS",
    "inspect_file",
    "read_file",
    "_parse_zone_identifier",
    "_history",
    "FileReadPathPolicy",
    "_classify_read_path",
]
