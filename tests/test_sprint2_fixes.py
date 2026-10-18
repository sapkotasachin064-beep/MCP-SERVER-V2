"""Regression tests for the Sprint-2 audit fixes.

Covers, one block per audit finding:
  * NEW-screenshot-1  — headless Agg render returns a valid PNG (no GUI-thread crash)
  * I15               — drawing_finalize runs the premium critique as part of the gate
  * R4                — dim_overlap critique actually fires (was a guaranteed no-op)
  * N4                — dim / construction layers resolve per the active layer set
  * NEW-AUTH-1        — the remote-bind guard runs on the run_async launch path
  * NEW-gear-roottooth— gear outline never dips inside the root circle (high tooth counts)
  * NEW-section-dupbore / NEW-validator-keyway / NEW-gear-baseconstr
"""

from __future__ import annotations

import math

import pytest

pytestmark = pytest.mark.asyncio


class _FakeCtx:
    """Minimal Context stand-in: drawing_finalize only needs lifespan_context + warning."""

    def __init__(self, backend):
        self.lifespan_context = {"backend": backend}
        self.warnings: list[str] = []

    async def warning(self, message):
        self.warnings.append(message)


# ── NEW-screenshot-1 ────────────────────────────────────────────────────────


async def test_screenshot_renders_png_without_gui_thread_crash(backend):
    """view_screenshot runs in a worker thread; the Agg figure must not crash and
    must return valid PNG bytes."""
    await backend.entity_create_line(0, 0, 100, 100)
    png = await backend.view_screenshot()
    assert png is not None
    assert png[:4] == b"\x89PNG"  # PNG magic


# ── I15 — critique is part of the finalize gate ─────────────────────────────


async def test_finalize_runs_critique_and_blocks_on_construction(backend, tmp_path):
    from fastmcp.exceptions import ToolError

    import server

    await backend.drawing_apply_iso_layers("mech")
    await backend.entity_create_line(0, 0, 100, 0, layer="GEOMETRY")
    await backend.construction_xline(0, 0, 90)  # leftover scaffold -> construction_left ERROR
    ctx = _FakeCtx(backend)
    save = str(tmp_path / "part.dxf")

    with pytest.raises(ToolError) as exc:
        await server.drawing_finalize(save_path=save, ctx=ctx)
    assert "critique" in str(exc.value).lower()

    # Clear the scaffold; finalize now passes and the payload carries the critique.
    await backend.construction_clear()
    payload = await server.drawing_finalize(save_path=save, ctx=ctx)
    assert payload["ok"] is True
    assert "critique" in payload
    assert payload["critique_summary"]["error"] == 0


# ── R4 — dim_overlap critique fires ─────────────────────────────────────────


async def test_dim_overlap_critique_is_not_a_noop(backend):
    await backend.drawing_apply_iso_layers("mech")
    # Two dimensions measuring the same segment overlap exactly.
    await backend.dimension_linear(0, 0, 100, 0, 50, 20, layer="DIM")
    await backend.dimension_linear(0, 0, 100, 0, 50, 20, layer="DIM")
    issues = await backend.drawing_critique(focus=["dim_overlap"])
    assert len(issues) >= 1
    assert all(i.focus == "dim_overlap" for i in issues)


# ── N4 — dim / construction layers follow the active layer set ──────────────


async def test_iso13567_dim_and_construction_layers_resolve(backend):
    await backend.drawing_apply_iso_layers("iso13567")
    assert backend._active_layer_set_id() == "iso13567"
    assert backend._role_layer("dim") == "M-DIMEN-T-N"
    assert backend._role_layer("construction") == "M-CONST-E-N"

    ln = await backend.entity_create_line(0, 0, 80, 0, layer="M-GEOMET-E-N")
    dims = await backend.dimension_auto([ln.handle], style="chain")
    assert dims[0].layer == "M-DIMEN-T-N"

    xl = await backend.construction_xline(0, 0, 90)
    assert xl.layer == "M-CONST-E-N"
    # construction_left must catch iso13567 scaffold (layer name independent).
    left = await backend.drawing_critique(focus=["construction_left"])
    assert len(left) == 1 and left[0].severity == "error"
    cleared = await backend.construction_clear()
    assert cleared["deleted"] == 1
    assert await backend.drawing_critique(focus=["construction_left"]) == []


