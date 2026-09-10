"""Barcode images and the printable A4 label sheet (ADR-0010, ADR-0018 §2/§3).

No Flask import (ADR-0003 §1). Sheet geometry is configuration, not code
(ADR-0010) — ``load_geometry`` reads it from the ``setting`` table with sane
defaults for a common 3x8 A4 sticker sheet.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import barcode
from barcode.writer import ImageWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from sukoon.services import settings_service

_A4_W, _A4_H = A4


def render_barcode_png(code: str, *, module_height: float = 12.0) -> bytes:
    """A Code 128 barcode image (PNG) whose printed digits are ``code`` itself."""
    if not code:
        raise ValueError("cannot render a barcode for an empty code")
    writer = ImageWriter()
    obj = barcode.get("code128", code, writer=writer)
    buf = io.BytesIO()
    obj.write(
        buf,
        options={
            "module_height": module_height,
            "font_size": 8,
            "text_distance": 3,
            "quiet_zone": 2,
        },
    )
    return buf.getvalue()


@dataclass(frozen=True)
class LabelGeometry:
    columns: int = 3
    rows: int = 8
    margin_top_mm: float = 12.0
    margin_left_mm: float = 6.0
    gutter_x_mm: float = 2.5
    gutter_y_mm: float = 0.0
    label_width_mm: float = 64.0
    label_height_mm: float = 33.9

    @property
    def per_page(self) -> int:
        return self.columns * self.rows


def load_geometry() -> LabelGeometry:
    d = LabelGeometry()
    return LabelGeometry(
        columns=settings_service.get_int("label_sheet.columns", d.columns),
        rows=settings_service.get_int("label_sheet.rows", d.rows),
        margin_top_mm=_get_float("label_sheet.margin_top_mm", d.margin_top_mm),
        margin_left_mm=_get_float("label_sheet.margin_left_mm", d.margin_left_mm),
        gutter_x_mm=_get_float("label_sheet.gutter_x_mm", d.gutter_x_mm),
        gutter_y_mm=_get_float("label_sheet.gutter_y_mm", d.gutter_y_mm),
        label_width_mm=_get_float("label_sheet.label_width_mm", d.label_width_mm),
        label_height_mm=_get_float("label_sheet.label_height_mm", d.label_height_mm),
    )


def _get_float(key: str, default: float) -> float:
    raw = settings_service.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class LabelSpec:
    code: str
    caption: str = ""


def render_label_sheet(
    labels: list[LabelSpec], *, geometry: LabelGeometry | None = None
) -> bytes:
    """One or more A4 pages of barcode labels. Returns PDF bytes."""
    geo = geometry or LabelGeometry()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    cell_w = geo.label_width_mm * mm
    cell_h = geo.label_height_mm * mm
    step_x = cell_w + geo.gutter_x_mm * mm
    step_y = cell_h + geo.gutter_y_mm * mm
    origin_x = geo.margin_left_mm * mm
    origin_y = _A4_H - geo.margin_top_mm * mm

    per_page = geo.per_page
    for index, spec in enumerate(labels):
        slot = index % per_page
        if index and slot == 0:
            c.showPage()
        col = slot % geo.columns
        row = slot // geo.columns
        x = origin_x + col * step_x
        y = origin_y - (row + 1) * step_y

        img = ImageReader(io.BytesIO(render_barcode_png(spec.code)))
        iw, ih = img.getSize()
        draw_w = cell_w - 6 * mm
        draw_h = draw_w * ih / iw
        max_img_h = cell_h - 10 * mm
        if draw_h > max_img_h:
            draw_h = max_img_h
            draw_w = draw_h * iw / ih
        c.drawImage(
            img,
            x + (cell_w - draw_w) / 2,
            y + cell_h - draw_h - 3 * mm,
            width=draw_w,
            height=draw_h,
            preserveAspectRatio=True,
            mask="auto",
        )
        if spec.caption:
            c.setFont("Helvetica", 7)
            c.drawCentredString(x + cell_w / 2, y + 3 * mm, spec.caption[:48])

    c.showPage()
    c.save()
    return buf.getvalue()
