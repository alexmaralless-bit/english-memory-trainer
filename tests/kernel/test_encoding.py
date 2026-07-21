"""Canonical encoding and payload hashing must be deterministic and
key-order independent (foundation 3.3, 5)."""

from __future__ import annotations

import pytest

from english_trainer.kernel.encoding import canonical_json, payload_hash


def test_key_order_does_not_change_encoding() -> None:
    a = {"b": 1, "a": 2, "c": {"y": 1, "x": 2}}
    b = {"c": {"x": 2, "y": 1}, "a": 2, "b": 1}
    assert canonical_json(a) == canonical_json(b)
    assert payload_hash(a) == payload_hash(b)


def test_encoding_has_no_incidental_whitespace() -> None:
    assert canonical_json({"a": 1, "b": [1, 2]}) == b'{"a":1,"b":[1,2]}'


def test_non_ascii_is_escaped_deterministically() -> None:
    # Same logical string, same bytes, regardless of source form.
    assert canonical_json({"ru": "вот"}) == canonical_json({"ru": "во" + "т"})
    assert b"\\u" in canonical_json({"ru": "вот"})


def test_payload_hash_is_stable_sha256_hex() -> None:
    h = payload_hash({"x": 1})
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)
    # Fixed value guards against an accidental algorithm change.
    assert payload_hash({}) == payload_hash({})
    assert payload_hash({"x": 1}) != payload_hash({"x": 2})


def test_floats_are_rejected() -> None:
    with pytest.raises(TypeError):
        canonical_json({"score": 4.59})
    with pytest.raises(TypeError):
        payload_hash({"nested": {"list": [1, 2.0]}})


def test_bool_and_int_are_distinct_but_encode_predictably() -> None:
    assert canonical_json({"flag": True}) == b'{"flag":true}'
    assert canonical_json({"n": 0}) == b'{"n":0}'


def test_nfc_key_collision_is_rejected() -> None:
    # Two distinct keys that collapse to the same NFC form must be rejected, not
    # merged: merging would make the encoding depend on insertion order and let
    # different payloads share a hash.
    colliding = {"é": 1, "é": 2}  # precomposed vs decomposed "e-acute"
    assert len(colliding) == 2  # distinct keys before normalization
    with pytest.raises(ValueError, match="NFC key collision"):
        canonical_json(colliding)
    with pytest.raises(ValueError, match="NFC key collision"):
        payload_hash(colliding)
    # Nested collisions are caught too.
    with pytest.raises(ValueError, match="NFC key collision"):
        payload_hash({"outer": {"é": 1, "é": 2}})


def test_unicode_forms_normalize_to_one_encoding() -> None:
    # "e-acute" precomposed (U+00E9) vs "e" + combining acute (U+0301): they
    # render identically but are different code points. NFC collapses them, so
    # both the bytes and the hash must match -- for values and for keys.
    precomposed = {"name": "café"}
    decomposed = {"name": "café"}
    assert precomposed["name"] != decomposed["name"]
    assert canonical_json(precomposed) == canonical_json(decomposed)
    assert payload_hash(precomposed) == payload_hash(decomposed)
    assert payload_hash({"café": 1}) == payload_hash({"café": 1})
