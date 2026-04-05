"""Startup lifecycle behavior tests."""

import pytest

from app import bootstrap as app_bootstrap
from app import main as app_main


@pytest.mark.asyncio
async def test_lifespan_runs_bootstrap(monkeypatch):
    calls = {"bootstrap": 0}

    async def fake_bootstrap_application_state() -> None:
        calls["bootstrap"] += 1

    monkeypatch.setattr(app_main, "bootstrap_application_state", fake_bootstrap_application_state)

    async with app_main.lifespan(app_main.app):
        pass

    assert calls == {"bootstrap": 1}


@pytest.mark.asyncio
async def test_bootstrap_skips_table_autocreate_by_default(monkeypatch):
    calls = {"create_all": 0, "seed_beta": 0}

    async def fake_create_all_tables() -> None:
        calls["create_all"] += 1

    async def fake_seed_beta_invite_if_configured() -> None:
        calls["seed_beta"] += 1

    monkeypatch.setattr(app_bootstrap.settings, "auto_create_tables", False)
    monkeypatch.setattr(app_bootstrap, "create_all_tables", fake_create_all_tables)
    monkeypatch.setattr(
        app_bootstrap,
        "seed_beta_invite_if_configured",
        fake_seed_beta_invite_if_configured,
    )

    await app_bootstrap.bootstrap_application_state()

    assert calls == {"create_all": 0, "seed_beta": 1}


@pytest.mark.asyncio
async def test_bootstrap_blocks_table_autocreate_in_production(monkeypatch):
    calls = {"create_all": 0, "seed_beta": 0}

    async def fake_create_all_tables() -> None:
        calls["create_all"] += 1

    async def fake_seed_beta_invite_if_configured() -> None:
        calls["seed_beta"] += 1

    monkeypatch.setattr(app_bootstrap.settings, "auto_create_tables", True)
    monkeypatch.setattr(app_bootstrap.settings, "environment", "production")
    monkeypatch.setattr(app_bootstrap, "create_all_tables", fake_create_all_tables)
    monkeypatch.setattr(
        app_bootstrap,
        "seed_beta_invite_if_configured",
        fake_seed_beta_invite_if_configured,
    )

    with pytest.raises(RuntimeError, match="AUTO_CREATE_TABLES"):
        await app_bootstrap.bootstrap_application_state()

    assert calls == {"create_all": 0, "seed_beta": 0}
