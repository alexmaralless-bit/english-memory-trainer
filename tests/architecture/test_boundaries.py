"""Architectural invariants as a machine-checked gate (foundation 8).

The contract demands machine-readable rules, not prose: a declarative
layer/dependency allowlist plus AST checks. pytest IS the gate -- these tests
run with every suite, so a violation fails the build the moment it appears,
not in a later review.

Rules enforced here:

1. Layer allowlist: kernel imports only kernel (platform never imports business
   or edge layers -- acyclicity); storage builds on kernel; cli is the edge and
   may use both. A new package must be added to the allowlist explicitly.
2. Clock/random discipline: system time and randomness are touched only inside
   ``kernel/clock.py`` (and ``secrets`` additionally in ``kernel/store.py`` for
   the transient write capability). Everything else injects Clock/RandomSource.
3. IO discipline: ``sqlite3`` is imported only by kernel and storage -- the
   layers allowed to persist. The CLI talks through their abstractions.
4. Command registry coverage: every published CLI command is registered with
   its mutability and idempotency-key class, and vice versa -- an endpoint
   missing from the registry is a contract violation (foundation 8, review G-2).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

SRC = Path(__file__).resolve().parents[2] / "src" / "english_trainer"

# Rule 1: package -> packages it may import from within english_trainer.
LAYER_ALLOWLIST: dict[str, set[str]] = {
    "": set(),  # the root package imports nothing
    "kernel": {"kernel"},
    "storage": {"kernel", "storage"},
    "curriculum": {"kernel", "curriculum"},
    # control is the pure composition brain; lessons runs its transactions
    # (the canon assigns the CLI commands to lessons and their behavior to
    # control -- this direction avoids an import cycle).
    "control": {"kernel", "control"},
    # lessons owns the session triggers and delegates attempt closures to
    # evidence inside its own UoW (0.5/0.4 4.3) -- the dependency points
    # lessons -> evidence, never back. adapters resolves required_skills
    # synchronously at start (adapters 4.2, lessons 4b [P0-Q1]); scoring folds
    # the tutor briefing at resume (lessons [P0-5]), the same read-only shape
    # memory already uses for its own projection.
    "lessons": {"kernel", "control", "evidence", "scheduler", "scoring", "adapters", "lessons"},
    # evidence consumes published events, never other modules' code (0.4):
    # the event log is its boundary with lessons/control.
    # State-transition facts are emitted atomically with evidence outcomes;
    # scoring owns their deterministic construction, so evidence may call that
    # narrow producer while all score reads still cross the event boundary.
    "evidence": {"kernel", "evidence", "scoring"},
    # scoring folds published events under its pinned policy; same boundary.
    "scoring": {"kernel", "scoring", "audit"},
    # scheduler consumes scoring's fold (Retrievability/Stability) by canon.
    "scheduler": {"kernel", "scoring", "scheduler"},
    # assessments owns placement diagnostics: it may address curriculum targets
    # and write placement evidence/scoring facts, but the event log is its
    # boundary with scoring/scheduler and it never imports cli or lessons.
    "assessments": {"kernel", "curriculum", "evidence", "scoring", "assessments"},
    # memory is a read-only projection over the folds and aggregates; it
    # renders FOR the human and never feeds anything back.
    "memory": {"kernel", "scoring", "scheduler", "memory"},
    # adapters owns the canonical Agent Skills; it resolves cli_calls against
    # the command registry and stores its sync manifest under the storage
    # layout (adapters 6). It imports only `cli.registry` (a standalone
    # module with no engine imports of its own), done as a local import
    # inside `validate()` -- `cli` also imports `adapters` (below), and a
    # top-level `adapters -> cli.registry` import would otherwise resolve
    # through `cli/__init__.py`, which imports `cli.app`, which imports
    # `adapters` -- a real circular import at process-start time. The gate
    # here only checks package-level names, so both directions are declared.
    "adapters": {"kernel", "storage", "cli", "adapters"},
    # Audit is a pure query layer over the authoritative kernel event table.
    "audit": {"kernel", "audit"},
    # learner owns the personal lexicon (layer 3): an event-sourced fold over
    # the kernel event log. It never imports a business module -- the active
    # curriculum program is passed in by the caller (the CLI edge) as a plain
    # dict, so linked_item resolution needs no curriculum import.
    "learner": {"kernel", "learner"},
    "cli": {
        "kernel",
        "storage",
        "curriculum",
        "control",
        "lessons",
        "evidence",
        "scoring",
        "scheduler",
        "memory",
        "adapters",
        "assessments",
        "audit",
        "cli",
    },
}

# Rule 2/3: module -> stdlib modules it may import from the restricted set.
RESTRICTED_IMPORTS = {"random", "secrets", "time", "sqlite3"}
RESTRICTED_ALLOWANCES: dict[str, set[str]] = {
    "kernel/clock.py": {"random", "secrets", "time"},
    "kernel/store.py": {"secrets", "sqlite3"},
    "kernel/aggregates.py": {"sqlite3"},
    "kernel/uow.py": {"sqlite3"},
    "kernel/policy.py": {"sqlite3"},
    "kernel/outbox.py": {"sqlite3"},
    "kernel/projections.py": {"sqlite3"},
    "storage/layout.py": {"sqlite3"},
}


def _modules() -> list[tuple[str, str, ast.Module]]:
    """(package, relative path, parsed AST) for every source module."""
    out = []
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        package = relative.split("/")[0] if "/" in relative else ""
        out.append((package, relative, ast.parse(path.read_text(encoding="utf-8"))))
    return out


def _imported_names(tree: ast.Module) -> list[str]:
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def test_layer_allowlist_is_respected() -> None:
    violations = []
    for package, relative, tree in _modules():
        allowed = LAYER_ALLOWLIST[package]
        for name in _imported_names(tree):
            if not name.startswith("english_trainer"):
                continue
            parts = name.split(".")
            target = parts[1] if len(parts) > 1 else ""
            if target and target not in allowed:
                violations.append(f"{relative} imports {name} (allowed: {sorted(allowed)})")
    assert not violations, "layer boundary violations:\n" + "\n".join(violations)


def test_kernel_never_imports_edge_layers() -> None:
    # Acyclicity spelled out: the platform cannot depend on cli/storage or any
    # future business module, whatever the allowlist above evolves into.
    for package, relative, tree in _modules():
        if package != "kernel":
            continue
        for name in _imported_names(tree):
            assert not name.startswith(("english_trainer.cli", "english_trainer.storage")), (
                f"{relative} imports {name}: kernel must not depend on edge layers"
            )


def test_restricted_stdlib_imports_are_allowlisted() -> None:
    violations = []
    for _, relative, tree in _modules():
        allowed = RESTRICTED_ALLOWANCES.get(relative, set())
        for name in _imported_names(tree):
            root = name.split(".")[0]
            if root in RESTRICTED_IMPORTS and root not in allowed:
                violations.append(f"{relative} imports {root}")
    assert not violations, (
        "restricted imports outside their allowlisted homes (inject Clock/RandomSource, "
        "or route IO through kernel/storage):\n" + "\n".join(violations)
    )


def test_no_direct_system_clock_calls() -> None:
    # datetime.now()/today()/utcnow() belong to kernel/clock.py alone; everyone
    # else receives an injected Clock (foundation 3.2, 8).
    violations = []
    for _, relative, tree in _modules():
        if relative == "kernel/clock.py":
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"now", "today", "utcnow"}
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "datetime"
            ):
                violations.append(f"{relative}:{node.lineno} calls datetime.{node.func.attr}()")
    assert not violations, "direct system-clock calls:\n" + "\n".join(violations)


def test_command_registry_covers_the_published_surface() -> None:
    from english_trainer.cli.app import app
    from english_trainer.cli.registry import command_registry

    published = {command.name or command.callback.__name__ for command in app.registered_commands}  # type: ignore[union-attr]

    def collect(prefix: str, typer_app: Any) -> None:
        commands = typer_app.registered_commands
        groups = typer_app.registered_groups
        for command in commands:
            assert command.callback is not None
            published.add(f"{prefix}.{command.name or command.callback.__name__}")
        for group in groups:
            assert group.name is not None and group.typer_instance is not None
            collect(f"{prefix}.{group.name}", group.typer_instance)

    for group in app.registered_groups:
        assert group.name is not None and group.typer_instance is not None
        collect(group.name, group.typer_instance)

    registered = {descriptor.name for descriptor in command_registry()}
    assert published == registered, (
        f"published commands and the registry diverged: only-published={sorted(published - registered)}, "
        f"only-registered={sorted(registered - published)}"
    )


def test_every_mutating_command_requires_the_idempotency_key() -> None:
    from english_trainer.cli.registry import command_registry

    for descriptor in command_registry():
        if descriptor.mutating:
            assert descriptor.requires_idempotency_key, (
                f"{descriptor.name} mutates state but does not require an idempotency key (cli 4.3)"
            )
        else:
            assert not descriptor.requires_idempotency_key, (
                f"{descriptor.name} is read-only; requiring a key would be surface noise"
            )
