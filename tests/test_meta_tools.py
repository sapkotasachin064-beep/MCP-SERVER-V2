"""Tests for the premium meta-tool layer (Task #10).

Coverage: drawing_plan, drawing_critique, point_from_snap, construction_*,
drawing_apply_iso_layers, dimension_auto, entity_select_smart.
Plus a small integration pipeline: plan → draw → critique.
"""

import pytest

pytestmark = pytest.mark.asyncio


def _close(a, b, tol=1e-6):
    return abs(a - b) < tol


# ─── drawing_plan ──────────────────────────────────────────────────────────


class TestDrawingPlan:
    async def test_plan_returns_spec_with_intent(self, backend):
        plan = await backend.drawing_plan(
            "L-bracket 50x80",
            sheet_size="A4",
            scale=1.0,
        )
        assert plan.intent == "L-bracket 50x80"
        assert plan.sheet_size == "A4"
        assert plan.scale == 1.0
        assert plan.layer_set_id == "mech"

    async def test_plan_to_dict(self, backend):
        plan = await backend.drawing_plan("X", sheet_size="A3", scale=2.0)
        d = plan.to_dict()
        assert d["intent"] == "X"
        assert d["sheet_size"] == "A3"
        assert d["notes"] == []


# ─── drawing_critique ──────────────────────────────────────────────────────


class TestDrawingCritique:
    async def test_critique_clean_drawing(self, backend):
        # Bootstrap layer set so layer_color/iso128 don't trigger.
        await backend.drawing_apply_iso_layers("mech")
        issues = await backend.drawing_critique()
        assert issues == []

    async def test_critique_construction_left(self, backend):
        await backend.construction_xline(0, 0, 0)
        issues = await backend.drawing_critique(focus=["construction_left"])
        assert len(issues) == 1
        assert issues[0].focus == "construction_left"
        assert issues[0].severity == "error"

    async def test_critique_construction_clear_resets(self, backend):
        await backend.construction_xline(0, 0, 0)
        await backend.construction_clear()
        issues = await backend.drawing_critique(focus=["construction_left"])
        assert issues == []

    async def test_critique_untrimmed_corner(self, backend):
        # Two lines with a 0.1 mm gap — should flag.
        await backend.entity_create_line(0, 0, 50, 0)
        await backend.entity_create_line(50.1, 0, 50.1, 50)
        issues = await backend.drawing_critique(focus=["untrimmed_corner"])
        assert len(issues) >= 1
        assert all(i.focus == "untrimmed_corner" for i in issues)

    async def test_critique_duplicate_entities(self, backend):
        await backend.entity_create_line(0, 0, 100, 0)
        await backend.entity_create_line(0, 0, 100, 0)
        issues = await backend.drawing_critique(focus=["duplicate_entities"])
        assert len(issues) >= 1


# ─── point_from_snap ───────────────────────────────────────────────────────


class TestPointFromSnap:
    async def test_snap_end_default(self, backend):
        line = await backend.entity_create_line(0, 0, 100, 0)
        pt = await backend.point_from_snap(line.handle, "end")
        assert pt == (0.0, 0.0)

    async def test_snap_end_with_ref(self, backend):
        line = await backend.entity_create_line(0, 0, 100, 0)
        pt = await backend.point_from_snap(line.handle, "end", ref_x=90, ref_y=0)
        assert pt == (100.0, 0.0)

    async def test_snap_mid(self, backend):
        line = await backend.entity_create_line(0, 0, 100, 0)
        pt = await backend.point_from_snap(line.handle, "mid")
        assert pt == (50.0, 0.0)

    async def test_snap_perp(self, backend):
        line = await backend.entity_create_line(0, 0, 100, 0)
        pt = await backend.point_from_snap(line.handle, "perp", ref_x=50, ref_y=30)
        assert pt == (50.0, 0.0)

    async def test_snap_near_clamped(self, backend):
        line = await backend.entity_create_line(0, 0, 100, 0)
        pt = await backend.point_from_snap(line.handle, "near", ref_x=200, ref_y=30)
        assert pt == (100.0, 0.0)

    async def test_snap_circle_center(self, backend):
        c = await backend.entity_create_circle(50, 50, 10)
        pt = await backend.point_from_snap(c.handle, "center")
        assert pt == (50.0, 50.0)

    async def test_snap_circle_quad_east(self, backend):
        c = await backend.entity_create_circle(50, 50, 10)
        pt = await backend.point_from_snap(c.handle, "quad", ref_x=70, ref_y=50)
        assert pt == (60.0, 50.0)

    async def test_snap_unknown_raises(self, backend):
        line = await backend.entity_create_line(0, 0, 100, 0)
        with pytest.raises(RuntimeError, match="unknown snap"):
            await backend.point_from_snap(line.handle, "moonbeam")

    async def test_snap_perp_requires_ref(self, backend):
        line = await backend.entity_create_line(0, 0, 100, 0)
        with pytest.raises(RuntimeError, match="ref_x"):
            await backend.point_from_snap(line.handle, "perp")


# ─── construction layer ───────────────────────────────────────────────────


