import base64
import hashlib
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError, VerificationError
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

settings = get_settings()
_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password cannot be empty")
    return _password_hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    if not password or not encoded or not encoded.startswith("$argon2"):
        return False
    try:
        return _password_hasher.verify(encoded, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def is_hashed_password(value: str) -> bool:
    return bool(value and value.startswith("$argon2"))


def _fernet() -> Fernet:
    # Derive a valid 32-byte urlsafe-base64 Fernet key from the configured
    # secret, so operators can set PASSWORD_ENC_KEY to any string.
    raw = hashlib.sha256(settings.password_enc_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def encrypt_password(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_password(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("password_enc_key changed or data corrupted") from exc


def create_access_token(*, user_id: str, username: str, role: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
