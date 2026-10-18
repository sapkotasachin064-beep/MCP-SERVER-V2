"""Regression tests for the CI-verifiable (ezdxf / shared) Sprint-3 fixes.

* N2  — drawing_save_as derives the on-disk format from the path extension
* N3  — ARC carries a `length` property; entity_select_smart length_range selects it
* N5  — properties parity: ezdxf sets bounding_box; MTEXT carries char_height + rotation
* NEW-dimauto-baseline-rotation — baseline dims run parallel to a rotated baseline
* NEW-dimauto-ordinate-misnomer — ordinate dims are staggered, not stacked at one offset
"""

from __future__ import annotations

import os
import tempfile

import pytest

pytestmark = pytest.mark.asyncio


class _Ctx:
    def __init__(self, backend):
        self.lifespan_context = {"backend": backend}

    async def info(self, message):
        pass


# ── N2 — format follows the file extension ──────────────────────────────────


async def test_save_as_derives_format_from_extension(backend):
    import server

    ctx = _Ctx(backend)
    d = tempfile.mkdtemp()
    res = await server.drawing_save_as(path=os.path.join(d, "part.dxf"), ctx=ctx)
    assert res.get("format") == "dxf"  # not the old "dwg" default

    # ezdxf cannot write real DWG — must refuse rather than mislabel a .dwg file.
    with pytest.raises(RuntimeError):
        await server.drawing_save_as(path=os.path.join(d, "part.dwg"), ctx=ctx)


# ── N3 — ARC length + length_range selection ────────────────────────────────


async def test_arc_has_length_and_is_selectable(backend):
    arc = await backend.entity_create_arc(0, 0, 10, 0, 90)  # r=10, 90deg -> len ~15.708
    info = await backend.entity_get(arc.handle)
    assert info.properties.get("length") == pytest.approx(15.70796, rel=1e-4)

    sel = await backend.entity_select_smart({"type": "ARC", "length_range": [15, 16]})
    assert len(sel) == 1
    # Out-of-range excludes it (was: all arcs silently rejected for lack of length).
    assert await backend.entity_select_smart({"type": "ARC", "length_range": [1, 2]}) == []


# ── N5 — cross-backend property parity ──────────────────────────────────────


async def test_ezdxf_populates_bounding_box(backend):
    line = await backend.entity_create_line(0, 0, 30, 40)
    info = await backend.entity_get(line.handle)
    bb = info.properties.get("bounding_box")
    assert bb is not None and set(bb) == {"min", "max"}  # same shape as COM


async def test_mtext_has_char_height_and_rotation(backend):
    mt = await backend.entity_create_mtext("hello", 5, 5, height=2.5)
    info = await backend.entity_get(mt.handle)
    assert "char_height" in info.properties
    assert "rotation" in info.properties


async def test_mtext_honors_caller_rotation(backend):
    # NEW-mtext-1: entity_create_mtext now accepts a rotation that round-trips.
    mt = await backend.entity_create_mtext("rot", 0, 0, width=50, height=2.5, rotation=30.0)
    info = await backend.entity_get(mt.handle)
    assert float(info.properties.get("rotation", 0.0)) == pytest.approx(30.0, abs=1e-6)


# ── NEW-dimauto-baseline-rotation ───────────────────────────────────────────


async def test_baseline_dim_runs_parallel_to_rotated_baseline(backend):
    ln = await backend.entity_create_line(0, 0, 40, 40)  # 45-degree baseline
    dims = await backend.dimension_auto([ln.handle], style="baseline")
    doc = backend._require_doc()
    ent = doc.entitydb[dims[0].handle]
    # Dimension line angle must match the baseline (45), not the old hardcoded 0.
    assert ent.dxf.get("angle", 0.0) == pytest.approx(45.0, abs=1e-6)
    assert ent.get_measurement() == pytest.approx(56.5685, rel=1e-3)  # true len, not projection


# ── NEW-dimauto-ordinate-misnomer ───────────────────────────────────────────


async def test_ordinate_dims_are_staggered_not_overlapping(backend):
    l1 = await backend.entity_create_line(0, 0, 20, 10)
    l2 = await backend.entity_create_line(0, 0, 40, 30)
    dims = await backend.dimension_auto([l1.handle, l2.handle], style="ordinate")
    # Each segment emits an X and a Y dim; with per-feature staggering the
    # X-dim reference Y-offsets differ between the two features.
    doc = backend._require_doc()
    y_offsets = []
    for d in dims:
        ent = doc.entitydb[d.handle]
        dp = ent.dxf.get("defpoint", None)
        if dp is not None:
            y_offsets.append(round(float(dp[1]), 3))
    # Not every dim collapses onto a single offset value.
    assert len(set(y_offsets)) > 1
