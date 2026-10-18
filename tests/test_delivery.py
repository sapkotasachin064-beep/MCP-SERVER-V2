"""Release delivery contract: artifacts, hashes, validation and DXF parity."""

from __future__ import annotations

import hashlib
import json

import pytest

import server
from engineering.delivery import compare_drawing_snapshots, deliver_drawing, drawing_snapshot
from engineering.layers import ensure_engineering_layers, ensure_standard_linetypes
from version import __version__


async def _clean_drawing(backend) -> None:
    await ensure_standard_linetypes(backend)
    await ensure_engineering_layers(backend)
    await backend.entity_create_line(0, 0, 40, 0, layer="GEOMETRY")


@pytest.mark.asyncio
async def test_delivery_writes_hashed_manifest_and_reopen_parity(backend, tmp_path):
    await _clean_drawing(backend)

    result = await deliver_drawing(
        backend,
        tmp_path,
        formats=["dxf"],
        min_score=0,
        strict_critique=False,
    )

    assert result.status == "success"
    manifest_path = tmp_path / "manifest.json"
    validation_path = tmp_path / "validation.json"
    assert manifest_path.is_file()
    assert validation_path.is_file()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dxf = next(item for item in manifest["artifacts"] if item["format"] == "dxf")
    artifact_path = tmp_path / dxf["filename"]
    assert dxf["status"] == "created"
    assert dxf["sha256"] == hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    assert manifest["parity"]["ok"] is True
    assert manifest["version"] == __version__
    assert manifest["capabilities"]["backend"] == "ezdxf"


@pytest.mark.asyncio
async def test_delivery_keeps_artifacts_when_validation_fails(backend, tmp_path):
    await _clean_drawing(backend)
    await backend.construction_xline(0, 0, 45)

    result = await deliver_drawing(
        backend,
        tmp_path,
        formats=["dxf"],
        min_score=100,
        strict_critique=True,
    )

    assert result.status == "failed_validation"
    assert (tmp_path / "drawing.dxf").is_file()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed_validation"
    assert any(issue["focus"] == "construction_left" for issue in manifest["critique"])


def test_snapshot_comparison_reports_type_and_bounds_drift():
    source = {
        "entity_count": 2,
        "types": {"LINE": 2},
        "layers": {"GEOMETRY": 2},
        "extents_min": [0.0, 0.0],
        "extents_max": [10.0, 5.0],
    }
    reopened = {
        "entity_count": 2,
        "types": {"LINE": 1, "CIRCLE": 1},
        "layers": {"GEOMETRY": 2},
        "extents_min": [0.0, 0.0],
        "extents_max": [10.5, 5.0],
    }

    result = compare_drawing_snapshots(source, reopened)

    assert result["ok"] is False
    assert {item["field"] for item in result["differences"]} == {"types", "extents_max"}


@pytest.mark.asyncio
async def test_snapshot_parity_rejects_incomplete_entity_inventory(backend, monkeypatch):
    await backend.entity_create_line(0, 0, 10, 0)
    await backend.entity_create_circle(5, 5, 2)
    original_entity_list = backend.entity_list

    async def incomplete_entity_list(*args, **kwargs):
        return (await original_entity_list(*args, **kwargs))[:1]

    monkeypatch.setattr(backend, "entity_list", incomplete_entity_list)
    source = await drawing_snapshot(backend)
    reopened = dict(source, inventory_complete=True, listed_entity_count=2)

    result = compare_drawing_snapshots(source, reopened)

    assert source["entity_count"] == 2
    assert source["listed_entity_count"] == 1
    assert source["inventory_complete"] is False
    assert result["ok"] is False
    assert "source_inventory_complete" in {item["field"] for item in result["differences"]}


@pytest.mark.asyncio
async def test_delivery_rejects_unknown_format(backend, tmp_path):
    await _clean_drawing(backend)

    with pytest.raises(ValueError, match="Unsupported delivery format"):
        await deliver_drawing(backend, tmp_path, formats=["step"])


@pytest.mark.asyncio
async def test_server_drawing_deliver_exposes_manifest_tool(backend, tmp_path):
    await _clean_drawing(backend)

    class Ctx:
        lifespan_context = {"backend": backend}

    result = await server.drawing_deliver(
        output_dir=str(tmp_path),
        formats=["dxf"],
        min_score=0,
        strict_critique=False,
        ctx=Ctx(),
    )

    assert result["status"] == "success"
    assert result["manifest_path"].endswith("manifest.json")
