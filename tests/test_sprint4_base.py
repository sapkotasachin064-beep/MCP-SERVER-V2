"""Sprint-4 regression tests for backends/base.py concrete helpers.

Covers:
- N7 — point_from_snap ARC end/mid raises a descriptive RuntimeError (not an
  opaque KeyError) when start_angle/end_angle are absent.
- NEW-base-1 — point_tangent does not raise a raw ValueError ("math domain
  error") for a from-point exactly on / marginally inside the perimeter band.
- NEW-snap-quad-arc / NEW-snap-near-arc — quad/near snaps on an ARC return a
  point that lies on the arc sweep (not an off-sweep full-circle point).
- N8 — get_plan_spec() makes the stored PlanSpec readable.
"""

from __future__ import annotations

import math

import pytest

from backends.base import EntityInfo

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _on_arc(pt, cx, cy, r, sa_deg, ea_deg, tol=1e-6):
    """True if pt lies on the circle of radius r AND within the [sa, ea] sweep
    (degrees, CCW, with wraparound)."""
    if abs(math.hypot(pt[0] - cx, pt[1] - cy) - r) > tol:
        return False
    theta = math.degrees(math.atan2(pt[1] - cy, pt[0] - cx)) % 360.0
    sa = sa_deg % 360.0
    sweep = (ea_deg - sa_deg) % 360.0
    rel = (theta - sa) % 360.0
    return rel <= sweep + 1e-6


# ---------------------------------------------------------------------------
# N7 — ARC snap angle-missing raises RuntimeError, not KeyError
# ---------------------------------------------------------------------------


class TestN7ArcAngleMissing:
    async def _patch_entity_get(self, backend, info: EntityInfo):
        async def _fake(handle):
            return info

        backend.entity_get = _fake  # type: ignore[method-assign]

    async def test_end_snap_missing_angles_raises_runtimeerror(self, backend):
        """An ARC entity whose properties lack start_angle/end_angle must raise
        a descriptive RuntimeError, not a KeyError."""
        bad = EntityInfo(
            handle="DEAD",
            type="ARC",
            layer="0",
            color=256,
            linetype="ByLayer",
            visible=True,
            properties={"center": [0.0, 0.0], "radius": 10.0},  # no angles
        )
        await self._patch_entity_get(backend, bad)
        with pytest.raises(RuntimeError, match="start_angle/end_angle"):
            await backend.point_from_snap("DEAD", "end")

    async def test_mid_snap_missing_angles_raises_runtimeerror(self, backend):
        bad = EntityInfo(
            handle="DEAD",
            type="ARC",
            layer="0",
            color=256,
            linetype="ByLayer",
            visible=True,
            properties={"center": [0.0, 0.0], "radius": 10.0},
        )
        await self._patch_entity_get(backend, bad)
        with pytest.raises(RuntimeError, match="start_angle/end_angle"):
            await backend.point_from_snap("DEAD", "mid")

    async def test_end_snap_missing_angles_not_keyerror(self, backend):
        """Explicitly assert the failure is NOT the old opaque KeyError."""
        bad = EntityInfo(
            handle="DEAD",
            type="ARC",
            layer="0",
            color=256,
            linetype="ByLayer",
            visible=True,
            properties={"center": [0.0, 0.0], "radius": 10.0},
        )
        await self._patch_entity_get(backend, bad)
        with pytest.raises(Exception) as excinfo:
            await backend.point_from_snap("DEAD", "end")
        assert not isinstance(excinfo.value, KeyError)
        assert isinstance(excinfo.value, RuntimeError)

    async def test_real_arc_end_snap_still_works(self, backend):
        """Sanity: a well-formed ARC still resolves end-snap correctly."""
        arc = await backend.entity_create_arc(0, 0, 10, 0, 90)
        sp = await backend.point_from_snap(arc.handle, "end", ref_x=11, ref_y=0)
        # start angle 0 -> (10, 0)
        assert abs(sp[0] - 10.0) < 1e-6
        assert abs(sp[1] - 0.0) < 1e-6


# ---------------------------------------------------------------------------
# NEW-base-1 — point_tangent on/near the perimeter must not raise ValueError
# ---------------------------------------------------------------------------


class TestNewBase1TangentClamp:
    async def test_from_point_exactly_on_circle_no_valueerror(self, backend):
        """A from-point exactly on the perimeter (d == r) degenerates to the
        tangent-at-that-point; -r/d == -1 must not blow up math.acos."""
        circ = await backend.entity_create_circle(0, 0, 10)
        # Point exactly on perimeter at (10, 0).
        pt = await backend.point_tangent(circ.handle, 10.0, 0.0)
        # Tangent point coincides with the from-point (on the circle).
        assert abs(math.hypot(pt[0], pt[1]) - 10.0) < 1e-6
        assert abs(pt[0] - 10.0) < 1e-6
        assert abs(pt[1] - 0.0) < 1e-6

    async def test_from_point_in_narrow_inside_band_no_valueerror(self, backend):
        """A from-point a hair inside the perimeter (within 1e-9 of r, so past
        the d < r-1e-9 guard) used to raise a raw 'math domain error'
        ValueError. After clamping it must degenerate without ValueError."""
        circ = await backend.entity_create_circle(0, 0, 10)
        # d = 10 - 5e-10  -> inside r but NOT below r-1e-9, so the guard passes
        # and -r/d is marginally < -1.
        fx = 10.0 - 5e-10
        try:
            pt = await backend.point_tangent(circ.handle, fx, 0.0)
        except ValueError as exc:  # pragma: no cover - this is the bug we fixed
            pytest.fail(f"point_tangent raised ValueError (NEW-base-1): {exc}")
        # Result still lies on the circle.
        assert abs(math.hypot(pt[0], pt[1]) - 10.0) < 1e-4

    async def test_genuine_internal_point_still_raises_runtimeerror(self, backend):
        """The internal-point guard (d < r) must still raise RuntimeError."""
        circ = await backend.entity_create_circle(0, 0, 10)
        with pytest.raises(RuntimeError, match="inside"):
            await backend.point_tangent(circ.handle, 1.0, 1.0)


