"""Centralized SQLAlchemy model registry and exports."""

from . import abha as _abha_models  # noqa: F401
from . import audit as _audit_models  # noqa: F401
from . import beta as _beta_models  # noqa: F401
from . import consent as _consent_models  # noqa: F401
from . import deletion_request as _deletion_request_models  # noqa: F401
from . import feedback as _feedback_models  # noqa: F401
from . import otp as _otp_models  # noqa: F401
from . import scan as _scan_models  # noqa: F401
from . import user as _user_models  # noqa: F401
from . import vitality_report as _vitality_report_models  # noqa: F401
from .abha import AbhaLink, AbhaSyncRecord
from .audit import AuditLog
from .beta import BetaEnrollment, BetaInvite
from .consent import ConsentAction, ConsentRecord
from .deletion_request import DeletionRequest, DeletionRequestStatus
from .feedback import ScanFeedback
from .otp import OTPRequest
from .scan import ScanResult, ScanSession, SessionStatus
from .user import User
from .vitality_report import VitalityReport


def register_models() -> None:
    """Ensure all SQLAlchemy model modules are imported and registered."""
    return None


__all__ = [
    "AbhaLink",
    "AbhaSyncRecord",
    "AuditLog",
    "BetaEnrollment",
    "BetaInvite",
    "ConsentAction",
    "ConsentRecord",
    "DeletionRequest",
    "DeletionRequestStatus",
    "OTPRequest",
    "ScanResult",
    "ScanFeedback",
    "ScanSession",
    "SessionStatus",
    "User",
    "VitalityReport",
    "register_models",
]
