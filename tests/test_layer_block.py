"""Tests for layer and block operations via ezdxf backend."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Layer tests
# ---------------------------------------------------------------------------


async def test_layer_create(backend):
    result = await backend.layer_create("WALLS", color=1)
    assert result.name == "WALLS"
    assert result.color == 1


async def test_layer_list(backend):
    await backend.layer_create("A")
    await backend.layer_create("B")
    layers = await backend.layer_list()
    names = [lyr.name for lyr in layers]
    assert "A" in names
    assert "B" in names


async def test_layer_delete(backend):
    await backend.layer_create("TEMP")
    result = await backend.layer_delete("TEMP")
    assert result.get("ok") is True
    layers = await backend.layer_list()
    names = [lyr.name for lyr in layers]
    assert "TEMP" not in names


async def test_layer_set_current(backend):
    await backend.layer_create("CURRENT_TEST")
    result = await backend.layer_set_current("CURRENT_TEST")
    assert result.get("ok") is True


async def test_layer_modify(backend):
    await backend.layer_create("MOD_LAYER", color=1)
    result = await backend.layer_modify("MOD_LAYER", color=3)
    assert result.color == 3


async def test_layer_freeze_thaw(backend):
    await backend.layer_create("FREEZE_TEST")
    result = await backend.layer_freeze("FREEZE_TEST")
    assert result.get("ok") is True
    result = await backend.layer_thaw("FREEZE_TEST")
    assert result.get("ok") is True


async def test_layer_lock_unlock(backend):
    await backend.layer_create("LOCK_TEST")
    result = await backend.layer_lock("LOCK_TEST")
    assert result.get("ok") is True
    result = await backend.layer_unlock("LOCK_TEST")
    assert result.get("ok") is True


async def test_layer_hide_show(backend):
    await backend.layer_create("VIS_TEST")
    result = await backend.layer_hide("VIS_TEST")
    assert result.get("ok") is True
    result = await backend.layer_show("VIS_TEST")
    assert result.get("ok") is True


# ---------------------------------------------------------------------------
# Block tests
# ---------------------------------------------------------------------------


async def test_block_create_and_list(backend):
    line = await backend.entity_create_line(0, 0, 10, 0)
    circle = await backend.entity_create_circle(5, 5, 3)
    result = await backend.block_create_from_entities(
        "MY_BLOCK", [line.handle, circle.handle], base_x=0, base_y=0
    )
    assert result.get("ok") is True
    blocks = await backend.block_list()
    block_names = [b.name for b in blocks]
    assert "MY_BLOCK" in block_names


async def test_block_insert(backend):
    line = await backend.entity_create_line(0, 0, 10, 0)
    await backend.block_create_from_entities("INS_BLOCK", [line.handle])
    result = await backend.block_insert("INS_BLOCK", 50, 50)
    assert result.handle
    assert result.type == "INSERT"


async def test_block_explode(backend):
    line = await backend.entity_create_line(0, 0, 10, 0)
    await backend.block_create_from_entities("EXPLODE_BLK", [line.handle])
    ref = await backend.block_insert("EXPLODE_BLK", 0, 0)
    result = await backend.block_explode(ref.handle)
    assert result.get("ok") is True


async def test_block_get_attributes(backend):
    line = await backend.entity_create_line(0, 0, 10, 0)
    await backend.block_create_from_entities("ATTR_BLK", [line.handle])
    ref = await backend.block_insert("ATTR_BLK", 0, 0)
    attrs = await backend.block_get_attributes(ref.handle)
    assert isinstance(attrs, dict)
