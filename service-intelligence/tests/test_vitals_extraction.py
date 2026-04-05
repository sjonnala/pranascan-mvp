"""Tests for the gRPC vitals extraction bridge."""

from app.services.vitals_extraction import extract_vitals_from_media


def test_extract_vitals_from_media_returns_deterministic_payload():
    media_bytes = bytes((index * 17) % 256 for index in range(512))

    first = extract_vitals_from_media(media_bytes)
    second = extract_vitals_from_media(media_bytes)

    assert first == second
    assert 30.0 <= first.heart_rate <= 220.0
    assert first.hrv >= 0.0
    assert 90.0 <= first.spo2 <= 100.0


def test_extract_vitals_from_media_rejects_tiny_payload():
    try:
        extract_vitals_from_media(b"short")
    except ValueError as exc:
        assert "at least" in str(exc)
    else:
        raise AssertionError("Expected a ValueError for an undersized media payload.")
