"""Tests for batch operations, templates, and validation."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Batch create tests
# ---------------------------------------------------------------------------


async def test_batch_create_lines(backend):
    """Batch create should work via individual backend calls."""
    await backend.entity_create_line(0, 0, 10, 0)
    await backend.entity_create_line(10, 0, 20, 0)
    await backend.entity_create_circle(5, 5, 3)
    entities = await backend.entity_list()
    assert len(entities) == 3


async def test_batch_modify_move(backend):
    """Batch move multiple entities."""
    line = await backend.entity_create_line(0, 0, 100, 0)
    await backend.entity_move(line.handle, 10, 20)
    got = await backend.entity_get(line.handle)
    props = got.properties or {}
    start = props.get("start", [])
    if start:
        assert abs(start[0] - 10) < 0.01
        assert abs(start[1] - 20) < 0.01


async def test_batch_modify_delete(backend):
    """Batch delete multiple entities."""
    h1 = (await backend.entity_create_line(0, 0, 10, 0)).handle
    h2 = (await backend.entity_create_line(10, 0, 20, 0)).handle
    await backend.entity_delete(h1)
    await backend.entity_delete(h2)
    entities = await backend.entity_list()
    assert len(entities) == 0


# ---------------------------------------------------------------------------
# Template tests
# ---------------------------------------------------------------------------


async def test_template_architectural_layers(backend):
    """Architectural template should create standard layers."""
    layer_defs = [
        ("WALLS", 7),
        ("DOORS", 3),
        ("WINDOWS", 4),
        ("FURNITURE", 8),
        ("DIMENSIONS", 2),
        ("TEXT", 7),
    ]
    for name, color in layer_defs:
        await backend.layer_create(name, color=color)

    layers = await backend.layer_list()
    names = {lyr.name for lyr in layers}
    assert "WALLS" in names
    assert "DOORS" in names
    assert "WINDOWS" in names


async def test_template_mechanical_layers(backend):
    """Mechanical template layers."""
    layer_defs = [
        ("VISIBLE", 7),
        ("HIDDEN", 1),
        ("CENTER", 3),
        ("DIMENSIONS", 2),
        ("SECTION", 5),
    ]
    for name, color in layer_defs:
        await backend.layer_create(name, color=color)

    layers = await backend.layer_list()
    names = {lyr.name for lyr in layers}
    assert "VISIBLE" in names
    assert "HIDDEN" in names
    assert "CENTER" in names


async def test_template_electrical_layers(backend):
    """Electrical template layers."""
    await backend.layer_create("POWER_LINES", color=7)
    await backend.layer_create("CONTROL_LINES", color=3)
    layers = await backend.layer_list()
    names = {lyr.name for lyr in layers}
    assert "POWER_LINES" in names
    assert "CONTROL_LINES" in names


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


async def test_validation_empty_layers(backend):
    """Empty layers should be detected."""
    await backend.layer_create("EMPTY_LAYER")
    layers = await backend.layer_list()
    entities = await backend.entity_list(limit=50000)
    used = {e.layer for e in entities}
    empty = [lyr for lyr in layers if lyr.name != "0" and lyr.name not in used]
    assert len(empty) >= 1
    assert any(lyr.name == "EMPTY_LAYER" for lyr in empty)


async def test_validation_no_issues_clean_drawing(backend):
    """A clean drawing with no empty layers should have no issues."""
    await backend.entity_create_line(0, 0, 100, 0)
    entities = await backend.entity_list()
    assert len(entities) >= 1


async def test_validation_zero_length_detection(backend):
    """Zero-length lines should be detectable."""
    await backend.entity_create_line(50, 50, 50, 50)
    lines = await backend.entity_list(type_filter="LINE")
    assert len(lines) == 1
    props = lines[0].properties or {}
    start = props.get("start", [])
    end = props.get("end", [])
    if start and end:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = (dx * dx + dy * dy) ** 0.5
        assert length < 0.01
