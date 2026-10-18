"""Tests for the scalar drawing-score / invalidity-ratio (engineering/scoring.py)
and its wiring into drawing_finalize."""

from __future__ import annotations

import pytest

from engineering.scoring import combine, score_findings

pytestmark = pytest.mark.asyncio


async def test_clean_drawing_scores_100():
    s = score_findings(0, 0, 0)
    assert s["score"] == 100.0
    assert s["invalidity_ratio"] == 0.0
    assert s["grade"] == "A"


async def test_errors_dominate_penalty():
    err = score_findings(1, 0, 0)["score"]
    warn = score_findings(0, 1, 0)["score"]
    info = score_findings(0, 0, 1)["score"]
    assert err < warn < info < 100.0


async def test_score_clamped_to_zero():
    s = score_findings(100, 100, 100)
    assert s["score"] == 0.0
    assert s["grade"] == "F"


async def test_invalidity_ratio_is_error_fraction():
    s = score_findings(1, 3, 0)  # 1 of 4 findings is a hard error
    assert s["invalidity_ratio"] == 0.25


async def test_combine_sums_summaries():
    a = {"error": 1, "warning": 0, "info": 0}
    b = {"error": 0, "warning": 2, "info": 1}
    combined = combine(a, b)
    assert combined["errors"] == 1
    assert combined["warnings"] == 2
    assert combined["info"] == 1


# ── finalize wiring ─────────────────────────────────────────────────────────


class _FakeCtx:
    def __init__(self, backend):
        self.lifespan_context = {"backend": backend}

    async def warning(self, message):
        pass


async def test_finalize_payload_carries_score(backend, tmp_path):
    import server

    await backend.drawing_apply_iso_layers("mech")
    await backend.entity_create_line(0, 0, 100, 0, layer="GEOMETRY")
    ctx = _FakeCtx(backend)
    payload = await server.drawing_finalize(
        save_path=str(tmp_path / "part.dxf"),
        ctx=ctx,
    )
    assert "score" in payload
    assert 0.0 <= payload["score"]["score"] <= 100.0
    assert "invalidity_ratio" in payload["score"]
    assert payload["score"]["grade"] in ("A", "B", "C", "D", "F")
