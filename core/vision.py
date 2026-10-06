from __future__ import annotations

import base64
from pathlib import Path


def image_input_item(path: str | Path, *, max_bytes: int = 5_000_000, max_width: int = 1920) -> dict | None:
    """Converte uma imagem local em input_image da Responses API, com limite de tamanho."""
    source = Path(path)
    if not source.is_file():
        return None
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(source.suffix.lower())
    if mime is None:
        return None

    data = source.read_bytes()
    if len(data) > max_bytes:
        try:
            from PIL import Image
            image = Image.open(source)
            if image.width > max_width:
                ratio = max_width / float(image.width)
                size = (max_width, max(1, int(image.height * ratio)))
                image = image.resize(size)
            # Mantem PNG para screenshots, mas comprime; se ainda ficar grande,
            # usa JPEG como fallback visual para caber no limite.
            import io
            buf = io.BytesIO()
            image.save(buf, format="PNG", optimize=True)
            data = buf.getvalue()
            mime = "image/png"
            if len(data) > max_bytes:
                buf = io.BytesIO()
                image.convert("RGB").save(buf, format="JPEG", quality=82, optimize=True)
                data = buf.getvalue()
                mime = "image/jpeg"
        except Exception:
            return None
    if len(data) > max_bytes:
        return None
    encoded = base64.b64encode(data).decode("ascii")
    return {"type": "input_image", "image_url": f"data:{mime};base64,{encoded}"}
