"""User, Permission, and the role→permission mapping (ADR-0016, ADR-0008).

Authorisation is always checked against a *permission code*, never against
``role == 'admin'`` inline at a call site (ADR-0008 §3). The helper that resolves a
role's codes lives in ``services/auth_service.py``; these models only hold shape.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sukoon.extensions import db
from sukoon.models.base import TimestampMixin

ROLE_ADMIN = "admin"
ROLE_CASHIER = "cashier"
ROLES = (ROLE_ADMIN, ROLE_CASHIER)


class User(TimestampMixin, db.Model):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    initials: Mapped[str] = mapped_column(String(8), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # --- Flask-Login interface, implemented directly so models/ needs no
    # flask_login import (keeps the dependency graph in ADR-0003 clean) ---
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<User {self.id} {self.name!r} ({self.role})>"


class Permission(db.Model):
    __tablename__ = "permission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Permission {self.code!r}>"


class RolePermission(db.Model):
    __tablename__ = "role_permission"
    __table_args__ = (
        UniqueConstraint("role", "permission_id", name="role_permission_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permission.id"), nullable=False
    )

    permission: Mapped[Permission] = relationship(Permission)
