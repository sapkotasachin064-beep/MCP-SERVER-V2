"""Rule-based completeness findings, and the spec-level `fixtures` / `dry_run` /
`grid` additions that carry them (`engineering/arch/completeness.py`).

Headless ezdxf against a real document, the same fixture as
``test_arch_spec.py``: the net floor areas there are reused here unchanged.
"""

from __future__ import annotations

import copy

import pytest

from engineering.arch.completeness import (
    check,
    column_clashes,
    duplicate_walls,
    grid_misalignment,
    opening_swing_clashes,
)
from engineering.arch.model import Opening, Wall
from engineering.arch.spec import EXAMPLE_SPEC, draw_plan_from_spec, validate_spec


def _spec(**over) -> dict:
    spec = copy.deepcopy(EXAMPLE_SPEC)
    spec.update(over)
    return spec


def _rule_set(issues: list[dict]) -> set[str]:
    return {i["rule"] for i in issues}


async def _count(backend) -> int:
    return len(await backend.entity_list(limit=5000))


# -- the pure checker, over the example plan -------------------------------------


def test_the_example_plan_is_complete_by_this_checker():
    """Both EXAMPLE_SPEC rooms have a door and a window on their own bounding
    walls, the envelope is closed, every face is labelled, no tag repeats."""
    norm = validate_spec(EXAMPLE_SPEC)
    issues = check(norm)
    assert issues == []


def test_no_doors_anywhere_is_an_error():
    spec = _spec(openings=[o for o in EXAMPLE_SPEC["openings"] if o["kind"] != "door"])
    norm = validate_spec(spec)
    issues = check(norm)
    assert any(i["rule"] == "arch_missing_doors" and i["severity"] == "error" for i in issues)


def test_a_room_with_no_door_on_its_walls_is_flagged():
    # drop D2, the only door into HALL (D1 only serves LIVING)
    spec = _spec(openings=[o for o in EXAMPLE_SPEC["openings"] if o["id"] != "D2"])
    norm = validate_spec(spec)
    issues = check(norm)
    rows = [i for i in issues if i["rule"] == "arch_room_no_door"]
    assert [r["room"] for r in rows] == ["R2"]
    assert all(i["severity"] == "warning" for i in rows)


def test_a_room_with_no_window_on_its_walls_is_flagged():
    spec = _spec(openings=[o for o in EXAMPLE_SPEC["openings"] if o["id"] != "W2"])
    norm = validate_spec(spec)
    issues = check(norm)
    rows = [i for i in issues if i["rule"] == "arch_room_no_window"]
    assert [r["room"] for r in rows] == ["R2"]


def test_walls_with_no_room_named_is_an_error():
    spec = _spec(rooms=[])
    norm = validate_spec(spec)
    issues = check(norm)
    assert any(i["rule"] == "arch_missing_rooms" and i["severity"] == "error" for i in issues)
    # the faces are still there and still unlabelled - reported too, not swallowed
    assert any(i["rule"] == "arch_unlabelled_face" for i in issues)


def test_an_open_envelope_gap_is_an_error():
    # B's start sits 10 mm short of A's end: within wall_gaps' 50 mm gap
    # window but past its 1 mm join tolerance - a near miss, not a join.
    spec = {
        "walls": [
            {"id": "A", "axis": [[0, 0], [1000, 0]], "thickness": 100},
            {"id": "B", "axis": [[1010, 0], [1010, 1000]], "thickness": 100},
        ]
    }
    norm = validate_spec(spec)
    issues = check(norm)
    gaps = [i for i in issues if i["rule"] == "arch_envelope_gap"]
    assert gaps and gaps[0]["severity"] == "error"
    assert set(gaps[0]["walls"]) == {"A", "B"}


def test_a_repeated_tag_is_flagged():
    spec = _spec()
    spec["openings"][1]["tag"] = spec["openings"][0]["tag"] = "D1"
    norm = validate_spec(spec)
    issues = check(norm)
    rows = [i for i in issues if i["rule"] == "arch_duplicate_tag"]
    assert rows and rows[0]["tag"] == "D1" and set(rows[0]["openings"]) == {"D1", "D2"}


def test_a_fixture_outside_every_room_is_flagged():
    spec = _spec(fixtures=[{"id": "F1", "name": "double_bed", "at": [50000, 50000], "rotation": 0}])
    norm = validate_spec(spec)
    issues = check(norm)
    rows = [i for i in issues if i["rule"] == "arch_fixture_outside_room"]
    assert rows and rows[0]["fixture"] == "F1"


