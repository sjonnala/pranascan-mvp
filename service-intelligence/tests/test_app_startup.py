"""Startup lifecycle behavior tests."""

import pytest

from app import bootstrap as app_bootstrap
from app import main as app_main


@pytest.mark.asyncio
async def test_lifespan_runs_bootstrap(monkeypatch):
    calls = {"bootstrap": 0, "grpc_start": 0, "grpc_stop": 0}

    async def fake_bootstrap_application_state() -> None:
        calls["bootstrap"] += 1

    async def fake_start_grpc_server(bind_address: str):
        calls["grpc_start"] += 1
        return {"bind_address": bind_address}

    async def fake_stop_grpc_server(server) -> None:
        calls["grpc_stop"] += 1
        assert server == {"bind_address": app_main.build_grpc_bind_address()}

    monkeypatch.setattr(app_main, "bootstrap_application_state", fake_bootstrap_application_state)
    monkeypatch.setattr(app_main, "start_grpc_server", fake_start_grpc_server)
    monkeypatch.setattr(app_main, "stop_grpc_server", fake_stop_grpc_server)

    async with app_main.app.router.lifespan_context(app_main.app):
        pass

    assert calls == {"bootstrap": 1, "grpc_start": 1, "grpc_stop": 1}


def test_default_app_exposes_internal_routes_only():
    routes = {route.path for route in app_main.app.routes}
    assert "/internal/intelligence/scan-evaluations" not in routes
    assert "/api/v1/auth/me" not in routes
    assert "/api/v1/scans/sessions" not in routes


def test_create_app_can_disable_grpc_for_tests():
    internal_only_app = app_main.create_app(enable_grpc=False)
    assert internal_only_app.state.grpc_enabled is False
    routes = {route.path for route in internal_only_app.routes}
    assert "/api/v1/auth/me" not in routes


@pytest.mark.asyncio
async def test_bootstrap_skips_table_autocreate_by_default(monkeypatch):
    calls = {"create_all": 0}

    async def fake_create_all_tables() -> None:
        calls["create_all"] += 1

    monkeypatch.setattr(app_bootstrap.settings, "auto_create_tables", False)
    monkeypatch.setattr(app_bootstrap, "create_all_tables", fake_create_all_tables)

    await app_bootstrap.bootstrap_application_state()

    assert calls == {"create_all": 0}


@pytest.mark.asyncio
async def test_bootstrap_blocks_table_autocreate_in_production(monkeypatch):
    calls = {"create_all": 0}

    async def fake_create_all_tables() -> None:
        calls["create_all"] += 1

    monkeypatch.setattr(app_bootstrap.settings, "auto_create_tables", True)
    monkeypatch.setattr(app_bootstrap.settings, "environment", "production")
    monkeypatch.setattr(app_bootstrap, "create_all_tables", fake_create_all_tables)

    with pytest.raises(RuntimeError, match="AUTO_CREATE_TABLES"):
        await app_bootstrap.bootstrap_application_state()

    assert calls == {"create_all": 0}
