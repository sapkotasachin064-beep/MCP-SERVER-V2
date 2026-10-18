"""Tests for analysis tools and entity modification via ezdxf backend."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Entity modification tests
# ---------------------------------------------------------------------------


async def test_entity_copy(backend):
    line = await backend.entity_create_line(0, 0, 100, 0)
    copy = await backend.entity_copy(line.handle, 0, 50)
    assert copy.handle
    assert copy.handle != line.handle
    entities = await backend.entity_list()
    assert len(entities) == 2


async def test_entity_offset(backend):
    line = await backend.entity_create_line(0, 0, 100, 0)
    result = await backend.entity_offset(line.handle, 10)
    assert result.handle


async def test_entity_array_rectangular(backend):
    line = await backend.entity_create_line(0, 0, 10, 0)
    copies = await backend.entity_array_rectangular(line.handle, 3, 4, 20, 30)
    assert len(copies) == 11


async def test_entity_set_properties(backend):
    await backend.layer_create("PROP_LAYER", color=5)
    line = await backend.entity_create_line(0, 0, 100, 0)
    result = await backend.entity_set_properties(line.handle, layer="PROP_LAYER", color=3)
    assert result.get("ok") is True
    got = await backend.entity_get(line.handle)
    assert got.layer == "PROP_LAYER"
    assert got.color == 3


async def test_entity_delete_many(backend):
    h1 = (await backend.entity_create_line(0, 0, 10, 0)).handle
    h2 = (await backend.entity_create_line(10, 0, 20, 0)).handle
    h3 = (await backend.entity_create_line(20, 0, 30, 0)).handle
    entities_before = await backend.entity_list()
    assert len(entities_before) == 3
    await backend.entity_delete(h1)
    await backend.entity_delete(h2)
    await backend.entity_delete(h3)
    entities_after = await backend.entity_list()
    assert len(entities_after) == 0


# ---------------------------------------------------------------------------
# Analysis tests
# ---------------------------------------------------------------------------


async def test_analysis_entity_stats(backend):
    await backend.entity_create_line(0, 0, 100, 0)
    await backend.entity_create_circle(50, 50, 25)
    await backend.entity_create_line(0, 100, 100, 100)
    stats = await backend.analysis_stats()
    assert isinstance(stats, dict)
    by_type = stats.get("by_type", stats)
    total = stats.get(
        "total",
        stats.get("total_entities", sum(by_type.values()) if isinstance(by_type, dict) else 0),
    )
    assert total >= 3


async def test_analysis_find_in_region(backend):
    await backend.entity_create_line(10, 10, 20, 20)
    await backend.entity_create_line(500, 500, 600, 600)
    result = await backend.analysis_entities_in_region(0, 0, 50, 50)
    assert len(result) >= 1


async def test_analysis_measure_distance(backend):
    dist = await backend.analysis_measure_distance(0, 0, 3, 4)
    assert dist == pytest.approx(5.0, abs=0.001)


async def test_analysis_measure_area(backend):
    area = await backend.analysis_measure_area([[0, 0], [10, 0], [10, 10], [0, 10]])
    assert area == pytest.approx(100.0, abs=0.01)


async def test_analysis_bounding_box(backend):
    await backend.entity_create_line(0, 0, 100, 0)
    await backend.entity_create_line(0, 0, 0, 50)
    bbox = await backend.analysis_bounding_box()
    assert isinstance(bbox, dict)


async def test_analysis_select_by_layer(backend):
    await backend.layer_create("SEL_LAYER")
    await backend.entity_create_line(0, 0, 10, 0, layer="SEL_LAYER")
    await backend.entity_create_circle(50, 50, 5)
    result = await backend.analysis_select_by_layer("SEL_LAYER")
    assert len(result) == 1
    assert result[0].layer == "SEL_LAYER"


async def test_analysis_select_by_type(backend):
    await backend.entity_create_line(0, 0, 10, 0)
    await backend.entity_create_circle(50, 50, 5)
    await backend.entity_create_line(0, 100, 10, 100)
    result = await backend.analysis_select_by_type("CIRCLE")
    assert len(result) == 1
    assert result[0].type == "CIRCLE"
