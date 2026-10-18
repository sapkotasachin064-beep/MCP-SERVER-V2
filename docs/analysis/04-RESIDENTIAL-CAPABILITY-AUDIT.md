# 04 — Residential Floor-Plan Capability Audit

Scope: `engineering/arch/*`, the 12 `arch_*` MCP tools (server.py), both backends.
Baseline: `pytest tests/test_arch*.py` — **515 passed, 0 failed** (ezdxf backend, pinned by
`tests/conftest.py`'s autouse fixture; no arch test touches live COM).

No code changed to produce this audit. Every row cites the file that backs the claim.

## A. Basic architectural geometry

| Requirement | Existing implementation | Source | Tests | Status | Proposed improvement | Verification |
|---|---|---|---|---|---|---|
| Closed external boundary | Wall engine resolves axis network into faces; `Wall.closed` flag | `engineering/arch/walls.py`, `model.py:44` | `test_arch_walls.py` | implemented | Add hard-error validator rule: outer ring must be one closed loop (today only a >50mm gap is *warned*, an open-ended boundary with no gap over 50mm is not refused) | new unit test: boundary with a 10mm visual gap |
| Consistent wall thickness | `Wall.thickness` per-wall field, freely variable | `model.py:44` | none direct | partial | Validator warning when exterior-tagged walls disagree on thickness | new test: two exterior walls, different thickness |
| Connected internal partitions | L/T/X junction resolution | `walls.py` | `test_arch_walls.py` | implemented | — | — |
| Correct wall intersections/corners | Junction geometry in wall engine | `walls.py` | `test_arch_walls.py` | implemented | — | — |
| No gaps / duplicate overlapping walls | Gaps: `arch_wall_gap` critique + `arch_envelope_gap` completeness (>`GAP_MM`=50mm). Duplicate/overlapping walls on the same axis: **no check anywhere** | `critique.py:51`, `completeness.py:174` | `test_arch_critique.py` | partial | New validator rule: two wall axes within tolerance occupying the same line | new test: duplicate wall stacked on another |
| Correct door/window openings in host wall | `Opening.wall/offset/width`, refused if `offset+width` exceeds wall length | `model.py:54`, `model.py` validation | `test_arch_model.py`, `test_arch_openings.py` | implemented | — | — |
| Doors not colliding with walls / obstructing circulation | `arch_opening_clash` catches two openings overlapping on *one wall*. Door swing arc vs. another wall/fixture, or vs. the circulation path: **not checked** | `critique.py:338` | `test_arch_critique.py` | partial | New validator warning: swing-arc vs. nearest wall/fixture point | new geometry test |
| Consistent geometry between connected rooms | Guaranteed by construction — one wall axis, both rooms read the same face from the planar-face finder | `faces.py` | `test_arch_faces.py`, `test_arch_rooms.py` | implemented | — | — |

## B. Rooms and circulation

| Requirement | Existing implementation | Source | Tests | Status | Proposed improvement | Verification |
|---|---|---|---|---|---|---|
| Room names + unique IDs | `Room.id/name/number` fields | `model.py:81` | `test_arch_model.py` | partial | **No duplicate id/number check exists** (only opening tags are checked for duplicates, `arch_duplicate_tag`). Add `arch_duplicate_room` rule | new test: two rooms, same number |
| Correct room boundaries | Planar-face finder (half-edge walk, holes nested); area read back via `polygon_area_perimeter` | `faces.py` | `test_arch_faces.py` | implemented | — | — |
| Room dimensions + calculated area | `label_room` writes measured `face.area` into the record; area is **never typed**, `room_from_dict` refuses a caller-supplied `area` | `rooms.py:398-498`, `model.py:289` | `test_arch_rooms.py` | implemented | — | — |
| Doors providing appropriate access | `arch_room_no_door` (completeness, warning) — probes jamb into each labelled room's face | `completeness.py:239` | `test_arch_completeness.py` | implemented (as a warning, by design) | — | — |
| Circulation connecting intended spaces | **Not modeled.** No corridor/circulation graph; only per-room door presence is checked, not reachability between rooms | — | — | missing | New completeness rule: graph reachability from every room to the entry door, via the door-adjacency already computed for `arch_room_no_door` | new test: a bedroom whose only door opens into another bedroom, not circulation |
| Kitchen location/usable layout | Catalogue has `kitchen_sink` block; no kitchen-specific layout rule (clearance, work-triangle) | `catalogue.py:326` | `test_arch_catalogue.py` | partial | Out of scope for a rule-based geometric validator without a program brief; flag as advisory only if pursued | — |
| Bathroom/toilet layout + fixture clearances | Catalogue has `wc`, `shower_tray`, `bathtub`; **no clearance check** between fixtures or fixture-to-wall | `catalogue.py:263,308,317` | `test_arch_catalogue.py` | partial | New completeness rule: minimum clear space in front of wc/shower (informational severity — no code citation) | new test: wc placed against a wall with <required clear space |
| Staircase geometry + storey connection | `arch_stair` draws one flight (`straight\|l\|u`); Blondel relation (`2R+G` 600-650mm) computed and **reported, never enforced**. **No storey/floor concept exists anywhere in the pack** — each `arch_plan_from_spec` call is one document; linking G/F and F/F stairs is entirely the caller's job | `stairs.py:50-56,140-164`, confirmed absent in `model.py`, `spec.py:51-62` | `test_arch_stairs.py` | partial (single-storey only) | Document the constraint; for this project, generate two independent plans (ground, first) and keep the stair's plan-position identical by convention — not a code change, a drawing-plan discipline | manual position cross-check between the two `arch_plan_from_spec` calls |
| No labels outside their room | `arch_unlabelled_face`/`arch_room_unlabelled` catch a face *without* a label; the reverse (a label point landing outside its own room's face) is not explicitly named as a rule, though `label_room` would simply attribute it to whatever face it lands in — effectively self-correcting, not a defect class | `completeness.py:204`, `critique.py` | `test_arch_critique.py` | implemented (by construction) | — | — |
| No room geometry outside the building envelope | **Not checked directly.** Rooms are faces of the wall network; a room can only exist if it's a face the walls form, so pure wall-topology makes an "outside" room impossible by construction *for drawn plans*. `arch_fixture_outside_room` exists for fixtures, not room faces vs. a stated envelope bound | `completeness.py:279` | `test_arch_completeness.py` | implemented (by construction) for rooms; n/a for a separate envelope bound | — | — |

## C. Structural coordination

| Requirement | Existing implementation | Source | Tests | Status | Proposed improvement | Verification |
|---|---|---|---|---|---|---|
| Structural grid representation | `arch_grid` draws CENTER-linetype axis lines + bubbles from caller-supplied positions only | `symbols.py:117-198` | `test_arch_symbols.py` | implemented | — | — |
| Candidate column locations at grid intersections | **Does not exist.** No column symbol, no intersection-point generator anywhere in the repo (`grep -i column` under `engineering/` hits only unrelated words — table columns, catalogue columns) | — | — | missing | Add a *non-dimensioned* marker block at each x/y grid-line intersection (pure geometry from caller-supplied axis positions — no size, no load, no material: respects "invents no structural design") | new test: 3×2 grid → 6 intersection markers at the right coordinates |
| Column/wall/door/circulation coordination | Not applicable — no columns exist yet | — | — | missing | Once intersection markers exist: completeness rule flagging a marker that lands inside a door/window opening's clear width | new test: grid line through a door opening |
| Ground/first floor structural coordination | Not applicable — no cross-document link exists (see storey gap above) | — | — | missing | Out of scope without a storey concept; flag as a manual cross-check step, not a code feature, per "do not invent structural adequacy" | manual: compare both floors' grid dumps |
| Detection of columns obstructing openings/space | See above — no columns to check yet | — | — | missing | Covered by the rule proposed two rows up | — |
| Detection of unsupported/inconsistent structural assumptions | `grid_misalignment` (completeness) flags a wall-axis vertex far from *caller-supplied* grid lines; it is explicitly documented as never deriving/sizing/verifying a structural member | `completeness.py:102-143` | `test_arch_completeness.py` | implemented (as a coordination *check*, not structural design) | — | — |

## D. Dimensions and annotations

| Requirement | Existing implementation | Source | Tests | Status | Proposed improvement | Verification |
|---|---|---|---|---|---|---|
| Overall building dimensions | `arch_dimension_chains` draws an `overall` row per chosen facade side | `dimension.py:39,129-208` | `test_arch_dimension.py` | implemented | — | — |
| Main wall/partition dimensions | Same tool's `walls` row (both faces of every wall meeting the facade) | `dimension.py:39` | `test_arch_dimension.py` | implemented | — | — |
| Room dimensions where required | Not a dedicated row; room *area* is in the label/schedule, not a room-by-room dimension chain | `rooms.py`, `schedule.py` | `test_arch_schedule.py` | partial | Could add a room-internal dimension pass if required; flagged as optional per CLAUDE.md ("manual dimensions only for special cases") | — |
| Door/window identifiers | `Opening.tag` field; `arch_duplicate_tag` checks uniqueness | `model.py:54`, `completeness.py:262` | `test_arch_model.py` | implemented | — | — |
| Consistent text height/annotation styles | Generic `textstyle_*`/`dimstyle_*` tools (SECTION 18), not arch-specific | `server.py` styles section | n/a (generic) | implemented (generic, reused) | — | — |
| Dimension styles and units | `dimstyle_*`, `drawing_settings` | `server.py` | generic tests | implemented (generic, reused) | — | — |
| Readable text placement | Label placement logic in `rooms.py`/`schedule.py`; no automatic overlap-avoidance beyond what's built in | `rooms.py` | `test_arch_rooms.py` | partial | Out of scope — generic `dim_overlap` critique focus (SECTION core) already exists for dimension text, not room labels | — |
| North arrow | `arch_symbol(kind="north_arrow")` | `symbols.py:40,204,338` | `test_arch_symbols.py` | implemented | — | — |
| Scale and drawing title | `drawing_plan(intent, scale, sheet)` (premium meta-tool), `titleblock_apply` | `backends/contracts/premium.py`, `server.py:9308` | generic tests | implemented (generic, reused) | — | — |
| Drawing number / revision | `revision_add` (SECTION 24, generic) | `server.py` | generic tests | implemented (generic, reused) | — | — |
| Door/window schedule | `arch_schedule(kind="doors"\|"windows")` → real TABLE from `ACADMCP_ARCH` records | `schedule.py:52,84,144` | `test_arch_schedule.py` | implemented | — | — |
| Room schedule | `arch_schedule(kind="rooms")` | `schedule.py:52,196` | `test_arch_schedule.py` | implemented | — | — |
| Correct layer assignment | `arch_catalogue_insert`/wall/opening draw paths target arch layer set; see layers.py | `engineering/arch/layers.py` | `test_arch_foundation.py` | implemented | — | — |

## E. Sheet and drawing quality

| Requirement | Existing implementation | Source | Tests | Status | Proposed improvement | Verification |
|---|---|---|---|---|---|---|
| Layer naming/lineweights | ISO 13567-style arch layer set, ISO 128 lineweights | `layers.py` | `test_arch_foundation.py` | implemented | — | — |
| Readable linework | Poche hatching by material (ISO 128-50 / JIS / AR-* conventions) | `materials.py` | `test_arch_foundation.py` | implemented | — | — |
| Plotting scale / page setup | `page_setup_apply`, `batch_plot` (generic, SECTION 19) | `server.py:7485,7561` | generic tests | implemented (generic, reused) | — | — |
| Title block | `titleblock_apply` (generic, ISO 7200, SECTION 24) | `server.py:9308` | generic tests | implemented (generic, reused) | — | — |
| No unintended off-sheet geometry | Not arch-specific; relies on generic `drawing_critique` | n/a | n/a | not verified for arch plans specifically | Run `drawing_critique(focus=None)` as a finalize gate (already a repo convention) | existing finalize workflow |
| No duplicate/stray entities | Generic `duplicate_entities` critique focus; arch-specific duplicate *walls* is the gap noted in section A | `backends/contracts` critique | generic tests | partial | Covered by section-A wall-duplicate rule once added | — |
| Correct drawing units | `drawing_settings` facade (SECTION 11/20); project requires ft input, mm internal — needs an explicit ft→mm conversion step at spec-build time, not a drawing-settings concern | `server.py` | generic tests | implemented (generic; conversion is caller's job) | Add a small ft→mm helper in the spec-building step (new code I write, not a backend change) | unit test on the conversion helper |
| Clear arch vs structural distinction | Arch layers vs. a (currently nonexistent) structural layer set — once grid/column markers exist they should get their own layer, e.g. `S-GRID` | `layers.py` | — | partial | Put new grid-intersection markers on a distinct, clearly structural layer | new test asserting marker layer name |
| Editable geometry, not flattened image | All `arch_*` tools emit real DXF/COM entities (LWPOLYLINE, INSERT, TABLE, TEXT) | throughout `engineering/arch/*` | all arch tests | implemented | — | — |
| Export validation | `drawing_export_dwg`/`drawing_export_pdf` generic; `batch_plot`'s `mediabox_mm` verifies page size from the file itself | `server.py` | generic tests | implemented (generic, reused) | — | — |

## Backend support

All 12 `arch_*` tools call only the **generic** `AutoCADBackend` contract (line/polyline/table/hatch
create, layer ops, block define/insert, xdata, transactions, dimension_linear) — there is no
`arch_*`-named contract method and no `arch_*` entry in `backends/capability.py`. Every generic
member they use is implemented once in `backends/com_backend.py` and once in
`backends/ezdxf_backend.py`. Conclusion: **all 12 tools are fully implemented on both backends**,
by construction, not by a maintained per-tool capability flag.

## Test coverage summary

20 files, 515 tests, all against the headless `EzdxfBackend` (autouse fixture in
`tests/conftest.py` pins `AUTOCAD_MCP_BACKEND=ezdxf`); zero arch tests are gated behind a
live-COM marker. `scripts/smoke_arch_com.py` is the one place live AutoCAD 2026 COM was exercised
for this pack (per CLAUDE.md, not re-verified in this audit).

## Confirmed gaps driving Phase 4/5 work

1. No duplicate/overlapping-wall check.
2. No room id/number duplicate check.
3. No circulation-reachability check (room → entry).
4. No door-swing-arc collision check.
5. No fixture-clearance check (wc/shower/bathtub).
6. No structural grid-intersection (candidate column) markers at all.
7. No storey/floor linkage concept — each floor is an independent `arch_plan_from_spec` call;
   multi-storey coordination is a manual, not automated, discipline.
8. No ft→mm input conversion helper (project requires ft input, mm drawing units).
