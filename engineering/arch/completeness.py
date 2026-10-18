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

from .critique import body_distance, point_in_loop, wall_gaps
from .model import Opening, Room, Wall, axis_segments, room_from_dict, segment_of
from .rooms import DEFAULT_MIN_AREA, detect_rooms
from .symbols import grid_axes, grid_intersections
from .walls import face_offsets, room_segments, wall_geometry, wall_segments

CHECKS: tuple[str, ...] = (
    "arch_missing_rooms",
    "arch_missing_doors",
    "arch_missing_stair",
    "arch_envelope_gap",
    "arch_duplicate_wall",
    "arch_unlabelled_face",
    "arch_room_no_door",
    "arch_room_no_window",
    "arch_room_unreachable",
    "arch_opening_swing_clash",
    "arch_duplicate_tag",
    "arch_duplicate_room_number",
    "arch_fixture_outside_room",
    "arch_no_dimension_chains",
    "arch_sheet_intent_default",
    "arch_grid_misaligned",
    "arch_column_clash",
)

#: Severities, in the order Phase 4 of the residential-UX brief distinguishes
#: them: ``error`` blocks nothing by itself (nothing in this module raises)
#: but names a defect almost never intentional in a residential plan;
#: ``warning`` is a heuristic worth a human's attention; ``info`` is an
#: assumption or a recommendation, never a defect.
SEVERITIES: tuple[str, ...] = ("error", "warning", "info")

#: Two wall axis segments collinear and overlapping by more than this are a
#: duplicate wall, not two walls that happen to touch end-to-end.
DUPLICATE_WALL_OVERLAP_MM = 50.0
#: How far a point may sit off a line and still be "on" it, for the duplicate-
#: wall and candidate-column checks - a drafting tolerance, not a standard.
COLLINEAR_TOL_MM = 5.0

#: How far past the wall's own half-thickness a probe point is nudged to land
#: inside the room the opening serves - a drafting margin of this check, not
#: a standard.
PROBE_CLEARANCE_MM = 150.0
#: Default coordination tolerance for arch_grid_misaligned - a wall axis
#: further than this from the nearest grid line in both x and y is flagged.
DEFAULT_GRID_TOLERANCE_MM = 75.0


def _issue(
    severity: str,
    rule: str,
    message: str,
    *,
    resolved: bool = False,
    manual_review_required: bool = True,
    **data,
) -> dict:
    """One finding: ``{severity, rule, message, resolved, manual_review_required, ...}``.

    ``resolved`` is always ``False`` from this module - it only reports,
    never corrects (Phase 6's human-review checkpoint: a caller, not this
    validator, decides whether and how to fix a finding). ``data`` carries
    whatever entity ids this finding names (``wall``, ``room``, ``openings``,
    ...) as the closest thing to an entity handle before anything is drawn -
    the post-draw ``critique`` focuses carry real handles instead.
    """
    return {
        "severity": severity,
        "rule": rule,
        "message": message,
        "resolved": resolved,
        "manual_review_required": manual_review_required,
        **data,
    }


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


def _band(wall: Wall) -> tuple[float, float]:
    """Where the two faces lie along the axis's left normal, low to high.

    Mirrors ``critique._band`` exactly (duplicated rather than imported across
    a module-private name): this module runs before anything is drawn, that
    one after, and both need the same four-line rule.
    """
    t = float(wall.thickness)
    if wall.justification == "left":
        return (0.0, t)
    if wall.justification == "right":
        return (-t, 0.0)
    return (-t / 2.0, t / 2.0)


def _line_overlap(a1, a2, b1, b2, tol: float) -> float:
    """Collinear overlap length of segment ``a`` on segment ``b``'s line, 0 if not collinear."""
    bx, by = b2[0] - b1[0], b2[1] - b1[1]
    length = math.hypot(bx, by)
    if length <= 1e-9:
        return 0.0
    ux, uy = bx / length, by / length
    nx, ny = -uy, ux

    def perp(p) -> float:
        return abs((p[0] - b1[0]) * nx + (p[1] - b1[1]) * ny)

    if perp(a1) > tol or perp(a2) > tol:
        return 0.0

    def proj(p) -> float:
        return (p[0] - b1[0]) * ux + (p[1] - b1[1]) * uy

    lo_a, hi_a = sorted((proj(a1), proj(a2)))
    lo, hi = max(0.0, lo_a), min(length, hi_a)
    return max(0.0, hi - lo)


