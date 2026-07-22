"""Memory: the Obsidian projection of learner state (contract 0.6).

A readable, linked view for the human -- never a scoring source, never how an
agent restores state. The engine owns ``memory/`` completely; ``notes/``
belongs to the learner and is neither written nor read.
"""

from english_trainer.memory.engine import (
    EVENT_PROJECTION_UPDATED,
    check,
    emit_projection_updated,
    rebuild,
    render,
    render_pages,
)

__all__ = [
    "EVENT_PROJECTION_UPDATED",
    "check",
    "emit_projection_updated",
    "rebuild",
    "render",
    "render_pages",
]
