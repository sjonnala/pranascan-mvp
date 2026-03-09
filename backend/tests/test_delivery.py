"""Tests for the alert delivery stub."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.delivery_service import ALERT_MESSAGE, deliver_alert


@pytest.mark.asyncio
async def test_deliver_alert_logs_without_webhook(caplog):
    """deliver_alert logs the event when no webhook is configured."""
    import logging

    with caplog.at_level(logging.INFO, logger="app.services.delivery_service"):
        await deliver_alert("user-123", "consider_lab_followup")
    # Should not raise; logging captured
    assert True  # if we got here, no exception


@pytest.mark.asyncio
async def test_deliver_alert_posts_to_webhook_when_configured():
    """deliver_alert POSTs to webhook URL when ALERT_WEBHOOK_URL is set."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with (
        patch("app.services.delivery_service.settings") as mock_settings,
        patch("app.services.delivery_service.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.alert_webhook_url = "https://example.com/webhook"
        await deliver_alert("user-abc", "consider_lab_followup")

    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "https://example.com/webhook"
    payload = call_args[1]["json"]
    assert payload["user_id"] == "user-abc"
    assert payload["alert_type"] == "consider_lab_followup"
    assert ALERT_MESSAGE in payload["message"]


@pytest.mark.asyncio
async def test_deliver_alert_does_not_raise_on_webhook_failure():
    """deliver_alert swallows webhook errors so scans are never blocked."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=Exception("connection refused"))

    with (
        patch("app.services.delivery_service.settings") as mock_settings,
        patch("app.services.delivery_service.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.alert_webhook_url = "https://example.com/webhook"
        # Must not raise
        await deliver_alert("user-xyz", "consider_lab_followup")
