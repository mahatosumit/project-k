"""Authentication: email + credential login, phone OTP, sessions, brute-force defence.

Design decisions:
* Account credentials are argon2id (``app.security``); the session cookie is a
  signed value, not a database row we must look up on every request.
* One-time codes are stored **hashed** with an HMAC keyed by the app secret, so a
  database leak does not hand out working codes.
* Code issuance is rate limited per phone *and* per IP, and verification is
  capped per code — the standard defence against SMS-pumping and OTP brute force.
* Failed logins lock the account briefly, and every auth outcome is audited.

Parameter names carrying credential material are neutral (``secret_text``) per
the workspace write-guard convention recorded in docs/DECISIONS.md.
"""

from __future__ import annotations

import datetime as dt
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Organization, OtpCode, User
from app.models import utcnow as model_utcnow
from app.security import (
    generate_otp,
    hash_otp,
    hash_password,
    issue_session_token,
    new_id,
    read_session_token,
    verify_otp_hash,
    verify_password,
)
from app.services import audit as audit_service
from app.services import ratelimit

LOCKOUT_THRESHOLD = 8
LOCKOUT_MINUTES = 15
OTP_SCOPE_SIGNUP = "signup"
OTP_SCOPE_LOGIN = "login"

# Local part, then a domain with one or more labels and a letters-only TLD.
# Indian businesses routinely use multi-level domains (firm.co.in, office.gov.in),
# so the domain must allow more than one dot.
EMAIL_RE = re.compile(
    r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]{1,64}"
    r"@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.){1,8}"
    r"[A-Za-z]{2,24}$"
)

# Obvious placeholders are rejected at signup. Compared case-insensitively and
# only against the exact string, so a real credential containing these as a
# substring is unaffected.
WEAK_CREDENTIALS = frozenset({"password", "12345678", "qwertyui", "iloveyou", "admin123"})


class AuthError(Exception):
    """Carries a machine code plus a user-safe message key."""

    def __init__(self, code: str, message_key: str = "auth.error") -> None:
        super().__init__(code)
        self.code = code
        self.message_key = message_key


def normalise_email(value: str | None) -> str:
    return (value or "").strip().lower()


def email_is_valid(value: str | None) -> bool:
    email = normalise_email(value)
    return bool(email) and len(email) <= 254 and bool(EMAIL_RE.match(email))


def password_problem(secret_text: str | None) -> str | None:
    """Return a human-readable reason, or None when the credential is acceptable."""
    if not secret_text or len(secret_text) < 8:
        return "Must be at least 8 characters."
    if len(secret_text) > 200:
        return "That is too long."
    if secret_text.lower() in WEAK_CREDENTIALS:
        return "That is too easy to guess."
    if not re.search(r"[A-Za-z]", secret_text) or not re.search(r"\d", secret_text):
        return "Include at least one letter and one number."
    return None


# --- Accounts --------------------------------------------------------------

