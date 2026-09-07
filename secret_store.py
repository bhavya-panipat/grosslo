"""
secret_store.py — the encryption seam for per-tenant RazorpayX credentials.

MULTI_TENANT_DESIGN.md 3.5 is specific about what "encrypted at rest" has to
mean here: envelope encryption via a managed KMS, where the master key never
leaves the KMS and is reachable only through an IAM role the application
process assumes. It explicitly rejects two cheaper things — pgcrypto with a
static key (which puts the decryption key in the same database or .env as the
ciphertext it protects, defeating the point for a credential whose threat model
IS "the database was read"), and hand-rolled application crypto.

THAT KMS DOES NOT EXIST YET, and cannot be built here: section 6's hosting
decision (self-managed vs RDS/Supabase/Neon) is still open, and it determines
whether this is AWS KMS or GCP KMS. Rather than store plaintext and describe it
as encrypted — the exact unearned claim 3.5 says this document does not get an
exemption from — this module makes the gap STRUCTURAL:

    A credential that is not a RazorpayX TEST-mode key cannot be stored at all
    until a real KMS backend is configured. Not discouraged. Refused.

So the honest state of the system is: test-mode credentials are held in a
clearly-labelled, self-describing non-encrypted envelope for local development,
and live credentials have nowhere to go. Nothing in the database can be
mistaken for KMS ciphertext, because every stored value names the backend that
produced it.

Wiring up a real KMS means implementing _KmsBackend and setting
SECRET_STORE_BACKEND=kms. Nothing else in the codebase changes.
"""

from __future__ import annotations

import base64
import os

# Stored values are self-describing: "<backend>:<version>:<payload>". A value
# written by one backend is never silently readable by another — decrypt()
# refuses a prefix it does not own, so a database restored into a differently
# configured environment fails loudly instead of returning garbage that looks
# like a credential.
_DEV_PREFIX = "dev-plaintext:v1:"
_KMS_PREFIX = "kms-envelope:v1:"

TEST_KEY_PREFIX = "rzp_test_"


class SecretStoreUnavailable(RuntimeError):
    """The configured backend cannot service the request (e.g. KMS not built)."""


class LiveCredentialRefused(RuntimeError):
    """
    Refusing to store a non-test-mode credential without real encryption.

    Deliberately has no override flag, mirroring
    razorpayx_client.fetch_account_balance()'s live-key guard, which also has
    none on purpose. An override would be used exactly once, in a hurry, by
    someone who meant to come back to it.
    """


def backend() -> str:
    """'dev-plaintext' (default) or 'kms'. Set via SECRET_STORE_BACKEND."""
    return os.environ.get("SECRET_STORE_BACKEND", "dev-plaintext")


def is_real_encryption() -> bool:
    """
    False for the dev backend. Callers that need to tell a user the truth about
    how their credentials are held should ask this rather than assuming.
    """
    return backend() == "kms"


def encrypt(plaintext: str, *, is_credential: bool = True) -> str:
    """
    Returns a self-describing stored value for `plaintext`.

    With the dev backend and is_credential=True, refuses anything that is not a
    RazorpayX test-mode key. That refusal is the whole design: it makes it
    impossible to end up holding a real banking credential in a store that only
    claims to protect it.
    """
    if plaintext is None:
        return None
    if backend() == "kms":
        raise SecretStoreUnavailable(
            "SECRET_STORE_BACKEND=kms but the KMS backend is not implemented. "
            "MULTI_TENANT_DESIGN.md 3.5 specifies envelope encryption against a "
            "managed KMS; which one depends on section 6's hosting decision, "
            "which is still open. Implement _KmsBackend before setting this."
        )
    if is_credential and not plaintext.startswith(TEST_KEY_PREFIX):
        raise LiveCredentialRefused(
            f"Refusing to store a credential that is not a RazorpayX test-mode key "
            f"(expected a '{TEST_KEY_PREFIX}' prefix). The only backend available is "
            f"'dev-plaintext', which does NOT encrypt anything — storing a live "
            f"banking credential in it would make 'encrypted at rest' a false claim. "
            f"Implement the KMS backend (MULTI_TENANT_DESIGN.md 3.5) first."
        )
    return _DEV_PREFIX + base64.b64encode(plaintext.encode()).decode()


def decrypt(stored: str | None) -> str | None:
    """Reverses encrypt(). Refuses a value written by a different backend."""
    if stored is None:
        return None
    if stored.startswith(_DEV_PREFIX):
        return base64.b64decode(stored[len(_DEV_PREFIX):].encode()).decode()
    if stored.startswith(_KMS_PREFIX):
        raise SecretStoreUnavailable(
            "This value was written by the KMS backend, which is not implemented "
            "in this build. Do not attempt to read it with the dev backend."
        )
    raise SecretStoreUnavailable(
        f"Unrecognised secret envelope prefix. Stored credentials must name the "
        f"backend that produced them; this value does not, so it is not safe to "
        f"guess. Value starts: {stored[:24]!r}"
    )
