"""Password hashes and the strength rule for users' own passwords (see
api/auth.py, which keeps them in api/data/passwords.json).

Stored as "pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>".
"""
import hashlib
import hmac
import secrets

PASSWORD_ITERATIONS = 600_000


def password_problem(password: str) -> str | None:
    """Why `password` is too weak to be set, or None: at least 9 characters,
    an uppercase letter and a digit."""
    if len(password) < 9:
        return "at least 9 characters"
    if not any(c.isupper() for c in password):
        return "at least one uppercase letter"
    if not any(c.isdigit() for c in password):
        return "at least one number"
    return None


def hash_password(password: str, iterations: int = PASSWORD_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def password_matches(stored: str, password: str) -> bool:
    try:
        algo, iterations, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                  bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(got, bytes.fromhex(digest))
    except ValueError:
        return False

