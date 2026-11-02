"""Password hashing with scrypt from the standard library (no extra dependency). The stored string
carries its own parameters, so they can be raised later and old hashes still verify."""

import base64
import hashlib
import hmac
import secrets

N, R, P = 2**14, 8, 1
MIN_LENGTH = 10
MAX_LENGTH = 200


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=64 * 1024 * 1024)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _derive(password, salt, N, R, P)
    return f"scrypt${N}${R}${P}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        got = _derive(password, base64.b64decode(salt), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, expected)


def check_strength(password: str, name: str = "") -> None:
    """Length and one obvious case; no composition rules, which push people to predictable passwords."""
    if len(password) < MIN_LENGTH:
        raise ValueError(f"the password must be at least {MIN_LENGTH} characters")
    if len(password) > MAX_LENGTH:
        raise ValueError(f"the password must be at most {MAX_LENGTH} characters")
    if name and password.casefold() == name.casefold():
        raise ValueError("the password cannot be the same as the name")
    if len(set(password)) < 4:
        raise ValueError("the password is too repetitive")
