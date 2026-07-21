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
    "lessons": {"kernel", "control", "lessons"},
    # evidence consumes published events, never other modules' code (0.4):
    # the event log is its boundary with lessons/control.
    "evidence": {"kernel", "evidence"},
    "cli": {"kernel", "storage", "curriculum", "control", "lessons", "evidence", "cli"},
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
    for group in app.registered_groups:
        assert group.name is not None and group.typer_instance is not None
        for command in group.typer_instance.registered_commands:
            assert command.callback is not None
            published.add(f"{group.name}.{command.name or command.callback.__name__}")

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
