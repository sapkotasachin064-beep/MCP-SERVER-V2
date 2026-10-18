The lineweight truncation bug is confirmed devastating: ENGINEERING_LAYERS uses floats like 0.50, 0.25, 0.18, 0.13, 0.05 mm, and `layer_create` does `int(lineweight)` (ezdxf_backend.py:1034), so every one floors to 0. Counts confirmed: 109 tools, 6 resources, 5 prompts; LICENSE/benchmarks/ci.yml all absent. All load-bearing claims verified against source. I have everything needed to synthesize.

# AutoCAD MCP Pro — Understanding & Research Dossier

## 1. Architecture at a Glance

AutoCAD MCP Pro is a **single-file FastMCP 3.0 server** (`server.py`, 2881 lines) exposing **109 `@mcp.tool` registrations, 6 `@mcp.resource` endpoints, 5 `@mcp.prompt` templates** (verified by grep, not the docs' "87"). It uses a **strategy-pattern dual backend** behind one ABC (`backends/base.py`, ~73 abstract methods + 5 dataclasses): a **live COM backend** (`com_backend.py`, pywin32, single STA-thread `ThreadPoolExecutor`) and a **headless ezdxf backend** (`ezdxf_backend.py`, file-based DXF, all sync work via `asyncio.to_thread` under one `asyncio.Lock`). Backend selection (`server.py::_make_backend`, server.py:69): env `AUTOCAD_MCP_BACKEND`; Windows `auto`/`com` tries COM then falls back to ezdxf; non-Windows always ezdxf.

Request path: `ErrorHandlingMiddleware → AuditMiddleware → TimingMiddleware → LoggingMiddleware` (server.py:197-200) → tool fn → `_backend(ctx)` (server.py:207, raises `ToolError` if backend None) → identically-named backend method → `_dc()` dataclass→dict serialization (server.py:216). Lifespan (`autocad_lifespan`, server.py:107) builds the backend singleton into `ctx.lifespan_context["backend"]`.

A **deterministic engineering layer** (`engineering/` package) backs the "premium" workflow: parametric gear/keyway/titleblock primitives, a closed-enum `drawing_critique`, an 8-step `DrawingValidator`, ISO layer/linetype scaffolds, and a `PlanSpec` plan-before-draw contract. **The central architectural fact: the premium workflow is fully implemented only on ezdxf; the COM backend stubs all 8 premium meta-tools with `NotImplementedError` (com_backend.py:1637-1660, verified) — yet COM is the default Windows backend.**

---

## 2. Per-Subsystem Summary

**`server.py` (transport + tool registry).** Thin async wrappers over the backend singleton, grouped into 13 sections (1–12 + sub-sections 8b/8c/8d batch/template/validation + 13 premium). Owns server-side composition tools (`entity_delete_many` server.py:1065, `layer_isolate` :1216, `block_find_references` :1362, `analysis_layer_stats` :1506, `entity_batch_*` :1538/:1590, `template_*` :1695/:1730, `validation_check` :1749). Entry point manually parses `--transport/--port/--host` (server.py:2866) and refuses non-loopback HTTP unless `ALLOW_REMOTE_HTTP` + `MCP_AUTH_TOKEN` (`_validate_http_bind`).

**`backends/base.py` (the contract).** `AutoCADBackend` ABC: ~73 `@abstractmethod`, 2 concrete (`set_layer_active`, `ensure_linetypes`), 5 dataclasses (`EntityInfo/LayerInfo/BlockInfo/DrawingInfo/CommandResult`), 3 helpers (`shoelace_area`, `deg2rad`, `rad2deg`). Both backends define a body for every abstract method (no structural gaps); divergences are behavioral.

**`backends/ezdxf_backend.py` (headless).** Full create/modify/query/analysis/dimension/block/layer + premium meta-tools + corner ops. Transactions = full DXF snapshot to tempfile on `_undo_stack` (trimmed to `max_undo_stack=5`, O(drawing-size) per `transaction_begin`). View ops and `system_run_command/run_lisp` are documented no-ops. Screenshot/PDF via matplotlib.

**`backends/com_backend.py` (live AutoCAD).** All COM through one STA worker with per-call timeout (`com_call_timeout`, default 60s) and executor-rebuild on timeout/fatal HRESULT. Corner ops via `_safe_send_command` (CMDACTIVE-polling). Win32 `PrintWindow` screenshots. **8 premium meta-tools + `block_create_from_entities` are stubs.**

**`engineering/` (deterministic CAD).** `gear.py` (involute spur/helical outlines), `keyway.py` (DIN 6885), `titleblock.py` (ISO 7200 A3), `layers.py` (mech/pid/iso13567 sets), `critique.py` (6 focuses), `validator.py` (8-step gate), `plan_spec.py` (PlanSpec/Issue + ISO-128 lineweight set). `section.py` (`cutting_plane_line`, `apply_section_hatch`) and `gear.generate_tooth_profile` are **dead code** (exported, zero callers/tests).

**`tests/` (184 functions, 14 files).** One ezdxf-only `backend` fixture (`conftest.py`). COM backend, server→sanitizer wiring, and `section.py` have **zero coverage**.

---

## 3. Complete MCP Tool Inventory (grouped; ✅ real / ⚠️ partial / ❌ stub-or-missing)

> All 109 tools are **registered** in `server.py` and have **real ezdxf implementations**. "Status" below reflects the **COM backend** (the Windows default) plus correctness caveats. Nothing is purely aspirational/unregistered.

| § | Tools | ezdxf | COM | Notes |
|---|---|---|---|---|
| 1 Drawing (12, doc says 11) | info, new, open, save, save_as, export_dxf, export_pdf, purge, audit, close, undo, redo | ✅ (redo ❌ no-op ezdxf_backend.py:487) | ✅ | `drawing_redo` inert on ezdxf; header says 11 but 12 registered (drawing_redo server.py:426) |
| 2 Entity Create (13) | line, circle, arc, polyline, rectangle(→polyline), text, mtext, hatch, spline, ellipse, point, block_ref | ✅ | ✅ | mtext has no rotation param on ezdxf (:578); hatch pattern-only single loop |
| 3 Dimensions (5) | linear, aligned, angular, radius, diameter | ⚠️ aligned/angular **xfail** (tests/test_dimensions.py:16); angular ignores tx/ty + fixed dist=10 (ezdxf:705) | ✅ | No dimstyle/tolerance support either backend |
| 4 Modify (14) | move, copy, rotate, scale, mirror, offset, trim, extend, fillet, chamfer, delete, array_rectangular, array_polar, set_properties | ⚠️ offset ignores side (:868); corner ops LINE+LINE only (:1535-1750); polar 360° dup (:946) | ⚠️ offset ignores side (:860); corner ops via SendCommand | |
| 5 Query (3) | entity_get, entity_list, entity_delete_many | ✅ | ✅ | COM entity_list = O(n) per-item COM reads (:967) |
| 6 Layer (14) | list, create, delete, set_current, modify, freeze, thaw, lock, unlock, hide, show, isolate, linetype_list, linetype_load | ⚠️ **lineweight int() truncation** (:1034) | ✅ | See RISK-2 |
| 7 Block (7) | list, insert, explode, get_attributes, set_attributes, create_from_entities, find_references | ✅ | ⚠️ create_from_entities ❌ stub (:1253) | BlockInfo.description never populated |
| 8 Analysis (8) | stats, find_in_region, measure_distance, measure_area, bounding_box, select_by_layer, select_by_type, layer_stats | ⚠️ region fallback insert/start only (:1330) | ✅ | hand-rolled loops vs ezdxf query/groupby |
| 8b Batch (2) | entity_batch_create, entity_batch_modify | ✅ | ✅ | |
| 8c Template (2) | template_apply_layers, template_list | ✅ | ✅ | Duplicates `_LAYER_TEMPLATES`/prompt layer sets |
| 8d Validation (1) | validation_check | ✅ | ✅ | |
| 9 View (4, doc says 5) | zoom_extents, zoom_window, screenshot, zoom_and_screenshot | ⚠️ zoom = no-op (:1394) | ✅ | Header says 5 |
| 10 Transactions (3) | begin, commit, rollback | ✅ (commit file-I/O outside lock :1452) | ⚠️ flag-leak on error (:1402) | |
| 11 System (6) | status, get_variable, set_variable, run_command, run_lisp, about | ⚠️ run_command/lisp no-op | ⚠️ run_lisp result always 'nil' (:1487); about catalog drifted | |
| 12 Engineering (7) | gear_draw_helical/spur/section_aa, keyway_draw_keyed_bore/section, titleblock_apply_iso_a3, drawing_finalize | ✅ | ✅ (use generic entity_create_*) | Validator/titleblock import-guarded → None risk |
| 13 Premium (8) | drawing_plan, drawing_critique, point_from_snap, construction_xline, construction_clear, drawing_apply_iso_layers, dimension_auto, entity_select_smart | ✅ | ❌ **all NotImplementedError** (:1637-1660) | **The documented-mandatory workflow is dead on COM** |

**Documented-but-missing entirely:** none. **Documented-as-working but stubbed on default backend:** the 8 premium tools (§13) + `block_create_from_entities` on COM.

---

## 4. Cross-Cutting RISK Register (merged, deduped, severity-sorted)

| # | Sev | Risk | Location | Evidence |
|---|---|---|---|---|
| R1 | **CRITICAL** | All 8 premium meta-tools `raise NotImplementedError` on COM (the Windows default). The "non-negotiable for production" workflow (`drawing_plan→apply_iso_layers→critique→finalize`) 500s on the primary platform. | com_backend.py:1637-1660 | **Verified verbatim**; ezdxf impls real (ezdxf_backend.py:1753-2050) |
| R2 | **CRITICAL** | `layer_create` does `int(lineweight)` so every sub-1.0 ISO mm value (0.50/0.25/0.18/0.13/0.05) floors to **0**. The entire ISO-128 lineweight discipline is silently nulled; `drawing_apply_iso_layers`/`drawing_new` bootstrap produce flat 0-weight layers. | ezdxf_backend.py:1034; values engineering/layers.py:16-26 | **Both verified.** ezdxf wants integer hundredths (50=0.50mm), not raw mm |
| R3 | **HIGH** | `_check_iso128` is a permanent no-op: `lw <= 0: continue` (critique.py:50) skips every layer made 0 by R2. The advertised ISO gate can never fire. Comment "the layer dataclass already normalises to mm" (critique.py:53) is **false** (ezdxf_backend.py:189 stores raw `float(lw)`). | engineering/critique.py:37-64 | **Verified verbatim** |
| R4 | **HIGH** | `_check_dim_overlap` reads `properties['text_position'/'defpoint'/'insertion_point']`, but the ezdxf DIM extractor sets only `dim_type` (ezdxf_backend.py:166-168) → `dim_points` always empty → check is a silent no-op. | engineering/critique.py:194-197 | — |
| R5 | **HIGH** | COM timeout path (`stuck.shutdown(wait=False)`) cannot kill the STA worker still blocked in SendCommand → **permanently leaks one CoInitialize'd thread + COM proxy per timeout**; no `CoUninitialize` anywhere. | com_backend.py:415-433, 68-71 | — |
| R6 | **HIGH** | Zero COM-backend test coverage (~80 methods incl. UndoMark transactions, SendCommand corner ops, CMDACTIVE guard). Passing ezdxf transaction tests give **false confidence** for the semantically different COM model. | tests/ (no ComBackend import); conftest.py:8-15 | — |
| R7 | **HIGH** | Server→sanitizer wiring untested: `test_security.py` tests `sanitize_command/lisp/validate_path` in isolation; no integration test proves `system_run_command/lisp` actually call them. A refactor dropping the call (server.py:2035/2052) passes all security tests while raw commands reach SendCommand. | server.py:2035,2052; tests/test_security.py | — |
| R8 | **HIGH** | LISP-aliasing bypass (`(setq f command)(f "ERASE")`) is claimed-defended in a comment (security.py:138-140) but has **no adversarial test**; UNC/`~`/symlink path escapes in `validate_path` also untested. | security.py:138-179; test_security.py:177-231 | — |
| R9 | **MED** | `entity_array_polar` full-360° fill double-places: `step=radians(360)/(count-1)` puts the last copy at 0°==original → duplicate. Hits the common bolt-circle/gear pattern the engineering layer relies on. | ezdxf_backend.py:946-947 | — |
| R10 | **MED** | `drawing_finalize` calls `drawing_save_as(str(validated))` with no `fmt`. ezdxf default `fmt='dxf'` (ezdxf:345) vs COM `fmt='dwg'` (com:515) vs save_as tool default `'dwg'` (server:336) → 3-way inconsistency; format backend-dependent, not path-derived. | server.py:2299 | **Verified** (omits fmt) |
| R11 | **MED** | `drawing_save_as(fmt='dwg')` on ezdxf writes DXF bytes to a `.dwg` path and returns `{'format':'dwg'}` — silent wrong-format file. ezdxf cannot write DWG; should error or use `odafc`. | ezdxf_backend.py:345-352 | — |
| R12 | **MED** | `dimension_angular` ignores tx/ty, fixed `distance=10.0` → arc radius wrong for large/small parts; breaks COM parity. | ezdxf_backend.py:705-722 | — |
| R13 | **MED** | `entity_offset` ignores `side_x/side_y` (both backends); only `distance` sign flips side; ARC/LWPOLYLINE/ELLIPSE raise "not supported". | ezdxf:868-908; com:860-874 | — |
| R14 | **MED** | Engineering titleblock/validator symbols import-guarded to `None` (engineering/__init__.py:40-51); if module truly fails to import, tools raise opaque "NoneType not callable" instead of clear ToolError. | server.py:2266,2294 | — |
| R15 | **MED** | `system_about` static `tool_groups` catalog drifted: omits all 15 engineering+premium tools, misfiles `entity_delete_many`. Agents inspecting capabilities can't see the CLAUDE.md-mandated tools. | server.py:2070-2106 | — |
| R16 | **MED** | COM `transaction_active` left stale-True if commit/rollback `_run` raises; `rollback` issues `EndUndoMark`+`UNDO B` SendCommand without the CMDACTIVE guard used elsewhere → can interleave mid-command. | com_backend.py:1402,1411-1421 | — |
| R17 | **MED** | `_safe_send_command` busy-polls CMDACTIVE with `time.sleep(0.05)` on the single STA thread → monopolizes the executor up to deadline; `deadline_s`(8s) decoupled from `_run` timeout(60s). | com_backend.py:1521-1536 | — |
| R18 | **MED** | `drawing_new` swallows bootstrap failures into `result['bootstrap']={'error':...}` and reports success → un-bootstrapped drawing looks normal though CLAUDE.md treats the scaffold as a precondition for gear_*/titleblock_*. | server.py:280-294 | — |
| R19 | **MED** | `dimension_aligned`/`dimension_angular` permanently `xfail(strict=False)` — advertised tools shipped broken; an accidental fix wouldn't alert. | tests/test_dimensions.py:16-27 | — |
| R20 | LOW | `_registered_tool_count` reaches into FastMCP privates (`mcp._local_provider._components`, `'tool:'` prefix); a minor upgrade → tool_count=-1 surfaced to clients. | server.py:231-234 | — |
| R21 | LOW | Involute flank prepends a straight radial root→base segment (no trochoid fillet) → geometrically wrong dedendum for `root_r<base_r`; root-arc gap when `root_r>=base_r`; degenerate arc for teeth≤2. | engineering/gear.py:40-50,163-190 | — |
| R22 | LOW | `drawing_undo`/`transaction_rollback` share one `_undo_stack` with no transaction-id/depth separation; reload doesn't reset `_doc_path`/`_current_layer`. | ezdxf_backend.py:470-484,1462-1476 | — |
| R23 | LOW | COM `system_run_lisp` always reports `result='nil'` (SendCommand returns None); no CMDACTIVE guard → a prompting LISP form deadlocks next call. | com_backend.py:1487-1492 | — |
| R24 | LOW | `_apply_attrs` sets `entity.dxf.linetype` without `_ensure_linetype_loaded` (unlike set_properties/layer_modify) → `linetype='HIDDEN'` on create may render Continuous or raise on save. | ezdxf_backend.py:491-501 | — |
| R25 | LOW | `block_find_references` calls `entity_list(type_filter='INSERT')` with no limit (bypasses `max_list_limit`) → unbounded INSERTs into memory; assumes every backend populates `properties['block_name']`. | server.py:1362-1370 | — |
| R26 | LOW | View zoom ops unconditionally registered but no-op on ezdxf → success response implies the view changed when it didn't; `view_zoom_and_screenshot` may not frame the requested region on ezdxf. | server.py:1814-1831,1870 | — |
| R27 | LOW | `validator.py` title check substring-matches 'SPUR'/'HELICAL SPUR' on TEXT layer → false-positive blocks `drawing_finalize` if any note contains 'SPUR'. | engineering/validator.py:166-181 | — |
| R28 | LOW | COM `_find_autocad_hwnd` grabs first visible window whose title contains 'AutoCAD' → may capture palette/splash/About dialog; not tied to `AcadApplication.HWND`. | com_backend.py:283-300 | — |
| R29 | LOW | Broad `except Exception: pass` swallows COM faults (disconnected/busy) at debug level in ~20 sites → bypasses the HRESULT reconnect logic in `_run`. | com_backend.py:199,244,868,901,1216,… | — |

---

## 5. Doc-vs-Code Drift Table

| Claim (source) | Reality | Verdict |
|---|---|---|
| "87 tools" (CLAUDE.md, README:6) | **109** `@mcp.tool` (verified) | STALE (soft — both add "count is dynamic" caveat) |
| "104 tests" (README:83) | **184** test functions across 14 files (verified) | STALE (~80 under) |
| Section 1 "(11 tools)" (CLAUDE.md) | 12 (`drawing_redo` server.py:426) | WRONG |
| Section 9 "(5 tools)" (CLAUDE.md) | 4 view tools registered | WRONG |
| "12-section taxonomy" (CLAUDE.md) | 1–12 + 8b/8c/8d + 13 = 6 extra groups | INCOMPLETE |
| Premium workflow "non-negotiable for production" (CLAUDE.md) | 8/8 premium tools dead on COM (default Windows backend) | OVERCLAIM |
| "MIT — see [LICENSE](LICENSE)" (README:409) | No LICENSE file (verified absent) | **DEAD LINK / legal drift** |
| `benchmarks/` referenced (README:39,302,367) | Absent (verified) | DEAD LINK (forward-looking) |
| ".github/workflows/ci.yml" + "GitHub Actions CI" (README:84,358) | git status `D`; absent on disk (verified) | **CI REMOVED while docs claim it** |
| "Premium discipline lives in `.claude/skills/autocad-mcp-premium/`" (CLAUDE.md) | Entire tree git-deleted (28 deletions) + all `.cursor/` deleted | DANGLING POINTER |
| README tests/ tree (README:347-355) | Omits 6 of 14 test files + engineering/ package | STALE |
| `system_about` tool_groups | Omits 15 engineering+premium tools | DRIFT |
| `BlockInfo.description` field (base.py:71) | Never populated by either backend | DEAD FIELD |
| critique.py:53 "normalises to mm" comment | Stores raw DXF lineweight (ezdxf:189) | FALSE COMMENT |
| `engineering/__init__.py:37-39` "Agent B … in flight"; com_backend "Task #7/#8/#9" | Multi-agent build seams shipped unreconciled | TODO-IN-PROD |
| Dockerfile, .env.example (README) | Present (verified) | OK |

---

## 6. Test Coverage Gaps (ranked)

1. **COM backend: 0% coverage** (com_backend.py entire file) — transactions (UndoMark vs ezdxf snapshot are *different* semantics), SendCommand corner ops, CMDACTIVE guard, timeout/HRESULT recovery, all 8 premium stubs. Highest-risk untested surface; it's the production path. (R6)
2. **Server→sanitizer integration** — no test proves tools invoke `sanitize_command/lisp`/`validate_path`. (R7)
3. **Sanitizer adversarial cases** — LISP aliasing, command word-boundary evasion (`.ERASE`), UNC/`~`/symlink path escapes — the comment claims defenses with no tests. (R8)
4. **Critique detection paths** — `iso128`, `layer_color`, `dim_overlap` only exercised on a *clean* drawing (assert they *don't* fire); their actual detection logic and the unknown-focus branch (critique.py:241) are never proven. (R3, R4)
5. **`dimension_auto` ordinate** (ezdxf:1988) untested; chain/baseline covered.
6. **`dimension_aligned`/`angular`** permanently xfail — shipped broken. (R19)
7. **Uncovered backend methods (both backends):** `system_get/set_variable`, `system_status`, `drawing_close`, `drawing_export_pdf`, `entity_create_block_ref`, `block_set_attributes`, `linetype_list/load` (load-bearing for bootstrap), `view_zoom_*`, `view_screenshot`.
8. **`engineering/section.py`** (dead code) — 0 coverage.
9. **Transaction nesting/error semantics** — only single begin→commit/rollback tested; nested, rollback-without-begin, layer/block restoration untested.
10. **Infrastructure:** CI workflow deleted (no PR gate); `pytest-cov` declared but no `--cov`/`fail-under`; several "template/validation" tests assert nothing about the named feature (vacuous `if start:` guards, test_batch_template.py:30-34).

---

## 7. Research Synthesis

### 7a. Academic techniques (2025–2026) that validate or upgrade this design

- **GeoGramBench (ICLR 2026, arxiv.org/abs/2505.17653):** frontier LLMs score **<50%** at high-abstraction Program-to-Geometry. → Empirically justifies the repo's no-coordinate-guessing rule and `point_from_snap`/`entity_select_smart`. **Action:** expand the deterministic geometry surface (`point_intersection`, `point_offset`, `point_along`) so the LLM *never* computes coordinates.
- **Self-Improving CAD w/ FEA feedback (arxiv.org/html/2605.17448v2):** deterministic controller owns validation, LLM owns design; **+13.4pp** per feedback round; frontier models get **zero** first-attempt strict passes — *iteration beats more tokens*. → This is the repo's architecture, but `drawing_critique` is one-shot. **Action:** make it a routed repair loop; `Issue` (plan_spec.py:64-81) already carries severity/handles/detail — add per-finding repair hints.
- **CADSmith (arxiv.org/abs/2603.26512):** 5-agent Planner/Coder/Executor/Validator/**Refiner**, dual loop, exact-kernel measurements + **independent VLM judge** → Chamfer 28.37mm→0.74mm (**38×**), IoU 0.81→0.96; *removing the rendered image alone made hard cases 35× worse.* → The repo renders a screenshot at finalize (server.py:2301-2309) but only checks bytes exist (validator step 7). **Highest-leverage single upgrade: feed that render to a VLM judge + add an automated Refiner.**
- **CADFusion (ICML 2025, arxiv.org/abs/2501.19054)** & **Seek-CAD (arxiv.org/abs/2505.17702):** render is a first-class signal; step-wise visual feedback catches errors mid-build. → Add a `visual` critique focus; run critique per construction step using the existing transaction model.
- **ProCAD "Clarify Before You Draw" (arxiv.org/html/2602.03045v1):** one-round clarification → invalidity 14.6%→0.9%, Chamfer ~80% lower. → `drawing_plan` records intent passively; add a pre-plan ambiguity/conflict detector that returns targeted questions before any `entity_create_*`.
- **FutureCAD (arxiv.org/abs/2603.11831):** NL → exact B-Rep primitive grounding fixes the fillet/chamfer "which primitive" problem. → Directly targets the repo's hardest API: trim/extend/fillet/chamfer need exact handles **plus** keep_x/keep_y. NL grounding ("fillet the top-left corner") removes the burden GeoGramBench shows LLMs fail at.
- **Text-to-CadQuery (2505.06507), CAD-Coder (2505.14646), EvoCAD (2510.11631):** field converged on Python/CadQuery macros; open local VLMs read CAD images reliably; candidate-generate + critique-as-fitness raises first-try quality. → Add more parametric meta-tools (the gear/keyway pattern) and/or a sandboxed parametric-script tool; an open VLM (CAD-Coder, **Florence-2 for GD&T**, arxiv.org/abs/2411.03707) keeps the visual tier off frontier APIs.
- **MUSE (arxiv.org/html/2605.28579) + CadBench (2605.10873):** grade manufacturability/functionality, not just shape; standard metrics = volumetric/surface IoU, Chamfer, **Invalidity Ratio**. → Replace `validator.py`'s regex/title heuristics with a staged code→geometric→rubric-judge protocol; emit a single scalar "drawing score" for regression tests (the repo has *no* quantitative quality metric).

### 7b. Competitive landscape

| Product | 3D | Render-critique loop | Validation gate | HTTP auth | Code escape hatch |
|---|---|---|---|---|---|
| **AutoCAD MCP Pro** | ❌ 2D only | ⚠️ finalize-only, symbolic | ✅ **unique** (critique+validator+ISO) | ❌ none | ⚠️ COM-only run_command/lisp |
| build123d-mcp/agentcad (github.com/pzfreo/build123d-mcp) | ✅ | ✅ in-loop | ❌ | — | ✅ |
| FreeCAD Robust MCP (150+ tools) | ✅ + FEM | ⚠️ | ❌ | — | ✅ |
| Blender MCP (~22k★) | ✅ | ✅ | ❌ | — | ✅ Python exec |
| RhinoMCP | ✅ | ✅ viewport | ❌ | — | ✅ |
| Fusion360/Onshape MCP | ✅ parametric | — | ❌ | ✅ OAuth/keys | — |

Snyk's 9-CAD-MCP roundup (snyk.io/articles/9-mcp-servers-for-computer-aided-drafting-cad-with-ai/): **vision only in FreeCAD/Blender/Rhino; design validation in none; HTTP auth only in Onshape/Fusion.** → **Our moat is the design-rule validation gate; the field beat us on 3D, in-loop render-critique, and auth.** Autodesk's own in-AutoCAD assistant demo (aecmag.com/features/autodesk-shows-its-ai-hand/) flagship = **automated compliance checking** — exactly our niche, so we must make standards compliance the sharpest, most-cited capability. Adam/Zoo (techcrunch.com/2025/10/31/...) set the UX bar: **parametric editability + post-gen dimension sliders + entity-level conversational editing**.

### 7c. Under-used COM / ezdxf API + ISO standards

**COM (ActiveX) gaps (every create call hits ModelSpace, com_backend.py:125-127):**
- **PaperSpace/Layouts + Plot config** — `drawing_export_pdf` (com_backend.py:528-534) calls bare `Plot.PlotToFile(path,'DWG To PDF.pc3')` with no page setup → ignores the A3/scale `drawing_plan` promised. Add `layout_*`/`viewport_*` (AddPViewport, StandardScale, CanonicalMediaName). (help.autodesk.com ActiveX ref)
- **AddTable** (BOM/revision tables), **AddMLeader** (ISO leader notes — CLAUDE.md *reserves* "leader notes" but no tool creates them), **Fields** (auto-updating title block), **GetDynamicBlockProperties** (parametric symbol libraries — `block_insert` only does attribute text, com:1195-1251), **DimStyles.Add+CopyFrom** (no ISO-129 dimstyle is ever set → undercuts the "Dimensions are ISO 129" rule), **named UCS** (per-view frames for `view_count`), **AttachExternalReference** (shared borders), **gradient/island hatch**.
- **3D solids/regions/booleans** — `system_status` advertises `all_entity_types` (com:1443) which is **false**; either implement `solid_*` or correct the claim.
- **Push selection into AutoCAD:** `entity_list` (com:967) and `analysis_select_by_type` (com:1352) loop ModelSpace.Item(i) in Python (O(n) COM round-trips — the #1 perf killer); `analysis_select_by_layer` (com:1339) already shows the right `SelectionSet.SelectAll` group-code-filter pattern to copy.

**ezdxf gaps (Grep confirms zero use of `set_gradient/set_solid_fill/paperspace/add_viewport/odafc/export_dwg/groupby/dimstyles/MTextEditor/add_ordinate/qsave`):**
- **`addons.odafc.export_dwg`** = real DWG (R12–R2018) → fixes R11/R10 (drawing_save_as fake DWG). (ezdxf.mozman.at/docs/addons/odafc.html)
- **drawing-addon `Configuration`** (lineweight_policy ABSOLUTE, background_policy, SVGBackend/PyMuPdfBackend) → true ISO lineweights + vector output, replacing raw matplotlib (ezdxf:357-379,1400-1424).
- **`query()` mini-language + `groupby()`** → replace hand-rolled loops in analysis_stats/select/entity_select_smart (which pulls 5000 entities then filters in memory, ezdxf:2008-2050).
- **`recover.readfile` + `Auditor.fix`** → real repair; `drawing_audit` (ezdxf:448) reports but never fixes; `drawing_open` (ezdxf:309) has no recover fallback.
- **`MTextEditor`** (stacked tolerance fractions), **Hatch gradients/islands/edge-paths**, **DimStyle overrides** (no ISO dimstyle today, ezdxf:668-774), **path-module offset** (generalizes LINE/CIRCLE-only offset + LINE-only corner ops).

**ISO standards conformance:**
- ✅ **ISO 128-2** lineweight set encoded (plan_spec.py:85, verified) — but **nulled by R2** and group-vs-element-class not checked.
- ⚠️ **ISO 7200** title block — A3-only hardcoded (titleblock.py:16-17), informal labels ("DWG NO" vs ISO field names), len×0.3 centering heuristic (titleblock.py:171), missing "Document type"/"Date of issue".
- ❌ **ISO 129-1 dimensioning** — biggest functional gap: `dimension_*` (base.py:226-257) have **no** param for ±/limit/fit (H7/g6) tolerances or text override → toleranced production dims impossible. (iso.org/obp/ui/#iso:std:iso:129)
- ❌ **ISO 1101 / ASME Y14.5 GD&T** — entirely absent (grep-confirmed): no feature control frame, datum, or ISO 2768 general-tolerance note. (gdandtbasics.com/iso-vs-asme-standards/)
- ⚠️ **ISO 13567** — static mech-only starter list (layers.py:51-62), no field-grammar parser/validator.

---

## 8. "What Would Make This the BEST AutoCAD MCP" — Prioritized Thesis

The evidence converges: **the repo is architecturally ahead on dual-backend + standards-validation but behind on the closed-loop, the production-output plumbing, and the very workflow it markets.** Priorities, evidence-backed:

**P0 — Make the marketed product actually work on its default platform.**
1. **Implement the 8 premium meta-tools on COM** (R1, com_backend.py:1637-1660). Today the CLAUDE.md-mandatory workflow 500s on every Windows install. Nothing else matters until this ships.
2. **Fix the lineweight `int()` truncation** (R2, ezdxf_backend.py:1034 → multiply mm by 100 / map to ACAD enum). This single bug nullifies the ISO-128 system *and* makes the iso128 critique a permanent no-op (R3). The standards-validation gate is the **competitive moat** (Snyk roundup; Autodesk's own flagship demo) — it must be real.
3. **Add CI + a coverage gate + the first COM smoke tests** (R6, ci.yml deleted; pytest-cov unconfigured). Restore the LICENSE file (legal drift).

**P1 — Own the moat by closing the loop (the #1 accuracy lever in every 2025–26 paper).**
4. **Turn `drawing_critique` into a routed iterative Refiner loop** with per-`Issue` repair hints and a bounded budget (CADSmith Refiner; FEA-agent +13.4pp/round; Physics-in-the-Loop 3.3–6.0 iters converge). The `Issue` dataclass already carries handles+detail.
5. **Promote the finalize screenshot to a first-class `visual` critique focus fed to a VLM judge** (CADSmith: dropping the render → 35× worse; CADFusion). Use an **open local VLM** (CAD-Coder / Florence-2 for GD&T) behind a `[vision]` extra so the headless path is unaffected. Add a **dimension round-trip check** (VLM-read dims vs created `dimension_*` entities) to catch what proximity-only `dim_overlap` (R4) cannot.
6. **Add a ProCAD-style pre-plan clarification pass to `drawing_plan`** (invalidity 14.6%→0.9%): detect missing/conflicting dims, material, tolerance, view_count-vs-intent before any geometry.
7. **Emit a scalar "drawing score" / Invalidity-Ratio** (MUSE/CadBench) so the premium workflow is regression-testable — the repo has no quantitative accuracy metric.

**P2 — Reach production-drawing parity (what un-toleranced ISO 128 can't deliver).**
8. **ISO 129 tolerances + ISO 1101/Y14.5 GD&T**: add ±/limit/fit params to `dimension_*` and a `gd_frame(symbol, tol, datums, modifiers)` + datum/ISO-2768-note primitive. This is the categorical gap blocking real part drawings; no surveyed text-to-CAD product covers 2D GD&T — a differentiator.
9. **Real plotted sheets**: COM Layout/PaperSpace/Plot-config so `drawing_plan(sheet_size, scale)` and `titleblock_apply_iso_a3` produce a correct A-series plot; on ezdxf wire `odafc.export_dwg` (kills the fake-DWG R11) and the drawing-addon `Configuration` for true-lineweight SVG/PDF.
10. **An ISO-129 `DimStyle`** created once and applied to all dims (COM `DimStyles.Add+CopyFrom`; ezdxf dimstyle overrides) so "Dimensions are ISO 129" becomes true, and **MLEADER** for the leader notes the docs already reserve.

**P3 — Catch the field on breadth (table-stakes elsewhere, absent here).**
11. **A 3D solids tier** (extrude/revolve from 2D profiles + booleans on COM; STEP/STL on ezdxf) — *or* correct the false `all_entity_types` claim (com:1443). Every competitor has 3D.
12. **Parametric editability + entity-level conversational editing** (Adam/Zoo): capture driving dims in PlanSpec, expose a re-drive tool; "select this circle → make it the 20mm bore" via existing handle model + `entity_select_smart`/`point_from_snap`.
13. **Authenticated remote HTTP** (API-key middleware) given `dangerous_commands_enabled` exists (server.py:111); a **standard-parts/symbol library** (`library_insert` over `block_insert`, dynamic-block props); **NL→B-Rep grounding** (FutureCAD) over the brittle trim/fillet/chamfer keep-point API.

**P4 — Hygiene that compounds with the above.** Generalize LINE-only corner ops + LINE/CIRCLE-only offset via the ezdxf path module; replace hand-rolled selection with `query()`/`groupby()` (ezdxf) and `SelectionSet.SelectAll` filters (COM); fix `entity_array_polar` 360° dup (R9), `dimension_angular` tx/ty (R12), the COM thread-leak `CoUninitialize` (R5); delete dead `section.py`/`generate_tooth_profile`; reconcile `system_about` catalog (R15) and the stale README/CLAUDE.md drift (§5).

**Files central to every priority:** `backends/com_backend.py:1637-1660` (P0.1), `backends/ezdxf_backend.py:1034` + `engineering/layers.py:14-26` (P0.2), `engineering/critique.py:37-64,194-197` (P0.2/P1.5), `engineering/plan_spec.py:64-87` (P1.4/P1.6/P2.8), `backends/base.py:226-257` (P2.8), `server.py:528-534/2294-2309` (P2.9).