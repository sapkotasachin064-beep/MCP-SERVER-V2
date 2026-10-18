"""Tests for entity creation — all entity types via ezdxf backend."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_create_circle(backend):
    info = await backend.entity_create_circle(50, 50, 25)
    assert info.handle
    assert info.type == "CIRCLE"
    got = await backend.entity_get(info.handle)
    assert got.type == "CIRCLE"
    assert got.properties.get("radius") == pytest.approx(25, abs=0.01)


async def test_create_arc(backend):
    info = await backend.entity_create_arc(0, 0, 50, 0, 90)
    assert info.handle
    assert info.type == "ARC"


async def test_create_polyline(backend):
    pts = [[0, 0], [100, 0], [100, 100], [0, 100]]
    info = await backend.entity_create_polyline(pts, closed=True)
    assert info.handle
    assert info.type == "LWPOLYLINE"


async def test_create_polyline_open(backend):
    pts = [[0, 0], [50, 50], [100, 0]]
    info = await backend.entity_create_polyline(pts, closed=False)
    assert info.handle
    assert info.type == "LWPOLYLINE"


async def test_create_text(backend):
    info = await backend.entity_create_text("Hello", 10, 20, height=5.0)
    assert info.handle
    assert info.type == "TEXT"


async def test_create_mtext(backend):
    info = await backend.entity_create_mtext("Multi\\Pline Text", 0, 0, width=200)
    assert info.handle
    assert info.type == "MTEXT"


async def test_create_hatch(backend):
    boundary = [[0, 0], [100, 0], [100, 100], [0, 100]]
    info = await backend.entity_create_hatch("SOLID", boundary, scale=1.0, angle=0)
    assert info.handle
    assert info.type == "HATCH"


async def test_create_spline(backend):
    pts = [[0, 0], [25, 50], [50, 25], [75, 75], [100, 0]]
    info = await backend.entity_create_spline(pts)
    assert info.handle
    assert info.type == "SPLINE"


async def test_create_ellipse(backend):
    info = await backend.entity_create_ellipse(50, 50, 40, 0, ratio=0.5)
    assert info.handle
    assert info.type == "ELLIPSE"


async def test_create_point(backend):
    info = await backend.entity_create_point(10, 20)
    assert info.handle
    assert info.type == "POINT"


async def test_create_line_with_layer(backend):
    await backend.layer_create("TEST_LAYER", color=1)
    info = await backend.entity_create_line(0, 0, 100, 0, layer="TEST_LAYER")
    assert info.handle
    assert info.layer == "TEST_LAYER"


async def test_create_circle_with_color(backend):
    info = await backend.entity_create_circle(0, 0, 10, color=3)
    assert info.handle
    got = await backend.entity_get(info.handle)
    assert got.color == 3


async def test_create_entity_appears_in_list(backend):
    await backend.entity_create_line(0, 0, 10, 0)
    await backend.entity_create_circle(50, 50, 5)
    await backend.entity_create_point(0, 0)
    entities = await backend.entity_list()
    assert len(entities) == 3
    types = {e.type for e in entities}
    assert "LINE" in types
    assert "CIRCLE" in types
    assert "POINT" in types
