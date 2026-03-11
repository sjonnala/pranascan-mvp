"""
Trend alert and report delivery service.

Delivery channels (all optional / feature-flagged via config):
  1. Structured log entry — always emitted.
  2. HTTP POST to ALERT_WEBHOOK_URL — if configured.
  3. Telegram Bot API — if TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID are configured.
  4. WhatsApp Cloud API — if WHATSAPP_ENABLED and the required credentials are configured.

Message copy never contains diagnostic language.
Delivery failures are caught and logged — they must never block the scan response.
"""

import logging
from datetime import datetime, timezone

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ALERT_MESSAGE = (
    "Your recent wellness scan trends suggest it may be worth scheduling "
    "a routine lab check-up. This is a wellness reminder, not a diagnosis."
)

_TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"
_WHATSAPP_API_BASE = "https://graph.facebook.com/{version}/{phone_number_id}/messages"
_WHATSAPP_TEXT_LIMIT = 4096


def _telegram_configured() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def _whatsapp_configured() -> bool:
    return (
        settings.whatsapp_enabled is True
        and bool(settings.whatsapp_access_token)
        and bool(settings.whatsapp_phone_number_id)
        and bool(settings.whatsapp_recipient_phone)
    )


def _truncate_plain_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


async def _send_telegram(text: str) -> None:
    """
    POST a plain-text message to the configured Telegram chat.

    Raises on HTTP/network error (caller decides whether to swallow).
    Only called when telegram_bot_token and telegram_chat_id are set.
    """
    url = _TELEGRAM_API_BASE.format(token=settings.telegram_bot_token)
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
    logger.info(
        "telegram_message_sent",
        extra={"chat_id": settings.telegram_chat_id, "text_length": len(text)},
    )


async def _send_whatsapp(text: str) -> None:
    """
    POST a plain-text WhatsApp message to the configured recipient.

    Raises on HTTP/network error (caller decides whether to swallow).
    Only called when whatsapp_enabled and the required credentials are set.
    """
    url = _WHATSAPP_API_BASE.format(
        version=settings.whatsapp_api_version,
        phone_number_id=settings.whatsapp_phone_number_id,
    )
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": settings.whatsapp_recipient_phone,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": _truncate_plain_text(text, _WHATSAPP_TEXT_LIMIT),
        },
    }
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
    logger.info(
        "whatsapp_message_sent",
        extra={"to": settings.whatsapp_recipient_phone, "text_length": len(payload["text"]["body"])},
    )


async def deliver_alert(user_id: str, alert_type: str) -> None:
    """
    Deliver a wellness trend alert for a user.

    Channels attempted (in order):
      1. Structured log (always)
      2. Webhook POST (if ALERT_WEBHOOK_URL configured)
      3. Telegram (if TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID configured)
      4. WhatsApp (if WHATSAPP_ENABLED and credentials configured)

    Parameters
    ----------
    user_id : pseudonymous user ID
    alert_type : alert string (e.g. "consider_lab_followup")
    """
    payload = {
        "user_id": user_id,
        "alert_type": alert_type,
        "message": ALERT_MESSAGE,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }

    # 1. Structured log
    logger.info(
        "wellness_alert_fired",
        extra={
            "user_id": payload["user_id"],
            "alert_type": payload["alert_type"],
            "alert_message": payload["message"],
            "timestamp": payload["timestamp"],
        },
    )

    # 2. Webhook
    if settings.alert_webhook_url:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(settings.alert_webhook_url, json=payload)
                response.raise_for_status()
                logger.info(
                    "wellness_alert_delivered_webhook",
                    extra={"status_code": response.status_code, "user_id": user_id},
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "wellness_alert_webhook_failed",
                extra={"error": str(exc), "user_id": user_id},
            )

    # 3. Telegram
    if _telegram_configured():
        telegram_text = (
            f"🌿 <b>PranaScan Wellness Alert</b>\n\n"
            f"{ALERT_MESSAGE}\n\n"
            f"<i>This is an automated wellness reminder, not a medical diagnosis.</i>"
        )
        try:
            await _send_telegram(telegram_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "wellness_alert_telegram_failed",
                extra={"error": str(exc), "user_id": user_id},
            )

    # 4. WhatsApp
    if _whatsapp_configured():
        whatsapp_text = (
            "PranaScan Wellness Alert\n\n"
            f"{ALERT_MESSAGE}\n\n"
            "This is an automated wellness reminder, not a medical diagnosis."
        )
        try:
            await _send_whatsapp(whatsapp_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "wellness_alert_whatsapp_failed",
                extra={"error": str(exc), "user_id": user_id},
            )


async def deliver_report(user_id: str, summary_text: str) -> None:
    """
    Deliver a weekly vitality report summary to the user.

    Currently supports:
      1. Structured log (always)
      2. Telegram (if configured)
      3. WhatsApp (if configured)

    Parameters
    ----------
    user_id : pseudonymous user ID
    summary_text : plain-text report body from vitality_report service
    """
    logger.info(
        "vitality_report_delivery_triggered",
        extra={"user_id": user_id, "summary_length": len(summary_text)},
    )

    if _telegram_configured():
        # Telegram message length limit: 4096 chars. Truncate gracefully if needed.
        truncated = _truncate_plain_text(summary_text, 4000)
        telegram_text = f"<pre>{truncated}</pre>"
        try:
            await _send_telegram(telegram_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "vitality_report_telegram_failed",
                extra={"error": str(exc), "user_id": user_id},
            )

    if _whatsapp_configured():
        try:
            await _send_whatsapp(summary_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "vitality_report_whatsapp_failed",
                extra={"error": str(exc), "user_id": user_id},
            )