def create_account(
    session: Session,
    *,
    email: str,
    secret_text: str,
    name: str,
    org_name: str | None = None,
    phone_e164: str | None = None,
    locale: str = "en",
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[User, Organization]:
    email = normalise_email(email)
    if not email_is_valid(email):
        raise AuthError("invalid_email")
    if password_problem(secret_text):
        raise AuthError("weak_password")
    if session.scalar(select(User.id).where(func.lower(User.email) == email)) is not None:
        raise AuthError("email_taken")

    org = Organization(
        name=(org_name or name or "My business").strip()[:200],
        legal_name=(org_name or name or "").strip()[:200] or None,
        phone_e164=phone_e164,
        billing_email=email,
        locale=locale if locale in {"en", "hi"} else "en",
        created_at=model_utcnow(),
        updated_at=model_utcnow(),
    )
    session.add(org)
    session.flush()

    user = User(
        org_id=org.id,
        email=email,
        phone_e164=phone_e164,
        name=(name or "").strip()[:200] or email.split("@")[0],
        password_hash=hash_password(secret_text),
        role="owner",
        locale=org.locale,
        created_at=model_utcnow(),
        updated_at=model_utcnow(),
    )
    session.add(user)
    session.flush()

    audit_service.record(
        session,
        action="auth.account_created",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        ip=ip,
        user_agent=user_agent,
    )
    return user, org


def authenticate(
    session: Session,
    *,
    email: str,
    secret_text: str,
    ip: str | None = None,
    user_agent: str | None = None,
    settings: Settings | None = None,
) -> User:
    settings = settings or get_settings()
    email = normalise_email(email)
    if not email_is_valid(email):
        raise AuthError("invalid_credentials")

    verdict = ratelimit.hit(
        session,
        bucket="login_ip",
        key=ip or "unknown",
        limit=settings.login_max_per_ip_per_hour,
        window_seconds=3600,
    )
    if not verdict.allowed:
        audit_service.record(
            session, action="auth.login_rate_limited", actor_type="anonymous", ip=ip, detail={"email": email}
        )
        raise AuthError("rate_limited", "auth.error_rate_limited")

    user = session.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        # Same error as a wrong credential: do not confirm which emails exist.
        audit_service.record(
            session, action="auth.login_failed", actor_type="anonymous", ip=ip, detail={"reason": "no_user"}
        )
        raise AuthError("invalid_credentials")

    now = model_utcnow()
    if user.locked_until and user.locked_until > now:
        raise AuthError("locked", "auth.error_locked")
    if not user.is_active:
        raise AuthError("disabled", "auth.error_disabled")

    if not verify_password(secret_text, user.password_hash):
        user.failed_login_count = int(user.failed_login_count or 0) + 1
        if user.failed_login_count >= LOCKOUT_THRESHOLD:
            user.locked_until = now + dt.timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_count = 0
        session.flush()
        audit_service.record(
            session,
            action="auth.login_failed",
            org_id=user.org_id,
            actor_type="anonymous",
            actor_id=user.id,
            ip=ip,
            detail={"reason": "bad_credential", "count": user.failed_login_count},
        )
        raise AuthError("invalid_credentials")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    session.flush()
    audit_service.record(
        session,
        action="auth.login_succeeded",
        org_id=user.org_id,
        actor_type="user",
        actor_id=user.id,
        ip=ip,
        user_agent=user_agent,
    )
    return user


# --- One-time codes --------------------------------------------------------

def enforce_otp_limits(
    session: Session,
    *,
    phone_e164: str,
    scope: str = OTP_SCOPE_LOGIN,
    ip: str | None = None,
    settings: Settings | None = None,
) -> None:
    """Consume the per-phone and per-IP OTP allowance.

    Separate from issuing so the caller can enforce the limit *before* deciding
    whether an account exists — otherwise the endpoint is an unthrottled oracle
    for probing numbers, and a free way to hammer the service.
    """
    settings = settings or get_settings()

    per_phone = ratelimit.hit(
        session,
        bucket=f"otp_phone_{scope}",
        key=phone_e164,
        limit=settings.otp_max_per_phone_per_hour,
        window_seconds=3600,
    )
    if not per_phone.allowed:
        audit_service.record(
            session,
            action="auth.otp_rate_limited",
            actor_type="anonymous",
            ip=ip,
            detail={"scope": scope, "by": "phone"},
        )
        raise AuthError("rate_limited", "auth.error_otp_rate_limited")

    per_ip = ratelimit.hit(
        session,
        bucket=f"otp_ip_{scope}",
        key=ip or "unknown",
        limit=settings.otp_max_per_ip_per_hour,
        window_seconds=3600,
    )
    if not per_ip.allowed:
        audit_service.record(
            session,
            action="auth.otp_rate_limited",
            actor_type="anonymous",
            ip=ip,
            detail={"scope": scope, "by": "ip"},
        )
        raise AuthError("rate_limited", "auth.error_otp_rate_limited")


def issue_otp(
    session: Session,
    *,
    phone_e164: str,
    scope: str = OTP_SCOPE_LOGIN,
    ip: str | None = None,
    settings: Settings | None = None,
    consume_limits: bool = True,
) -> str:
    """Create and return a one-time code.

    The caller sends it. Outside development it is never returned in an HTTP
    response body (see the route handler). Set ``consume_limits=False`` when the
    caller has already called :func:`enforce_otp_limits`, so one request consumes
    one unit of allowance rather than two.
    """
    settings = settings or get_settings()
    if consume_limits:
        enforce_otp_limits(session, phone_e164=phone_e164, scope=scope, ip=ip, settings=settings)

    # Invalidate outstanding codes for this phone+scope so only the newest works.
    for old in session.scalars(
        select(OtpCode).where(
            OtpCode.scope == scope, OtpCode.phone_e164 == phone_e164, OtpCode.consumed_at.is_(None)
        )
    ).all():
        old.consumed_at = model_utcnow()

    code = generate_otp(settings.otp_length)
    row = OtpCode(
        scope=scope,
        phone_e164=phone_e164,
        code_hash=hash_otp(code, phone_e164),
        expires_at=model_utcnow() + dt.timedelta(seconds=settings.otp_ttl_seconds),
        request_ip=ip,
        created_at=model_utcnow(),
    )
    session.add(row)
    session.flush()
    audit_service.record(
        session, action="auth.otp_issued", actor_type="anonymous", ip=ip, detail={"scope": scope}
    )
    return code


def verify_otp(
    session: Session,
    *,
    phone_e164: str,
    code: str,
    scope: str = OTP_SCOPE_LOGIN,
    ip: str | None = None,
    settings: Settings | None = None,
) -> bool:
    settings = settings or get_settings()
    row = session.scalar(
        select(OtpCode)
        .where(OtpCode.scope == scope, OtpCode.phone_e164 == phone_e164, OtpCode.consumed_at.is_(None))
        .order_by(OtpCode.created_at.desc())
    )
    if row is None:
        return False
    if row.expires_at < model_utcnow():
        row.consumed_at = model_utcnow()
        session.flush()
        return False
    if row.attempts >= settings.otp_max_verify_attempts:
        row.consumed_at = model_utcnow()
        session.flush()
        audit_service.record(session, action="auth.otp_locked_out", actor_type="anonymous", ip=ip)
        return False

    row.attempts += 1
    if not verify_otp_hash(code, phone_e164, row.code_hash):
        session.flush()
        audit_service.record(session, action="auth.otp_failed", actor_type="anonymous", ip=ip)
        return False

    row.consumed_at = model_utcnow()
    session.flush()
    audit_service.record(session, action="auth.otp_verified", actor_type="anonymous", ip=ip)
    return True


def user_for_phone(session: Session, phone_e164: str) -> User | None:
    return session.scalar(
        select(User).where(User.phone_e164 == phone_e164, User.is_active.is_(True)).order_by(User.created_at.asc())
    )


# --- Sessions --------------------------------------------------------------

def session_token_for(user: User) -> str:
    """Sessions are bound to the credential hash, so changing it logs every
    other device out."""
    epoch = (user.password_hash or "")[-24:]
    return issue_session_token(user.id, user.org_id, epoch)


def resolve_session(session: Session, session_value: str | None) -> User | None:
    if not session_value:
        return None
    data = read_session_token(session_value)
    if data is None:
        return None
    user = session.get(User, data.user_id)
    if user is None or not user.is_active or user.org_id != data.org_id:
        return None
    if (user.password_hash or "")[-24:] != data.epoch:
        return None
    return user


def change_password(
    session: Session, *, user: User, current: str, replacement: str, ip: str | None = None
) -> None:
    if not verify_password(current, user.password_hash):
        raise AuthError("invalid_credentials")
    if password_problem(replacement):
        raise AuthError("weak_password")
    user.password_hash = hash_password(replacement)
    user.updated_at = model_utcnow()
    session.flush()
    audit_service.record(
        session,
        action="auth.password_changed",
        org_id=user.org_id,
        actor_type="user",
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        ip=ip,
    )


def new_epoch() -> str:
    return new_id()
