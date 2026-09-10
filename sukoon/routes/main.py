"""Top-level pages. Thin by construction (ADR-0003 §2)."""
from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("main", __name__)


@bp.route("/")
def placeholder():
    return render_template("placeholder.html")
