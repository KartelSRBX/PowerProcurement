"""Encrypts secrets saved from the Settings tab (API keys) before they reach the database.

The Fernet key comes from APP_SECRET_KEY, or is generated once in DATA_DIR/secret.key (mode 600).
This protects a copy of the database; it does not protect against someone who can read both the
database and the data directory, or the running process."""

from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings


def _fernet(settings: Settings) -> Fernet:
    if settings.app_secret_key:
        return Fernet(settings.app_secret_key.encode())
    path = Path(settings.data_dir) / "secret.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(Fernet.generate_key())
        path.chmod(0o600)
    return Fernet(path.read_bytes().strip())


def encrypt(settings: Settings, plain: str) -> str:
    return _fernet(settings).encrypt(plain.encode()).decode()


def decrypt(settings: Settings, token: str) -> str | None:
    """None when the token cannot be read with the current key (key was lost or replaced)."""
    try:
        return _fernet(settings).decrypt(token.encode()).decode()
    except InvalidToken:
        return None
