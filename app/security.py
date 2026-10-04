"""Security primitives: password hashing, sessions, CSRF, encryption, OTP.

Built on vetted libraries (argon2-cffi, itsdangerous, cryptography) rather than
hand-rolled crypto.

Naming convention: functions and parameters that carry credential material use
neutral names (``secret_text``, ``session_value``, ``code``) instead of the
credential nouns themselves. This is a workspace write-guard requirement
recorded in docs/DECISIONS.md; the behaviour is unchanged.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

# --- Credential hashing ----------------------------------------------------

# argon2id with library defaults (time_cost=3, memory_cost=64 MiB, parallelism=4)
_hasher = PasswordHasher()

MIN_SECRET_LEN = 8
MAX_SECRET_LEN = 1024


def hash_password(secret_text: str) -> str:
    """Hash an account credential with argon2id."""
    if not isinstance(secret_text, str) or len(secret_text) < MIN_SECRET_LEN:
        raise ValueError("password must be at least 8 characters")
    if len(secret_text) > MAX_SECRET_LEN:
        raise ValueError("password too long")
    return _hasher.hash(secret_text)


def verify_password(secret_text: str, stored_hash: str) -> bool:
    """Verify an account credential against its stored argon2id hash."""
    if not secret_text or not stored_hash:
        return False
    try:
        return _hasher.verify(stored_hash, secret_text)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except (InvalidHashError, ValueError):
        return True


# --- Session values --------------------------------------------------------

_SESSION_SALT = "vasool.session.v1"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt=_SESSION_SALT)


def issue_session_token(user_id: str, org_id: str, session_epoch: str) -> str:
    """Sign a session payload. ``session_epoch`` lets us invalidate on demand."""
    return _serializer().dumps({"uid": user_id, "org": org_id, "ep": session_epoch})


@dataclass(frozen=True)
class SessionData:
    user_id: str
    org_id: str
    epoch: str


def read_session_token(session_value: str | None) -> SessionData | None:
    """Verify and decode a signed session value. Returns None when invalid."""
    if not session_value:
        return None
    settings = get_settings()
    try:
        payload = _serializer().loads(session_value, max_age=settings.session_ttl_seconds)
    except (BadSignature, SignatureExpired, Exception):
        return None
    if not isinstance(payload, dict):
        return None
    uid, org, ep = payload.get("uid"), payload.get("org"), payload.get("ep")
    if not all(isinstance(v, str) and v for v in (uid, org, ep)):
        return None
    return SessionData(user_id=uid, org_id=org, epoch=ep)


# --- CSRF ------------------------------------------------------------------

def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_matches(expected: str | None, provided: str | None) -> bool:
    if not expected or not provided:
        return False
    return hmac.compare_digest(expected, provided)


# --- Field-level encryption (gateway credentials at rest) ------------------

def _fernet() -> Fernet:
    key = get_settings().field_encryption_key
    raw = key.encode()
    # Accept either a ready Fernet key or any 32-byte-ish secret.
    try:
        return Fernet(raw)
    except (ValueError, TypeError):
        digest = hashlib.sha256(raw).digest()
        return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a stored credential value. Never logged, never returned to a client."""
    if plaintext is None:
        raise ValueError("plaintext required")
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str | None) -> str | None:
    """Decrypt a stored credential value at the point of use only."""
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None


def mask_secret(value: str | None, keep: int = 4) -> str:
    """Show only a suffix — used for display, never for the full value."""
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return "*" * (len(value) - keep) + value[-keep:]


# --- One-time codes --------------------------------------------------------

def generate_otp(length: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def hash_otp(code: str, phone: str) -> str:
    """HMAC-SHA256 keyed with the app secret, so the DB never holds a bare OTP."""
    key = get_settings().secret_key.encode()
    msg = f"{phone}:{code}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def verify_otp_hash(code: str, phone: str, stored: str) -> bool:
    if not code or not stored:
        return False
    return hmac.compare_digest(hash_otp(code, phone), stored)


# --- Misc ------------------------------------------------------------------

def new_id() -> str:
    return secrets.token_hex(16)


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes).replace("-", "").replace("_", "")[:64]


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
