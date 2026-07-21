"""English Memory Trainer — local-first CLI trainer for American English.

The engine is the sole authority over learner state; the LLM tutor is a
replaceable client. This package is the application code; ``kernel`` is the
platform foundation (determinism, audit, integrity) that business modules
build on. See ``wiki/platform/foundation.md``.
"""

from __future__ import annotations

__all__ = ["kernel"]
