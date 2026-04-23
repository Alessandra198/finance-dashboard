import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


SESSION_SECRET = os.getenv("SESSION_SECRET", "")
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "session")
SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(7 * 24 * 60 * 60)))
COOKIE_SECURE = _env_bool("COOKIE_SECURE", default=_env_bool("PRODUCTION", default=False))

_serializer: URLSafeTimedSerializer | None = None


def _get_serializer() -> URLSafeTimedSerializer:
    """Lazy init so scripts can import ``hash_password`` without ``SESSION_SECRET``."""
    global _serializer
    if _serializer is None:
        if not SESSION_SECRET or not SESSION_SECRET.strip():
            raise RuntimeError("SESSION_SECRET is not set")
        _serializer = URLSafeTimedSerializer(SESSION_SECRET, salt="finance-dashboard-session")
    return _serializer


def hash_password(password: str, *, iterations: int = 310_000) -> str:
    """
    Stores a salted PBKDF2-HMAC-SHA256 hash.

    Format: base64(salt)$iterations$base64(hash)
    """

    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)

    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"{salt_b64}${iterations}${digest_b64}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_b64, iterations_s, digest_b64 = stored_hash.split("$", 2)
        salt = base64.b64decode(salt_b64)
        iterations = int(iterations_s)
        expected_digest = base64.b64decode(digest_b64)
    except Exception:
        return False

    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(digest, expected_digest)


def encode_session(uid: int) -> str:
    # Keep payload minimal; the serializer adds an HMAC signature.
    return _get_serializer().dumps({"uid": uid})


def decode_session(token: str) -> int | None:
    try:
        payload: Any = _get_serializer().loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return int(payload["uid"])
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
        return None


@dataclass(frozen=True)
class SessionUser:
    id: int
    email: str


def set_session_cookie(response: Any, uid: int) -> None:
    token = encode_session(uid)
    response.set_cookie(
    key=SESSION_COOKIE_NAME,
    value=token,
    httponly=True,
    samesite="none",
    secure=COOKIE_SECURE,
    path="/",
    max_age=SESSION_MAX_AGE_SECONDS,
)


def clear_session_cookie(response: Any) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")

