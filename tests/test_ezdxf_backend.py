"""Tests for ezdxf backend — no AutoCAD required."""

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Basic CRUD
# ---------------------------------------------------------------------------


async def test_create_line(backend):
    info = await backend.entity_create_line(0, 0, 100, 0)
    assert info.handle
    assert info.type == "LINE"


async def test_get_entity(backend):
    info = await backend.entity_create_line(0, 0, 50, 50)
    fetched = await backend.entity_get(info.handle)
    assert fetched.handle == info.handle
    assert fetched.type == "LINE"


async def test_move_entity(backend):
    info = await backend.entity_create_line(0, 0, 10, 0)
    result = await backend.entity_move(info.handle, 5, 5)
    assert result["ok"]
    moved = await backend.entity_get(info.handle)
    start = moved.properties["start"]
    assert abs(start[0] - 5) < 1e-6
    assert abs(start[1] - 5) < 1e-6


async def test_delete_entity(backend):
    info = await backend.entity_create_line(0, 0, 10, 0)
    result = await backend.entity_delete(info.handle)
    assert result["ok"]
    entities = await backend.entity_list()
    assert len(entities) == 0


# ---------------------------------------------------------------------------
# Entity filtering — LINE vs LWPOLYLINE
# ---------------------------------------------------------------------------


async def test_entity_list_type_filter_exact_match(backend):
    """LINE filter must NOT match LWPOLYLINE."""
    await backend.entity_create_line(0, 0, 10, 0)
    await backend.entity_create_polyline([[0, 0], [10, 0], [10, 10]], closed=False)

    lines = await backend.entity_list(type_filter="LINE")
    polylines = await backend.entity_list(type_filter="LWPOLYLINE")

    assert len(lines) == 1
    assert lines[0].type == "LINE"
    assert len(polylines) == 1
    assert polylines[0].type == "LWPOLYLINE"


async def test_analysis_select_by_type_exact_match(backend):
    """analysis_select_by_type must use exact match, not substring."""
    await backend.entity_create_line(0, 0, 10, 0)
    await backend.entity_create_polyline([[0, 0], [10, 0], [10, 10]], closed=False)

    lines = await backend.analysis_select_by_type("LINE")
    assert len(lines) == 1
    assert lines[0].type == "LINE"


# ---------------------------------------------------------------------------
# Matrix transforms
# ---------------------------------------------------------------------------


async def test_rotate_around_origin(backend):
    """Rotate a line (10,0)-(20,0) by 90° around origin → (0,10)-(0,20)."""
    info = await backend.entity_create_line(10, 0, 20, 0)
    await backend.entity_rotate(info.handle, 0, 0, 90)
    rotated = await backend.entity_get(info.handle)
    start = rotated.properties["start"]
    end = rotated.properties["end"]
    assert abs(start[0] - 0) < 1e-4
    assert abs(start[1] - 10) < 1e-4
    assert abs(end[0] - 0) < 1e-4
    assert abs(end[1] - 20) < 1e-4


async def test_rotate_around_point(backend):
    """Rotate (10,0)-(20,0) by 90° around (10,0) → (10,0)-(10,10)."""
    info = await backend.entity_create_line(10, 0, 20, 0)
    await backend.entity_rotate(info.handle, 10, 0, 90)
    rotated = await backend.entity_get(info.handle)
    start = rotated.properties["start"]
    end = rotated.properties["end"]
    assert abs(start[0] - 10) < 1e-4
    assert abs(start[1] - 0) < 1e-4
    assert abs(end[0] - 10) < 1e-4
    assert abs(end[1] - 10) < 1e-4


async def test_scale_from_origin(backend):
    """Scale line (10,0)-(20,0) by 2x from origin → (20,0)-(40,0)."""
    info = await backend.entity_create_line(10, 0, 20, 0)
    await backend.entity_scale(info.handle, 0, 0, 2)
    scaled = await backend.entity_get(info.handle)
    start = scaled.properties["start"]
    end = scaled.properties["end"]
    assert abs(start[0] - 20) < 1e-4
    assert abs(end[0] - 40) < 1e-4


async def test_scale_from_point(backend):
    """Scale line (10,0)-(20,0) by 2x from (10,0) → (10,0)-(30,0)."""
    info = await backend.entity_create_line(10, 0, 20, 0)
    await backend.entity_scale(info.handle, 10, 0, 2)
    scaled = await backend.entity_get(info.handle)
    start = scaled.properties["start"]
    end = scaled.properties["end"]
    assert abs(start[0] - 10) < 1e-4
    assert abs(end[0] - 30) < 1e-4


async def test_mirror_across_y_axis(backend):
    """Mirror line (10,0)-(20,0) across Y axis → (-10,0)-(-20,0)."""
    info = await backend.entity_create_line(10, 0, 20, 0)
    mirrored = await backend.entity_mirror(info.handle, 0, 0, 0, 10)
    start = mirrored.properties["start"]
    end = mirrored.properties["end"]
    assert abs(start[0] - (-10)) < 1e-4
    assert abs(end[0] - (-20)) < 1e-4


async def test_array_polar(backend):
    """Polar array of 4 items at 360° around center should create 3 copies."""
    info = await backend.entity_create_line(10, 0, 20, 0)
    copies = await backend.entity_array_polar(info.handle, 4, 360, 0, 0)
    assert len(copies) == 3  # 4 total - 1 original


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


async def test_transaction_rollback(backend):
    """After rollback, entity created inside transaction should be gone."""
    await backend.transaction_begin()
    await backend.entity_create_line(0, 0, 100, 0)
    entities_before = await backend.entity_list()
    assert len(entities_before) == 1

    await backend.transaction_rollback()
    entities_after = await backend.entity_list()
    assert len(entities_after) == 0


async def test_transaction_commit(backend):
    """After commit, entity should still exist."""
    await backend.transaction_begin()
    await backend.entity_create_line(0, 0, 100, 0)
    await backend.transaction_commit()

    entities = await backend.entity_list()
    assert len(entities) == 1


# ---------------------------------------------------------------------------
# block_create_from_entities
# ---------------------------------------------------------------------------


async def test_block_create_from_entities(backend):
    line = await backend.entity_create_line(0, 0, 10, 0)
    circle = await backend.entity_create_circle(5, 5, 3)

    result = await backend.block_create_from_entities(
        "TestBlock", [line.handle, circle.handle], 0, 0
    )
    assert result["ok"]
    assert result["entity_count"] == 2

    blocks = await backend.block_list()
    names = [b.name for b in blocks]
    assert "TestBlock" in names


# ---------------------------------------------------------------------------
# Layer operations
# ---------------------------------------------------------------------------


async def test_layer_create_and_list(backend):
    layer = await backend.layer_create("TestLayer", color=1)
    assert layer.name == "TestLayer"
    assert layer.color == 1

    layers = await backend.layer_list()
    names = [lyr.name for lyr in layers]
    assert "TestLayer" in names
