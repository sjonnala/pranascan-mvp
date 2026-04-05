"""Deletion-request batch job with explicit per-request transaction ownership."""

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, delete
from sqlalchemy.orm import Session

from app.database import transaction_scope
from app.models.consent import ConsentRecord
from app.models.deletion_request import DeletionRequest, DeletionRequestStatus
from app.models.scan import ScanSession

logger = logging.getLogger(__name__)


class DataPurgerService:
    """Purge eligible deletion requests, one explicit transaction per request."""

    def __init__(self, db: Session):
        self.db = db

    def _delete_user_scan_sessions(self, user_id: uuid.UUID) -> int:
        """Deletes all scan sessions for a given user_id."""
        # DECISION: Assuming ScanSession has a 'user_id' column
        stmt = delete(ScanSession).where(ScanSession.user_id == user_id)
        result = self.db.execute(stmt)
        return result.rowcount

    def _delete_user_consent_records(self, user_id: uuid.UUID) -> int:
        """Deletes all consent records for a given user_id."""
        # DECISION: Assuming ConsentRecord has a 'user_id' column
        # See DECISION in summary regarding conflict with [ARCHITECTURE] for consent records.
        stmt = delete(ConsentRecord).where(ConsentRecord.user_id == user_id)
        result = self.db.execute(stmt)
        return result.rowcount

    def purge_old_deletion_requests(self) -> dict:
        """
        Identifies and processes deletion requests that are older than the 30-day hold period.
        Deletes associated user data (scan sessions, consent records) and updates request status.
        """
        logger.info("Starting data purging job.")
        start_time = datetime.utcnow()
        purged_users_count = 0
        total_scan_sessions_deleted = 0
        total_consent_records_deleted = 0
        processed_requests_count = 0

        # Calculate the cutoff time for 30 days ago
        cutoff_time = datetime.utcnow() - timedelta(days=30)

        eligible_requests: list[DeletionRequest] = (
            self.db.query(DeletionRequest)
            .filter(
                and_(
                    DeletionRequest.status == DeletionRequestStatus.PENDING.value,
                    DeletionRequest.requested_at <= cutoff_time,
                )
            )
            .all()
        )

        logger.info(f"Found {len(eligible_requests)} eligible deletion requests for purging.")

        if not eligible_requests:
            logger.info("No eligible deletion requests found for purging. Job finished.")
            return {
                "start_time": start_time,
                "end_time": datetime.utcnow(),
                "processed_requests": 0,
                "purged_users": 0,
                "scan_sessions_deleted": 0,
                "consent_records_deleted": 0,
                "status": "completed_no_purges",
            }

        for request in eligible_requests:
            processed_requests_count += 1
            user_id = request.user_id
            user_scan_sessions_deleted = 0
            user_consent_records_deleted = 0

            logger.info(f"Processing deletion request for user_id: {user_id}, request_id: {request.id}")

            try:
                with transaction_scope(self.db):
                    # Delete scan sessions
                    user_scan_sessions_deleted = self._delete_user_scan_sessions(user_id)
                    logger.info(
                        f"Deleted {user_scan_sessions_deleted} scan sessions for user_id: {user_id}"
                    )

                    # Delete consent records
                    user_consent_records_deleted = self._delete_user_consent_records(user_id)
                    logger.info(
                        f"Deleted {user_consent_records_deleted} consent records for user_id: {user_id}"
                    )

                    request.status = DeletionRequestStatus.COMPLETED.value
                    request.purged_at = datetime.utcnow()
                    request.failure_reason = None
                    self.db.add(request)

                total_scan_sessions_deleted += user_scan_sessions_deleted
                total_consent_records_deleted += user_consent_records_deleted
                purged_users_count += 1
                logger.info(f"Deletion request {request.id} for user {user_id} marked as COMPLETED.")

            except Exception as e:
                with transaction_scope(self.db):
                    request.status = DeletionRequestStatus.FAILED.value
                    request.purged_at = None
                    request.failure_reason = str(e)
                    self.db.add(request)
                logger.error(
                    f"Error processing deletion for user_id: {user_id}, request_id: {request.id}. "
                    f"Error: {e}",
                    exc_info=True,
                )
                logger.warning(f"Deletion request {request.id} for user {user_id} marked as FAILED.")

            finally:
                # Even if no data was found, mark as completed if no errors occurred.
                if (
                    request.status == DeletionRequestStatus.COMPLETED.value
                    and user_scan_sessions_deleted == 0
                    and user_consent_records_deleted == 0
                ):
                    logger.info(
                        f"No scan sessions or consent records found for user_id: {user_id}. "
                        f"Deletion request {request.id} marked as COMPLETED."
                    )

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"Data purging job finished in {duration:.2f} seconds.")
        logger.info(
            f"Summary: Processed {processed_requests_count} requests, "
            f"purged data for {purged_users_count} users, "
            f"deleted {total_scan_sessions_deleted} scan sessions, "
            f"deleted {total_consent_records_deleted} consent records."
        )

        return {
            "start_time": start_time,
            "end_time": end_time,
            "processed_requests": processed_requests_count,
            "purged_users": purged_users_count,
            "scan_sessions_deleted": total_scan_sessions_deleted,
            "consent_records_deleted": total_consent_records_deleted,
            "status": "completed_with_purges" if purged_users_count > 0 else "completed_no_purges",
        }
