"""The Obsidian projection (2.4): deterministic bytes, declared sources,
idempotent render, rebuild removes orphans, drift is caught, notes/ untouched."""

from __future__ import annotations

from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.lessons.delivery import next_step
from english_trainer.lessons.sessions import finish_session, start_session
from english_trainer.memory.engine import check, rebuild, render, render_pages


def _session_with_state(store: EventStore, registry: PolicyRegistry, clock, rnd) -> str:
    """Start a session and deliver its first step, so the projection has a
    session page, a plan page and delivered-step schedules to render."""
    manifest = start_session(store, registry, clock, rnd, provider="claude-code")
    session_id = str(manifest["session_id"])
    next_step(store, registry, clock, rnd, session_id, expected_plan_version=1)
    return session_id


def test_render_is_deterministic_to_the_byte(store, registry, clock, random_source) -> None:
    _session_with_state(store, registry, clock, random_source)
    first = render_pages(store, registry)
    second = render_pages(store, registry)
    assert first == second  # no wall clock anywhere: identical state -> identical bytes
    # Every page carries the generated frontmatter and a declared source.
    for path, content in first.items():
        assert content.startswith("---\ngenerated: true\n")
        assert "source: event-sourced" in content or "source: operational" in content
        assert path.endswith(".md")
    # The topic page links the target's schedule and knowledge state.
    topic_page = first["topics/grammar.be.identity.md"]
    assert "grammar.be.identity" in topic_page and "Состояние знания:" in topic_page


def test_render_writes_only_memory_and_is_idempotent(tmp_path, store, registry, clock, random_source) -> None:
    _session_with_state(store, registry, clock, random_source)
    memory = tmp_path / "memory"
    first = render(store, registry, memory)
    assert first["written"] and first["unchanged"] == 0
    # A second render changes nothing: unchanged bytes are not rewritten.
    second = render(store, registry, memory)
    assert second["written"] == [] and second["unchanged"] == first["pages"]
    assert first["content_hash"] == second["content_hash"]
    # Dashboards, entity pages and a session page all exist.
    assert (memory / "current" / "current-level.md").exists()
    assert (memory / "topics" / "grammar.be.identity.md").exists()
    assert list((memory / "sessions").rglob("*.md"))


def test_rebuild_removes_orphans(tmp_path, store, registry, clock, random_source) -> None:
    _session_with_state(store, registry, clock, random_source)
    memory = tmp_path / "memory"
    render(store, registry, memory)
    orphan = memory / "topics" / "deleted-topic.md"
    orphan.write_text("stale", encoding="utf-8")
    report = rebuild(store, registry, memory)
    assert "topics/deleted-topic.md" in report["removed"]
    assert not orphan.exists()
    assert check(store, registry, memory)["ok"]  # rebuild leaves a clean vault


def test_check_catches_drift_and_repairs_nothing(tmp_path, store, registry, clock, random_source) -> None:
    _session_with_state(store, registry, clock, random_source)
    memory = tmp_path / "memory"
    render(store, registry, memory)
    assert check(store, registry, memory)["ok"]

    edited = memory / "topics" / "grammar.be.identity.md"
    edited.write_text(edited.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")
    report = check(store, registry, memory)
    assert not report["ok"]
    assert "topics/grammar.be.identity.md" in report["drifted"]
    # Read-only: the hand edit is still there -- check never repairs.
    assert "hand edit" in edited.read_text(encoding="utf-8")


def test_notes_zone_is_never_touched(tmp_path, store, registry, clock, random_source) -> None:
    _session_with_state(store, registry, clock, random_source)
    root = tmp_path
    (root / "notes").mkdir()
    learner_note = root / "notes" / "my-thoughts.md"
    learner_note.write_text("[[grammar.be.identity]] is clicking now", encoding="utf-8")
    render(store, registry, root / "memory")
    rebuild(store, registry, root / "memory")
    # The learner's zone is untouched by render AND rebuild.
    assert learner_note.read_text(encoding="utf-8") == "[[grammar.be.identity]] is clicking now"


def test_finished_session_projects_its_status(tmp_path, store, registry, clock, random_source) -> None:
    manifest = start_session(store, registry, clock, random_source, provider="claude-code")
    session_id = str(manifest["session_id"])
    next_step(store, registry, clock, random_source, session_id, expected_plan_version=1)
    # mark in_progress already happened via next_step; finish it
    from english_trainer.lessons.sessions import mark_in_progress

    mark_in_progress(store, clock, session_id)
    finish_session(store, clock, random_source, session_id)
    pages = render_pages(store, registry)
    session_pages = [p for p in pages if p.startswith("sessions/")]
    assert len(session_pages) == 1
    assert "**FINISHED**" in pages[session_pages[0]]
