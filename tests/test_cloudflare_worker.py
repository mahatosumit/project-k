"""Tests for the Cloudflare Python Worker adapter layer."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cloudflare.worker import Default, app as worker_app, sync_cloudflare_env


def test_cloudflare_worker_exports():
    """Ensure the Cloudflare Worker module provides required symbols."""
    assert Default is not None
    assert worker_app is not None
    assert callable(sync_cloudflare_env)


def test_sync_cloudflare_env(monkeypatch):
    """Ensure environment attributes and Hyperdrive connection strings map to os.environ."""
    monkeypatch.delenv("CUSTOM_TEST_VAR", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    fake_env = SimpleNamespace(
        APP_NAME="Vasool-Worker",
        CUSTOM_TEST_VAR="cf-test-val",
        HYPERDRIVE=SimpleNamespace(connection_string="postgresql+psycopg://user:pass@hyperdrive.internal/db"),
    )

    sync_cloudflare_env(fake_env)

    assert os.environ.get("CUSTOM_TEST_VAR") == "cf-test-val"
    assert os.environ.get("DATABASE_URL") == "postgresql+psycopg://user:pass@hyperdrive.internal/db"


@pytest.mark.asyncio
async def test_cloudflare_worker_scheduled_execution():
    """Verify that the scheduled() cron handler executes reminder and reconciliation cycles cleanly."""
    worker = Default()
    controller = SimpleNamespace(cron="*/5 * * * *", scheduledTime=1700000000000)
    fake_env = SimpleNamespace(APP_ENV="dev")
    ctx = MagicMock()

    # scheduled is an async function
    await worker.scheduled(controller, fake_env, ctx)


def test_cloudflare_worker_app_routes(client):
    """Verify that the FastAPI application exported by the Worker adapter correctly handles endpoints."""
    resp = client.get("/robots.txt")
    assert resp.status_code == 200
    assert "User-agent: *" in resp.text

    resp = client.get("/favicon.ico")
    assert resp.status_code == 204