# ---------------------------------------------------------------------------
# NEW-snap-quad-arc / NEW-snap-near-arc — snaps stay on the arc sweep
# ---------------------------------------------------------------------------


class TestNewSnapArcSweep:
    async def test_quad_on_quarter_arc_stays_on_sweep(self, backend):
        """Quarter arc 0..90 deg, r=10 at origin. Only the 0-deg and 90-deg
        quadrants lie on the sweep; quad snap must return one of those, never
        the 180/270 quadrant points that are off the arc."""
        arc = await backend.entity_create_arc(0, 0, 10, 0, 90)
        # ref near the (10,0) quadrant
        q = await backend.point_from_snap(arc.handle, "quad", ref_x=12, ref_y=0)
        assert _on_arc(q, 0, 0, 10, 0, 90), f"quad point {q} off sweep"
        # ref near the (0,10) quadrant
        q2 = await backend.point_from_snap(arc.handle, "quad", ref_x=0, ref_y=12)
        assert _on_arc(q2, 0, 0, 10, 0, 90), f"quad point {q2} off sweep"

    async def test_quad_ref_toward_offsweep_quadrant_falls_back_to_sweep(self, backend):
        """Even when ref points toward the (-10,0) quadrant (off the 0..90
        sweep), the returned quad point must remain on the sweep."""
        arc = await backend.entity_create_arc(0, 0, 10, 0, 90)
        q = await backend.point_from_snap(arc.handle, "quad", ref_x=-50, ref_y=-50)
        assert _on_arc(q, 0, 0, 10, 0, 90), f"quad point {q} off sweep"

    async def test_quad_no_quadrant_on_sweep_falls_back_to_endpoint(self, backend):
        """A narrow arc (10..80 deg) contains no axis quadrant; quad must fall
        back to an arc endpoint, which is on the sweep."""
        arc = await backend.entity_create_arc(0, 0, 10, 10, 80)
        q = await backend.point_from_snap(arc.handle, "quad", ref_x=20, ref_y=0)
        assert _on_arc(q, 0, 0, 10, 10, 80), f"quad point {q} off sweep"

    async def test_near_within_sweep_projects_onto_arc(self, backend):
        """A ref inside the 0..90 sweep direction projects onto the arc."""
        arc = await backend.entity_create_arc(0, 0, 10, 0, 90)
        # 45-degree direction is inside the sweep.
        n = await backend.point_from_snap(arc.handle, "near", ref_x=5, ref_y=5)
        assert _on_arc(n, 0, 0, 10, 0, 90), f"near point {n} off sweep"
        # Should be ~ (10/sqrt2, 10/sqrt2)
        assert abs(n[0] - 10 / math.sqrt(2)) < 1e-6
        assert abs(n[1] - 10 / math.sqrt(2)) < 1e-6

    async def test_near_outside_sweep_clamps_to_endpoint(self, backend):
        """A ref in the (-x,-y) direction is outside the 0..90 sweep; near must
        clamp to the nearer arc endpoint (on the sweep), not return an off-sweep
        full-circle projection."""
        arc = await backend.entity_create_arc(0, 0, 10, 0, 90)
        # Direction ~ -27deg (just below the x-axis) is off the 0..90 sweep.
        # Of the two endpoints (10,0) and (0,10), the start (10,0) is clearly
        # nearer to (10, -5), so near must clamp there.
        n = await backend.point_from_snap(arc.handle, "near", ref_x=10, ref_y=-5)
        assert _on_arc(n, 0, 0, 10, 0, 90), f"near point {n} off sweep"
        # Endpoints are (10,0) [start] and (0,10) [end]; (10,0) is nearer.
        assert abs(n[0] - 10.0) < 1e-6
        assert abs(n[1] - 0.0) < 1e-6

    async def test_circle_quad_unchanged(self, backend):
        """CIRCLE quad behaviour is preserved (all four quadrants available)."""
        circ = await backend.entity_create_circle(0, 0, 10)
        q = await backend.point_from_snap(circ.handle, "quad", ref_x=-12, ref_y=0)
        assert abs(q[0] - (-10.0)) < 1e-6
        assert abs(q[1] - 0.0) < 1e-6


# ---------------------------------------------------------------------------
# N8 — get_plan_spec accessor exposes the stored PlanSpec
# ---------------------------------------------------------------------------


class TestN8GetPlanSpec:
    async def test_none_before_plan(self, backend):
        assert backend.get_plan_spec() is None

    async def test_returns_dict_after_plan(self, backend):
        await backend.drawing_plan("test shaft", sheet_size="A3", scale=2.0)
        spec = backend.get_plan_spec()
        assert isinstance(spec, dict)
        assert spec["intent"] == "test shaft"
        assert spec["sheet_size"] == "A3"
        assert spec["scale"] == 2.0
        # Returned object is a plain dict snapshot (not the live dataclass).
        assert "layer_set_id" in spec
