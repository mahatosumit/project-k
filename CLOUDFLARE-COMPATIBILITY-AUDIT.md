# Cloudflare Workers Compatibility Audit — Vasool

**Date:** 2026-10-04  
**Target Platform:** Cloudflare Python Workers (Pyodide / WASM runtime + ASGI + Hyperdrive)  
**Application:** Vasool — receivables follow-up & invoice collection for Indian service businesses  

---

## Executive Summary

Vasool is built on **FastAPI + Jinja2 + SQLAlchemy + SQLite/PostgreSQL**, with domain logic for Indian taxation (GST), legal interest (MSMED Act s.16), secure gateway integrations (Razorpay, Cashfree, Mock sandbox), and a deterministic 9-step reminder ladder.

This audit evaluates the feasibility of deploying Vasool to Cloudflare Workers using Cloudflare's **Python Workers** platform with the **Workers ASGI adapter** (`workers.asgi`), **Cron Triggers**, and **Hyperdrive** for PostgreSQL connectivity.

### Compatibility Overview
* **Compatible (Ready as-is)**: FastAPI application core, routing, Jinja2 template rendering, domain arithmetic (GST, MSMED, money formatting), Pydantic validation, itsdangerous session signing, Fernet encryption, and HTTP-based messaging adapters (WhatsApp Cloud API, SMS DLT API).
* **Requires Adaptation**: 
  1. Worker entrypoint routing via `workers.asgi.fetch` instead of `uvicorn` server process.
  2. Scheduled background jobs (`scripts/run_jobs.py`) converted to Cloudflare Cron Triggers (`async def scheduled`).
  3. Environment variables & secret injection mapped from Cloudflare Worker runtime bindings (`env`) to application settings.
  4. Filesystem logging (`RotatingFileHandler` to `/data/logs`) bypassed in favor of structured stdout/Logpush.
  5. Database connection pooling adapted for serverless invocation lifecycle via Cloudflare Hyperdrive.
* **Incompatible for In-Worker Execution**:
  1. Filesystem-based SQLite persistence across request lifecycles (Worker filesystem is ephemeral and read-only for persistence).
  2. Subprocess-based database backups (`pg_dump` / `pg_restore` shell execution).
  3. `uvicorn` command-line process manager (Workers runtime acts as the host server).
* **Security & Invariants Status**: Fully preserved. No security compromises, no downgrade from server-to-server gateway lookup to redirect validation, and no exposure of mock sandbox gateways in production.

---

## Detailed Subsystem Audit

### 1. Framework & HTTP Layer (FastAPI & Starlette)
* **Status**: **Compatible** (Requires ASGI Entrypoint)
* **Details**: 
  - FastAPI `0.142.2` and Starlette `1.7.0` run directly on Pyodide.
  - Middlewares (`SecurityHeadersMiddleware`, `BodyLimitMiddleware`, `RequestContextMiddleware`, `SessionMiddleware`) operate at the ASGI layer and function identically.
  - Custom error handling (`RequestValidationError`, `BadSignature`, 404 handler) works as expected.
* **Workers Adaptation**: Use `cloudflare/worker.py` with `workers.asgi.fetch(app, request, self.env)`.

---

### 2. Database & Data Layer (SQLAlchemy, PostgreSQL, Hyperdrive, SQLite)
* **Status**: **Requires Adaptation (PostgreSQL via Hyperdrive)** / **Incompatible (Persistent SQLite on Workers)**
* **Details**:
  - **SQLAlchemy `2.1.3`**: Pure Python core and ORM queries execute without issue in Pyodide.
  - **PostgreSQL Connectivity**: Cloudflare Python Workers support TCP sockets (GA September 2026). PostgreSQL queries through **Hyperdrive** (`postgresql+psycopg://` or `postgresql+asyncpg://`) provide connection pooling and query acceleration.
  - **SQLite**: Local SQLite files (`vasool.db`) are ephemeral in Workers. While SQLite in-memory works for unit tests, production deployments on Workers **must** connect to a hosted PostgreSQL instance via Hyperdrive.
  - **Migrations (`app/migrations/*.sql`)**: The forward-only migration runner (`run_migrations()`) reads bundled SQL files and executes them over the SQLAlchemy connection. When running in serverless mode, migrations can either run on worker startup/lifespan or as a pre-deployment step.

---

### 3. File System & Storage
* **Status**: **Classified & Adapted**
* **Classification**:
  | File System Asset | Current Path | Worker Classification | Strategy |
  |---|---|---|---|
  | HTML Templates | `app/web/templates/` | **Class A: Bundled / Read-Only** | Bundled in Worker package; loaded by Jinja2 from package root |
  | Static Assets (CSS, SVG) | `app/web/static/` | **Class A: Bundled / Read-Only** | Mounted via Starlette `StaticFiles` or Workers Static Assets |
  | SQL Migrations | `app/migrations/*.sql` | **Class A: Bundled / Read-Only** | Bundled with Worker; executed against PostgreSQL |
  | Translation Locales | `app/locales/*.json` | **Class A: Bundled / Read-Only** | Bundled; loaded into memory on startup |
  | Application Logs | `logs/app.log` | **Class D: External / Stdout** | Redirected to stdout JSON-lines (Cloudflare Logpush / Workers Logs) |
  | Database Backups | `backups/vasool-*.pgdump` | **Class B/E: R2 / External Host** | Kept outside Worker runtime; managed via R2 or managed DB automated snapshots |
  | Database File | `vasool.db` | **Class E: External Database** | Use PostgreSQL over Hyperdrive (no persistent local file) |

