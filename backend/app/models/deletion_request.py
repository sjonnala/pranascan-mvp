import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class DeletionRequestStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class DeletionRequest(Base):
    __tablename__ = "deletion_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String, default=DeletionRequestStatus.PENDING.value, nullable=False)
    purged_at = Column(DateTime, nullable=True)
    failure_reason = Column(String, nullable=True)

    user = relationship("User")

    def __repr__(self):
        return (
            f"<DeletionRequest(id={self.id}, user_id={self.user_id}, "
            f"status='{self.status}', requested_at='{self.requested_at}')>"
        )
