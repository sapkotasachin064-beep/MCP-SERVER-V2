"""End-to-end smoke test for the premium drafting layer.

Runs the full plan → draw → corners → critique → finalize pipeline against the
ezdxf backend (no AutoCAD required). Exits non-zero on any failure.

Usage:
    python scripts/smoke_premium.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

# Make the project root importable when this script is run from anywhere.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


async def _run() -> int:
    from backends.ezdxf_backend import EzdxfBackend

    backend = EzdxfBackend()
    await backend.connect()
    await backend.drawing_new()

    print("[1/9] drawing_plan ...", end=" ")
    plan = await backend.drawing_plan(
        intent="L-bracket 100x80 R5 inner corner",
        sheet_size="A4",
        scale=1.0,
        layer_set_id="mech",
        dim_style="chain",
    )
    assert plan.intent.startswith("L-bracket"), plan
    print("ok")

    print("[2/9] drawing_apply_iso_layers(mech) ...", end=" ")
    res = await backend.drawing_apply_iso_layers("mech")
    assert res["ok"]
    print(f"ok ({len(res['layers'])} layers)")

    print("[3/9] construction_xline ...", end=" ")
    xl = await backend.construction_xline(0, 0, 0)
    assert xl.layer == "CONSTRUCTION"
    print("ok")

    print("[4/9] entity_create_line × 2 ...", end=" ")
    l1 = await backend.entity_create_line(0, 0, 100, 0, layer="GEOMETRY")
    l2 = await backend.entity_create_line(100, 0, 100, 80, layer="GEOMETRY")
    print("ok")

    print("[5/9] entity_fillet R=5 ...", end=" ")
    arc = await backend.entity_fillet(l1.handle, l2.handle, radius=5)
    assert arc.type == "ARC"
    cx, cy = arc.properties["center"]
    assert abs(cx - 95) < 1e-6 and abs(cy - 5) < 1e-6, (cx, cy)
    print(f"ok (center=({cx},{cy}), r=5)")

    print("[6/9] entity_select_smart ...", end=" ")
    geom = await backend.entity_select_smart(
        {
            "type": "LINE",
            "layer": "GEOMETRY",
        }
    )
    assert len(geom) >= 2, len(geom)
    print(f"ok ({len(geom)} lines selected)")

    print("[7/9] dimension_auto ...", end=" ")
    dims = await backend.dimension_auto(
        [e.handle for e in geom],
        style="chain",
        offset=12.0,
    )
    assert len(dims) == len(geom), (len(dims), len(geom))
    print(f"ok ({len(dims)} dims)")

    print("[8/9] construction_clear ...", end=" ")
    res = await backend.construction_clear()
    assert res["ok"], res
    print(f"ok (deleted {res['deleted']})")

    print("[9/9] drawing_critique (full) ...", end=" ")
    issues = await backend.drawing_critique(focus=None)
    if issues:
        print("FAIL")
        for i in issues:
            print(f"     [{i.severity}] {i.focus}: {i.message}")
        return 1
    print("ok ([] — clean)")

    print("[bonus] export DXF ...", end=" ")
    out = Path(tempfile.gettempdir()) / "smoke_premium.dxf"
    await backend.drawing_export_dxf(str(out))
    assert out.exists() and out.stat().st_size > 0
    print(f"ok ({out}, {out.stat().st_size} bytes)")

    await backend.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
