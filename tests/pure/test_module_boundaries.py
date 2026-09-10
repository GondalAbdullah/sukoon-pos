"""ADR-0003 §1, enforced mechanically rather than by review discipline:
``sukoon/services/`` never imports Flask."""
from __future__ import annotations

import re
from pathlib import Path

SERVICES = Path(__file__).resolve().parents[2] / "sukoon" / "services"

# `flask` as a bare top-level module — not `flask_login`, `flask_sqlalchemy`, etc.
_FLASK_IMPORT = re.compile(r"^\s*(from flask import |from flask\.|import flask(\s|$))", re.M)


def test_services_never_import_flask():
    offenders = []
    for path in SERVICES.rglob("*.py"):
        if _FLASK_IMPORT.search(path.read_text()):
            offenders.append(str(path.relative_to(SERVICES.parent.parent)))
    assert not offenders, f"services/ must not import Flask: {offenders}"
