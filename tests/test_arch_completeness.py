"""Rule-based completeness findings, and the spec-level `fixtures` / `dry_run` /
`grid` additions that carry them (`engineering/arch/completeness.py`).

Headless ezdxf against a real document, the same fixture as
``test_arch_spec.py``: the net floor areas there are reused here unchanged.
"""

from __future__ import annotations

import copy

import pytest

from engineering.arch.completeness import check, grid_misalignment
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
