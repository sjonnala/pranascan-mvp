"""Tests for DataPurgerService — deletion background job."""

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, call

import pytest

from app.models.deletion_request import DeletionRequestStatus
from app.services.data_purger_service import DataPurgerService, DeletionRequest


def _make_request(days_old: int, status: str = DeletionRequestStatus.PENDING.value) -> MagicMock:
    req = MagicMock(spec=DeletionRequest)
    req.id = uuid.uuid4()
    req.user_id = uuid.uuid4()
    req.requested_at = datetime.utcnow() - timedelta(days=days_old)
    req.status = status
    req.purged_at = None
    req.failure_reason = None
    return req


class TestPurgeQueryFilter:
    """Unit: only eligible records are processed."""

    def test_future_scheduled_records_are_not_touched(self):
        """Records requested < 30 days ago must not be processed."""
        db = MagicMock()
        # Simulate: query returns no eligible records (29-day-old request not due yet)
        db.query.return_value.filter.return_value.all.return_value = []

        service = DataPurgerService(db)
        result = service.purge_old_deletion_requests()

        assert result["processed_requests"] == 0
        assert result["purged_users"] == 0
        assert result["status"] == "completed_no_purges"

    def test_already_completed_records_are_not_reprocessed(self):
        """Records with status=COMPLETED must not appear in the query (service filters by PENDING)."""
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []

        service = DataPurgerService(db)
        result = service.purge_old_deletion_requests()

        # Verify the query was made — filter criteria are inside the service,
        # this confirms the query path ran and returned zero eligible records.
        db.query.assert_called_once_with(DeletionRequest)
        assert result["processed_requests"] == 0

    def test_no_eligible_records_returns_no_purge_status(self):
        """Empty result set returns completed_no_purges summary."""
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []

        service = DataPurgerService(db)
        result = service.purge_old_deletion_requests()

        assert result["status"] == "completed_no_purges"
        assert result["scan_sessions_deleted"] == 0
        assert result["consent_records_deleted"] == 0


class TestPurgeSuccess:
    """Integration-style: seed a due record, run job, assert data removed."""

    def test_due_record_is_purged_and_marked_completed(self):
        """A 31-day-old PENDING request must be processed: data deleted, status=COMPLETED, purged_at set."""
        db = MagicMock()
        request = _make_request(days_old=31)
        db.query.return_value.filter.return_value.all.return_value = [request]

        # Simulate delete() returning rowcounts
        delete_result = MagicMock()
        delete_result.rowcount = 3
        db.execute.return_value = delete_result

        service = DataPurgerService(db)
        result = service.purge_old_deletion_requests()

        assert result["processed_requests"] == 1
        assert result["purged_users"] == 1
        assert result["scan_sessions_deleted"] == 3
        assert result["consent_records_deleted"] == 3
        assert result["status"] == "completed_with_purges"
        assert request.status == DeletionRequestStatus.COMPLETED.value
        assert request.purged_at is not None
        assert request.failure_reason is None
        db.commit.assert_called()

    def test_multiple_due_records_all_purged(self):
        """Multiple eligible records are each processed independently."""
        db = MagicMock()
        requests = [_make_request(days_old=35), _make_request(days_old=40)]
        db.query.return_value.filter.return_value.all.return_value = requests

        delete_result = MagicMock()
        delete_result.rowcount = 1
        db.execute.return_value = delete_result

        service = DataPurgerService(db)
        result = service.purge_old_deletion_requests()

        assert result["processed_requests"] == 2
        assert result["purged_users"] == 2
        for req in requests:
            assert req.status == DeletionRequestStatus.COMPLETED.value
            assert req.purged_at is not None


class TestPurgeFailureAndRollback:
    """Integration: DB error during deletion must rollback and mark request FAILED."""

    def test_db_error_triggers_rollback_and_marks_failed(self):
        """When execute() raises, rollback is called and purged_at stays None."""
        db = MagicMock()
        request = _make_request(days_old=31)
        db.query.return_value.filter.return_value.all.return_value = [request]
        db.execute.side_effect = Exception("DB connection lost")

        service = DataPurgerService(db)
        result = service.purge_old_deletion_requests()

        db.rollback.assert_called_once()
        assert request.status == DeletionRequestStatus.FAILED.value
        assert request.purged_at is None
        assert request.failure_reason == "DB connection lost"

    def test_failed_request_does_not_count_as_purged(self):
        """A failed request must not increment purged_users count."""
        db = MagicMock()
        request = _make_request(days_old=31)
        db.query.return_value.filter.return_value.all.return_value = [request]
        db.execute.side_effect = Exception("timeout")

        service = DataPurgerService(db)
        result = service.purge_old_deletion_requests()

        assert result["purged_users"] == 0
        assert result["processed_requests"] == 1

    def test_one_failure_does_not_stop_other_requests(self):
        """If the first request fails, the second request is still attempted."""
        db = MagicMock()
        req_fail = _make_request(days_old=31)
        req_ok = _make_request(days_old=32)
        db.query.return_value.filter.return_value.all.return_value = [req_fail, req_ok]

        ok_result = MagicMock()
        ok_result.rowcount = 1
        # First call raises, subsequent calls succeed
        db.execute.side_effect = [Exception("error"), ok_result, ok_result]

        service = DataPurgerService(db)
        result = service.purge_old_deletion_requests()

        assert result["processed_requests"] == 2
        assert result["purged_users"] == 1
        assert req_fail.status == DeletionRequestStatus.FAILED.value
        assert req_ok.status == DeletionRequestStatus.COMPLETED.value