def test_a_fixture_inside_a_room_is_not_flagged():
    spec = _spec(fixtures=[{"id": "F1", "name": "double_bed", "at": [2500, 2000], "rotation": 0}])
    norm = validate_spec(spec)
    issues = check(norm)
    assert not [i for i in issues if i["rule"] == "arch_fixture_outside_room"]


# -- grid coordination -------------------------------------------------------------


def test_walls_on_the_grid_are_not_flagged():
    norm = validate_spec(EXAMPLE_SPEC)
    # EXT's axis vertices are exactly (0,0) (9000,0) (9000,6000) (0,6000)
    issues = grid_misalignment(norm["walls"], [0, 9000], [0, 6000], tol=10)
    assert issues == []


def test_a_wall_off_the_grid_is_flagged():
    norm = validate_spec(EXAMPLE_SPEC)
    # neither axis lines up with EXT's corner (0,0) in either direction
    issues = grid_misalignment(norm["walls"], [2000, 9000], [1000, 6000], tol=10)
    assert any(i["rule"] == "arch_grid_misaligned" and i["wall"] == "EXT" for i in issues)


def test_check_takes_grid_through_the_same_entry_point():
    norm = validate_spec(EXAMPLE_SPEC)
    issues = check(norm, grid={"x_axes": [2000, 9000], "y_axes": [1000, 6000], "tolerance": 10})
    assert any(i["rule"] == "arch_grid_misaligned" for i in issues)


def test_grid_misalignment_refuses_bad_axes_the_same_way_arch_grid_does():
    norm = validate_spec(EXAMPLE_SPEC)
    with pytest.raises(ValueError, match="a grid needs at least one axis"):
        grid_misalignment(norm["walls"], [], [0, 6000])


# -- fixtures through the spec document --------------------------------------------


def test_an_unknown_fixture_name_is_refused_by_path_with_the_nearest_names():
    spec = _spec(fixtures=[{"id": "F1", "name": "doubel_bed", "at": [2500, 2000]}])
    with pytest.raises(ValueError, match=r"^fixtures\[0\]\.name: .*nearest: double_bed"):
        validate_spec(spec)


def test_two_fixtures_sharing_an_id_are_refused():
    spec = _spec(
        fixtures=[
            {"id": "F1", "name": "double_bed", "at": [2500, 2000]},
            {"id": "F1", "name": "wardrobe", "at": [2800, 2000]},
        ]
    )
    with pytest.raises(ValueError, match=r"^fixtures\[1\]\.id: 'F1' is used twice"):
        validate_spec(spec)


@pytest.mark.asyncio
async def test_fixtures_are_drawn_inside_the_same_transaction(backend):
    spec = _spec(fixtures=[{"id": "F1", "name": "double_bed", "at": [2500, 2000], "rotation": 90}])
    result = await draw_plan_from_spec(backend, spec)
    assert len(result["fixtures"]) == 1
    assert result["fixtures"][0]["item"] == "double_bed"
    assert result["completeness"] == []
    assert await _count(backend) > 0


@pytest.mark.asyncio
async def test_a_bad_fixture_rolls_the_whole_plan_back(backend):
    spec = _spec(fixtures=[{"id": "F1", "name": "not_a_real_item", "at": [2500, 2000]}])
    with pytest.raises(ValueError, match=r"^fixtures\[0\]\.name: "):
        await draw_plan_from_spec(backend, spec)
    assert await _count(backend) == 0


# -- dry_run: validate and check, touch nothing ------------------------------------


@pytest.mark.asyncio
async def test_dry_run_draws_nothing_and_reports_completeness(backend):
    spec = _spec(openings=[o for o in EXAMPLE_SPEC["openings"] if o["kind"] != "door"])
    result = await draw_plan_from_spec(backend, spec, dry_run=True)
    assert result["dry_run"] is True
    assert result["walls"] == ["EXT", "INT"]
    assert any(i["rule"] == "arch_missing_doors" for i in result["completeness"])
    assert await _count(backend) == 0
    assert backend.get_plan_spec() is None, "dry_run must not even open the plan spec"


@pytest.mark.asyncio
async def test_dry_run_still_refuses_a_broken_document_by_path(backend):
    with pytest.raises(ValueError, match=r"^walls\[1\]\.thickness: must be greater than zero"):
        spec = _spec()
        spec["walls"][1]["thickness"] = -100
        await draw_plan_from_spec(backend, spec, dry_run=True)
    assert await _count(backend) == 0


