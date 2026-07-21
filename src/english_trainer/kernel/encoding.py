"""Canonical encoding and payload hashing (foundation 3.3, 5; OPEN-20).

Determinism needs one and only one byte representation of a payload, so that
the same fact always produces the same ``payload_hash`` and replay is
reproducible across machines and processes. ``canonical_json`` fixes every
degree of freedom a JSON encoder normally leaves open: keys are sorted, there is
no incidental whitespace, non-ASCII is escaped, strings are Unicode-normalized
(NFC) so equivalent spellings share one encoding, and the number domain is
restricted so ``1``, ``1.0`` and ``1e0`` cannot masquerade as the same value at
rest.

The hash algorithm is fixed at SHA-256 over the canonical bytes. It is a
content fingerprint for idempotency and audit, not a scoring number -- scoring's
own numeric rules (Decimal, rounding) live in the pinned scoring policy (0.4).
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any

JSONValue = None | bool | int | str | float | list["JSONValue"] | dict[str, "JSONValue"]

HASH_ALGORITHM = "sha256"


def _nfc(value: Any) -> Any:
    """Return ``value`` with every string (key and scalar) NFC-normalized.

    The same text can be spelled with different Unicode code points -- "é"
    (e + combining acute) and "é" (precomposed e-acute) render identically
    but are distinct byte sequences. Without a fixed normalization form, two
    payloads that look the same would hash differently, so replay and idempotency
    would depend on how the caller happened to type a character. NFC gives one
    spelling. Applied to keys too; if two keys collapse to the same form the last
    wins, which is the intended canonicalization.
    """
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        return {
            (unicodedata.normalize("NFC", k) if isinstance(k, str) else k): _nfc(v) for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_nfc(v) for v in value]
    return value


def _reject_non_canonical_floats(value: Any) -> None:
    """Floats are ambiguous at rest (1.0 vs 1). Force the caller to be explicit.

    A payload that needs an exact decimal must carry it as a string and let the
    owning policy parse it; a float in a hashed payload would make the hash
    depend on the encoder's float formatting.
    """
    if isinstance(value, float):
        raise TypeError(
            "floats are not allowed in canonical payloads: represent an exact "
            "number as a string and parse it in the owning policy (0.4)"
        )
    if isinstance(value, dict):
        for v in value.values():
            _reject_non_canonical_floats(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _reject_non_canonical_floats(v)


def canonical_json(payload: Any) -> bytes:
    """Deterministic UTF-8 JSON: sorted keys, no whitespace, escaped non-ASCII.

    ``bool`` stays ``true``/``false``; ``int`` and ``str`` pass through; ``float``
    is rejected (see ``_reject_non_canonical_floats``). Two payloads that differ
    only in key order or insignificant whitespace encode to identical bytes.
    """
    _reject_non_canonical_floats(payload)
    text = json.dumps(
        _nfc(payload),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return text.encode("utf-8")


def payload_hash(payload: Any) -> str:
    """Hex SHA-256 of the canonical encoding. Fixed algorithm (foundation 3.3)."""
    return hashlib.sha256(canonical_json(payload)).hexdigest()
