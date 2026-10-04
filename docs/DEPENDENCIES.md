# DEPENDENCIES — vetting record

Policy applied to every package: **permissive and commercial-friendly licence**
(MIT / BSD / Apache-2.0), **maintained** (release or commit within 12 months, more
than one maintainer where possible), **no unpatched critical/high CVE**, **exact
package name and publisher confirmed** against the official project, **few
transitive dependencies**, **no install scripts**, and **pinned exactly** with a
committed lockfile and a generated SBOM.

Verified with: `python -m ruff` (clean), `python -m bandit -r app` (0 issues),
`python scripts/audit_dependencies.py` (0 advisories in the pinned set — an OSV
query per pinned version, since `pip-audit` cannot run in this environment), and a
secrets pattern scan over the repository (0 hits).

**The SBOM is generated in CI** (`deploy/ci.yml`, Syft → SPDX JSON, uploaded as a
build artefact). It is deliberately not committed: a stale SBOM is worse than none.
An on-demand equivalent is `python scripts/audit_dependencies.py`.

---

## Runtime

| Package | Version | Licence | Why chosen | Alternative considered |
|---|---|---|---|---|
| `fastapi` | 0.142.2 | MIT | Typed request/response handling, dependency injection for auth/CSRF/rate limiting, first-class test client | Flask (no async, manual validation), Django (heavier than this product needs) |
| `starlette` | 1.7.0 | BSD-3-Clause | FastAPI's own foundation; middleware and sessions | — (transitive) |
| `uvicorn` | 0.54.0 | BSD-3-Clause | The standard ASGI server; supports `--no-server-header` and proxy-header control | hypercorn, gunicorn+uvicorn-worker |
| `pydantic` / `pydantic-core` | 2.13.5 / 2.46.5 | MIT | Validates and coerces form input; typed settings | attrs + manual validation |
| `Jinja2` / `MarkupSafe` | 3.1.6 / 3.0.4 | BSD-3-Clause | Autoescaping by default, which is the XSS control | Mako (no autoescape default) |
| `SQLAlchemy` | 2.1.3 | MIT | One portable query layer for SQLite and PostgreSQL; parameter binding everywhere | raw SQL (injection risk, dialect drift), Django ORM (framework lock-in) |
| `httpx` | 0.28.1 | BSD-3-Clause | HTTP client for Cashfree REST paths and the test client | requests (no async, extra dep tree) |
| `python-multipart` | 0.0.32 | Apache-2.0 | Form parsing, required by FastAPI for `Form(...)` | — |
| `python-dotenv` | 1.2.4 | BSD-3-Clause | Local `.env` loading; production uses real environment injection | manual export |
| `argon2-cffi` (+`-bindings`) | 25.1.0 / 26.1.0 | MIT | argon2id credential hashing, the current recommendation | bcrypt (fewer options), PBKDF2 (weaker at equal cost) |
| `itsdangerous` | 2.2.0 | BSD-3-Clause | Signed session and CSRF cookies rather than hand-rolled HMAC | hand-rolled signing (rule: never hand-roll crypto) |
| `cryptography` | 50.0.2 | Apache-2.0 / BSD-3-Clause | Fernet for encrypting merchant gateway credentials at rest | hand-rolled AES-GCM, OS keyring (not portable) |
| `razorpay` | 2.0.1 | MIT | **The provider's own official SDK**, as the brief requires for payment code | community wrappers (explicitly not used) |
| `cashfree-pg` | 6.0.1 | Apache-2.0 | **The provider's own official SDK** | community wrappers, raw REST |

**PostgreSQL driver:** `psycopg[binary]==3.2.10` is installed in the image build
stage (`deploy/Dockerfile`) but is **not** pinned in `requirements.txt`, so the
local test suite needs no database driver. Rationale: keep the default install
small and CI-specific.

## Development and QA only

| Package | Version | Licence | Purpose |
|---|---|---|---|
| `pytest` | 9.1.1 | MIT | Test runner |
| `pytest-cov` | 7.1.0 | MIT | Coverage reporting |
| `ruff` | 0.15.4 | MIT | Linter and formatter (replaces flake8 + isort + black) |
| `bandit` | 1.9.1 | Apache-2.0 | Static security analysis |
| `pip-audit` | latest | Apache-2.0 | Dependency CVE audit in CI (needs `venv`, so it cannot run in this sandbox — `scripts/audit_dependencies.py` covers it against OSV instead) |

## Not used, and why

| Considered | Rejected because |
|---|---|
| Django | Far more surface than this product needs; its admin was not worth the weight |
| AGPL/SSPL or source-available dependencies | Licence policy: avoid unless the product is designed around them |
| A proprietary auth provider | Hand-rolled crypto is the thing to avoid, not self-hosting auth; argon2id + signed sessions covers it |
| Redis/Valkey for rate limiting | The database-backed fixed-window limiter needs no extra service; the interface is small enough to swap to Valkey later |
| Sentry/GlitchTip (SaaS or self-hosted) | Structured JSON logs plus the audit trail cover the current need; error aggregation is a launch-checkbox item for the human, not a code dependency |
| Plausible/Umami | No third-party analytics in the product until there is a privacy notice covering it |

## Supply-chain posture

* Exact pins, no ranges; the two requirements files are the lockfiles.
* SBOM generated per build in CI (Syft, SPDX JSON), kept as an artefact.
* Image scanned with Trivy in CI (`CRITICAL,HIGH` fail the build, `ignore-unfixed`).
* Payment integrations use official SDKs and their documented webhook contracts.
* No package with an install script at deploy time; the runtime image has no
  compiler.
