"""Cloudflare Worker adapter module forwarding to root worker.py."""

from __future__ import annotations

from worker import Default, app, sync_cloudflare_env

__all__ = ["Default", "app", "sync_cloudflare_env"]