def duplicate_walls(
    walls: Sequence[Wall],
    *,
    overlap: float = DUPLICATE_WALL_OVERLAP_MM,
    tol: float = COLLINEAR_TOL_MM,
) -> list[dict]:
    """Two different walls whose axes run collinear and overlap by more than ``overlap``.

    A real duplicate - the same physical wall described twice - not two walls
    that merely meet end to end (a shared end is a junction the wall engine
    resolves; a short miss is ``arch_envelope_gap``). One row per pair:
    ``{"walls": (a, b), "overlap_mm", "at"}``.

    In the ordinary ``arch_plan_from_spec`` pipeline, ``validate_spec`` calls
    the wall engine before a document ever reaches ``check()``, and the wall
    engine already refuses most overlapping walls itself (as a 0-degree
    junction it cannot resolve) - a blunter, earlier refusal than this one.
    This check still runs (and ``check()`` still reports it) for a ``norm``
    assembled another way, without going through the wall engine first.
    """
    out: list[dict] = []
    for i, wa in enumerate(walls):
        for wb in walls[i + 1 :]:
            best = 0.0
            best_mid: tuple[float, float] | None = None
            for a1, a2 in axis_segments(wa):
                for b1, b2 in axis_segments(wb):
                    span = _line_overlap(a1, a2, b1, b2, tol)
                    if span > best:
                        best = span
                        best_mid = ((a1[0] + a2[0]) / 2.0, (a1[1] + a2[1]) / 2.0)
            if best > overlap and best_mid is not None:
                out.append(
                    {
                        "walls": tuple(sorted((wa.id, wb.id))),
                        "overlap_mm": round(best, 1),
                        "at": [best_mid[0], best_mid[1]],
                    }
                )
    return out


def _swing_sector(wall: Wall, opening: Opening):
    """``(hinge, radius, a0, a1)`` of a door's swing arc, sweeping CCW a0 -> a1; ``None``
    for a window or a zero-length host segment.

    Mirrors ``openings.opening_prims``'s hinge/angle math (duplicated, not
    imported: that function builds drawable ``Prim`` objects this check does
    not need) over the same wall/opening numbers, so the arc checked here is
    the arc actually drawn.
    """
    if opening.kind != "door":
        return None
    width = float(opening.width)
    index, along = segment_of(wall, float(opening.offset))
    (ax, ay), (bx, by) = wall_segments(wall)[index]
    length = math.hypot(bx - ax, by - ay)
    if length <= 1e-9:
        return None
    u = ((bx - ax) / length, (by - ay) / length)
    n = (-u[1], u[0])
    left, right = face_offsets(wall)

    def at(s: float, offset: float) -> tuple[float, float]:
        return (ax + u[0] * s + n[0] * offset, ay + u[1] * s + n[1] * offset)

    s0, s1 = along, along + width
    side = 1.0 if opening.swing == "in" else -1.0
    face = left if side > 0 else right
    toward = side if opening.hand == "left" else -side
    hinge_s, free_s = (s1, s0) if toward > 0 else (s0, s1)
    hinge = at(hinge_s, face)
    closed = at(free_s, face)
    opened = (hinge[0] + n[0] * side * width, hinge[1] + n[1] * side * width)

    def deg(v: tuple[float, float]) -> float:
        return math.degrees(math.atan2(v[1], v[0])) % 360.0

    a_closed = deg((closed[0] - hinge[0], closed[1] - hinge[1]))
    a_open = deg((opened[0] - hinge[0], opened[1] - hinge[1]))
    if abs(((a_open - a_closed) % 360.0) - 90.0) < 1e-6:
        return hinge, width, a_closed, a_open
    return hinge, width, a_open, a_closed


