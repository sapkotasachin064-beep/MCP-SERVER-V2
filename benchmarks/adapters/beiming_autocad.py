"""Black-box adapter for beiming183-cloud/AutoCAD-MCP (headless ezdxf lane).

Contract verified against the pinned checkout's ``server.py`` (v3.10 line):

- document identity comes from ``transaction(operation="context")`` and every
  mutation must carry ``doc_id`` + ``expected_revision`` — top-level for the
  ``entity``/``annotation`` tools, inside ``data`` for ``drawing`` operations;
- ``entity create_line`` takes top-level ``x1..y2``; circle/dimension payloads
  sit under ``data`` (same field spellings as the upstream puran-water base);
- ``transaction begin/commit/rollback`` are compatibility operations that the
  headless backend may reject with ``E_UNSUPPORTED*`` — that outcome is
  reported as ``unsupported`` rather than ``fail``.

Verification is artifact-based: geometry claims are checked by exporting a DXF
(``drawing save_as_dxf``) and re-reading it with ezdxf in the harness.
"""

from __future__ import annotations

import math
from typing import Any

from benchmarks.adapters.base import TaskResult
from benchmarks.adapters.mcp_stdio import (
    McpStdioAdapter,
    ToolCallFailed,
    extract_handle,
)
from benchmarks.competitors_env import CompetitorSpec

PINNED_SHA = "11f7c47e5038796a20451b38b23032e625b5aa26"


def _find_key(payload: Any, *keys: str) -> Any:
    if isinstance(payload, dict):
        for key in keys:
            if key in payload and payload[key] not in (None, ""):
                return payload[key]
        for value in payload.values():
            found = _find_key(value, *keys)
            if found is not None:
                return found
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            found = _find_key(item, *keys)
            if found is not None:
                return found
    return None


