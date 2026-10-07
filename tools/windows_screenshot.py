from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from core.tool_result import ToolResult
from tools.windows_input import (
    _contexto_dpi_per_monitor_windows,
    _limites_tela_virtual_windows,
    _user32,
)


def capturar_tela_windows() -> ToolResult:
    """Captura todas as telas e devolve um artefato de imagem para a rodada multimodal."""
    if os.name != "nt":
        return ToolResult.failure("Captura de tela so esta disponivel no Windows.", error_code="windows_only")

    try:
        from PIL import ImageGrab
    except Exception as exc:
        return ToolResult.failure(
            "A captura de tela precisa da dependencia Pillow. Instale Pillow para habilitar a visao de tela.",
            error_code="pillow_missing",
            data={"detalhe": str(exc)},
        )

    destino_dir = Path(__file__).resolve().parents[1] / "runtime" / "screenshots"
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / f"screen_{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.png"
    try:
        user32 = _user32()
        with _contexto_dpi_per_monitor_windows(user32) as dpi_aplicado:
            imagem = ImageGrab.grab(all_screens=True)
            origem_x, origem_y, largura_virtual, altura_virtual = _limites_tela_virtual_windows(user32)
        imagem.save(destino, format="PNG", optimize=True)
        largura_imagem, altura_imagem = imagem.size
        return ToolResult.success(
            f"Tela capturada: {destino.name}",
            data={
                "image_path": str(destino),
                "mime_type": "image/png",
                "image_width": largura_imagem,
                "image_height": altura_imagem,
                "virtual_screen_x": origem_x,
                "virtual_screen_y": origem_y,
                "virtual_screen_width": largura_virtual,
                "virtual_screen_height": altura_virtual,
                "coordinate_space": "windows_virtual_screen_physical_pixels",
                "dpi_per_monitor_aware": bool(dpi_aplicado),
                "geometry_match": (
                    largura_imagem == largura_virtual
                    and altura_imagem == altura_virtual
                ),
            },
        )
    except Exception as exc:
        return ToolResult.failure(
            f"Nao consegui capturar a tela: {exc}",
            error_code="screenshot_failed",
        )

