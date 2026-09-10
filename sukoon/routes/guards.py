"""Route-protection decorators (ADR-0008 §4).

A hidden button is not access control: every Admin-only action is enforced here,
server-side, and an authenticated user without the permission gets a real 403 —
never a redirect, never a 200 with the controls greyed out.
"""
from __future__ import annotations

from functools import wraps

from flask import abort
from flask_login import current_user

from sukoon.services.auth_service import role_has_permission


def permission_required(code: str):
    """Require ``code`` on the current user's role. Assumes an authenticated
    user — stack ``@login_required`` above this for the anonymous case."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if not role_has_permission(current_user.role, code):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
