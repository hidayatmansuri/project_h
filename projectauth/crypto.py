"""
Cryptographic primitives for projectauth (Section 7 / Constraint C8):
- AES-256-GCM authenticated encryption at rest with AAD binding and key rotation.
- HKDF-SHA256 key derivation and domain-separated HMAC-SHA256 for codes, tokens, and throttles.
- NFKC + lowercase identifier normalization.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import unicodedata
import warnings
from typing import Dict, List, Tuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger("projectauth.security")

CIPHERTEXT_VERSION = "v1"
NONCE_BYTES = 12  # 96-bit nonce for AES-GCM
KEY_BYTES = 32    # 256-bit key for AES-256-GCM
HMAC_HKDF_INFO = b"projectauth-hmac-v1"
DEV_KEY_HKDF_INFO = b"projectauth-dev-aes256gcm-v1"

_DEV_KEY_WARNED = False


class CryptoError(ValueError):
    """Raised when ciphertext is malformed, uses an unknown key ID, or fails GCM authentication."""


def normalize_identifier(value: str) -> str:
    """
    Normalizes a username or email address using Unicode NFKC and lowercase stripping
    to prevent case or Unicode confusable duplicates (Section 19.11).
    """
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value)).strip()
    return normalized.lower()


def _raw_keys_setting() -> str:
    val = getattr(settings, "PROJECTAUTH_ENCRYPTION_KEYS", None)
    if val is None:
        val = os.getenv("PROJECTAUTH_ENCRYPTION_KEYS", "")
    return (val or "").strip()


def has_configured_encryption_keys() -> bool:
    """Returns True if explicit, non-placeholder encryption keys are configured."""
    raw = _raw_keys_setting()
    if not raw or "<generate" in raw:
        return False
    return True


def _decode_urlsafe_b64_key(b64_str: str, key_id: str) -> bytes:
    padded = b64_str.strip()
    rem = len(padded) % 4
    if rem:
        padded += "=" * (4 - rem)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:
        raise ImproperlyConfigured(
            f"PROJECTAUTH_ENCRYPTION_KEYS entry '{key_id}' is not valid urlsafe base64."
        ) from exc
    if len(raw) != KEY_BYTES:
        raise ImproperlyConfigured(
            f"PROJECTAUTH_ENCRYPTION_KEYS entry '{key_id}' must decode to {KEY_BYTES} bytes (256 bits), got {len(raw)}."
        )
    return raw


def _derive_dev_key() -> bytes:
    global _DEV_KEY_WARNED
    if not _DEV_KEY_WARNED:
        msg = (
            "PROJECTAUTH_ENCRYPTION_KEYS is not set; deriving a dev-only AES-256-GCM key "
            "from SECRET_KEY because DEBUG=True. Do NOT use this in production."
        )
        warnings.warn(msg, RuntimeWarning, stacklevel=2)
        logger.warning(msg)
        _DEV_KEY_WARNED = True
    secret_bytes = str(settings.SECRET_KEY).encode("utf-8")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_BYTES,
        salt=b"projectauth-dev-salt-v1",
        info=DEV_KEY_HKDF_INFO,
    )
    return hkdf.derive(secret_bytes)


def get_keyring() -> Tuple[str, Dict[str, bytes]]:
    """
    Parses PROJECTAUTH_ENCRYPTION_KEYS="kid1:<b64>,kid0:<b64>".
    Returns (active_key_id, {key_id: 32_byte_key}).
    In DEBUG=False, missing or placeholder keys raise ImproperlyConfigured.
    """
    raw = _raw_keys_setting()
    if not raw or "<generate" in raw:
        if not getattr(settings, "DEBUG", False):
            raise ImproperlyConfigured(
                "PROJECTAUTH_ENCRYPTION_KEYS must be set to at least one 32-byte key when DEBUG=False."
            )
        dev_key = _derive_dev_key()
        return "dev", {"dev": dev_key}

    entries: List[Tuple[str, bytes]] = []
    seen_ids = set()
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        if ":" not in item:
            raise ImproperlyConfigured(
                "Each entry in PROJECTAUTH_ENCRYPTION_KEYS must be formatted as '<key_id>:<urlsafe-b64-32-bytes>'."
            )
        kid, b64_key = item.split(":", 1)
        kid = kid.strip()
        if not kid:
            raise ImproperlyConfigured("Key ID in PROJECTAUTH_ENCRYPTION_KEYS cannot be empty.")
        if kid in seen_ids:
            raise ImproperlyConfigured(f"Duplicate key ID '{kid}' in PROJECTAUTH_ENCRYPTION_KEYS.")
        seen_ids.add(kid)
        entries.append((kid, _decode_urlsafe_b64_key(b64_key, kid)))

    if not entries:
        raise ImproperlyConfigured("PROJECTAUTH_ENCRYPTION_KEYS contained no valid key entries.")

    active_kid = entries[0][0]
    return active_kid, dict(entries)


def get_active_key_id() -> str:
    active_kid, _ = get_keyring()
    return active_kid


def encrypt(plaintext: bytes | str, *, aad: bytes) -> str:
    """
    Encrypts plaintext with AES-256-GCM using the active key and a random 96-bit nonce.
    Returns 'v1:<key_id>:<b64_nonce>:<b64_ciphertext_and_tag>'.
    """
    if isinstance(plaintext, str):
        pt_bytes = plaintext.encode("utf-8")
    elif isinstance(plaintext, (bytes, bytearray)):
        pt_bytes = bytes(plaintext)
    else:
        raise TypeError("plaintext must be bytes or str")

    if not isinstance(aad, (bytes, bytearray)) or not aad:
        raise ValueError("aad must be non-empty bytes binding the encrypted field to its row")

    active_kid, keyring = get_keyring()
    key = keyring[active_kid]
    nonce = secrets.token_bytes(NONCE_BYTES)
    aesgcm = AESGCM(key)
    ct_and_tag = aesgcm.encrypt(nonce, pt_bytes, bytes(aad))

    b64_nonce = base64.urlsafe_b64encode(nonce).decode("ascii")
    b64_ct = base64.urlsafe_b64encode(ct_and_tag).decode("ascii")
    return f"{CIPHERTEXT_VERSION}:{active_kid}:{b64_nonce}:{b64_ct}"


def decrypt(token: str, *, aad: bytes) -> bytes:
    """
    Decrypts and authenticates a 'v1:<key_id>:<b64_nonce>:<b64_ciphertext_and_tag>' string.
    Raises CryptoError if tampered, wrong AAD, malformed, or key_id unknown.
    """
    if not isinstance(token, str) or not token:
        raise CryptoError("Ciphertext token must be a non-empty string.")
    if not isinstance(aad, (bytes, bytearray)) or not aad:
        raise ValueError("aad must be non-empty bytes.")

    parts = token.split(":")
    if len(parts) != 4:
        raise CryptoError("Malformed ciphertext envelope.")

    version, kid, b64_nonce, b64_ct = parts
    if version != CIPHERTEXT_VERSION:
        raise CryptoError(f"Unsupported ciphertext version '{version}'.")

    _, keyring = get_keyring()
    # Allow decrypting 'dev' key in DEBUG even if keys were later supplied in tests
    if kid not in keyring:
        if kid == "dev" and getattr(settings, "DEBUG", False):
            key = _derive_dev_key()
        else:
            raise CryptoError(f"Unknown encryption key ID '{kid}'.")
    else:
        key = keyring[kid]

    try:
        nonce = base64.urlsafe_b64decode(b64_nonce.encode("ascii"))
        ct_and_tag = base64.urlsafe_b64decode(b64_ct.encode("ascii"))
    except Exception as exc:
        raise CryptoError("Invalid base64 encoding in ciphertext.") from exc

    if len(nonce) != NONCE_BYTES:
        raise CryptoError("Invalid nonce length in ciphertext.")

    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ct_and_tag, bytes(aad))
    except InvalidTag as exc:
        raise CryptoError("Ciphertext authentication failed (tampered data or mismatched AAD).") from exc


def decrypt_str(token: str, *, aad: bytes) -> str:
    """Convenience wrapper returning UTF-8 decoded string from decrypt()."""
    return decrypt(token, aad=aad).decode("utf-8")


def needs_reencryption(token: str) -> bool:
    """Returns True if token is not encrypted under the current active key ID."""
    if not token or not isinstance(token, str):
        return False
    parts = token.split(":")
    if len(parts) != 4:
        return True
    active_kid = get_active_key_id()
    return parts[1] != active_kid


def _derive_hmac_key() -> bytes:
    secret_bytes = str(settings.SECRET_KEY).encode("utf-8")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_BYTES,
        salt=b"projectauth-hmac-salt-v1",
        info=HMAC_HKDF_INFO,
    )
    return hkdf.derive(secret_bytes)


def hmac_sha256(purpose: str, value: str | bytes) -> str:
    """
    Computes a domain-separated HMAC-SHA-256 hex digest using an HKDF-derived key.
    Used for OTP codes, recovery codes, signed token nonces, trusted-device tokens, and throttle keys.
    """
    if not purpose or not isinstance(purpose, str):
        raise ValueError("purpose must be a non-empty string")
    if isinstance(value, str):
        val_bytes = value.encode("utf-8")
    elif isinstance(value, (bytes, bytearray)):
        val_bytes = bytes(value)
    else:
        raise TypeError("value must be str or bytes")

    key = _derive_hmac_key()
    msg = f"{purpose}:".encode("utf-8") + val_bytes
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def compare_hmac(purpose: str, candidate: str | bytes, expected_hex: str) -> bool:
    """Constant-time verification of a candidate value against a stored HMAC hex digest."""
    if not expected_hex or not isinstance(expected_hex, str):
        return False
    actual = hmac_sha256(purpose, candidate)
    return hmac.compare_digest(actual, expected_hex)

