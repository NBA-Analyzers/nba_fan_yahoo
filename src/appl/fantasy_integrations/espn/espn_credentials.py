"""Encryption of the ESPN cookies (espn_s2, SWID).

They open the owner's whole ESPN account, so they are stored only as Fernet tokens,
with the key in ESPN_COOKIE_KEY (a Secret Manager secret on Cloud Run). With no key
nothing is stored or read: better no ESPN than plaintext cookies.

Generate a key with:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import os

from cryptography.fernet import Fernet, InvalidToken


class CredentialsError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = os.getenv("ESPN_COOKIE_KEY")
    if not key:
        raise CredentialsError("ESPN_COOKIE_KEY is not set; ESPN cookies cannot be stored safely")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise CredentialsError("ESPN_COOKIE_KEY is not a valid Fernet key")


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        # Key rotated or the row was tampered with; the user has to reconnect
        raise CredentialsError("Stored ESPN cookies can't be decrypted; please reconnect ESPN")
