"""
Trend alert delivery stub.

Delivers a wellness alert via:
  - Structured log entry (always)
  - HTTP POST to ALERT_WEBHOOK_URL if configured

Message copy never contains diagnostic language.
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


async def deliver_alert(user_id: str, alert_type: str) -> None:
    """
    Deliver a wellness trend alert for a user.

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

    log_extra = {
        "user_id": payload["user_id"],
        "alert_type": payload["alert_type"],
        "alert_message": payload["message"],
        "timestamp": payload["timestamp"],
    }
    logger.info("wellness_alert_fired", extra=log_extra)

    if settings.alert_webhook_url:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(settings.alert_webhook_url, json=payload)
                response.raise_for_status()
                logger.info(
                    "wellness_alert_delivered",
                    extra={"status_code": response.status_code, "user_id": user_id},
                )
        except Exception as exc:  # noqa: BLE001
            # Delivery failure must NOT block the scan response
            logger.warning(
                "wellness_alert_delivery_failed",
                extra={"error": str(exc), "user_id": user_id},
            )
