"""Centralized SQLAlchemy model registry and exports."""

from . import audit as _audit_models  # noqa: F401
from .audit import AuditLog


def register_models() -> None:
    """Ensure all SQLAlchemy model modules are imported and registered."""
    return None


__all__ = [
    "AuditLog",
    "register_models",
]
