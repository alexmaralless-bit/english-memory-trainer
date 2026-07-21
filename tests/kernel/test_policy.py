"""Policy registry: immutable content-addressed snapshots, pinned vs active
resolve, retention, and the deprecated/retired lifecycle (foundation 3.6)."""

from __future__ import annotations

import sqlite3

import pytest

from english_trainer.kernel.encoding import canonical_and_hash
from english_trainer.kernel.errors import KernelError, NoActivePolicy, PinnedPolicyUnavailable
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore


def _registry(store: EventStore, clock) -> PolicyRegistry:
    return PolicyRegistry(store._conn, clock)


def test_register_and_resolve_roundtrip(store, clock) -> None:
    reg = _registry(store, clock)
    content = {"bands": ["A", "B", "C"], "threshold": "0.60"}
    digest = reg.register("scoring", "v1", content)
    assert reg.resolve_pinned("scoring", "v1") == content
    # Content-addressed by the same canonical hash as event payloads.
    assert digest == canonical_and_hash(content)[1]
    assert reg.content_hash("scoring", "v1") == digest


def test_register_is_idempotent_for_identical_content(store, clock) -> None:
    reg = _registry(store, clock)
    first = reg.register("scoring", "v1", {"a": 1})
    second = reg.register("scoring", "v1", {"a": 1})  # no-op, not an error
    assert first == second
    assert reg.resolve_pinned("scoring", "v1") == {"a": 1}


def test_reregister_with_different_content_is_refused(store, clock) -> None:
    reg = _registry(store, clock)
    reg.register("scoring", "v1", {"a": 1})
    with pytest.raises(KernelError):
        reg.register("scoring", "v1", {"a": 2})
    assert reg.resolve_pinned("scoring", "v1") == {"a": 1}  # original untouched


def test_content_is_immutable_at_the_storage_layer(store, clock) -> None:
    reg = _registry(store, clock)
    reg.register("scoring", "v1", {"a": 1})
    # A direct UPDATE of content is refused by the trigger, not just the API.
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        store._conn.execute("UPDATE policies SET content = '{\"a\":2}' WHERE version_id = 'v1';")


def test_versions_are_retained_never_deleted(store, clock) -> None:
    reg = _registry(store, clock)
    reg.register("scoring", "v1", {"a": 1})
    with pytest.raises(sqlite3.IntegrityError, match="retained"):
        store._conn.execute("DELETE FROM policies WHERE version_id = 'v1';")


def test_missing_pinned_version_is_hard_error(store, clock) -> None:
    reg = _registry(store, clock)
    with pytest.raises(PinnedPolicyUnavailable):
        reg.resolve_pinned("scoring", "nope")


def test_activate_and_resolve_active(store, clock) -> None:
    reg = _registry(store, clock)
    reg.register("control", "v1", {"budget": 10})
    reg.register("control", "v2", {"budget": 20})
    reg.activate("control", "v2")
    version_id, content = reg.resolve_active("control")
    assert version_id == "v2"
    assert content == {"budget": 20}


def test_no_active_policy_is_distinct_error(store, clock) -> None:
    reg = _registry(store, clock)
    reg.register("control", "v1", {"budget": 10})
    with pytest.raises(NoActivePolicy):
        reg.resolve_active("control")


def test_activation_is_not_retroactive_for_pins(store, clock) -> None:
    reg = _registry(store, clock)
    reg.register("scoring", "v1", {"a": 1})
    reg.register("scoring", "v2", {"a": 2})
    reg.activate("scoring", "v1")
    # A pin to v2 resolves to v2 regardless of which version is active.
    assert reg.resolve_pinned("scoring", "v2") == {"a": 2}
    reg.activate("scoring", "v2")
    assert reg.resolve_pinned("scoring", "v1") == {"a": 1}


def test_retired_version_still_resolves_when_pinned(store, clock) -> None:
    reg = _registry(store, clock)
    reg.register("scoring", "v1", {"a": 1})
    reg.register("scoring", "v2", {"a": 2})
    reg.activate("scoring", "v2")
    reg.deprecate("scoring", "v1", retire=True)
    # Retention: a retired version a pin still references must resolve.
    assert reg.resolve_pinned("scoring", "v1") == {"a": 1}
    assert reg.status("scoring", "v1") == "retired"


