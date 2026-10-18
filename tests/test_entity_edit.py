"""Tests for in-place editing: entity_edit_text and entity_edit_geometry.

These let a user re-label text or re-drive geometry without deleting and
recreating (which would lose the entity handle)."""

from __future__ import annotations

import math

import pytest

pytestmark = pytest.mark.asyncio


# ── entity_edit_text ────────────────────────────────────────────────────────


async def test_edit_text_changes_content_keeps_handle(backend):
    t = await backend.entity_create_text("OLD LABEL", 0, 0, height=2.5, layer="TEXT")
    updated = await backend.entity_edit_text(t.handle, text="NEW LABEL")
    assert updated.handle == t.handle  # handle preserved
    assert updated.properties["text"] == "NEW LABEL"


async def test_edit_text_changes_height_and_rotation(backend):
    t = await backend.entity_create_text("HELLO", 0, 0, height=2.5, layer="TEXT")
    updated = await backend.entity_edit_text(t.handle, height=5.0, rotation=90.0)
    assert math.isclose(updated.properties["height"], 5.0)
    assert math.isclose(updated.properties["rotation"], 90.0)
    # Content untouched when text is omitted.
    assert updated.properties["text"] == "HELLO"


async def test_edit_mtext_content(backend):
    m = await backend.entity_create_mtext("first draft", 0, 0, width=100, height=3, layer="TEXT")
    updated = await backend.entity_edit_text(m.handle, text="final copy")
    assert "final copy" in updated.properties["text"]


async def test_edit_text_rejects_non_text(backend):
    c = await backend.entity_create_circle(0, 0, 10, layer="GEOMETRY")
    with pytest.raises(RuntimeError):
        await backend.entity_edit_text(c.handle, text="nope")


# ── entity_edit_geometry ────────────────────────────────────────────────────


async def test_edit_circle_radius_and_center(backend):
    c = await backend.entity_create_circle(0, 0, 10, layer="GEOMETRY")
    updated = await backend.entity_edit_geometry(c.handle, cx=5, cy=5, radius=20)
    assert updated.handle == c.handle
    assert math.isclose(updated.properties["radius"], 20.0)
    center = updated.properties["center"]
    assert math.isclose(center[0], 5.0) and math.isclose(center[1], 5.0)


async def test_edit_line_endpoints(backend):
    ln = await backend.entity_create_line(0, 0, 10, 0, layer="GEOMETRY")
    updated = await backend.entity_edit_geometry(ln.handle, x2=10, y2=10)
    end = updated.properties["end"]
    assert math.isclose(end[0], 10.0) and math.isclose(end[1], 10.0)
    # Start unchanged.
    start = updated.properties["start"]
    assert math.isclose(start[0], 0.0) and math.isclose(start[1], 0.0)


async def test_edit_arc_angles(backend):
    arc = await backend.entity_create_arc(0, 0, 10, 0, 90, layer="GEOMETRY")
    updated = await backend.entity_edit_geometry(arc.handle, start_angle=10, end_angle=170)
    assert math.isclose(updated.properties["start_angle"], 10.0)
    assert math.isclose(updated.properties["end_angle"], 170.0)


async def test_edit_geometry_rejects_unsupported(backend):
    poly = await backend.entity_create_polyline([[0, 0], [1, 1]], layer="GEOMETRY")
    with pytest.raises(RuntimeError):
        await backend.entity_edit_geometry(poly.handle, radius=5)
