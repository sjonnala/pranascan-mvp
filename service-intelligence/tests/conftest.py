"""Test-only settings isolation for the compute-only FastAPI module."""

from collections.abc import Iterator

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def isolate_runtime_settings() -> Iterator[None]:
    """Keep local .env overrides from changing deterministic test behavior."""
    original_skip_quality_gate = settings.skip_quality_gate
    original_internal_service_token = settings.internal_service_token

    settings.skip_quality_gate = False
    settings.internal_service_token = "dev-internal-service-token"

    try:
        yield
    finally:
        settings.skip_quality_gate = original_skip_quality_gate
        settings.internal_service_token = original_internal_service_token