def test_retired_version_cannot_be_activated(store, clock) -> None:
    reg = _registry(store, clock)
    reg.register("scoring", "v1", {"a": 1})
    reg.register("scoring", "v2", {"a": 2})
    reg.activate("scoring", "v2")
    reg.deprecate("scoring", "v1", retire=True)
    with pytest.raises(KernelError):
        reg.activate("scoring", "v1")


def test_active_version_cannot_be_retired(store, clock) -> None:
    reg = _registry(store, clock)
    reg.register("scoring", "v1", {"a": 1})
    reg.activate("scoring", "v1")
    with pytest.raises(KernelError):
        reg.deprecate("scoring", "v1", retire=True)  # activate a replacement first


def test_deprecated_version_is_still_usable(store, clock) -> None:
    reg = _registry(store, clock)
    reg.register("scoring", "v1", {"a": 1})
    reg.deprecate("scoring", "v1")  # discouraged, not retired
    assert reg.status("scoring", "v1") == "deprecated"
    assert reg.resolve_pinned("scoring", "v1") == {"a": 1}
    reg.activate("scoring", "v1")  # still activatable
    assert reg.active_version("scoring") == "v1"


def test_identity_is_immutable_at_the_storage_layer(store, clock) -> None:
    # Renaming (kind, version_id) would orphan every pin to it: refused by
    # trigger, not just absent from the API.
    reg = _registry(store, clock)
    reg.register("scoring", "v1", {"a": 1})
    with pytest.raises(sqlite3.IntegrityError, match="identity"):
        store._conn.execute("UPDATE policies SET version_id = 'v9' WHERE version_id = 'v1';")
    assert reg.resolve_pinned("scoring", "v1") == {"a": 1}


def test_invalid_status_is_refused_at_the_storage_layer(store, clock) -> None:
    reg = _registry(store, clock)
    reg.register("scoring", "v1", {"a": 1})
    with pytest.raises(sqlite3.IntegrityError, match="invalid policy status"):
        store._conn.execute("UPDATE policies SET status = 'nonsense' WHERE version_id = 'v1';")


def test_retired_is_terminal_via_api_and_sql(store, clock) -> None:
    reg = _registry(store, clock)
    reg.register("scoring", "v1", {"a": 1})
    reg.register("scoring", "v2", {"a": 2})
    reg.activate("scoring", "v2")
    reg.deprecate("scoring", "v1", retire=True)
    # API: un-retiring (even to deprecated) is refused -- else a retired version
    # could be laundered back into an activatable state.
    with pytest.raises(KernelError, match="terminal"):
        reg.deprecate("scoring", "v1")
    # SQL: the trigger enforces the same.
    with pytest.raises(sqlite3.IntegrityError, match="terminal"):
        store._conn.execute("UPDATE policies SET status = 'deprecated' WHERE version_id = 'v1';")
    with pytest.raises(KernelError):
        reg.activate("scoring", "v1")


def test_retire_of_active_is_refused_at_the_storage_layer(store, clock) -> None:
    # The activate-vs-retire race: whichever statement runs second is refused by
    # a trigger, so the pointer can never rest on a retired version.
    reg = _registry(store, clock)
    reg.register("scoring", "v1", {"a": 1})
    reg.activate("scoring", "v1")
    with pytest.raises(sqlite3.IntegrityError, match="active"):
        store._conn.execute("UPDATE policies SET status = 'retired' WHERE version_id = 'v1';")
    assert reg.status("scoring", "v1") == "registered"


def test_activating_retired_is_refused_at_the_storage_layer(store, clock) -> None:
    reg = _registry(store, clock)
    reg.register("scoring", "v1", {"a": 1})
    reg.register("scoring", "v2", {"a": 2})
    reg.activate("scoring", "v2")
    reg.deprecate("scoring", "v1", retire=True)
    with pytest.raises(sqlite3.IntegrityError, match="retired"):
        store._conn.execute("UPDATE policy_active SET version_id = 'v1' WHERE kind = 'scoring';")
    assert reg.active_version("scoring") == "v2"


def test_active_pointer_cannot_name_an_unknown_version(store, clock) -> None:
    # The foreign key: a direct write cannot point active at a version that does
    # not exist in the registry.
    reg = _registry(store, clock)
    reg.register("scoring", "v1", {"a": 1})
    reg.activate("scoring", "v1")
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute("UPDATE policy_active SET version_id = 'ghost' WHERE kind = 'scoring';")
