"""The concrete-learner-error fact (``evidence.error_observed``).

The fact anchors a negative finding to an attempt and an exact UTF-8 span of
the saved answer; it feeds control's recurring-error fold and the brief's
recent errors, and is not itself mastery evidence. Since the brief/report
protocol [PD-2026-09-23] it is written by the lesson report
(``evidence.report.build_error_payload``, ``reported_by: tutor``, span derived
by the engine). The per-step writer (``record_observed`` / ``trainer observed
record``) was removed with that protocol; its historic facts keep the same
type and stay readable.
"""

from __future__ import annotations

EVENT_ERROR_OBSERVED = "evidence.error_observed"
