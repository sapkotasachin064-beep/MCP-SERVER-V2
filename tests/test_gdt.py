"""Tests for 2D GD&T (ISO 1101) — pure layout math, backend composition, and
the datum-consistency critique focus."""

from __future__ import annotations

import pytest

from engineering.gdt import (
    DIAMETER_PREFIX,
    GEOMETRIC_SYMBOLS,
    MATERIAL_MODIFIERS,
    datum_triangle,
    fcf_compartments,
    fcf_layout,
)

pytestmark = pytest.mark.asyncio


# ── pure: compartments ──────────────────────────────────────────────────────


async def test_form_tolerance_needs_no_datum():
    comps = fcf_compartments("flatness", 0.1)
    assert comps[0] == GEOMETRIC_SYMBOLS["flatness"]
    assert comps[1] == "0.1"
    assert len(comps) == 2


async def test_position_requires_datum():
    with pytest.raises(ValueError):
        fcf_compartments("position", 0.2)  # location control, no datum


async def test_position_with_datums_and_diameter_and_modifier():
    comps = fcf_compartments(
        "position",
        0.2,
        ["A", "B", "C"],
        diameter=True,
        modifier="M",
    )
    assert comps[0] == GEOMETRIC_SYMBOLS["position"]
    assert comps[1] == f"{DIAMETER_PREFIX}0.2{MATERIAL_MODIFIERS['M']}"
    assert comps[2:] == ["A", "B", "C"]


async def test_unknown_symbol_and_modifier_raise():
    with pytest.raises(ValueError):
        fcf_compartments("bogus", 0.1)
    with pytest.raises(ValueError):
        fcf_compartments("flatness", 0.1, modifier="Z")


# ── pure: layout geometry ───────────────────────────────────────────────────


async def test_fcf_layout_box_closed_and_dividers_count():
    comps = fcf_compartments("position", 0.2, ["A", "B"], diameter=True)
    lay = fcf_layout(comps, 0.0, 0.0, 5.0)
    # Closed rectangle: first == last point.
    assert lay["box"][0] == lay["box"][-1]
    # n compartments -> n-1 internal dividers, n labels.
    assert len(lay["dividers"]) == len(comps) - 1
    assert len(lay["labels"]) == len(comps)
    assert lay["width"] > 0 and lay["height"] == 5.0


async def test_datum_triangle_is_closed_triangle():
    tri = datum_triangle(10.0, 20.0, 4.0, down=True)
    assert tri[0] == (10.0, 20.0)  # apex
    assert tri[0] == tri[-1]  # closed
    assert len(tri) == 4


# ── backend composition ─────────────────────────────────────────────────────


async def test_draw_feature_control_frame_creates_entities(backend):
    await backend.drawing_apply_iso_layers("mech")
    res = await backend.draw_feature_control_frame(
        "perpendicularity",
        0.05,
        0.0,
        0.0,
        datums=["A"],
        height=5.0,
    )
    assert res["ok"] is True
    assert res["layer"] == "DIM"
    # box + 2 dividers (3 compartments) + 3 texts = several handles
    assert len(res["handles"]) >= 5
    for h in res["handles"]:
        assert await backend.entity_get(h) is not None


async def test_draw_datum_feature_records_letter(backend):
    await backend.drawing_apply_iso_layers("mech")
    res = await backend.draw_datum_feature("A", 0.0, 0.0, size=5.0)
    assert res["datum"] == "A"
    assert "A" in backend._gdt_datums_defined


# ── gdt critique focus ──────────────────────────────────────────────────────


async def test_gdt_critique_flags_missing_datum(backend):
    await backend.drawing_apply_iso_layers("mech")
    await backend.draw_feature_control_frame(
        "position",
        0.2,
        0.0,
        0.0,
        datums=["A", "B"],
        diameter=True,
    )
    issues = await backend.drawing_critique(focus=["gdt"])
    assert len(issues) == 1
    assert issues[0].focus == "gdt"
    assert issues[0].severity == "error"
    assert set(issues[0].detail["missing_datums"]) == {"A", "B"}


async def test_gdt_critique_passes_when_datums_defined(backend):
    await backend.drawing_apply_iso_layers("mech")
    await backend.draw_feature_control_frame(
        "position",
        0.2,
        0.0,
        0.0,
        datums=["A"],
        diameter=True,
    )
    await backend.draw_datum_feature("A", 50.0, 0.0)
    issues = await backend.drawing_critique(focus=["gdt"])
    assert issues == []


async def test_clean_drawing_gdt_focus_is_noop(backend):
    await backend.drawing_apply_iso_layers("mech")
    # No FCFs at all — gdt must not fire, and full critique stays clean.
    assert await backend.drawing_critique(focus=["gdt"]) == []
    assert await backend.drawing_critique() == []
