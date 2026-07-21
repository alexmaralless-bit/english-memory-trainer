"""The Repository boundary (foundation 3.9).

Domain code must not know the storage engine: aggregates are loaded and saved
through a ``Repository``, transactions run through the kernel's ``UnitOfWork``.
This module defines the protocol only -- concrete repositories arrive with the
operational-state modules that own their aggregates (sessions, attempts, review
queues), because a repository without an aggregate to persist is dead machinery.

The protocol is deliberately narrow. Optimistic concurrency (foundation 3.5)
shows up here as the ``expected_revision`` argument of ``save``: a concrete
repository must refuse a write whose expectation is stale
(:class:`~english_trainer.kernel.errors.StaleRevision`), which is what makes
multi-aggregate all-or-nothing writes possible inside one UnitOfWork.
"""

from __future__ import annotations

from typing import Protocol


class Repository[AggregateT](Protocol):
    """Load/save boundary for one aggregate type (foundation 3.9, 3.5)."""

    def get(self, aggregate_id: str) -> AggregateT | None:
        """Return the aggregate or ``None`` -- never a half-loaded object."""
        ...

    def save(self, aggregate: AggregateT, *, expected_revision: int) -> None:
        """Persist with compare-and-set on ``expected_revision``.

        A stale expectation raises ``StaleRevision`` and writes nothing.
        """
        ...
