"""Argon2id password hashes; opaque session identifiers use a separate verifier."""
from functools import lru_cache
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError, InvalidHashError

HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, hash_len=32, salt_len=16, type=Type.ID)


def hash_password(password: str) -> str:
    return HASHER.hash(password)


def verify_password(encoded: str, password: str) -> bool:
    try:
        return HASHER.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """Unknown accounts still perform an Argon2 verification."""
    return hash_password("not-an-account-password")