# ── NEW-AUTH-1 — bind guard on the run_async launch path ────────────────────


async def test_run_async_invokes_bind_guard_for_http(monkeypatch):
    import server

    seen = {}

    def fake_guard(host):
        seen["host"] = host
        raise SystemExit("blocked before bind")

    monkeypatch.setattr(server, "_validate_http_bind", fake_guard)
    with pytest.raises(SystemExit):
        await server.mcp.run_async(transport="http", host="0.0.0.0")
    assert seen["host"] == "0.0.0.0"


async def test_run_async_skips_guard_for_stdio(monkeypatch):
    import server

    seen = {}
    monkeypatch.setattr(server, "_validate_http_bind", lambda h: seen.setdefault("host", h))

    async def fake_orig(*args, **kwargs):
        return "stdio-ran"

    monkeypatch.setattr(server, "_orig_run_async", fake_orig)
    out = await server.mcp.run_async(transport="stdio")
    assert out == "stdio-ran"
    assert seen == {}  # guard not invoked for stdio


# ── NEW-gear-roottooth — outline never dips inside the root circle ──────────


async def test_gear_outline_stays_outside_root_circle():
    from engineering.gear import generate_full_gear_outline

    for module, teeth, pa in [(2, 20, 20.0), (2, 50, 20.0), (3, 60, 20.0), (1, 6, 20.0)]:
        pitch_r = module * teeth / 2.0
        root_r = pitch_r - 1.25 * module
        pts = generate_full_gear_outline(module, teeth, pa)
        radii = [math.hypot(x, y) for x, y in pts]
        # No point may sit inside the root circle (the self-overlap bug for z>=~42).
        assert min(radii) >= root_r - 1e-6, (
            f"m={module} z={teeth}: min_r {min(radii)} < root_r {root_r}"
        )


# ── NEW-section-dupbore / NEW-validator-keyway / NEW-gear-baseconstr ─────────


async def test_gear_front_view_base_circle_persists_and_keyway_validates(backend, tmp_path):
    from engineering.gear import draw_helical_gear_front_view
    from engineering.validator import DrawingValidator

    await backend.drawing_apply_iso_layers("mech")
    res = await draw_helical_gear_front_view(
        backend,
        module=2,
        teeth=20,
        helix_angle=0,
        center=(0, 0),
        bore_diameter=20,
        keyway_width=6,
        keyway_depth=2.8,
    )
    # NEW-gear-baseconstr: base circle is a persistent PHANTOM reference, not CONSTRUCTION.
    base = await backend.entity_get(res["base_circle"])
    assert base.layer == "PHANTOM"
    await backend.construction_clear()
    assert await backend.entity_get(res["base_circle"])  # survives, handle still valid

    # NEW-validator-keyway: the open 4-point keyway polyline is now recognised.
    await backend.drawing_save_as(str(tmp_path / "gear.dxf"))
    vr = await DrawingValidator().run(
        backend,
        expected={"must_have_bore": True, "must_have_keyway": True},
    )
    assert "keyway_section_unverified" not in [f.code for f in vr.findings]


async def test_gear_section_does_not_duplicate_bore_lines(backend):
    from engineering.gear import draw_gear_section_aa

    await backend.drawing_apply_iso_layers("mech")
    await draw_gear_section_aa(
        backend,
        gear_metadata={
            "outer_radius": 22,
            "center": [0, 0],
            "bore_diameter": 20,
            "keyway_width": 6,
            "keyway_depth": 2.8,
        },
        x_offset=100,
        face_width=30,
    )
    dups = await backend.drawing_critique(focus=["duplicate_entities"])
    assert dups == []
