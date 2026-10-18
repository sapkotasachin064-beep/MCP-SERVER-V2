"""Scalar drawing-quality score + invalidity ratio.

Every 2025-26 CAD-generation benchmark (MUSE, CadBench) grades an *Invalidity
Ratio*, not just shape similarity. This module turns the validator's and
critique's severity counts into a single regression-trackable scalar so the
premium workflow has an objective function (the prerequisite for an automated
refiner loop and for smoke-test regression tracking).

The weights are a documented convention, not ground truth — they exist so the
number moves in the right direction (errors hurt most, info barely registers)
and can be asserted in tests.
"""

from __future__ import annotations

# Penalty weights per severity. Errors dominate; info is nearly free.
_W_ERROR = 25.0
_W_WARNING = 8.0
_W_INFO = 1.0


def score_findings(
    errors: int,
    warnings: int,
    info: int = 0,
    *,
    w_error: float = _W_ERROR,
    w_warning: float = _W_WARNING,
    w_info: float = _W_INFO,
) -> dict:
    """Collapse severity counts into a 0-100 score + invalidity ratio.

    - ``score``: ``100 - (errors·Wₑ + warnings·Wᵥᵥ + info·Wᵢ)`` clamped to [0, 100].
      A clean drawing scores 100.
    - ``invalidity_ratio``: ``errors / max(1, total_findings)`` — the fraction of
      findings that are hard failures (0.0 when there are no findings).
    - ``grade``: coarse A-F bucket for at-a-glance reporting.
    """
    errors = max(0, int(errors))
    warnings = max(0, int(warnings))
    info = max(0, int(info))

    penalty = errors * w_error + warnings * w_warning + info * w_info
    score = max(0.0, min(100.0, 100.0 - penalty))

    total = errors + warnings + info
    invalidity_ratio = (errors / total) if total else 0.0

    return {
        "score": round(score, 1),
        "invalidity_ratio": round(invalidity_ratio, 3),
        "grade": _grade(score),
        "errors": errors,
        "warnings": warnings,
        "info": info,
    }


def combine(*severity_dicts: dict) -> dict:
    """Sum several ``{'error': n, 'warning': n, 'info': n}`` summaries then score.

    Accepts the shapes emitted by both ``DrawingValidator`` (``summary``) and the
    finalize ``critique_summary`` so the finalize gate can score the union of the
    structural validator and the premium critique in one number.
    """
    errors = warnings = info = 0
    for d in severity_dicts:
        if not d:
            continue
        errors += int(d.get("error", 0))
        warnings += int(d.get("warning", 0))
        info += int(d.get("info", 0))
    return score_findings(errors, warnings, info)


def _grade(score: float) -> str:
    if score >= 95.0:
        return "A"
    if score >= 85.0:
        return "B"
    if score >= 70.0:
        return "C"
    if score >= 50.0:
        return "D"
    return "F"