class TestConstructionLayer:
    async def test_xline_creates_on_construction_layer(self, backend):
        xl = await backend.construction_xline(0, 0, 45)
        assert xl.layer == "CONSTRUCTION"

    async def test_clear_removes_xlines(self, backend):
        await backend.construction_xline(0, 0, 0)
        await backend.construction_xline(10, 10, 90)
        result = await backend.construction_clear()
        assert result["deleted"] == 2

    async def test_clear_empty_layer_is_zero(self, backend):
        result = await backend.construction_clear()
        assert result["deleted"] == 0


# ─── drawing_apply_iso_layers ──────────────────────────────────────────────


class TestApplyISOLayers:
    async def test_mech_layer_set(self, backend):
        result = await backend.drawing_apply_iso_layers("mech")
        assert result["ok"] is True
        layers = await backend.layer_list()
        names = {lyr.name for lyr in layers}
        assert {"GEOMETRY", "DIM", "CENTER", "HIDDEN", "CONSTRUCTION"}.issubset(names)

    async def test_pid_layer_set(self, backend):
        result = await backend.drawing_apply_iso_layers("pid")
        assert result["ok"] is True
        layers = await backend.layer_list()
        names = {lyr.name for lyr in layers}
        assert "PROCESS-PIPING-MAIN" in names
        assert "INSTRUMENT-SYMBOL" in names

    async def test_iso13567_layer_set(self, backend):
        result = await backend.drawing_apply_iso_layers("iso13567")
        assert result["ok"] is True
        layers = await backend.layer_list()
        names = {lyr.name for lyr in layers}
        assert "M-GEOMET-E-N" in names

    async def test_bad_standard_raises(self, backend):
        with pytest.raises(RuntimeError, match="Unknown layer set"):
            await backend.drawing_apply_iso_layers("mars")


# ─── dimension_auto ────────────────────────────────────────────────────────


class TestDimensionAuto:
    async def test_chain_creates_one_dim_per_segment(self, backend):
        l1 = await backend.entity_create_line(0, 0, 30, 0)
        l2 = await backend.entity_create_line(30, 0, 70, 0)
        l3 = await backend.entity_create_line(70, 0, 100, 0)
        dims = await backend.dimension_auto(
            [l1.handle, l2.handle, l3.handle],
            style="chain",
        )
        assert len(dims) == 3

    async def test_baseline_creates_dims(self, backend):
        l1 = await backend.entity_create_line(0, 0, 30, 0)
        l2 = await backend.entity_create_line(30, 0, 70, 0)
        dims = await backend.dimension_auto([l1.handle, l2.handle], style="baseline")
        assert len(dims) == 2

    async def test_unknown_style_raises(self, backend):
        ln = await backend.entity_create_line(0, 0, 50, 0)
        with pytest.raises(RuntimeError, match="unknown style"):
            await backend.dimension_auto([ln.handle], style="diagonal")

    async def test_empty_handles_returns_empty(self, backend):
        result = await backend.dimension_auto([], style="chain")
        assert result == []


# ─── entity_select_smart ───────────────────────────────────────────────────


class TestEntitySelectSmart:
    async def test_select_by_type(self, backend):
        await backend.entity_create_line(0, 0, 50, 0)
        await backend.entity_create_line(0, 50, 50, 50)
        await backend.entity_create_circle(25, 25, 5)
        result = await backend.entity_select_smart({"type": "LINE"})
        assert len(result) == 2

    async def test_select_by_layer(self, backend):
        await backend.layer_create("ALPHA", color=2)
        await backend.entity_create_line(0, 0, 50, 0, layer="ALPHA")
        await backend.entity_create_line(0, 50, 50, 50)  # default layer
        result = await backend.entity_select_smart({"layer": "ALPHA"})
        assert len(result) == 1

    async def test_select_by_near(self, backend):
        await backend.entity_create_line(0, 0, 10, 0)  # near origin
        await backend.entity_create_line(1000, 1000, 1010, 1000)  # far
        result = await backend.entity_select_smart({"type": "LINE", "near": [0, 0, 50]})
        assert len(result) == 1

    async def test_select_by_length_range(self, backend):
        await backend.entity_create_line(0, 0, 10, 0)  # length 10
        await backend.entity_create_line(0, 50, 100, 50)  # length 100
        result = await backend.entity_select_smart({"type": "LINE", "length_range": [50, 200]})
        assert len(result) == 1


# ─── Integration: plan → draw → critique pipeline ──────────────────────────


class TestPremiumPipeline:
    async def test_full_l_bracket_pipeline_clean(self, backend):
        """plan → apply_layers → draw + fillet → clear construction → critique = []."""
        plan = await backend.drawing_plan("L-bracket", sheet_size="A4", scale=1.0)
        assert plan.intent == "L-bracket"
        await backend.drawing_apply_iso_layers("mech")
        l1 = await backend.entity_create_line(0, 0, 100, 0, layer="GEOMETRY")
        l2 = await backend.entity_create_line(100, 0, 100, 80, layer="GEOMETRY")
        await backend.entity_fillet(l1.handle, l2.handle, radius=5)
        await backend.construction_clear()
        # Closed corner with fillet, no construction left, no duplicates.
        issues = await backend.drawing_critique(
            focus=["construction_left", "untrimmed_corner", "duplicate_entities"],
        )
        assert issues == []