@pytest.mark.asyncio
async def test_a_real_run_carries_the_same_completeness_list(backend):
    result = await draw_plan_from_spec(backend, EXAMPLE_SPEC)
    assert result["completeness"] == []


# -- the registered tool ------------------------------------------------------------


# -- duplicate / overlapping walls ---------------------------------------------


def test_duplicate_overlapping_walls_are_flagged():
    a = Wall(id="A", axis=((0, 0), (3000, 0)), thickness=200)
    b = Wall(id="B", axis=((500, 0), (2500, 0)), thickness=200)
    rows = duplicate_walls([a, b])
    assert rows and set(rows[0]["walls"]) == {"A", "B"}
    assert rows[0]["overlap_mm"] == pytest.approx(2000.0, abs=1.0)


def test_walls_meeting_end_to_end_are_not_duplicates():
    a = Wall(id="A", axis=((0, 0), (1000, 0)), thickness=200)
    b = Wall(id="B", axis=((1000, 0), (1000, 1000)), thickness=200)
    assert duplicate_walls([a, b]) == []


def test_check_reports_duplicate_walls_given_a_norm_built_without_the_wall_engine():
    # validate_spec itself already refuses this through the wall engine's own
    # junction-angle check (a 0-degree "corner" cannot be resolved) before a
    # document ever reaches completeness.check - a blunter, earlier refusal.
    # arch_duplicate_wall exists for a `norm` assembled another way; built
    # directly here the same way `check()`'s other pure helpers are tested.
    a = Wall(id="A", axis=((0, 0), (3000, 0)), thickness=200)
    b = Wall(id="B", axis=((500, 0), (2500, 0)), thickness=200)
    norm = {
        "walls": [a, b],
        "openings": [],
        "poche": True,
        "rooms": [],
        "fixtures": [],
        "chains": ("bottom", "left"),
        "sheet": {"intent": "duplicate-wall probe"},
        "requires_stair": False,
    }
    issues = check(norm)
    assert any(i["rule"] == "arch_duplicate_wall" and i["severity"] == "error" for i in issues)


# -- door swing clashes -------------------------------------------------------------


def test_a_door_swinging_into_a_facing_wall_is_flagged():
    host = Wall(id="EXT1", axis=((0, 0), (2000, 0)), thickness=100)
    facing = Wall(id="FACING", axis=((0, 500), (2000, 500)), thickness=100)
    door = Opening(
        id="D1", wall="EXT1", kind="door", offset=500, width=900, swing="in", hand="left"
    )
    rows = opening_swing_clashes([host, facing], [door])
    assert rows and rows[0]["opening"] == "D1" and "FACING" in rows[0]["clashes"]


def test_a_door_with_room_to_swing_is_not_flagged():
    host = Wall(id="EXT1", axis=((0, 0), (2000, 0)), thickness=100)
    facing = Wall(id="FACING", axis=((0, 2000), (2000, 2000)), thickness=100)
    door = Opening(
        id="D1", wall="EXT1", kind="door", offset=500, width=900, swing="in", hand="left"
    )
    assert opening_swing_clashes([host, facing], [door]) == []


# -- candidate-column / opening coordination -----------------------------------------


def test_a_grid_intersection_inside_an_opening_span_is_flagged():
    wall = Wall(id="EXT", axis=((0, 0), (4000, 0)), thickness=200)
    door = Opening(id="D1", wall="EXT", kind="door", offset=1000, width=1000)
    rows = column_clashes([wall], [door], [1500], [0])
    assert rows and rows[0]["wall"] == "EXT" and rows[0]["opening"] == "D1"


def test_a_grid_intersection_clear_of_any_opening_is_not_flagged():
    wall = Wall(id="EXT", axis=((0, 0), (4000, 0)), thickness=200)
    door = Opening(id="D1", wall="EXT", kind="door", offset=1000, width=1000)
    assert column_clashes([wall], [door], [3800], [0]) == []


def test_check_adds_column_clashes_only_when_grid_columns_is_requested():
    spec = _spec()
    norm = validate_spec(spec)
    # D1 is EXT.offset=1000..2000; a grid line through it with columns=True clashes.
    with_columns = check(norm, grid={"x_axes": [1500], "y_axes": [0], "columns": True})
    without_columns = check(norm, grid={"x_axes": [1500], "y_axes": [0]})
    assert any(i["rule"] == "arch_column_clash" for i in with_columns)
    assert not any(i["rule"] == "arch_column_clash" for i in without_columns)


