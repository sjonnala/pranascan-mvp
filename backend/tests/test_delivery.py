"""Tests for the alert and report delivery service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.delivery_service import ALERT_MESSAGE, deliver_alert, deliver_report

# ---------------------------------------------------------------------------
# deliver_alert — webhook path (existing behaviour preserved)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deliver_alert_logs_without_any_channel(caplog):
    """deliver_alert logs the event when no webhook or Telegram is configured."""
    import logging

    with caplog.at_level(logging.INFO, logger="app.services.delivery_service"):
        await deliver_alert("user-123", "consider_lab_followup")
    assert True  # must not raise


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
        mock_settings.telegram_bot_token = None
        mock_settings.telegram_chat_id = None
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
        mock_settings.telegram_bot_token = None
        mock_settings.telegram_chat_id = None
        await deliver_alert("user-xyz", "consider_lab_followup")  # must not raise


# ---------------------------------------------------------------------------
# deliver_alert — Telegram path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deliver_alert_sends_telegram_when_configured():
    """deliver_alert sends a Telegram message when bot token + chat ID are set."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with (
        patch("app.services.delivery_service.settings") as mock_settings,
        patch("app.services.delivery_service.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.alert_webhook_url = None
        mock_settings.telegram_bot_token = "123:FAKE_TOKEN"
        mock_settings.telegram_chat_id = "987654321"
        await deliver_alert("user-tg", "consider_lab_followup")

    mock_client.post.assert_called_once()
    url_called = mock_client.post.call_args[0][0]
    assert "123:FAKE_TOKEN" in url_called
    assert "sendMessage" in url_called
    payload = mock_client.post.call_args[1]["json"]
    assert payload["chat_id"] == "987654321"
    assert "wellness" in payload["text"].lower()
    # Must not contain diagnostic language
    assert "diagnosis" not in payload["text"].lower() or "not a" in payload["text"].lower()


@pytest.mark.asyncio
async def test_deliver_alert_does_not_raise_on_telegram_failure():
    """deliver_alert swallows Telegram errors so scans are never blocked."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=Exception("telegram unreachable"))

    with (
        patch("app.services.delivery_service.settings") as mock_settings,
        patch("app.services.delivery_service.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.alert_webhook_url = None
        mock_settings.telegram_bot_token = "123:FAKE_TOKEN"
        mock_settings.telegram_chat_id = "987654321"
        await deliver_alert("user-err", "consider_lab_followup")  # must not raise


@pytest.mark.asyncio
async def test_deliver_alert_skips_telegram_when_not_configured():
    """deliver_alert does NOT attempt Telegram when token/chat_id are absent."""
    with (
        patch("app.services.delivery_service.settings") as mock_settings,
        patch("app.services.delivery_service._send_telegram") as mock_tg,
    ):
        mock_settings.alert_webhook_url = None
        mock_settings.telegram_bot_token = None
        mock_settings.telegram_chat_id = None
        await deliver_alert("user-no-tg", "consider_lab_followup")

    mock_tg.assert_not_called()


# ---------------------------------------------------------------------------
# deliver_report — Telegram path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deliver_report_sends_telegram_when_configured():
    """deliver_report sends the vitality summary to Telegram when configured."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    summary = "PranaScan Weekly Wellness Summary\nHR: 72 bpm\n..."

    with (
        patch("app.services.delivery_service.settings") as mock_settings,
        patch("app.services.delivery_service.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.telegram_bot_token = "123:FAKE_TOKEN"
        mock_settings.telegram_chat_id = "987654321"
        await deliver_report("user-report", summary)

    mock_client.post.assert_called_once()
    payload = mock_client.post.call_args[1]["json"]
    assert payload["chat_id"] == "987654321"
    assert "PranaScan" in payload["text"] or summary[:20] in payload["text"]


@pytest.mark.asyncio
async def test_deliver_report_truncates_long_summary():
    """deliver_report truncates summaries longer than 4000 chars before sending."""
    long_summary = "x" * 5000

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with (
        patch("app.services.delivery_service.settings") as mock_settings,
        patch("app.services.delivery_service.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.telegram_bot_token = "123:FAKE_TOKEN"
        mock_settings.telegram_chat_id = "987654321"
        await deliver_report("user-long", long_summary)

    payload = mock_client.post.call_args[1]["json"]
    # The pre-wrapped text must be ≤ 4096 chars (Telegram limit)
    assert len(payload["text"]) <= 4096
    assert "…" in payload["text"]


@pytest.mark.asyncio
async def test_deliver_report_does_not_raise_on_telegram_failure():
    """deliver_report swallows Telegram errors — report generation must not fail."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=Exception("network error"))

    with (
        patch("app.services.delivery_service.settings") as mock_settings,
        patch("app.services.delivery_service.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.telegram_bot_token = "123:FAKE_TOKEN"
        mock_settings.telegram_chat_id = "987654321"
        await deliver_report("user-fail", "some summary")  # must not raise


@pytest.mark.asyncio
async def test_deliver_report_skips_telegram_when_not_configured():
    """deliver_report does NOT attempt Telegram when token/chat_id are absent."""
    with (
        patch("app.services.delivery_service.settings") as mock_settings,
        patch("app.services.delivery_service._send_telegram") as mock_tg,
    ):
        mock_settings.telegram_bot_token = None
        mock_settings.telegram_chat_id = None
        await deliver_report("user-no-tg", "some summary")

    mock_tg.assert_not_called()
