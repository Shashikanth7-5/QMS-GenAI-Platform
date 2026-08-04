"""Security helpers: e-signature binding and audit hash chain.

Both use SHA-256 over deterministic JSON serialisation so the hash
is stable across processes and Python versions.

Two use cases:
  * ``capa_content_hash(capa)`` — bound to an electronic signature so
    tampering with the CAPA body breaks the signature.
  * ``chain_next(prev_hash, entry)`` — append-only audit chain: each
    row commits to the previous row's digest, so a single altered entry
    invalidates every following one.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any, Iterable, Mapping


_CANONICAL_ENCODING = "utf-8"


def _canonical(payload: Any) -> bytes:
    """Deterministic JSON: sorted keys, ASCII-safe fallback, no NaN."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    ).encode(_CANONICAL_ENCODING)


# Fields that must never influence the CAPA body hash — they change on every
# save (timestamps) or are derived (validation warnings, review metadata).
_CAPA_HASH_EXCLUDE = frozenset({
    "updatedAt",
    "capaMetadata",
    "_source",
    "_similar_capas",
    "_fallback",
    "_error",
    "notification",
    "warnings",
})


def capa_content_hash(capa: Mapping[str, Any], exclude: Iterable[str] = ()) -> str:
    """SHA-256 over the immutable content of a CAPA record.

    Signing a CAPA binds the signature to this hash. Any later change to
    ``rootCause``, actions, owner, etc. invalidates the signature.
    """
    exclusions = _CAPA_HASH_EXCLUDE | frozenset(exclude)
    filtered = {k: v for k, v in capa.items() if k not in exclusions}
    return hashlib.sha256(_canonical(filtered)).hexdigest()


def chain_next(prev_hash: str | None, entry: Mapping[str, Any]) -> str:
    """Return the digest for ``entry`` in a hash chain rooted at ``prev_hash``.

    The genesis row uses an empty previous hash. Callers persist both the
    entry AND its digest; a verifier recomputes the chain to detect tampering.
    """
    seed = (prev_hash or "").encode(_CANONICAL_ENCODING)
    return hashlib.sha256(seed + b"|" + _canonical(entry)).hexdigest()


def verify_chain(rows: Iterable[Mapping[str, Any]], hash_field: str = "row_hash",
                 prev_field: str = "prev_hash", payload_key: str = "payload") -> bool:
    """Return True if a sequence of audit rows forms an unbroken chain."""
    prev = ""
    for row in rows:
        expected = chain_next(prev, row.get(payload_key, row))
        if row.get(hash_field) != expected:
            return False
        if row.get(prev_field, "") != prev:
            return False
        prev = expected
    return True


def hmac_signature(secret: str, message: bytes) -> str:
    """HMAC-SHA256 for webhook signatures. Constant-time comparison recommended."""
    return hmac.new(secret.encode(_CANONICAL_ENCODING), message, hashlib.sha256).hexdigest()


def is_hmac_valid(secret: str, message: bytes, provided: str) -> bool:
    if not secret or not provided:
        return False
    expected = hmac_signature(secret, message)
    return hmac.compare_digest(expected, provided)
