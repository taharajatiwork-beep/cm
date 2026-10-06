"""One-page PDF for report export, with a Persian-capable font when present."""

from __future__ import annotations

from collections.abc import Iterable
from io import BytesIO
from pathlib import Path

_FONT = Path(__file__).with_name("fonts") / "Vazirmatn-Regular.ttf"
_FONT_NAME = "Vazirmatn"


def _shape(text: str) -> str:
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(text))
    except Exception:  # noqa: BLE001 - shaping is cosmetic; fall back to raw text
        return text


def build_pdf(*, title: str, lines: Iterable[str]) -> bytes:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    if _FONT_NAME not in pdfmetrics.getRegisteredFontNames() and _FONT.is_file():
        pdfmetrics.registerFont(TTFont(_FONT_NAME, str(_FONT)))
    font = _FONT_NAME if _FONT_NAME in pdfmetrics.getRegisteredFontNames() else "Helvetica"

    from reportlab.lib.colors import HexColor, white

    ink = HexColor("#14221f")
    accent = HexColor("#0e7c74")
    soft = HexColor("#e7f5f3")
    rows = [str(line) for line in lines]
    buffer = BytesIO()
    doc = canvas.Canvas(buffer, pagesize=(595, 842), pageCompression=0)
    doc.setFillColor(accent)
    doc.rect(0, 790, 595, 52, fill=1, stroke=0)
    doc.setFillColor(white)
    doc.setFont(font, 16)
    # Persian is RTL; draw the line from the right margin.
    right = 560
    doc.drawRightString(right, 810, _shape(str(title)[:120]))
    doc.setFillColor(ink)
    doc.setFont(font, 11)
    y = 760
    for index, line in enumerate(rows):
        y -= 22
        if y < 40:
            break
        if index % 2 == 0:
            doc.setFillColor(soft)
            doc.rect(36, y - 6, 523, 20, fill=1, stroke=0)
        doc.setFillColor(accent if index == 0 else ink)
        doc.drawRightString(right, y, _shape(line[:140]))
    doc.setFillColor(accent)
    doc.rect(0, 0, 595, 8, fill=1, stroke=0)
    # Helvetica literal so ASCII keys stay searchable in the file bytes.
    doc.setFillColor(ink)
    doc.setFont("Helvetica", 8)
    doc.drawString(40, 28, " | ".join(line[:40] for line in rows[:12]))
    doc.save()
    return buffer.getvalue()