# -- requires_stair -----------------------------------------------------------------


def test_requires_stair_true_with_no_stair_is_an_error():
    spec = _spec(stairs=[], requires_stair=True)
    norm = validate_spec(spec)
    issues = check(norm)
    assert any(i["rule"] == "arch_missing_stair" and i["severity"] == "error" for i in issues)


def test_requires_stair_true_with_a_stair_is_not_flagged():
    norm = validate_spec(_spec(requires_stair=True))
    issues = check(norm)
    assert not any(i["rule"] == "arch_missing_stair" for i in issues)


def test_requires_stair_defaults_false_and_is_not_flagged():
    norm = validate_spec(_spec(stairs=[]))
    issues = check(norm)
    assert not any(i["rule"] == "arch_missing_stair" for i in issues)


# -- duplicate room numbers ----------------------------------------------------------


def test_a_repeated_room_number_is_flagged():
    spec = _spec()
    spec["rooms"][1]["number"] = spec["rooms"][0]["number"]
    norm = validate_spec(spec)
    issues = check(norm)
    rows = [i for i in issues if i["rule"] == "arch_duplicate_room_number"]
    assert rows and set(rows[0]["rooms"]) == {"R1", "R2"}
    assert rows[0]["manual_review_required"] is False


# -- circulation reachability ---------------------------------------------------------


def test_a_room_reachable_only_through_other_rooms_with_no_exterior_door_is_unreachable():
    spec = {
        "walls": [
            {
                "id": "EXT1",
                "axis": [[0, 0], [3000, 0], [3000, 3000], [0, 3000]],
                "thickness": 200,
                "closed": True,
            },
            {
                "id": "EXT2",
                "axis": [[10000, 0], [16000, 0], [16000, 3000], [10000, 3000]],
                "thickness": 200,
                "closed": True,
            },
            {"id": "INT2", "axis": [[13000, 0], [13000, 3000]], "thickness": 100},
        ],
        "openings": [
            {"id": "D1", "wall": "EXT1", "kind": "door", "offset": 1000, "width": 900},
            {"id": "D2", "wall": "INT2", "kind": "door", "offset": 1200, "width": 900},
        ],
        "rooms": [
            {"id": "R1", "name": "A", "number": "01", "at": [1500, 1500]},
            {"id": "R2", "name": "B", "number": "02", "at": [11500, 1500]},
            {"id": "R3", "name": "C", "number": "03", "at": [14500, 1500]},
        ],
    }
    norm = validate_spec(spec)
    issues = check(norm)
    unreachable = {i["room"] for i in issues if i["rule"] == "arch_room_unreachable"}
    assert unreachable == {"R2", "R3"}
    assert not any(i["rule"] == "arch_room_no_door" for i in issues)


# -- informational findings ----------------------------------------------------------


def test_missing_chains_is_an_info_recommendation():
    spec = _spec()
    del spec["chains"]
    norm = validate_spec(spec)
    issues = check(norm)
    rows = [i for i in issues if i["rule"] == "arch_no_dimension_chains"]
    assert rows and rows[0]["severity"] == "info" and rows[0]["manual_review_required"] is False


def test_default_sheet_intent_is_an_info_recommendation():
    spec = _spec(sheet={"sheet_size": "A3", "scale": 50})
    norm = validate_spec(spec)
    issues = check(norm)
    rows = [i for i in issues if i["rule"] == "arch_sheet_intent_default"]
    assert rows and rows[0]["severity"] == "info"


def test_every_issue_carries_resolved_and_manual_review_fields():
    spec = _spec(openings=[o for o in EXAMPLE_SPEC["openings"] if o["kind"] != "door"])
    norm = validate_spec(spec)
    issues = check(norm)
    assert issues
    for issue in issues:
        assert issue["resolved"] is False
        assert isinstance(issue["manual_review_required"], bool)


@pytest.mark.asyncio
async def test_the_tool_accepts_dry_run_and_grid():
    from fastmcp import Client

    import server

    async with Client(server.mcp) as client:
        await client.call_tool("drawing_new", {})
        result = (
            await client.call_tool(
                "arch_plan_from_spec",
                {
                    "spec": EXAMPLE_SPEC,
                    "dry_run": True,
                    "grid": {"x_axes": [2000, 9000], "y_axes": [1000, 6000], "tolerance": 10},
                },
            )
        ).structured_content
        assert result["dry_run"] is True
        assert any(i["rule"] == "arch_grid_misaligned" for i in result["completeness"])