def opening_swing_clashes(
    walls: Sequence[Wall], openings: Sequence[Opening], *, samples: int = 7
) -> list[dict]:
    """A door's open swing sweeping into a wall other than the one that hosts it.

    Samples points around the swing arc (radius = the leaf's width) and tests
    each against every other wall's body (``critique.body_distance``); any
    sample inside another wall's body is a clash. Sampling, not an exact
    sector-vs-polygon test: it can miss a clash that falls entirely between
    two samples, and never reports one that is not there. One row per
    opening: ``{"opening", "wall", "clashes": [other wall ids], "at"}``.
    """
    by_wall = {wall.id: wall for wall in walls}
    out: list[dict] = []
    for opening in openings:
        wall = by_wall.get(opening.wall)
        if wall is None:
            continue
        sector = _swing_sector(wall, opening)
        if sector is None:
            continue
        hinge, radius, a0, a1 = sector
        sweep = (a1 - a0) % 360.0
        points = [
            (
                hinge[0] + radius * math.cos(math.radians(a0 + sweep * t / (samples - 1))),
                hinge[1] + radius * math.sin(math.radians(a0 + sweep * t / (samples - 1))),
            )
            for t in range(samples)
        ]
        hit_walls: set[str] = set()
        for other in walls:
            if other.id == wall.id:
                continue
            band = _band(other)
            for a, b in axis_segments(other):
                if any(body_distance(p, a, b, band) <= 1e-6 for p in points):
                    hit_walls.add(other.id)
                    break
        if hit_walls:
            out.append(
                {
                    "opening": opening.id,
                    "wall": wall.id,
                    "clashes": sorted(hit_walls),
                    "at": [hinge[0], hinge[1]],
                }
            )
    return out


def column_clashes(
    walls: Sequence[Wall],
    openings: Sequence[Opening],
    x_axes,
    y_axes,
    *,
    labels=None,
    tol: float = COLLINEAR_TOL_MM,
) -> list[dict]:
    """A candidate column (a structural grid intersection) inside a door/window's clear span.

    For each grid intersection, every wall whose axis passes within ``tol`` of
    it is found; when the point's distance along that wall's axis falls
    inside an opening's ``[offset, offset + width]`` span, the column would
    stand in the opening. Coordination only: it draws nothing and sizes no
    column (CLAUDE.md's rule against inventing a structural design).
    """
    intersections = grid_intersections(x_axes, y_axes, labels=labels)
    out: list[dict] = []
    for item in intersections:
        px, py = item["at"]
        for wall in walls:
            run = 0.0
            hit_run: float | None = None
            for a, b in axis_segments(wall):
                length = math.dist(a, b)
                if length <= 1e-9:
                    continue
                ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
                nx, ny = -uy, ux
                dx, dy = px - a[0], py - a[1]
                along = dx * ux + dy * uy
                across = dx * nx + dy * ny
                if -tol <= along <= length + tol and abs(across) <= tol:
                    hit_run = run + max(0.0, min(along, length))
                    break
                run += length
            if hit_run is None:
                continue
            for opening in openings:
                if opening.wall != wall.id:
                    continue
                lo = float(opening.offset) - tol
                hi = float(opening.offset) + float(opening.width) + tol
                if lo <= hit_run <= hi:
                    out.append(
                        {
                            "label": item["label"],
                            "at": [px, py],
                            "wall": wall.id,
                            "opening": opening.id,
                        }
                    )
    return out


