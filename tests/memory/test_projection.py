"""The Obsidian projection (2.4): deterministic bytes, declared sources,
idempotent render, rebuild removes orphans, drift is caught, notes/ untouched."""

from __future__ import annotations

from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.memory.engine import check, rebuild, render, render_pages
from tests.lessons.report_support import enable_reports, item, reported_session


def _session_with_state(store: EventStore, registry: PolicyRegistry, clock, rnd) -> str:
    """One reported lesson [PD-2026-09-23], so the projection has a session
    page, a plan page and evidence-opened schedules to render."""
    enable_reports(registry)
    return reported_session(
        store,
        registry,
        clock,
        rnd,
        [item("i1", "I am a developer.", target_ref="grammar.be.identity", dimension="recognition")],
    )


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
    # The committed report finished the session in its own transaction.
    _session_with_state(store, registry, clock, random_source)
    pages = render_pages(store, registry)
    session_pages = [p for p in pages if p.startswith("sessions/")]
    assert len(session_pages) == 1
    assert "**FINISHED**" in pages[session_pages[0]]
