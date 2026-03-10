"""
ABHA / ABDM Gateway adapter.

Feature-flagged via settings.abha_enabled.
When abha_sandbox=True (default), all gateway calls are mocked locally —
no real HTTP requests are made. Set abha_sandbox=False + provide real
abha_gateway_url / abha_client_id / abha_client_secret for production.

Sync flow:
  1. Caller checks is_enabled() — skip entirely if disabled.
  2. sync_vitals() looks up the user's AbhaLink (active link required).
  3. In sandbox mode: build the payload, log it, return a mock gateway_ref.
  4. In live mode: POST to the ABDM gateway endpoint (future implementation).
  5. Write an AbhaSyncRecord for audit trail regardless of outcome.

Architecture note:
  Raw biometrics never leave the device (edge-first design). Only anonymised
  wellness indicator metadata is synced to the ABDM gateway.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.abha import AbhaLink, AbhaSyncRecord

log = logging.getLogger(__name__)


@dataclass
class SyncResult:
    status: str  # "success" | "skipped_disabled" | "skipped_no_link" | "failed"
    abha_id: str | None
    gateway_ref: str | None
    sandbox: bool
    synced_at: datetime


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def is_enabled() -> bool:
    """Return True when ABHA integration is turned on via settings."""
    return settings.abha_enabled


async def get_active_link(db: AsyncSession, user_id: str) -> AbhaLink | None:
    """Return the current active AbhaLink for a user, or None."""
    stmt = (
        select(AbhaLink)
        .where(
            AbhaLink.user_id == user_id,
            AbhaLink.unlinked_at.is_(None),
        )
        .order_by(AbhaLink.linked_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def link_account(
    db: AsyncSession,
    user_id: str,
    abha_id: str,
) -> AbhaLink:
    """
    Link an ABHA ID to a user.

    If the user already has an active link, it is soft-deleted first.
    Returns the new AbhaLink record.
    """
    now = datetime.now(tz=timezone.utc)

    # Soft-delete any existing active link
    existing = await get_active_link(db, user_id)
    if existing is not None:
        existing.unlinked_at = now
        await db.flush()

    link = AbhaLink(
        user_id=user_id,
        abha_id=abha_id,
        linked_at=now,
    )
    db.add(link)
    await db.flush()
    await db.refresh(link)

    log.info(
        "abha_link user_id=%s abha_id=%s sandbox=%s",
        user_id,
        abha_id,
        settings.abha_sandbox,
    )
    return link


async def unlink_account(db: AsyncSession, user_id: str) -> bool:
    """
    Soft-delete the active ABHA link for a user.

    Returns True if a link was found and unlinked, False if no active link.
    """
    link = await get_active_link(db, user_id)
    if link is None:
        return False

    link.unlinked_at = datetime.now(tz=timezone.utc)
    await db.flush()
    log.info("abha_unlink user_id=%s abha_id=%s", user_id, link.abha_id)
    return True


async def get_last_sync(db: AsyncSession, user_id: str) -> AbhaSyncRecord | None:
    """Return the most recent AbhaSyncRecord for a user."""
    stmt = (
        select(AbhaSyncRecord)
        .where(AbhaSyncRecord.user_id == user_id)
        .order_by(AbhaSyncRecord.synced_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def sync_vitals(
    db: AsyncSession,
    user_id: str,
    session_id: str,
    vitals: dict,
) -> SyncResult:
    """
    Sync anonymised wellness indicators for a completed scan to the ABDM gateway.

    vitals dict keys (all optional / nullable):
      hr_bpm, hrv_ms, respiratory_rate,
      voice_jitter_pct, voice_shimmer_pct,
      vascular_age_estimate, hb_proxy_score

    Raw biometric data must NOT be passed here — edge-processed summaries only.
    """
    now = datetime.now(tz=timezone.utc)

    if not is_enabled():
        rec = AbhaSyncRecord(
            session_id=session_id,
            user_id=user_id,
            abha_id="",
            status="skipped_disabled",
            sandbox=settings.abha_sandbox,
            gateway_ref=None,
        )
        db.add(rec)
        await db.flush()
        return SyncResult(
            status="skipped_disabled",
            abha_id=None,
            gateway_ref=None,
            sandbox=settings.abha_sandbox,
            synced_at=now,
        )

    link = await get_active_link(db, user_id)
    if link is None:
        rec = AbhaSyncRecord(
            session_id=session_id,
            user_id=user_id,
            abha_id="",
            status="skipped_no_link",
            sandbox=settings.abha_sandbox,
            gateway_ref=None,
        )
        db.add(rec)
        await db.flush()
        return SyncResult(
            status="skipped_no_link",
            abha_id=None,
            gateway_ref=None,
            sandbox=settings.abha_sandbox,
            synced_at=now,
        )

    abha_id = link.abha_id

    if settings.abha_sandbox:
        gateway_ref, status = await _sandbox_sync(abha_id, session_id, vitals)
    else:
        gateway_ref, status = await _live_sync(abha_id, session_id, vitals)

    rec = AbhaSyncRecord(
        session_id=session_id,
        user_id=user_id,
        abha_id=abha_id,
        status=status,
        sandbox=settings.abha_sandbox,
        gateway_ref=gateway_ref,
    )
    db.add(rec)
    await db.flush()

    return SyncResult(
        status=status,
        abha_id=abha_id,
        gateway_ref=gateway_ref,
        sandbox=settings.abha_sandbox,
        synced_at=now,
    )


# ---------------------------------------------------------------------------
# Internal gateway implementations
# ---------------------------------------------------------------------------


async def _sandbox_sync(
    abha_id: str,
    session_id: str,
    vitals: dict,
) -> tuple[str, str]:
    """
    Sandbox (mock) ABDM gateway sync.

    Simulates a successful FHIR-style observation bundle push.
    No real HTTP call is made. Returns (gateway_ref, status).
    """
    # Construct the anonymised payload that would go to the real gateway.
    # Mirroring FHIR R4 Observation resource structure (simplified).
    payload = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": _build_fhir_observations(abha_id, session_id, vitals),
    }

    # In sandbox: generate a deterministic-looking mock transaction ID
    mock_txn_id = f"SANDBOX-{str(uuid.uuid4()).upper()[:16]}"

    log.info(
        "abha_sandbox_sync abha_id=%s session_id=%s gateway_ref=%s payload_entries=%d",
        abha_id,
        session_id,
        mock_txn_id,
        len(payload["entry"]),
    )

    return mock_txn_id, "success"


async def _live_sync(
    abha_id: str,
    session_id: str,
    vitals: dict,
) -> tuple[str | None, str]:
    """
    Live ABDM gateway sync (stub for post-MVP ABDM certification).

    In production, this will:
    1. Obtain an ABDM access token via client credentials flow.
    2. POST a FHIR R4 Bundle to the Health Information Provider (HIP) endpoint.
    3. Return the ABDM transaction ID.

    Currently raises NotImplementedError to prevent accidental live calls
    until ABDM HIU/HIP registration is complete.
    """
    log.error(
        "abha_live_sync_not_implemented abha_id=%s session_id=%s — "
        "Set ABHA_SANDBOX=true until ABDM HIU/HIP registration is complete.",
        abha_id,
        session_id,
    )
    raise NotImplementedError(
        "Live ABDM gateway sync is not yet implemented. "
        "Set ABHA_SANDBOX=true in your environment."
    )


def _build_fhir_observations(abha_id: str, session_id: str, vitals: dict) -> list[dict]:
    """
    Build a list of simplified FHIR R4 Observation entries for wellness indicators.

    Uses LOINC codes where applicable.
    All values are wellness indicators — not diagnostic measurements.
    """
    entries = []

    metric_map = [
        ("hr_bpm", "8867-4", "Heart rate", "bpm"),
        ("hrv_ms", "80404-7", "HRV RMSSD", "ms"),
        ("respiratory_rate", "9279-1", "Respiratory rate", "/min"),
        ("voice_jitter_pct", None, "Voice jitter", "%"),
        ("voice_shimmer_pct", None, "Voice shimmer", "%"),
        ("vascular_age_estimate", None, "Vascular age estimate (heuristic)", "a"),
        ("hb_proxy_score", None, "Hemoglobin proxy score (heuristic)", "score"),
    ]

    for key, loinc, display, unit in metric_map:
        value = vitals.get(key)
        if value is None:
            continue

        obs: dict = {
            "resource": {
                "resourceType": "Observation",
                "status": "preliminary",
                "subject": {"identifier": {"value": abha_id}},
                "identifier": [{"value": session_id}],
                "valueQuantity": {"value": round(float(value), 4), "unit": unit},
                "note": [
                    {
                        "text": (
                            "Wellness indicator only. Not a diagnostic measurement. "
                            "Consult a qualified healthcare professional."
                        )
                    }
                ],
            }
        }

        if loinc:
            obs["resource"]["code"] = {
                "coding": [{"system": "http://loinc.org", "code": loinc, "display": display}]
            }
        else:
            obs["resource"]["code"] = {"text": display}

        entries.append(obs)

    return entries
