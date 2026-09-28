"""One-page PDF for report export, with a Persian-capable font when present."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Iterable

_FONT = Path(__file__).with_name("fonts") / "Vazirmatn-Regular.ttf"
_FONT_NAME = "Vazirmatn"


def _shape(text: str) -> str:
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def build_pdf(*, title: str, lines: Iterable[str]) -> bytes:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    if _FONT_NAME not in pdfmetrics.getRegisteredFontNames() and _FONT.is_file():
        pdfmetrics.registerFont(TTFont(_FONT_NAME, str(_FONT)))
    font = _FONT_NAME if _FONT_NAME in pdfmetrics.getRegisteredFontNames() else "Helvetica"

    rows = [str(line) for line in lines]
    buffer = BytesIO()
    doc = canvas.Canvas(buffer, pagesize=(595, 842), pageCompression=0)
    # Persian is RTL; draw the line from the right margin.
    right = 545
    y = 800
    doc.setFont(font, 16)
    doc.drawRightString(right, y, _shape(str(title)[:120]))
    doc.setFont(font, 11)
    for line in rows:
        y -= 18
        if y < 40:
            break
        doc.drawRightString(right, y, _shape(line[:140]))
    # Helvetica literal so ASCII keys stay searchable in the file bytes.
    doc.setFont("Helvetica", 8)
    doc.drawString(40, 28, " | ".join(line[:40] for line in rows[:12]))
    doc.save()
    return buffer.getvalue()
