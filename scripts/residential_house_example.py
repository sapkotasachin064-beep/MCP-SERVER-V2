"""A worked `arch_plan_from_spec` example: a two-storey residential test fixture.

DEMO / LOCAL ONLY - not an approved architectural or structural design
(CLAUDE.md's rule for the whole `arch` pack; `drawing_critique` and
`completeness` never certify code compliance or structural adequacy).

The brief (a capability-audit test project, not a real commission):

* Plot 40 x 30 ft, road-facing north. Assumed, since the brief does not say
  which dimension faces the road: the 30 ft side is the frontage (east-west),
  the 40 ft side runs north-south (depth).
* Setbacks front/side/rear 5/3/3 ft - a test-fixture assumption, not a
  citation of any local regulation.
* Ground floor: living/dining, kitchen, one shared bathroom, a stair hall.
  First floor: all four bedrooms, two bathrooms, a stair landing.
* A U-shaped stair in its own stairwell, in the same plan position on both
  floors - this repository has no storey-link concept (CLAUDE.md), so
  keeping the stair's position identical across the two independent
  `arch_plan_from_spec` calls is this script's job, by hand, not the tool's.

Because there is no storey link, `arch_room_unreachable` fires on every room
of the first-floor document: that check's only notion of "reachable" is a
path to an exterior door, and a stair to the floor below is not a connection
it can see. That is a documented limitation of the check (completeness.py),
not a defect in this plan - see the printed completeness report.

Usage::

    uv run --frozen python scripts/residential_house_example.py --out D:/tmp/house
    uv run --frozen python scripts/residential_house_example.py --out D:/tmp/house --dry-run

Refuses an --out folder inside this repository: a generated drawing, even a
synthetic demo one, is not a repository asset (the same discipline as
scripts/field_test_takeoff.py).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REFUSED = 2

# -- the plot ------------------------------------------------------------------

PLOT_WIDTH_FT = 30.0  # frontage, east-west (assumed)
PLOT_DEPTH_FT = 40.0  # depth, north-south (assumed)
FRONT_SETBACK_FT, SIDE_SETBACK_FT, REAR_SETBACK_FT = 5.0, 3.0, 3.0

EXT_THICKNESS = 230.0  # mm, one-sided inward (justification="left")
PARTITION_THICKNESS = 115.0
P1_Y = 4200.0  # the floor-to-floor partition between the north and south zones
COL_X1, COL_X2 = 2700.0, 5200.0  # the two north-south partitions

STAIR_PARAMS = {
    "width": 900.0,
    "risers": 17,
    "riser_height": 175.0,  # 17 x 175 = 2975 mm floor-to-floor
    "going": 280.0,  # Blondel 2(175) + 280 = 630, within 600-650
    "kind": "u",
    "turn": "left",
}
STAIR_START = (1700.0, 280.0)
STAIR_DIRECTION_DEG = 90.0


def _envelope() -> tuple[float, float]:
    from engineering.arch.units import ft_to_mm

    width = ft_to_mm(PLOT_WIDTH_FT - 2.0 * SIDE_SETBACK_FT)
    depth = ft_to_mm(PLOT_DEPTH_FT - FRONT_SETBACK_FT - REAR_SETBACK_FT)
    return width, depth


def _side_length(axis, side_index: int) -> float:
    a, b = axis[side_index], axis[(side_index + 1) % len(axis)]
    return math.dist(a, b)


def _side_base_offset(axis, side_index: int) -> float:
    return sum(_side_length(axis, i) for i in range(side_index))


def _opening_on_side(
    axis, side_index: int, world_lo: float, world_hi: float
) -> tuple[float, float]:
    """``(offset, width)`` on a closed wall's side, from a WORLD coordinate range.

    Avoids hand-mirroring a side that runs backwards (e.g. the north side of
    a CCW rectangle runs from +x to 0): give the world x or y range you want
    the opening to occupy, and this walks it back to the wall's own offset.
    """
    a, b = axis[side_index], axis[(side_index + 1) % len(axis)]
    length = _side_length(axis, side_index)
    horizontal = abs(b[0] - a[0]) > abs(b[1] - a[1])
    a_coord, b_coord = (a[0], b[0]) if horizontal else (a[1], b[1])
    t_lo = (world_lo - a_coord) / (b_coord - a_coord)
    t_hi = (world_hi - a_coord) / (b_coord - a_coord)
    t_lo, t_hi = sorted((t_lo, t_hi))
    base = _side_base_offset(axis, side_index)
    local_lo, local_hi = t_lo * length, t_hi * length
    return base + local_lo, local_hi - local_lo


def _ext_axis(width: float, depth: float) -> list[list[float]]:
    return [[0.0, 0.0], [width, 0.0], [width, depth], [0.0, depth]]


def _stair(stair_id: str) -> dict:
    return {
        "id": stair_id,
        "start": list(STAIR_START),
        "direction_deg": STAIR_DIRECTION_DEG,
        **STAIR_PARAMS,
    }


def ground_floor_spec(width: float, depth: float) -> dict:
    axis = _ext_axis(width, depth)
    front_door_offset, front_door_width = _opening_on_side(
        axis, 2, width / 2.0 - 450.0, width / 2.0 + 450.0
    )
    living_window_offset, living_window_width = _opening_on_side(axis, 2, 4700.0, 6300.0)
    kitchen_window_offset, kitchen_window_width = _opening_on_side(axis, 0, 3850.0, 5050.0)
    bath_window_offset, bath_window_width = _opening_on_side(axis, 1, 1800.0, 2400.0)

    return {
        "sheet": {
            "intent": "Residential house - ground floor (test fixture, not an approved design)",
            "sheet_size": "A3",
            "scale": 50,
        },
        "requires_stair": True,
        "walls": [
            {
                "id": "EXT",
                "axis": axis,
                "thickness": EXT_THICKNESS,
                "justification": "left",
                "material": "brick",
                "closed": True,
            },
            {
                "id": "P1",
                "axis": [[0.0, P1_Y], [width, P1_Y]],
                "thickness": PARTITION_THICKNESS,
                "material": "brick",
            },
            {
                "id": "P2",
                "axis": [[COL_X1, 0.0], [COL_X1, P1_Y]],
                "thickness": PARTITION_THICKNESS,
                "material": "brick",
            },
            {
                "id": "P3",
                "axis": [[COL_X2, 0.0], [COL_X2, P1_Y]],
                "thickness": PARTITION_THICKNESS,
                "material": "brick",
            },
        ],
        "openings": [
            {
                "id": "D-FRONT",
                "wall": "EXT",
                "kind": "door",
                "offset": front_door_offset,
                "width": front_door_width,
                "tag": "D01",
            },
            {
                "id": "D-STAIR",
                "wall": "P1",
                "kind": "door",
                "offset": 600,
                "width": 900,
                "tag": "D02",
            },
            {
                "id": "D-KITCH",
                "wall": "P1",
                "kind": "door",
                "offset": 3000,
                "width": 900,
                "tag": "D03",
            },
            {
                "id": "D-BATH",
                "wall": "P1",
                "kind": "door",
                "offset": 5600,
                "width": 900,
                "tag": "D04",
            },
            {
                "id": "W-LIVING",
                "wall": "EXT",
                "kind": "window",
                "offset": living_window_offset,
                "width": living_window_width,
                "sill": 900,
                "height": 1200,
                "tag": "W01",
            },
            {
                "id": "W-KITCH",
                "wall": "EXT",
                "kind": "window",
                "offset": kitchen_window_offset,
                "width": kitchen_window_width,
                "sill": 1000,
                "height": 1200,
                "tag": "W02",
            },
            {
                "id": "W-BATH",
                "wall": "EXT",
                "kind": "window",
                "offset": bath_window_offset,
                "width": bath_window_width,
                "sill": 1500,
                "height": 600,
                "tag": "W03",
            },
        ],
        "stairs": [_stair("ST-G")],
        "rooms": [
            {
                "id": "LIVING",
                "name": "LIVING / DINING",
                "number": "G01",
                "at": [width / 2.0, P1_Y + (depth - P1_Y) / 2.0],
            },
            {"id": "STAIRHALL-G", "name": "STAIR HALL", "number": "G02", "at": [1350.0, 2100.0]},
            {"id": "KITCHEN", "name": "KITCHEN", "number": "G03", "at": [3950.0, 2100.0]},
            {"id": "BATH-G", "name": "BATHROOM", "number": "G04", "at": [6250.0, 2100.0]},
        ],
        "chains": {"sides": ["bottom", "left"]},
        "schedules": [
            {"kind": "doors", "at": [width + 1200.0, depth]},
            {"kind": "windows", "at": [width + 1200.0, depth - 2500.0]},
            {"kind": "rooms", "at": [width + 1200.0, depth - 5000.0]},
        ],
    }


def first_floor_spec(width: float, depth: float) -> dict:
    axis = _ext_axis(width, depth)
    bed1_window = _opening_on_side(axis, 3, depth - 2700.0, depth - 900.0)  # west wall
    bed2_window = _opening_on_side(axis, 2, width - 4400.0, width - 3200.0)  # north wall
    bed3_window = _opening_on_side(axis, 2, 5700.0, 6900.0)  # north wall
    bed4_window = _opening_on_side(axis, 0, 3850.0, 5050.0)  # south wall
    bath1_window = _opening_on_side(axis, 1, 600.0, 1200.0)  # east wall
    bath2_window = _opening_on_side(axis, 1, 2600.0, 3200.0)  # east wall

    return {
        "sheet": {
            "intent": "Residential house - first floor (test fixture, not an approved design)",
            "sheet_size": "A3",
            "scale": 50,
        },
        "walls": [
            {
                "id": "EXT",
                "axis": axis,
                "thickness": EXT_THICKNESS,
                "justification": "left",
                "material": "brick",
                "closed": True,
            },
            {
                "id": "FP1",
                "axis": [[0.0, P1_Y], [width, P1_Y]],
                "thickness": PARTITION_THICKNESS,
                "material": "brick",
            },
            {
                "id": "FP2",
                "axis": [[COL_X1, 0.0], [COL_X1, depth]],
                "thickness": PARTITION_THICKNESS,
                "material": "brick",
            },
            {
                "id": "FP3",
                "axis": [[COL_X2, 0.0], [COL_X2, depth]],
                "thickness": PARTITION_THICKNESS,
                "material": "brick",
            },
            {
                "id": "FP4",
                "axis": [[COL_X2, 2100.0], [width, 2100.0]],
                "thickness": PARTITION_THICKNESS,
                "material": "brick",
            },
        ],
        "openings": [
            {"id": "D1", "wall": "FP1", "kind": "door", "offset": 600, "width": 900, "tag": "D05"},
            {"id": "D2", "wall": "FP2", "kind": "door", "offset": 6500, "width": 900, "tag": "D06"},
            {"id": "D3", "wall": "FP3", "kind": "door", "offset": 6500, "width": 900, "tag": "D07"},
            {"id": "D4", "wall": "FP2", "kind": "door", "offset": 1800, "width": 900, "tag": "D08"},
            {"id": "D5", "wall": "FP3", "kind": "door", "offset": 600, "width": 900, "tag": "D09"},
            {"id": "D6", "wall": "FP4", "kind": "door", "offset": 700, "width": 800, "tag": "D10"},
            {
                "id": "W-BED1",
                "wall": "EXT",
                "kind": "window",
                "offset": bed1_window[0],
                "width": bed1_window[1],
                "sill": 900,
                "height": 1200,
                "tag": "W04",
            },
            {
                "id": "W-BED2",
                "wall": "EXT",
                "kind": "window",
                "offset": bed2_window[0],
                "width": bed2_window[1],
                "sill": 900,
                "height": 1200,
                "tag": "W05",
            },
            {
                "id": "W-BED3",
                "wall": "EXT",
                "kind": "window",
                "offset": bed3_window[0],
                "width": bed3_window[1],
                "sill": 900,
                "height": 1200,
                "tag": "W06",
            },
            {
                "id": "W-BED4",
                "wall": "EXT",
                "kind": "window",
                "offset": bed4_window[0],
                "width": bed4_window[1],
                "sill": 900,
                "height": 1200,
                "tag": "W07",
            },
            {
                "id": "W-BATH1",
                "wall": "EXT",
                "kind": "window",
                "offset": bath1_window[0],
                "width": bath1_window[1],
                "sill": 1500,
                "height": 600,
                "tag": "W08",
            },
            {
                "id": "W-BATH2",
                "wall": "EXT",
                "kind": "window",
                "offset": bath2_window[0],
                "width": bath2_window[1],
                "sill": 1500,
                "height": 600,
                "tag": "W09",
            },
        ],
        "stairs": [_stair("ST-F")],
        "rooms": [
            {"id": "STAIRHALL-F", "name": "STAIR LANDING", "number": "F01", "at": [1350.0, 2100.0]},
            {"id": "BED4", "name": "BEDROOM 4", "number": "F02", "at": [3950.0, 2100.0]},
            {"id": "BATH1-F", "name": "BATHROOM 1", "number": "F03", "at": [6250.0, 1050.0]},
            {"id": "BATH2-F", "name": "BATHROOM 2", "number": "F04", "at": [6250.0, 3150.0]},
            {"id": "BED1", "name": "BEDROOM 1", "number": "F05", "at": [1350.0, 6976.8]},
            {"id": "BED2", "name": "BEDROOM 2", "number": "F06", "at": [3950.0, 6976.8]},
            {"id": "BED3", "name": "BEDROOM 3", "number": "F07", "at": [6250.0, 6976.8]},
        ],
        "chains": {"sides": ["bottom", "left"]},
        "schedules": [
            {"kind": "doors", "at": [width + 1200.0, depth]},
            {"kind": "windows", "at": [width + 1200.0, depth - 2800.0]},
            {"kind": "rooms", "at": [width + 1200.0, depth - 7000.0]},
        ],
    }


def _inside_repository(folder: Path) -> bool:
    resolved = folder.resolve()
    return resolved == ROOT or ROOT in resolved.parents


def _parse(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="output folder (not inside this repository)")
    parser.add_argument(
        "--dry-run", action="store_true", help="validate and report only; draw nothing"
    )
    return parser.parse_args(argv)


async def _build(spec: dict, *, dry_run: bool, path: Path | None) -> dict:
    from engineering.arch.spec import draw_plan_from_spec

    if dry_run:
        from backends.ezdxf_backend import EzdxfBackend

        backend = EzdxfBackend()
        try:
            return await draw_plan_from_spec(backend, spec, dry_run=True)
        finally:
            pass

    from backends.ezdxf_backend import EzdxfBackend

    backend = EzdxfBackend()
    await backend.connect()
    await backend.drawing_new()
    result = await draw_plan_from_spec(backend, spec)
    if path is not None:
        await backend.drawing_save_as(str(path), fmt="dxf")
    await backend.disconnect()
    return result


def main(argv=None) -> int:
    args = _parse(argv)
    out = Path(args.out)
    if _inside_repository(out):
        print(
            f"refused: {out} is inside the repository ({ROOT}); a generated test drawing is "
            "not a repository asset. Pass --out outside it."
        )
        return REFUSED

    width, depth = _envelope()
    print(
        f"buildable envelope: {width:.1f} x {depth:.1f} mm ({width / 304.8:.2f} x {depth / 304.8:.2f} ft)"
    )

    specs = {
        "ground_floor": ground_floor_spec(width, depth),
        "first_floor": first_floor_spec(width, depth),
    }
    if not args.dry_run:
        out.mkdir(parents=True, exist_ok=True)

    report: dict = {}
    for name, spec in specs.items():
        path = None if args.dry_run else out / f"{name}.dxf"
        result = asyncio.run(_build(spec, dry_run=args.dry_run, path=path))
        report[name] = {
            "walls": result.get("walls"),
            "rooms": result.get("rooms"),
            "completeness": result.get("completeness"),
            "path": str(path) if path else None,
        }
        print(f"\n== {name} ==")
        print(json.dumps(result.get("completeness"), indent=2))
        if path:
            print(f"saved: {path}")

    if not args.dry_run:
        (out / "report.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