class BeimingAutocadAdapter(McpStdioAdapter):
    name = "beiming183-autocad-mcp"
    spec = CompetitorSpec(
        competitor_id="beiming183-autocad-mcp",
        repo_url="https://github.com/beiming183-cloud/AutoCAD-MCP.git",
        pinned_sha=PINNED_SHA,
        entry_candidates=(
            ("-m", "autocad_mcp"),
            ("server.py",),
            ("src/server.py",),
        ),
        pip_installs=(("-e", "."),),
        launch_env={"AUTOCAD_MCP_BACKEND": "ezdxf"},
        pythonpath="src",
    )

    def extra_launch_env(self) -> dict[str, str]:
        # The server redirects writes outside its managed output root; point
        # the root at the benchmark artifact directory so exports land where
        # the harness verifies them.
        return {
            "AUTOCAD_MCP_OUTPUT_ROOT": str(self.artifact_dir),
            "AUTOCAD_MCP_ALLOW_EXTERNAL_OUTPUTS": "true",
        }

    def warmup_calls(self):
        # Absorb lazy backend initialization once during setup.
        return (
            ("system", {"operation": "status"}),
            ("drawing", {"operation": "create", "data": {}}),
        )

    async def _ctx(self) -> dict[str, Any]:
        """Read doc_id + revision from ``transaction(operation="context")``."""
        try:
            payload = await self.call("transaction", {"operation": "context"})
        except ToolCallFailed:
            return {}
        doc_id = _find_key(payload, "doc_id", "document_id")
        revision = _find_key(payload, "revision", "expected_revision", "document_revision")
        context: dict[str, Any] = {}
        if doc_id is not None:
            context["doc_id"] = doc_id
        if revision is not None:
            context["expected_revision"] = revision
        return context

    async def _new_drawing(self) -> None:
        await self.call("drawing", {"operation": "create", "data": {}})

    async def _save_dxf(self, filename: str) -> str:
        target = self.save_target(filename)
        payload: dict[str, Any] = {"path": str(target)}
        try:
            await self.call("drawing", {"operation": "save_as_dxf", "data": payload})
        except ToolCallFailed:
            context = await self._ctx()
            await self.call("drawing", {"operation": "save_as_dxf", "data": {**payload, **context}})
        return str(target)

    async def _entity(self, operation: str, **fields: Any) -> Any:
        context = await self._ctx()
        return await self.call("entity", {"operation": operation, **context, **fields})

    async def _create_line(self, x1: float, y1: float, x2: float, y2: float):
        return await self._entity("create_line", x1=x1, y1=y1, x2=x2, y2=y2)

    # -- tasks ----------------------------------------------------------------

    async def _task_core_geometry(self) -> TaskResult:
        await self._new_drawing()
        await self._create_line(0, 0, 3, 4)
        await self._entity("create_circle", data={"cx": 10, "cy": 10, "radius": 2})
        artifact = await self._save_dxf("beiming_core_geometry.dxf")
        _, doc = self.verify_dxf(self.save_target("beiming_core_geometry.dxf"))
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
            artifacts=[artifact],
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
        await self._entity("move", entity_id=handle, data={"dx": 5, "dy": 2})
        artifact = await self._save_dxf("beiming_modify_query.dxf")
        _, doc = self.verify_dxf(self.save_target("beiming_modify_query.dxf"))
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
        context = await self._ctx()
        await self.call("drawing", {"operation": "setup_mechanical", "data": {**context}})
        artifact = await self._save_dxf("beiming_layers.dxf")
        _, doc = self.verify_dxf(self.save_target("beiming_layers.dxf"))
        layers = {layer.dxf.name.upper() for layer in doc.layers}
        linetypes = {lt.dxf.name.upper() for lt in doc.linetypes}
        expected_layers = {"OUTLINE", "CENTER", "DIM"}
        got_layers = expected_layers.issubset(layers)
        got_linetype = "CENTER" in linetypes
        if got_layers and got_linetype:
            return TaskResult("layers_linetypes", "pass", 100.0, artifacts=[artifact])
        if got_layers:
            return TaskResult(
                "layers_linetypes",
                "partial",
                50.0,
                "GB/T layers created but CENTER linetype missing from the table",
                artifacts=[artifact],
            )
        return TaskResult(
            "layers_linetypes",
            "fail",
            0.0,
            f"layers={sorted(layers)}",
            artifacts=[artifact],
        )

    async def _task_dimensions(self) -> TaskResult:
        await self._new_drawing()
        context = await self._ctx()
        await self.call(
            "annotation",
            {
                "operation": "create_dimension_linear",
                **context,
                "data": {"x1": 0, "y1": 0, "x2": 50, "y2": 0, "dim_x": 25, "dim_y": 10},
            },
        )
        artifact = await self._save_dxf("beiming_dimensions.dxf")
        _, doc = self.verify_dxf(self.save_target("beiming_dimensions.dxf"))
        dims = [e for e in doc.modelspace() if e.dxftype() == "DIMENSION"]
        return TaskResult(
            "dimensions",
            "pass" if dims else "fail",
            100.0 if dims else 0.0,
            metrics={"dimension_count": len(dims)},
            artifacts=[artifact],
        )

    async def _task_transactions(self) -> TaskResult:
        await self._new_drawing()
        context = await self._ctx()
        try:
            begin = await self.call("transaction", {"operation": "begin", **context})
        except ToolCallFailed as exc:
            if "E_UNSUPPORTED" in str(exc):
                return TaskResult(
                    "transactions",
                    "unsupported",
                    0.0,
                    "transaction begin is rejected as unsupported on the headless backend",
                )
            raise
        transaction_id = _find_key(begin, "transaction_id", "txn_id")
        await self._entity("create_circle", data={"cx": 0, "cy": 0, "radius": 1})
        context = await self._ctx()
        rollback_args: dict[str, Any] = {"operation": "rollback", **context}
        if transaction_id is not None:
            rollback_args["transaction_id"] = transaction_id
        await self.call("transaction", rollback_args)
        artifact = await self._save_dxf("beiming_transactions.dxf")
        _, doc = self.verify_dxf(self.save_target("beiming_transactions.dxf"))
        count = len(list(doc.modelspace()))
        return TaskResult(
            "transactions",
            "pass" if count == 0 else "fail",
            100.0 if count == 0 else 0.0,
            metrics={"entity_count_after_rollback": count},
            artifacts=[artifact],
        )

    async def _task_dxf_roundtrip(self) -> TaskResult:
        await self._new_drawing()
        await self._create_line(0, 0, 10, 10)
        artifact = await self._save_dxf("beiming_roundtrip.dxf")
        _, doc = self.verify_dxf(self.save_target("beiming_roundtrip.dxf"))
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
            "no TABLE or MLEADER operation in the annotation tool (v3.10)",
        )

    async def _task_preflight(self) -> TaskResult:
        return TaskResult("preflight", "unsupported", 0.0, "no requirements-preflight equivalent")

    async def _task_quality_refiner(self) -> TaskResult:
        return TaskResult(
            "quality_refiner",
            "unsupported",
            0.0,
            "audits detect issues but there is no automated repair loop",
        )

    async def _task_auditable_delivery(self) -> TaskResult:
        return TaskResult(
            "auditable_delivery",
            "unsupported",
            0.0,
            "drawing.deliver is documented as File-IPC only (not headless)",
        )


__all__ = ["BeimingAutocadAdapter"]
