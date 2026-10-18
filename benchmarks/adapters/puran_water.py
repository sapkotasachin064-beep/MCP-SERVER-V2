"""Black-box adapter for puran-water/autocad-mcp (headless ezdxf lane).

The competitor exposes 8 consolidated tools (``drawing``, ``entity``,
``layer``, ``block``, ``annotation``, ``pid``, ``view``, ``system``) whose
operations take an ``operation`` selector plus a payload. Argument spellings
are probed through ``wrapped_shapes`` fallbacks; every geometry claim is
verified by saving a DXF and re-reading it with ezdxf in the harness.

Tasks with no documented equivalent on this server are reported as
``unsupported`` with an explicit reason so the published JSON explains the
coverage gap instead of hiding it.
"""

from __future__ import annotations

import math

from benchmarks.adapters.base import TaskResult
from benchmarks.adapters.mcp_stdio import (
    McpStdioAdapter,
    ToolCallFailed,
    extract_handle,
)
from benchmarks.competitors_env import CompetitorSpec

PINNED_SHA = "95476a33a1c246308326eb4709d6379ef2efdbc1"


class PuranWaterAdapter(McpStdioAdapter):
    name = "puran-water-autocad-mcp"
    spec = CompetitorSpec(
        competitor_id="puran-water-autocad-mcp",
        repo_url="https://github.com/puran-water/autocad-mcp.git",
        pinned_sha=PINNED_SHA,
        entry_candidates=(
            ("-m", "autocad_mcp"),
            ("server.py",),
            ("src/server.py",),
            ("main.py",),
        ),
        pip_installs=(("-e", "."),),
        launch_env={"AUTOCAD_MCP_BACKEND": "ezdxf"},
        pythonpath="src",
    )

    # Exact v3.1 contract (verified against the pinned checkout's server.py):
    # entity create_line takes top-level x1..y2; circle/dimension payloads sit
    # under ``data``; modify ops take top-level ``entity_id`` + ``data``.

    def warmup_calls(self):
        # The first backend touch lazily initializes and can exceed the
        # per-call timeout; absorb it once during setup.
        return (
            ("system", {"operation": "status"}),
            ("drawing", {"operation": "create", "data": {}}),
        )

    async def _new_drawing(self) -> None:
        await self.call_op("drawing", "create", {})

    async def _save(self, filename: str) -> str:
        target = self.save_target(filename)
        await self.call_op("drawing", "save", {"path": str(target)})
        return str(target)

    async def _create_line(self, x1: float, y1: float, x2: float, y2: float):
        return await self.call(
            "entity",
            {"operation": "create_line", "x1": x1, "y1": y1, "x2": x2, "y2": y2},
        )

    # -- tasks ----------------------------------------------------------------

    async def _task_core_geometry(self) -> TaskResult:
        await self._new_drawing()
        await self._create_line(0, 0, 3, 4)
        await self.call_op("entity", "create_circle", {"cx": 10, "cy": 10, "radius": 2})
        preferred = await self._save("puran_core_geometry.dxf")
        _, doc = self.verify_dxf(self.save_target("puran_core_geometry.dxf"))
        lines = doc.modelspace().query("LINE")
        circles = doc.modelspace().query("CIRCLE")
        length = None
        if lines:
            start, end = lines[0].dxf.start, lines[0].dxf.end
            length = math.dist((start.x, start.y), (end.x, end.y))
        passed = (
            len(lines) == 1
            and len(circles) == 1
            and length is not None
            and abs(length - 5.0) < 1e-6
            and abs(circles[0].dxf.radius - 2.0) < 1e-6
        )
        return TaskResult(
            "core_geometry",
            "pass" if passed else "fail",
            100.0 if passed else 0.0,
            metrics={"line_length": length, "lines": len(lines), "circles": len(circles)},
            artifacts=[preferred],
        )

    async def _task_modify_query(self) -> TaskResult:
        await self._new_drawing()
        created = await self._create_line(0, 0, 10, 0)
        handle = extract_handle(created)
        if not handle:
            return TaskResult(
                "modify_query",
                "fail",
                0.0,
                "could not extract created-entity handle from the create_line response",
            )
        await self.call(
            "entity",
            {"operation": "move", "entity_id": handle, "data": {"dx": 5, "dy": 2}},
        )
        artifact = await self._save("puran_modify_query.dxf")
        _, doc = self.verify_dxf(self.save_target("puran_modify_query.dxf"))
        lines = doc.modelspace().query("LINE")
        moved = (
            bool(lines)
            and abs(lines[0].dxf.start.x - 5.0) < 1e-6
            and (abs(lines[0].dxf.start.y - 2.0) < 1e-6)
        )
        return TaskResult(
            "modify_query",
            "pass" if moved else "fail",
            100.0 if moved else 0.0,
            artifacts=[artifact],
        )

    async def _task_layers_linetypes(self) -> TaskResult:
        await self._new_drawing()
        try:
            await self.call_op(
                "layer",
                "create",
                {"name": "GEOMETRY", "color": 3, "linetype": "CENTER"},
            )
        except ToolCallFailed:
            await self.call_op("layer", "create", {"name": "GEOMETRY", "color": 3})
        artifact = await self._save("puran_layers.dxf")
        _, doc = self.verify_dxf(self.save_target("puran_layers.dxf"))
        has_layer = "GEOMETRY" in {layer.dxf.name.upper() for layer in doc.layers}
        has_center = "CENTER" in {lt.dxf.name.upper() for lt in doc.linetypes}
        if has_layer and has_center:
            return TaskResult("layers_linetypes", "pass", 100.0, artifacts=[artifact])
        if has_layer:
            return TaskResult(
                "layers_linetypes",
                "partial",
                50.0,
                "layer created; no linetype-loading operation is exposed",
                artifacts=[artifact],
            )
        return TaskResult("layers_linetypes", "fail", 0.0, artifacts=[artifact])

    async def _task_dimensions(self) -> TaskResult:
        await self._new_drawing()
        await self.call_op(
            "annotation",
            "create_dimension_linear",
            {"x1": 0, "y1": 0, "x2": 50, "y2": 0, "dim_x": 25, "dim_y": 10},
        )
        artifact = await self._save("puran_dimensions.dxf")
        _, doc = self.verify_dxf(self.save_target("puran_dimensions.dxf"))
        dims = [e for e in doc.modelspace() if e.dxftype() == "DIMENSION"]
        return TaskResult(
            "dimensions",
            "pass" if dims else "fail",
            100.0 if dims else 0.0,
            metrics={"dimension_count": len(dims)},
            artifacts=[artifact],
        )

    async def _task_dxf_roundtrip(self) -> TaskResult:
        await self._new_drawing()
        await self._create_line(0, 0, 10, 10)
        artifact = await self._save("puran_roundtrip.dxf")
        _, doc = self.verify_dxf(self.save_target("puran_roundtrip.dxf"))
        count = len(list(doc.modelspace()))
        return TaskResult(
            "dxf_roundtrip",
            "pass" if count == 1 else "fail",
            100.0 if count == 1 else 0.0,
            metrics={"entity_count": count},
            artifacts=[artifact],
        )

    # -- documented coverage gaps ----------------------------------------------

    async def _task_table_mleader(self) -> TaskResult:
        return TaskResult(
            "table_mleader",
            "unsupported",
            0.0,
            "no TABLE or MLEADER operation in the 8-tool surface (v3.1)",
        )

    async def _task_transactions(self) -> TaskResult:
        return TaskResult(
            "transactions",
            "unsupported",
            0.0,
            "no transaction begin/commit/rollback tool (undo/redo are File-IPC only)",
        )

    async def _task_preflight(self) -> TaskResult:
        return TaskResult("preflight", "unsupported", 0.0, "no requirements-preflight equivalent")

    async def _task_quality_refiner(self) -> TaskResult:
        return TaskResult(
            "quality_refiner", "unsupported", 0.0, "no critique/repair loop equivalent"
        )

    async def _task_auditable_delivery(self) -> TaskResult:
        return TaskResult(
            "auditable_delivery",
            "unsupported",
            0.0,
            "no hashed delivery-manifest equivalent (plot_pdf is File-IPC only)",
        )


__all__ = ["PuranWaterAdapter", "ToolCallFailed"]
