"""Deterministic repair handlers for the bounded drawing refiner."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .plan_spec import ISO_128_LINEWEIGHTS_MM, Issue

if TYPE_CHECKING:
    from backends.base import AutoCADBackend


async def repair_construction_left(backend: AutoCADBackend, issue: Issue) -> dict:
    deleted = []
    for handle in issue.handles:
        await backend.entity_delete(handle)
        deleted.append(handle)
    return {"deleted_handles": deleted}


async def repair_duplicate_entities(backend: AutoCADBackend, issue: Issue) -> dict:
    if len(issue.handles) < 2:
        raise RuntimeError("duplicate_entities repair requires two handles")
    handle = issue.handles[-1]
    await backend.entity_delete(handle)
    return {"deleted_handle": handle, "kept_handle": issue.handles[0]}


async def repair_layer_color(backend: AutoCADBackend, issue: Issue) -> dict:
    layer = str(issue.detail["layer"])
    expected = int(issue.detail["expected"])
    await backend.layer_modify(layer, color=expected)
    return {"layer": layer, "color": expected}


async def repair_iso128(backend: AutoCADBackend, issue: Issue) -> dict:
    layer = str(issue.detail["layer"])
    raw = float(issue.detail["lineweight"])
    millimetres = raw / 100.0 if raw > 2.05 else raw
    nearest = min(ISO_128_LINEWEIGHTS_MM, key=lambda item: abs(item - millimetres))
    await backend.layer_modify(layer, lineweight=nearest)
    return {"layer": layer, "lineweight_mm": nearest}


def _endpoint_kwargs(entity, old_point: list[float], new_point: tuple[float, float]) -> dict:
    start = entity.properties.get("start")
    end = entity.properties.get("end")
    if not start or not end:
        raise RuntimeError(f"LINE {entity.handle} is missing endpoints")
    old = (float(old_point[0]), float(old_point[1]))
    if math.dist((float(start[0]), float(start[1])), old) <= math.dist(
        (float(end[0]), float(end[1])), old
    ):
        return {"x1": new_point[0], "y1": new_point[1]}
    return {"x2": new_point[0], "y2": new_point[1]}


async def repair_untrimmed_corner(backend: AutoCADBackend, issue: Issue) -> dict:
    if len(issue.handles) != 2 or "p1" not in issue.detail or "p2" not in issue.detail:
        raise RuntimeError("untrimmed_corner repair requires two handles and endpoint details")
    p1 = issue.detail["p1"]
    p2 = issue.detail["p2"]
    midpoint = ((float(p1[0]) + float(p2[0])) / 2, (float(p1[1]) + float(p2[1])) / 2)
    first = await backend.entity_get(issue.handles[0])
    second = await backend.entity_get(issue.handles[1])
    await backend.entity_edit_geometry(issue.handles[0], **_endpoint_kwargs(first, p1, midpoint))
    await backend.entity_edit_geometry(issue.handles[1], **_endpoint_kwargs(second, p2, midpoint))
    return {"handles": list(issue.handles), "corner": list(midpoint)}


async def repair_dim_overlap(backend: AutoCADBackend, issue: Issue) -> dict:
    if len(issue.handles) < 2:
        raise RuntimeError("dim_overlap repair requires two handles")
    handle = issue.handles[-1]
    await backend.entity_move(handle, 0.0, 6.0)
    return {"moved_handle": handle, "dy": 6.0}
