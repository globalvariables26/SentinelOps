"""Security utilities using direct bcrypt and PyJWT (no passlib)."""
from datetime import timedelta
try:
    import bcrypt
except ImportError:  # local test/runtime fallback; production requirements include bcrypt
    bcrypt = None
import hashlib
import os
import jwt
from app.core.config import settings
from app.core.time import utcnow

ALGORITHM = "HS256"


def get_password_hash(password: str) -> str:
    if bcrypt is not None:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return "$pbkdf2$" + salt.hex() + "$" + digest.hex()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        if hashed_password.startswith("$pbkdf2$"):
            _, salt_hex, digest_hex = hashed_password.split("$")[1:]
            actual = hashlib.pbkdf2_hmac("sha256", plain_password.encode(), bytes.fromhex(salt_hex), 120_000).hex()
            return actual == digest_hex
        if bcrypt is None:
            return False
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = utcnow() + expires_delta
    else:
        expire = utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except Exception:
        return None
