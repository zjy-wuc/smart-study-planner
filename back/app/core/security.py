import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, ITERATIONS
    ).hex()
    return f"{ALGORITHM}${ITERATIONS}${salt.hex()}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest = stored_hash.split("$")
        iterations_int = int(iterations)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False

    if algorithm != ALGORITHM:
        return False
    if not 100000 <= iterations_int <= 2000000:
        return False

    computed = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations_int
    ).hex()
    return hmac.compare_digest(computed, digest)
