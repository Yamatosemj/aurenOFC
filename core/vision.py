from __future__ import annotations

import base64
import contextvars
import io
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)


_ACTIVE_VISION_GEOMETRY: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "auren_active_vision_geometry",
    default=None,
)


def set_active_vision_geometry(geometry: dict | None) -> None:
    """Vincula o snapshot visual atual ao contexto de execucao do Auren."""
    _ACTIVE_VISION_GEOMETRY.set(dict(geometry) if geometry is not None else None)


def clear_active_vision_geometry() -> None:
    """Remove qualquer snapshot visual herdado por uma tarefa anterior."""
    _ACTIVE_VISION_GEOMETRY.set(None)


def get_active_vision_geometry() -> dict | None:
    """Retorna uma copia do snapshot visual atualmente vinculado."""
    geometry = _ACTIVE_VISION_GEOMETRY.get()
    return dict(geometry) if geometry is not None else None


def _vision_snapshot_id(capture_data: dict) -> str:
    explicit = str(capture_data.get("vision_snapshot_id") or "").strip()
    if explicit:
        return explicit

    image_path = str(capture_data.get("image_path") or "").strip()
    if image_path:
        return Path(image_path).stem

    return ""


class PreparedImageInput:
    """Imagem realmente entregue ao modelo e sua geometria de referência."""

    item: dict
    source_width: int | None
    source_height: int | None
    sent_width: int | None
    sent_height: int | None
    mime_type: str
    resized: bool
    compressed: bool

    @property
    def scale_x_to_source(self) -> float | None:
        if not self.source_width or not self.sent_width:
            return None
        return self.source_width / self.sent_width

    @property
    def scale_y_to_source(self) -> float | None:
        if not self.source_height or not self.sent_height:
            return None
        return self.source_height / self.sent_height

    def metadata(self) -> dict:
        payload = asdict(self)
        payload.pop("item", None)
        payload["scale_x_to_source"] = self.scale_x_to_source
        payload["scale_y_to_source"] = self.scale_y_to_source
        return payload


def _imagem_pil(path: Path):
    try:
        from PIL import Image
        return Image.open(path)
    except Exception:
        return None


