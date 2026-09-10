"""Barcode image + label-sheet PDF (ADR-0010, ADR-0018). No database needed."""
from __future__ import annotations

import re

import barcode
import barcode.charsets.code128 as _cs

from sukoon.services.receipts import labels


def _decode_code128(bits: str) -> str:
    """Decode a python-barcode Code 128 module string back to its text, verifying
    the start code and the mod-103 checksum, and following CODE A/B/C subset
    switches (python-barcode packs digit runs into subset C). The automated
    stand-in for an optical scan (the true optical decode is a Phase 8 manual
    test)."""
    codes = _cs.CODES
    body, stop = bits[:-13], bits[-13:]
    assert stop == _cs.STOP + "11", stop
    values = [codes.index(body[i:i + 11]) for i in range(0, len(body), 11)]

    start = values[0]
    assert start in (103, 104, 105)
    *data, checksum = values[1:]
    calc = (start + sum((i + 1) * v for i, v in enumerate(data))) % 103
    assert calc == checksum, "checksum mismatch"

    subset = {103: "A", 104: "B", 105: "C"}[start]
    out = []
    for v in data:
        if v == 99:
            subset = "C"
        elif v == 100:
            subset = "B"
        elif v == 101:
            subset = "A"
        elif subset == "C":
            out.append(f"{v:02d}")
        else:  # A or B, printable ASCII range
            out.append(chr(v + 32))
    return "".join(out)


def _page_count(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf))


def test_generated_barcode_pattern_decodes_back_to_the_code():
    for code in ("SK-000001", "SK-123456", "8964000109283"):
        pattern = barcode.get_barcode_class("code128")(code).build()[0]
        assert _decode_code128(pattern) == code


def test_render_barcode_png_is_a_png():
    data = labels.render_barcode_png("SK-000042")
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(data) > 200


def test_label_sheet_is_a_pdf():
    pdf = labels.render_label_sheet([labels.LabelSpec(code="SK-000001", caption="X")])
    assert pdf[:5] == b"%PDF-"


def test_label_sheet_page_count_follows_geometry():
    geo = labels.LabelGeometry(columns=2, rows=2)  # 4 per page
    assert geo.per_page == 4
    specs = [labels.LabelSpec(code=f"SK-{i:06d}") for i in range(9)]
    assert _page_count(labels.render_label_sheet(specs, geometry=geo)) == 3
    assert _page_count(labels.render_label_sheet(specs[:4], geometry=geo)) == 1
