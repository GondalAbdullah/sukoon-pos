"""Route-protection helpers (ADR-0008 §4/§5).

A hidden button is not access control: every Admin-only action is enforced here,
server-side, and an authenticated user without the permission gets a real 403 —
never a redirect, never a 200 with the controls greyed out.
"""
from __future__ import annotations

from functools import wraps

from flask import abort, request
from flask_login import current_user

from sukoon.services import auth_service
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


def require_step_up(password_field: str = "step_up_password") -> None:
    """Verify a fresh password re-entry for a single destructive action
    (ADR-0008 §5). Aborts 403 if it is missing or wrong. Holds no session state —
    it authorises exactly this request."""
    password = request.form.get(password_field, "")
    if not password or not auth_service.verify_step_up(current_user, password):
        abort(403, description="This action needs your password re-entered.")