def _codificar_com_png_ou_jpeg(
    image,
    *,
    max_bytes: int,
) -> tuple[bytes, str, bool] | None:
    """Tenta manter dimensoes e reduzir apenas a codificacao antes de redimensionar."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    data = buffer.getvalue()
    if len(data) <= max_bytes:
        return data, "image/png", True

    # JPEG preserva a geometria e oferece uma queda de tamanho muito maior
    # para screenshots fotograficos/cheios de detalhes.
    for quality in (82, 70, 55, 40):
        buffer = io.BytesIO()
        image.convert("RGB").save(
            buffer,
            format="JPEG",
            quality=quality,
            optimize=True,
        )
        data = buffer.getvalue()
        if len(data) <= max_bytes:
            return data, "image/jpeg", True

    return data, "image/jpeg", False


def prepare_image_input(
    path: str | Path,
    *,
    max_bytes: int = 5_000_000,
    max_width: int = 1920,
    preserve_dimensions: bool = False,
) -> PreparedImageInput | None:
    """Prepara uma imagem e registra exatamente sua geometria antes do envio."""
    source = Path(path)
    if not source.is_file() or max_bytes <= 0 or max_width <= 0:
        return None

    mime_original = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(source.suffix.lower())
    if mime_original is None:
        return None

    data = source.read_bytes()
    imagem = None
    source_width: int | None = None
    source_height: int | None = None

    # Para screenshots e qualquer imagem que possa precisar de transformação,
    # abrimos o arquivo para que a geometria enviada ao modelo possa ser medida.
    if preserve_dimensions or len(data) > max_bytes:
        imagem = _imagem_pil(source)
        if imagem is None:
            return None
        source_width, source_height = map(int, imagem.size)

    resized = False
    compressed = False
    mime = mime_original

    if len(data) > max_bytes:
        if imagem is None:
            return None

        candidata = imagem
        if (
            not preserve_dimensions
            and source_width
            and source_height
            and source_width > max_width
        ):
            proporcao = max_width / float(source_width)
            tamanho = (
                max_width,
                max(1, int(round(source_height * proporcao))),
            )
            candidata = imagem.resize(tamanho)
            resized = candidata.size != imagem.size

        resultado = _codificar_com_png_ou_jpeg(
            candidata,
            max_bytes=max_bytes,
        )

        # Se foi pedido preservar dimensoes (caso de screenshots), só
        # redimensionamos como ultimo recurso quando a compressao nao coube.
        if resultado is not None and not resultado[2] and candidata.size[0] > max_width:
            proporcao = max_width / float(candidata.size[0])
            tamanho = (
                max_width,
                max(1, int(round(candidata.size[1] * proporcao))),
            )
            candidata = candidata.resize(tamanho)
            resized = True
            resultado = _codificar_com_png_ou_jpeg(
                candidata,
                max_bytes=max_bytes,
            )

        if resultado is None or not resultado[2]:
            return None

        data, mime, _ = resultado
        compressed = True
        sent_width, sent_height = map(int, candidata.size)
    else:
        if source_width is not None and source_height is not None:
            sent_width, sent_height = source_width, source_height
        else:
            sent_width = sent_height = None

    if len(data) > max_bytes:
        return None

    encoded = base64.b64encode(data).decode("ascii")
    item = {
        "type": "input_image",
        "image_url": f"data:{mime};base64,{encoded}",
    }

    return PreparedImageInput(
        item=item,
        source_width=source_width,
        source_height=source_height,
        sent_width=sent_width,
        sent_height=sent_height,
        mime_type=mime,
        resized=resized,
        compressed=compressed,
    )


def image_point_to_virtual_screen(
    x_image,
    y_image,
    *,
    image_width: int,
    image_height: int,
    virtual_screen_x: int,
    virtual_screen_y: int,
    virtual_screen_width: int,
    virtual_screen_height: int,
    aspect_tolerance: float = 0.01,
) -> tuple[int, int]:
    """Converte um ponto da imagem completa da tela para coordenadas Windows."""
    valores = (
        x_image,
        y_image,
        image_width,
        image_height,
        virtual_screen_x,
        virtual_screen_y,
        virtual_screen_width,
        virtual_screen_height,
    )
    if any(isinstance(value, bool) for value in valores):
        raise ValueError("Dimensoes e coordenadas devem ser numericas, nao booleanas.")

    try:
        x_image = float(x_image)
        y_image = float(y_image)
        image_width = int(image_width)
        image_height = int(image_height)
        virtual_screen_x = int(virtual_screen_x)
        virtual_screen_y = int(virtual_screen_y)
        virtual_screen_width = int(virtual_screen_width)
        virtual_screen_height = int(virtual_screen_height)
        aspect_tolerance = float(aspect_tolerance)
    except (TypeError, ValueError, OverflowError) as erro:
        raise ValueError("Geometria ou coordenadas invalidas.") from erro

    if image_width <= 0 or image_height <= 0:
        raise ValueError("Dimensoes da imagem devem ser positivas.")
    if virtual_screen_width <= 0 or virtual_screen_height <= 0:
        raise ValueError("Dimensoes da tela virtual devem ser positivas.")
    if not 0 <= aspect_tolerance < 1:
        raise ValueError("aspect_tolerance deve estar entre 0 e 1.")

    if not 0 <= x_image < image_width or not 0 <= y_image < image_height:
        raise ValueError(
            "Coordenada da imagem fora dos limites da imagem observada."
        )

    escala_x = virtual_screen_width / float(image_width)
    escala_y = virtual_screen_height / float(image_height)
    diferenca_relativa = abs(escala_x - escala_y) / max(escala_x, escala_y)

    if diferenca_relativa > aspect_tolerance:
        raise ValueError(
            "A proporcao da imagem nao corresponde a area de trabalho virtual; "
            "nao e seguro converter a coordenada silenciosamente."
        )

    x_windows = virtual_screen_x + round(x_image * escala_x)
    y_windows = virtual_screen_y + round(y_image * escala_y)

    x_windows = min(
        max(x_windows, virtual_screen_x),
        virtual_screen_x + virtual_screen_width - 1,
    )
    y_windows = min(
        max(y_windows, virtual_screen_y),
        virtual_screen_y + virtual_screen_height - 1,
    )
    return x_windows, y_windows


def build_vision_geometry(
    capture_data: dict,
    prepared: PreparedImageInput,
) -> dict | None:
    """Constroi o estado confiavel que o modelo usa ao interpretar coordenadas."""
    try:
        virtual_x = int(capture_data["virtual_screen_x"])
        virtual_y = int(capture_data["virtual_screen_y"])
        virtual_width = int(capture_data["virtual_screen_width"])
        virtual_height = int(capture_data["virtual_screen_height"])
        capture_width = int(capture_data["image_width"])
        capture_height = int(capture_data["image_height"])
        sent_width = int(prepared.sent_width)
        sent_height = int(prepared.sent_height)
    except (KeyError, TypeError, ValueError):
        return None

    if min(
        virtual_width,
        virtual_height,
        capture_width,
        capture_height,
        sent_width,
        sent_height,
    ) <= 0:
        return None

    snapshot_id = _vision_snapshot_id(capture_data)
    captura_consistente = (
        prepared.source_width is None
        or (
            prepared.source_width == capture_width
            and prepared.source_height == capture_height
        )
    )

    escala_x = virtual_width / float(sent_width)
    escala_y = virtual_height / float(sent_height)
    diferenca_relativa = abs(escala_x - escala_y) / max(escala_x, escala_y)

    proporcao_compativel = diferenca_relativa <= 0.01
    dpi_contexto_verificado = capture_data.get("dpi_per_monitor_aware") is True

    transformacao_segura = bool(
        snapshot_id
        and captura_consistente
        and proporcao_compativel
        and dpi_contexto_verificado
    )

    return {
        "tipo": "vision_geometry",
        "vision_snapshot_id": snapshot_id,
        "coordenadas_acao": "windows_virtual_screen_physical_pixels",
        "transformacao_segura": transformacao_segura,
        "dpi_contexto_verificado": dpi_contexto_verificado,
        "imagem_enviada_ao_modelo": {"width": sent_width, "height": sent_height},
        "captura_original": {"width": capture_width, "height": capture_height},
        "captura_vs_arquivo_consistente": captura_consistente,
        "area_de_trabalho_virtual_windows": {
            "x": virtual_x, "y": virtual_y,
            "width": virtual_width, "height": virtual_height,
        },
        "escala_imagem_para_windows": {"x": escala_x, "y": escala_y},
        "aspect_ratio_compativel": proporcao_compativel,
        "imagem_redimensionada": prepared.resized,
        "imagem_comprimida": prepared.compressed,
        "mime_type_enviado": prepared.mime_type,
    }


def transform_visual_tool_arguments(
    tool_name: str,
    arguments: dict,
) -> tuple[dict, dict | None, str | None]:
    """Converte pixels da visao em coordenadas fisicas antes da execucao."""
    if tool_name not in {"clicar_mouse_windows", "arrastar_mouse_windows"}:
        return dict(arguments), None, None

    coordinate_space = str(arguments.get("coordinate_space") or "windows").strip().lower()
    snapshot_id = str(arguments.get("vision_snapshot_id") or "").strip()
    usa_snapshot_visual = coordinate_space == "vision_image" or bool(snapshot_id)

    if not usa_snapshot_visual:
        return dict(arguments), None, None

    if coordinate_space not in {"vision_image", "windows"}:
        return dict(arguments), None, "Espaco de coordenadas invalido. Use 'windows' ou 'vision_image'."

    geometry = get_active_vision_geometry()
    if geometry is None:
        return dict(arguments), None, "Nao existe um snapshot visual ativo para converter esta coordenada."

    esperado = str(geometry.get("vision_snapshot_id") or "").strip()
    if not snapshot_id or snapshot_id != esperado:
        return (
            dict(arguments),
            None,
            "O snapshot visual informado nao corresponde a captura mais recente. "
            "Capture a tela novamente antes de usar coordenadas da imagem.",
        )

    if geometry.get("transformacao_segura") is not True:
        return (
            dict(arguments),
            None,
            "A geometria da visao nao foi validada para conversao segura. "
            "Capture a tela novamente ou use um controle exposto por UI Automation.",
        )

    try:
        image_width = int(geometry["imagem_enviada_ao_modelo"]["width"])
        image_height = int(geometry["imagem_enviada_ao_modelo"]["height"])
        virtual_x = int(geometry["area_de_trabalho_virtual_windows"]["x"])
        virtual_y = int(geometry["area_de_trabalho_virtual_windows"]["y"])
        virtual_width = int(geometry["area_de_trabalho_virtual_windows"]["width"])
        virtual_height = int(geometry["area_de_trabalho_virtual_windows"]["height"])
    except (KeyError, TypeError, ValueError):
        return dict(arguments), None, "O snapshot visual ativo nao possui geometria suficiente para conversao."

    execution = dict(arguments)
    try:
        if tool_name == "clicar_mouse_windows":
            x_windows, y_windows = image_point_to_virtual_screen(
                arguments["x"], arguments["y"],
                image_width=image_width, image_height=image_height,
                virtual_screen_x=virtual_x, virtual_screen_y=virtual_y,
                virtual_screen_width=virtual_width, virtual_screen_height=virtual_height,
            )
            execution.update({"x": x_windows, "y": y_windows})
            pontos = {
                "origem_imagem": {"x": arguments["x"], "y": arguments["y"]},
                "destino_windows": {"x": x_windows, "y": y_windows},
            }
        else:
            origem_x, origem_y = image_point_to_virtual_screen(
                arguments["x_inicial"], arguments["y_inicial"],
                image_width=image_width, image_height=image_height,
                virtual_screen_x=virtual_x, virtual_screen_y=virtual_y,
                virtual_screen_width=virtual_width, virtual_screen_height=virtual_height,
            )
            destino_x, destino_y = image_point_to_virtual_screen(
                arguments["x_final"], arguments["y_final"],
                image_width=image_width, image_height=image_height,
                virtual_screen_x=virtual_x, virtual_screen_y=virtual_y,
                virtual_screen_width=virtual_width, virtual_screen_height=virtual_height,
            )
            execution.update({
                "x_inicial": origem_x, "y_inicial": origem_y,
                "x_final": destino_x, "y_final": destino_y,
            })
            pontos = {
                "origem_imagem": {"x": arguments["x_inicial"], "y": arguments["y_inicial"]},
                "destino_imagem": {"x": arguments["x_final"], "y": arguments["y_final"]},
                "origem_windows": {"x": origem_x, "y": origem_y},
                "destino_windows": {"x": destino_x, "y": destino_y},
            }
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return dict(arguments), None, f"Coordenada visual rejeitada: {exc}"

    execution["coordinate_space"] = "windows"
    execution.pop("vision_snapshot_id", None)
    metadata = {
        "snapshot_id": esperado,
        "imagem": {"width": image_width, "height": image_height},
        "virtual_screen": {
            "x": virtual_x, "y": virtual_y,
            "width": virtual_width, "height": virtual_height,
        },
        "escala_imagem_para_windows": dict(geometry.get("escala_imagem_para_windows") or {}),
        "pontos": pontos,
    }
    return execution, metadata, None


def image_input_item(
    path: str | Path,
    *,
    max_bytes: int = 5_000_000,
    max_width: int = 1920,
) -> dict | None:
    """Mantem a API legada retornando apenas o input_image."""
    preparado = prepare_image_input(
        path,
        max_bytes=max_bytes,
        max_width=max_width,
    )
    return preparado.item if preparado is not None else None
