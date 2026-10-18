"""Prepare inbound product photos for vision models."""

import subprocess
import tempfile
from pathlib import Path


def prepare_image(data: bytes, mime: str = "") -> tuple[bytes, str]:
    """Return image bytes and a mime type OpenAI/Gemini can read."""
    if not data:
        return b"", ""
    kind = (mime or "").split(";")[0].strip().lower()
    if kind in {"image/jpg", "image/pjpeg"}:
        kind = "image/jpeg"
    if _looks_heic(data) or "heic" in kind or "heif" in kind:
        converted = _heic_to_jpeg(data)
        if converted:
            return converted, "image/jpeg"
    if not kind.startswith("image/"):
        kind = _sniff_mime(data) or "image/jpeg"
    return data, kind


def _looks_heic(data: bytes) -> bool:
    head = data[:64]
    return any(marker in head for marker in (b"ftypheic", b"ftypheif", b"ftypmif1", b"ftypmsf1"))


def _sniff_mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in {b"GIF87a", b"GIF89a"}:
        return "image/gif"
    if _looks_heic(data):
        return "image/heic"
    return ""


def _heic_to_jpeg(data: bytes) -> bytes:
    """Convert HEIC with macOS sips when available."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "inbound.heic"
            dst = Path(tmp) / "inbound.jpg"
            src.write_bytes(data)
            result = subprocess.run(
                ["sips", "-s", "format", "jpeg", str(src), "--out", str(dst)],
                capture_output=True,
                timeout=45,
                check=False,
            )
            if result.returncode == 0 and dst.is_file():
                out = dst.read_bytes()
                if out[:3] == b"\xff\xd8\xff":
                    return out
    except Exception:
        return b""
    return b""
