"""Tests for ISO 129 dimension tolerances (engineering/tolerances.py + the
ezdxf dimension_* override plumbing)."""

from __future__ import annotations

import pytest

from engineering.tolerances import build_dim_override

pytestmark = pytest.mark.asyncio


# ── pure: override builder ──────────────────────────────────────────────────


async def test_none_mode_is_empty():
    override, text = build_dim_override(tol_mode="none")
    assert override == {}
    assert text is None


async def test_symmetric_sets_equal_tp_tm():
    override, _ = build_dim_override(tol_upper=0.05, tol_mode="symmetric")
    assert override["dimtol"] == 1
    assert override["dimtp"] == 0.05
    assert override["dimtm"] == 0.05


async def test_deviation_sets_distinct_tp_tm():
    override, _ = build_dim_override(0.02, 0.01, "deviation")
    assert override["dimtp"] == 0.02
    assert override["dimtm"] == 0.01
    assert override["dimtol"] == 1


async def test_limit_mode_sets_dimlim():
    override, _ = build_dim_override(0.02, 0.01, "limit")
    assert override["dimlim"] == 1
    assert override["dimtol"] == 0


async def test_basic_mode_boxes_text():
    override, _ = build_dim_override(tol_mode="basic")
    assert override["dimgap"] < 0


async def test_text_override_passthrough():
    _, text = build_dim_override(text_override="20 H7")
    assert text == "20 H7"


async def test_bad_mode_and_missing_values_raise():
    with pytest.raises(ValueError):
        build_dim_override(tol_mode="wat")
    with pytest.raises(ValueError):
        build_dim_override(tol_mode="symmetric")  # no tol_upper
    with pytest.raises(ValueError):
        build_dim_override(0.02, None, "deviation")  # no tol_lower


# ── backend: toleranced dims are created without error ──────────────────────


async def test_linear_dim_with_symmetric_tolerance(backend):
    await backend.drawing_apply_iso_layers("mech")
    dim = await backend.dimension_linear(
        0,
        0,
        100,
        0,
        50,
        20,
        layer="DIM",
        tol_upper=0.05,
        tol_mode="symmetric",
    )
    assert dim.handle
    assert dim.type in ("DIMENSION", "DIMLINEAR")


async def test_diameter_dim_with_text_override(backend):
    await backend.drawing_apply_iso_layers("mech")
    c = await backend.entity_create_circle(0, 0, 10, layer="GEOMETRY")
    assert c.handle
    dim = await backend.dimension_diameter(
        -10,
        0,
        10,
        0,
        layer="DIM",
        text_override="<> H7",
    )
    assert dim.handle


async def test_radius_dim_with_deviation_tolerance(backend):
    await backend.drawing_apply_iso_layers("mech")
    dim = await backend.dimension_radius(
        0,
        0,
        10,
        0,
        layer="DIM",
        tol_upper=0.03,
        tol_lower=0.01,
        tol_mode="deviation",
    )
    assert dim.handle
