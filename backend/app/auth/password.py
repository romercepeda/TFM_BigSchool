"""Password hashing utilities using bcrypt (Spec 00b §2).

bcrypt is intentionally slow — that is the security property that makes
brute-forcing a stolen hash database impractical. Never use a faster
general-purpose hash (MD5, SHA-256) for passwords.
"""

import bcrypt


def hash_password(plain: str) -> str:
    """Hash a plaintext password. Returns a bcrypt hash string."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches hashed. Constant-time comparison."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
