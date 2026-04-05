import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.deletion_request import DeletionRequestStatus

class DeletionRequestBase(BaseModel):
    user_id: uuid.UUID = Field(..., description="The ID of the user whose data is requested for deletion.")

class DeletionRequestCreate(DeletionRequestBase):
    pass

class DeletionRequestUpdate(BaseModel):
    status: DeletionRequestStatus = Field(..., description="The new status of the deletion request.")
    purged_at: Optional[datetime] = Field(None, description="Timestamp when the data purge was completed.")
    failure_reason: Optional[str] = Field(None, description="Reason for deletion failure, if applicable.")

class DeletionRequest(DeletionRequestBase):
    id: uuid.UUID = Field(..., description="Unique identifier for the deletion request.")
    requested_at: datetime = Field(..., description="Timestamp when the deletion was requested.")
    status: DeletionRequestStatus = Field(..., description="Current status of the deletion request.")
    purged_at: Optional[datetime] = Field(None, description="Timestamp when the data purge was completed.")
    failure_reason: Optional[str] = Field(None, description="Reason for deletion failure, if applicable.")

    class Config:
        from_attributes = True
