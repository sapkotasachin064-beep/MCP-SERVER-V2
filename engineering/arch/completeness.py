"""Rule-based design-completeness checks over a plan document (track F, residential UX).

Distinct from ``spec.validate_spec``, which refuses a *broken* document
(bad geometry, an unknown material, a typed room area) before anything is
drawn: this module looks at a document that already passed that validation
and asks whether it reads as a *usable* plan - a door in every room, an
envelope with no leak, every room labelled, no duplicate tag. Nothing here
raises. Every finding is a dict ``{"severity": "error"|"warning", "rule",
"message", ...}``, meant to be read by the caller (a human, or the agent
driving ``arch_plan_from_spec`` on a person's behalf) and turned into a
question before the plan is drawn for real - ``arch_plan_from_spec(spec,
dry_run=True)`` runs these checks and draws nothing.

None of this is a building-code or egress check, the same way the stair
tool's Blondel relation is "a design rule, never a building code"
(CLAUDE.md): a room-needs-a-door or room-needs-a-window finding is a
heuristic over the geometry the spec describes, declared as one in its own
message, and it is never raised to an error that blocks drawing. The two
checks that *are* errors (``arch_missing_doors``, ``arch_envelope_gap``,
``arch_missing_rooms``) are errors because they are almost never
intentional in a residential plan, not because any standard requires them.

The room/door/window adjacency check reuses the existing wall engine
exactly as the live ``arch_room_unlabelled`` critique does, just before
anything is drawn instead of after: ``wall_geometry`` + ``room_segments`` +
``detect_rooms`` (``walls.py`` / ``rooms.py``) is pure and needs no backend,
so it runs the identical face-finder in memory. An opening's host wall and
offset give its midpoint; nudging that point to each side of the wall by
more than the wall's half-thickness and testing which face contains it
(``critique.point_in_loop``, also pure) finds which room(s) a door or window
serves, without guessing at a model no field in the document actually
carries.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from .critique import point_in_loop, wall_gaps
from .model import Opening, Room, Wall, room_from_dict, segment_of
from .rooms import DEFAULT_MIN_AREA, detect_rooms
from .symbols import grid_axes
from .walls import room_segments, wall_geometry

CHECKS: tuple[str, ...] = (
    "arch_missing_rooms",
    "arch_missing_doors",
    "arch_envelope_gap",
    "arch_unlabelled_face",
    "arch_room_no_door",
    "arch_room_no_window",
    "arch_duplicate_tag",
    "arch_fixture_outside_room",
    "arch_grid_misaligned",
)

#: How far past the wall's own half-thickness a probe point is nudged to land
#: inside the room the opening serves - a drafting margin of this check, not
#: a standard.
PROBE_CLEARANCE_MM = 150.0
#: Default coordination tolerance for arch_grid_misaligned - a wall axis
#: further than this from the nearest grid line in both x and y is flagged.
DEFAULT_GRID_TOLERANCE_MM = 75.0


def _issue(severity: str, rule: str, message: str, **data) -> dict:
    return {"severity": severity, "rule": rule, "message": message, **data}


def _opening_probe_points(wall: Wall, opening: Opening) -> tuple[tuple[float, float], ...]:
    """Two points just off the opening's midpoint, one into each side of its wall.

    Raises ``ValueError`` (never caught here - the caller already validated
    this opening against this wall through ``validate_openings``, so this is
    only reachable on a caller-constructed ``norm`` that skipped validation)
    when the midpoint does not land on the wall's axis.
    """
    mid = float(opening.offset) + float(opening.width) / 2.0
    index, along = segment_of(wall, mid)
    axis = [(float(p[0]), float(p[1])) for p in wall.axis]
    a, b = axis[index], axis[(index + 1) % len(axis)]
    length = math.dist(a, b)
    if length <= 1e-9:
        return ()
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    nx, ny = -uy, ux
    px, py = a[0] + ux * along, a[1] + uy * along
    d = float(wall.thickness) / 2.0 + PROBE_CLEARANCE_MM
    return ((px + nx * d, py + ny * d), (px - nx * d, py - ny * d))


def _room_faces(
    walls: Sequence[Wall], openings: Sequence[Opening], *, poche: bool
) -> tuple[dict, ...]:
    """Room faces purely in memory - the same finder ``arch_room_unlabelled`` reads
    off the drawing, run here before anything is drawn."""
    geometry = wall_geometry(walls, openings, poche=poche)
    return detect_rooms(room_segments(geometry))


def grid_misalignment(
    walls: Sequence[Wall], x_axes, y_axes, *, tol: float = DEFAULT_GRID_TOLERANCE_MM
) -> list[dict]:
    """Wall axis vertices that land on neither the nearest x nor the nearest y grid line.

    A coordination check only: it compares the plan's wall axes against grid
    positions the caller supplies (a structural grid this plan is meant to
    sit on), and never derives, sizes or verifies a structural member -
    CLAUDE.md's rule against inventing a structural design. ``x_axes`` /
    ``y_axes`` are the same shape ``arch_grid`` takes; refused the same way
    (``grid_axes``) when they are empty, non-finite or duplicated.
    """
    axes = grid_axes(x_axes, y_axes)
    xs = [a["position"] for a in axes["x"]]
    ys = [a["position"] for a in axes["y"]]
    out: list[dict] = []
    seen: set[tuple[str, float, float]] = set()
    for wall in walls:
        for point in wall.axis:
            x, y = float(point[0]), float(point[1])
            dx = min(abs(x - gx) for gx in xs)
            dy = min(abs(y - gy) for gy in ys)
            if dx <= tol or dy <= tol:
                continue
            key = (wall.id, round(x, 3), round(y, 3))
            if key in seen:
                continue
            seen.add(key)
            out.append(
                _issue(
                    "warning",
                    "arch_grid_misaligned",
                    f"Wall {wall.id} has an axis point at ({x:.0f}, {y:.0f}) that is "
                    f"{min(dx, dy):.0f} mm from the nearest grid line in both directions "
                    f"(tolerance {tol:g} mm); check it against the structural grid.",
                    wall=wall.id,
                    at=[x, y],
                    nearest_x_mm=round(dx, 1),
                    nearest_y_mm=round(dy, 1),
                )
            )
    return out


def check(norm: dict, *, grid: dict | None = None) -> list[dict]:
    """Every advisory finding over a document ``validate_spec`` already accepted.

    ``norm`` is exactly what ``validate_spec`` returns. ``grid``, when given,
    is ``{"x_axes": [...], "y_axes": [...], "tolerance": mm}`` and adds
    ``arch_grid_misaligned`` findings; it draws nothing and is unrelated to
    ``arch_grid`` (which draws the axis lines and bubbles).
    """
    walls: list[Wall] = norm["walls"]
    openings: list[Opening] = norm["openings"]
    poche: bool = norm["poche"]
    raw_rooms: list[dict] = norm["rooms"]
    fixtures: list[dict] = norm.get("fixtures") or []
    rooms: list[Room] = [room_from_dict(r, f"rooms[{i}]") for i, r in enumerate(raw_rooms)]

    issues: list[dict] = []

    doors = [o for o in openings if o.kind == "door"]
    if not doors:
        issues.append(
            _issue(
                "error",
                "arch_missing_doors",
                "The plan has no door anywhere: nothing connects it to the outside or "
                "between rooms. Add at least one opening with kind='door'.",
            )
        )

    for row in wall_gaps(walls):
        a, b = row["walls"]
        issues.append(
            _issue(
                "error",
                "arch_envelope_gap",
                f"Wall end {row['end']} stops {row['gap_mm']:g} mm short of wall "
                f"{row['other']} without joining it: the envelope leaks there.",
                walls=[a, b],
                gap_mm=row["gap_mm"],
                at=list(row["at"]),
            )
        )

    try:
        faces = _room_faces(walls, openings, poche=poche)
    except ValueError:
        faces = ()

    if walls and not rooms:
        issues.append(
            _issue(
                "error",
                "arch_missing_rooms",
                "The plan draws walls but names no room: ask for a name (and a point "
                "inside each enclosed space) before drawing, or the plan has no room "
                "schedule and no labelled floor area.",
            )
        )

    significant = [f for f in faces if f["area"] >= DEFAULT_MIN_AREA]
    for face in significant:
        if not any(point_in_loop(room.at, face["loop"]) for room in rooms):
            centroid = face.get("centroid") or face["loop"][0]
            issues.append(
                _issue(
                    "warning",
                    "arch_unlabelled_face",
                    f"A closed face of {float(face['area']) / 1.0e6:.2f} m² around "
                    f"({float(centroid[0]):.0f}, {float(centroid[1]):.0f}) carries no room "
                    "label.",
                    area_mm2=float(face["area"]),
                    centroid=[float(c) for c in centroid],
                )
            )

    by_wall = {wall.id: wall for wall in walls}
    served_doors: list[set[str]] = [set() for _ in faces]
    served_windows: list[set[str]] = [set() for _ in faces]
    for opening in openings:
        wall = by_wall.get(opening.wall)
        if wall is None:
            continue
        try:
            probes = _opening_probe_points(wall, opening)
        except ValueError:
            continue
        for i, face in enumerate(faces):
            if any(point_in_loop(p, face["loop"]) for p in probes):
                (served_doors if opening.kind == "door" else served_windows)[i].add(opening.id)

    for room in rooms:
        for i, face in enumerate(faces):
            if not point_in_loop(room.at, face["loop"]):
                continue
            if not served_doors[i]:
                issues.append(
                    _issue(
                        "warning",
                        "arch_room_no_door",
                        f"Room {room.name!r} ({room.id}) has no door on any wall that "
                        "borders it; check whether it is reachable.",
                        room=room.id,
                    )
                )
            if not served_windows[i]:
                issues.append(
                    _issue(
                        "warning",
                        "arch_room_no_window",
                        f"Room {room.name!r} ({room.id}) has no window on any wall that "
                        "borders it; a heuristic for daylight/ventilation, not a code "
                        "check.",
                        room=room.id,
                    )
                )
            break

    seen_tags: dict[str, list[str]] = {}
    for opening in openings:
        if opening.tag:
            seen_tags.setdefault(opening.tag, []).append(opening.id)
    for tag, ids in sorted(seen_tags.items()):
        if len(ids) > 1:
            issues.append(
                _issue(
                    "warning",
                    "arch_duplicate_tag",
                    f"Tag {tag!r} is used by {len(ids)} openings ({', '.join(ids)}); the "
                    "door/window schedule will show it more than once.",
                    tag=tag,
                    openings=ids,
                )
            )

    for fixture in fixtures:
        if faces and not any(point_in_loop(fixture["at"], f["loop"]) for f in faces):
            issues.append(
                _issue(
                    "warning",
                    "arch_fixture_outside_room",
                    f"Fixture {fixture['id']!r} ({fixture['name']}) at "
                    f"({fixture['at'][0]:.0f}, {fixture['at'][1]:.0f}) does not land inside "
                    "any detected room face.",
                    fixture=fixture["id"],
                    at=list(fixture["at"]),
                )
            )

    if grid is not None:
        x_axes = grid.get("x_axes")
        y_axes = grid.get("y_axes")
        tol = grid.get("tolerance", DEFAULT_GRID_TOLERANCE_MM)
        issues.extend(grid_misalignment(walls, x_axes, y_axes, tol=float(tol)))

    return issues
