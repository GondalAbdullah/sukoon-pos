"""The compiled stylesheet, checked mechanically (field-manual finding B1).

A plain ``:hover`` on a button has the same specificity as ``:disabled`` and is
emitted after it, so a disabled "Complete sale" turned bright teal under the
pointer and looked clickable. Hover must be guarded by ``:not(:disabled)``.
"""
from __future__ import annotations

import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[2] / "sukoon" / "static" / "css" / "tailwind.css"


def test_hover_never_restyles_a_disabled_button():
    css = CSS.read_text(encoding="utf-8")
    for btn in ("btn-primary", "btn-ghost"):
        assert f".{btn}:hover{{" not in css, f"unguarded hover on .{btn}"
        assert f".{btn}:not(:disabled):hover" in css


_TEMPLATES = Path(__file__).resolve().parents[2] / "sukoon" / "templates"
# Tailwind's default spacing scale has half steps only up to 3.5; anything like
# ``px-4.5`` compiles to nothing and the padding silently vanishes.
_PHANTOM_SPACING = re.compile(
    r"(?<![\w-])-?(?:[pm][xytblrse]?|gap(?:-[xy])?|space-[xy]|[wh]|top|left|right|bottom|inset)"
    r"-(?:[4-9]|\d{2,})\.5(?![\w.])"
)


def test_templates_use_no_spacing_class_tailwind_cannot_generate():
    offenders = [
        f"{path.relative_to(_TEMPLATES)}: {m.group(0)}"
        for path in _TEMPLATES.rglob("*.html")
        for m in _PHANTOM_SPACING.finditer(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_a_table_column_can_right_align_its_heading():
    # a numbers column's heading must follow its own text-right; the table's default
    # left alignment has to lose to it (Stock's Price heading sat left of its prices)
    css = CSS.read_text(encoding="utf-8")
    assert ":where(.table th){text-align:left}" in css
    assert ".table th{text-align:left" not in css
