"""The compiled stylesheet, checked mechanically (field-manual finding B1).

A plain ``:hover`` on a button has the same specificity as ``:disabled`` and is
emitted after it, so a disabled "Complete sale" turned bright teal under the
pointer and looked clickable. Hover must be guarded by ``:not(:disabled)``.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

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


_ROOT = Path(__file__).resolve().parents[2]
_TAILWIND = _ROOT / "node_modules" / ".bin" / "tailwindcss"


@pytest.mark.skipif(not _TAILWIND.exists(), reason="tailwindcss not installed (npm install)")
def test_the_committed_stylesheet_is_built_from_the_current_templates(tmp_path):
    """Tailwind only emits classes it finds in a template, and the compiled file is committed.
    Phase 7's Settings, Staff and recovery-sheet screens shipped in 1.0.0 without a rebuild,
    so classes they used (the backup key's font-mono and break-all among them) did nothing.
    Run scripts/build_css.sh and commit the result."""
    out = tmp_path / "tailwind.css"
    subprocess.run([str(_TAILWIND), "-c", "tailwind.config.js",
                    "-i", "sukoon/static/css/input.css", "-o", str(out), "--minify"],
                   cwd=_ROOT, check=True, capture_output=True)
    assert out.read_text(encoding="utf-8") == CSS.read_text(encoding="utf-8"), (
        "sukoon/static/css/tailwind.css is stale: run scripts/build_css.sh and commit it")
