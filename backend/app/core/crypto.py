"""BYOK envelope encryption (AES-256-GCM).

Model: a platform master KEK (env) wraps a per-tenant DEK; the DEK encrypts
values. Wrapped DEKs live in `tenant_keys`. For BYOK tenants the master KEK can
be replaced by the tenant's own KMS key reference (extension point).

Applied to high-risk secrets (integration secrets, documents), not to lookup
columns (emails/phones must stay searchable) — documented tradeoff,
docs/SECURITY.md.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

settings = get_settings()

NONCE_LEN = 12


def _decode_key(value: str, what: str) -> bytes:
    try:
        key = base64.b64decode(value)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{what} is not valid base64") from exc
    if len(key) != 32:
        raise ValueError(f"{what} must decode to exactly 32 bytes")
    return key


def master_key() -> bytes:
    if not settings.master_kek_b64:
        raise ValueError(
            "MASTER_KEK_B64 is not configured — generate one with: openssl rand -base64 32"
        )
    return _decode_key(settings.master_kek_b64, "MASTER_KEK_B64")


def _encrypt(key: bytes, plaintext: bytes) -> bytes:
    nonce = os.urandom(NONCE_LEN)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def _decrypt(key: bytes, blob: bytes) -> bytes:
    return AESGCM(key).decrypt(blob[:NONCE_LEN], blob[NONCE_LEN:], None)


def generate_dek() -> str:
    """A fresh tenant DEK, base64 — store only the WRAPPED form."""
    return base64.b64encode(os.urandom(32)).decode()


def wrap_dek(dek_b64: str) -> str:
    dek = _decode_key(dek_b64, "tenant DEK")
    return base64.b64encode(_encrypt(master_key(), dek)).decode()


def unwrap_dek(wrapped_b64: str) -> str:
    blob = base64.b64decode(wrapped_b64)
    return base64.b64encode(_decrypt(master_key(), blob)).decode()


def encrypt_value(dek_b64: str, plaintext: str) -> str:
    dek = _decode_key(dek_b64, "tenant DEK")
    return base64.b64encode(_encrypt(dek, plaintext.encode("utf-8"))).decode()


def decrypt_value(dek_b64: str, blob_b64: str) -> str:
    dek = _decode_key(dek_b64, "tenant DEK")
    return _decrypt(dek, base64.b64decode(blob_b64)).decode("utf-8")


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a platform-held integration secret with the master KEK.

    Used for OAuth tokens on shared-tenant integrations (accounting). Requires
    MASTER_KEK_B64; callers should treat a missing KEK as a configuration error.
    """
    return base64.b64encode(_encrypt(master_key(), plaintext.encode("utf-8"))).decode()


def decrypt_secret(blob_b64: str) -> str:
    return _decrypt(master_key(), base64.b64decode(blob_b64)).decode("utf-8")