def check(norm: dict, *, grid: dict | None = None) -> list[dict]:
    """Every advisory finding over a document ``validate_spec`` already accepted.

    ``norm`` is exactly what ``validate_spec`` returns. ``grid``, when given,
    is ``{"x_axes": [...], "y_axes": [...], "tolerance": mm, "columns": bool}``:
    it adds ``arch_grid_misaligned`` findings, and with ``columns: True`` also
    ``arch_column_clash`` findings for a grid intersection landing inside a
    door or window's clear span. It draws nothing and is unrelated to
    ``arch_grid`` (which draws the axis lines, bubbles and - with its own
    ``columns=True`` - the candidate-column markers).
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

    if norm.get("requires_stair") and not norm.get("stairs"):
        issues.append(
            _issue(
                "error",
                "arch_missing_stair",
                "requires_stair is true but the plan draws no stair. Add a stairs[] entry, "
                "or set requires_stair=false if this floor genuinely has none.",
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

    for row in duplicate_walls(walls):
        a, b = row["walls"]
        issues.append(
            _issue(
                "error",
                "arch_duplicate_wall",
                f"Walls {a} and {b} run collinear and overlap by {row['overlap_mm']:g} mm: "
                "the same physical wall may be described twice.",
                walls=[a, b],
                overlap_mm=row["overlap_mm"],
                at=row["at"],
            )
        )

    for row in opening_swing_clashes(walls, openings):
        issues.append(
            _issue(
                "warning",
                "arch_opening_swing_clash",
                f"Door {row['opening']}'s open swing reaches wall(s) "
                f"{', '.join(row['clashes'])}, other than its own host wall {row['wall']}; "
                "it may not open fully.",
                opening=row["opening"],
                wall=row["wall"],
                clashes=row["clashes"],
                at=row["at"],
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

    faces_for_door: dict[str, list[int]] = {}
    for i, face_set in enumerate(served_doors):
        for door_id in face_set:
            faces_for_door.setdefault(door_id, []).append(i)
    adjacency: dict[int, set[int]] = {i: set() for i in range(len(faces))}
    entries: set[int] = set()
    for idxs in faces_for_door.values():
        if len(idxs) == 1:
            entries.add(idxs[0])
        elif len(idxs) >= 2:
            for a_i in idxs:
                for b_i in idxs:
                    if a_i != b_i:
                        adjacency[a_i].add(b_i)
    reachable = set(entries)
    frontier = list(entries)
    while frontier:
        current = frontier.pop()
        for nxt in adjacency.get(current, ()):
            if nxt not in reachable:
                reachable.add(nxt)
                frontier.append(nxt)
    for room in rooms:
        for i, face in enumerate(faces):
            if not point_in_loop(room.at, face["loop"]):
                continue
            if i not in reachable:
                issues.append(
                    _issue(
                        "warning",
                        "arch_room_unreachable",
                        f"Room {room.name!r} ({room.id}) is not reachable from any exterior "
                        "door through the interior doors this plan draws; check the "
                        "circulation.",
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
                    manual_review_required=False,
                )
            )

    seen_numbers: dict[str, list[str]] = {}
    for room in rooms:
        if room.number:
            seen_numbers.setdefault(room.number, []).append(room.id)
    for number, ids in sorted(seen_numbers.items()):
        if len(ids) > 1:
            issues.append(
                _issue(
                    "warning",
                    "arch_duplicate_room_number",
                    f"Room number {number!r} is used by {len(ids)} rooms ({', '.join(ids)}); "
                    "the room schedule will show it more than once.",
                    number=number,
                    rooms=ids,
                    manual_review_required=False,
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

    if norm.get("chains") is None:
        issues.append(
            _issue(
                "info",
                "arch_no_dimension_chains",
                "No exterior dimension chain was requested (spec.chains is absent). "
                "arch_plan_from_spec(chains={'sides': [...]}) adds overall, wall and "
                "opening dimensions per facade.",
                manual_review_required=False,
            )
        )

    if norm.get("sheet", {}).get("intent") == "architectural plan":
        issues.append(
            _issue(
                "info",
                "arch_sheet_intent_default",
                'sheet.intent was not given; the default "architectural plan" was used. '
                "Name the drawing's actual intent for the title block and drawing_plan record.",
                manual_review_required=False,
            )
        )

    if grid is not None:
        x_axes = grid.get("x_axes")
        y_axes = grid.get("y_axes")
        tol = grid.get("tolerance", DEFAULT_GRID_TOLERANCE_MM)
        issues.extend(grid_misalignment(walls, x_axes, y_axes, tol=float(tol)))
        if grid.get("columns"):
            for row in column_clashes(walls, openings, x_axes, y_axes):
                issues.append(
                    _issue(
                        "warning",
                        "arch_column_clash",
                        f"Candidate column {row['label']} at ({row['at'][0]:.0f}, "
                        f"{row['at'][1]:.0f}) falls inside opening {row['opening']} on wall "
                        f"{row['wall']}'s clear span.",
                        label=row["label"],
                        at=row["at"],
                        wall=row["wall"],
                        opening=row["opening"],
                    )
                )

    return issues
