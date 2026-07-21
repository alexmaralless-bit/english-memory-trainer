# Repository Guidelines

## Project Structure & Source of Truth

This checkout is currently a documentation-first scaffold. `docs/english-memory-trainer-brief.md` is the product and architecture brief; `docs/english-memory-trainer-build-prompt.md` defines the implementation contract. `docs/design-direction.md` records the agreed concept corrections and takes precedence wherever it conflicts with the other two (notably: advisory prerequisites instead of hard topic locks, a free-form session lifecycle instead of the rigid lesson state machine, and text-only modality scope). Accepted specs in `wiki/` outrank all docs within their own scope. Read the relevant sections before changing behaviour, policies, or data models.

Dev knowledge follows the wiki constitution (`wiki/README.md`): specs are target-state with `[mvp]`/`[post-mvp]` tags, one module = one spec, terms are defined once in `wiki/glossary.md`, current status lives only in `wiki/roadmap.md`, unresolved questions only in `wiki/OPEN.md`. Product forks are decided by the user and marked `[PD-YYYY-MM-DD]`; canon is written only after an approved concept. Session summaries go to `staging/journal/` (append-only).

The planned Python application should keep runtime code, tests, curriculum/configuration, and agent skills separate. Canonical skills belong in `agent-skills/`; generated provider copies belong in `.agents/skills/` and `.claude/skills/`. Treat SQLite, JSONL events, and rendered `memory/` Markdown as managed state, not hand-edited content.

## Development, Validation, and Local Commands

Dependencies live in `pyproject.toml`; Python 3.12+, `uv` where available. Phase 0 (contracts) is complete; the kernel (`src/english_trainer/kernel/`, roadmap 1.2) is the first application code. Runtime deps are only what existing code imports (`pydantic`, `pyyaml`); `typer`/SQLAlchemy stay absent until needed (SQLite via a thin `sqlite3` layer, no ORM).

```bash
pip install -e . --group dev             # or: uv sync
pytest                                   # kernel determinism + lexicon invariants (no network)
ruff check .
ruff format --check src tests
mypy src                                 # strict; kernel is fully typed

# Reproduce the corpus frequencies from the pinned artifacts (needs network).
# The cache must live outside the repo: raw datasets are never committed.
python tools/enrich_lexicon.py --cache <dir> --check
```

These already pass. `trainer` CLI subcommands below arrive with later kernel increments:

```bash
trainer curriculum validate
trainer skills validate
trainer adapters compare
trainer database check
trainer memory check
trainer scoring replay
```

Run `trainer doctor` first when diagnosing a local setup. Agent-facing CLI commands must emit valid JSON on stdout when invoked with `--format json`; write diagnostics to stderr.

## Coding Style & Naming

Use four-space Python indentation, type annotations, `snake_case` functions and modules, `PascalCase` classes, and stable lowercase dotted IDs such as `grammar.present-perfect.result`. Prefer small, deterministic domain services behind storage interfaces. Validate external inputs with versioned schemas, use UTC timestamps, and retain idempotency keys. Format and lint with Ruff; add a type-checker configuration before relying on mypy or Pyright in CI.

## Testing Guidelines

Use `pytest` with focused unit and integration tests named `test_<behavior>.py` / `test_<behavior>()`. Cover prerequisite and state-transition rules, scoring bounds and replay, scheduling, event persistence, SQLite integrity, Markdown rendering, and provider-skill parity. Keep fixtures deterministic and ensure demo flows require no network or external API.

## Agent and State Safety

Read learner state through the CLI. Never directly alter progress, scores, SQLite rows, event logs, or generated memory. Run the required skill, record structured evidence, and finish sessions only through the CLI. Change curriculum only through the `maintain-english-curriculum` workflow, then run relevant validations.

## Commits & Pull Requests

No Git history is available in this checkout, so no established commit convention can be inferred. Use concise imperative subjects (for example, `Add curriculum graph validation`). PRs should explain the behavioural change, list validation commands run, link relevant issues, and include CLI JSON or screenshots when user-visible output changes. Never commit secrets, SQLite WAL/SHM files, or incidental generated data.