---

### 4. Background Jobs & Schedulers
* **Status**: **Requires Adaptation (Cloudflare Cron Triggers)**
* **Details**:
  - The existing background loop (`scripts/run_jobs.py` running in Docker sidecar) executes two tasks:
    1. Reminder dispatch (`reminder_service.dispatch_due`)
    2. Gateway sweep & reconciliation (`payment_service.daily_reconciliation`)
    3. Maintenance & audit log pruning (`audit_service.prune_audit`, `ratelimit.prune`)
  - **Workers Solution**: Define `async def scheduled(self, controller, env, ctx)` in `cloudflare/worker.py` and register a 5-minute cron trigger (`*/5 * * * *`) in `wrangler.jsonc`.
  - The domain and service logic remains 100% unchanged.

---

### 5. Payment Gateways & Cryptography
* **Status**: **Compatible & High Security Preserved**
* **Details**:
  - **Razorpay**: Official SDK (`razorpay==2.0.1`) is pure Python and makes HTTP calls. Webhook verification calculates HMAC-SHA256 over `raw_body` using `hmac.compare_digest`.
  - **Cashfree**: Official SDK (`cashfree-pg==6.0.1`) makes REST calls. Webhook verification handles both `timestamp + '.' + raw_body` and SDK `timestamp + raw_body` schemes.
  - **Field Encryption**: `cryptography.fernet.Fernet` encrypts merchant gateway keys at rest. Fully supported in Pyodide with WASM-compiled cryptography.
  - **Password Hashing**: `argon2-cffi` provides Argon2id hashing. Supported in Pyodide WASM builds.
  - **Session Signing**: `itsdangerous.URLSafeTimedSerializer` uses HMAC-SHA1/SHA256 and is pure Python.
  - **Invariant Check**: No mock sandbox gateway is allowed in production (`_assert_production_ready()` enforces this). Server-to-server validation is strictly retained.

---

### 6. Outbound Messaging
* **Status**: **Compatible**
* **Details**:
  - **WhatsApp**: Calls Meta Graph API over `httpx.post` (HTTPS).
  - **SMS (DLT)**: Calls Indian SMS gateway over `httpx.post` (HTTPS).
  - **Email (SMTP)**: Python `smtplib` requires direct outbound TCP sockets (supported on Cloudflare Workers) or can route through transactional HTTP email APIs (e.g. Mailchannels / Resend / AWS SES).
  - **Console Sink**: Logs to stdout for dev/sandbox.

---

## Subsystem Audit Matrix

| Subsystem | Component | Status | Action Required |
|---|---|---|---|
| **Entrypoint** | `uvicorn app.main:app` | Incompatible in Workers | Replaced by `cloudflare/worker.py` using `workers.asgi` |
| **Routing** | FastAPI / Starlette Routes | **Compatible** | None. Preserved completely |
| **Templates** | Jinja2 Server-side rendering | **Compatible** | Bundled as read-only package assets |
| **Static Files** | CSS, SVG, Icons | **Compatible** | Served via Starlette StaticFiles or Workers Assets |
| **ORM** | SQLAlchemy 2.x | **Compatible** | Configured with Hyperdrive PostgreSQL URL |
| **Database** | PostgreSQL | **Compatible** | Connect via Cloudflare Hyperdrive binding |
| **Database** | SQLite (persistent) | **Incompatible** | Replaced with PostgreSQL in Cloudflare environments |
| **Migrations** | `app/migrations/*.sql` | **Compatible** | Applied against PostgreSQL database |
| **Crypto: Fernet** | `cryptography` | **Compatible** | Uses Pyodide pre-built cryptography |
| **Crypto: Argon2** | `argon2-cffi` | **Compatible** | Uses Pyodide pre-built CFFI package |
| **Crypto: HMAC** | `hmac`, `hashlib` | **Compatible** | Standard library |
| **Payments** | Razorpay SDK | **Compatible** | SDK HTTP calls work; HMAC verification preserved |
| **Payments** | Cashfree SDK | **Compatible** | SDK HTTP calls work; HMAC verification preserved |
| **Messaging** | WhatsApp Cloud API | **Compatible** | `httpx` HTTPS calls |
| **Messaging** | SMS DLT Gateway | **Compatible** | `httpx` HTTPS calls |
| **Cron Jobs** | `scripts/run_jobs.py` | **Requires Adaptation** | Triggered via `scheduled()` handler in `worker.py` |
| **Backups** | `scripts/backup.py` (`pg_dump`) | **Incompatible in Worker** | Handled at database/infrastructure layer |
| **File Logs** | `RotatingFileHandler` | **Requires Adaptation** | Switched to stdout/Logpush when filesystem is read-only |

---

## Conclusion & Architecture Decision

Vasool is **fully capable of deploying to Cloudflare Python Workers** with a lightweight adapter layer:
1. `cloudflare/worker.py` bridges Cloudflare Worker requests to the FastAPI ASGI application and maps cron events to the reminder/reconciliation services.
2. `wrangler.jsonc` configures the Python Worker, cron triggers, environment variables, and Hyperdrive connection.
3. The core application (`app/`), database schema, security invariants, payment adapters, domain maths, and Docker/Caddy deployment files remain **completely intact and functional**.
