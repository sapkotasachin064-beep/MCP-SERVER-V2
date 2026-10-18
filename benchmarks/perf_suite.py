"""Headless performance suite (v3 lane): wall-time on real drawing workloads.

Complements the correctness/coverage lanes with *scale* evidence: how long the
ezdxf engine takes to create, roundtrip, query and quality-check real geometry.
Workloads drive the backend exactly like the MCP tools do (same async methods),
so the numbers include the server-side call overhead, not just raw ezdxf.

Honesty boundaries:

- Self-measurement only — no competitor timing claims (their servers would pay
  an extra stdio serialization cost ours does not pay in-process).
- Wall-clock on the machine recorded in the report; absolute numbers move with
  hardware, the workload definitions do not.

Run:

    python -m benchmarks.perf_suite            # human summary
    python -m benchmarks.perf_suite --json     # machine-readable report
    python -m benchmarks.perf_suite --out benchmarks/results/published/perf-ezdxf.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from backends.ezdxf_backend import EzdxfBackend


@dataclass
class WorkloadResult:
    workload_id: str
    description: str
    wall_ms: float
    metric: str
    metric_value: float
    detail: dict


async def _timed(coro) -> tuple[float, object]:
    started = time.perf_counter()
    result = await coro
    return (time.perf_counter() - started) * 1000.0, result


async def workload_create_lines_2k(backend: EzdxfBackend) -> WorkloadResult:
    """2,000 individual entity_create_line calls (per-call tool overhead included)."""
    await backend.drawing_new()
    started = time.perf_counter()
    for index in range(2_000):
        y = float(index % 100)
        await backend.entity_create_line(0.0, y, 100.0, y + 1.0)
    wall_ms = (time.perf_counter() - started) * 1000.0
    count = (await backend.drawing_info()).entity_count
    return WorkloadResult(
        "create_lines_2k",
        "Create 2,000 lines through individual backend calls",
        round(wall_ms, 1),
        "entities_per_second",
        round(2_000 / (wall_ms / 1000.0), 1),
        {"entity_count": count},
    )


async def workload_roundtrip_10k(backend: EzdxfBackend, scratch: Path) -> WorkloadResult:
    """Build a 10,000-entity drawing, export DXF, reopen, read info."""
    await backend.drawing_new()
    build_started = time.perf_counter()
    for index in range(10_000):
        x = float(index % 500)
        y = float(index // 500)
        await backend.entity_create_line(x, y, x + 0.8, y + 0.8)
    build_ms = (time.perf_counter() - build_started) * 1000.0

    target = scratch / "perf_roundtrip_10k.dxf"
    export_ms, _ = await _timed(backend.drawing_export_dxf(str(target)))

    reopened = EzdxfBackend()
    await reopened.connect()
    try:
        reopen_ms, _ = await _timed(reopened.drawing_open(str(target)))
        count = (await reopened.drawing_info()).entity_count
    finally:
        await reopened.disconnect()

    total = build_ms + export_ms + reopen_ms
    return WorkloadResult(
        "roundtrip_10k",
        "Create 10,000 lines, export DXF, reopen and verify",
        round(total, 1),
        "entities_per_second",
        round(10_000 / (total / 1000.0), 1),
        {
            "build_ms": round(build_ms, 1),
            "export_ms": round(export_ms, 1),
            "reopen_ms": round(reopen_ms, 1),
            "file_bytes": target.stat().st_size,
            "entity_count": count,
        },
    )


async def workload_region_query_10k(backend: EzdxfBackend) -> WorkloadResult:
    """Rectangular region query against the 10,000-entity drawing."""
    # backend still holds the 10k drawing from the roundtrip workload builder;
    # rebuild deterministically to stay order-independent.
    await backend.drawing_new()
    for index in range(10_000):
        x = float(index % 500)
        y = float(index // 500)
        await backend.entity_create_line(x, y, x + 0.8, y + 0.8)
    wall_ms, found = await _timed(backend.analysis_entities_in_region(0.0, 0.0, 250.0, 10.0))
    return WorkloadResult(
        "region_query_10k",
        "Crossing-selection region query over 10,000 entities",
        round(wall_ms, 1),
        "entities_matched",
        float(len(found)),
        {"entity_count": 10_000},
    )


async def workload_premium_pass(backend: EzdxfBackend) -> WorkloadResult:
    """Small end-to-end quality loop: layers, geometry, dimensions, critique."""
    started = time.perf_counter()
    await backend.drawing_new()
    await backend.drawing_apply_iso_layers("mech")
    plate = [
        (0.0, 0.0, 120.0, 0.0),
        (120.0, 0.0, 120.0, 80.0),
        (120.0, 80.0, 0.0, 80.0),
        (0.0, 80.0, 0.0, 0.0),
    ]
    for x1, y1, x2, y2 in plate:
        await backend.entity_create_line(x1, y1, x2, y2, layer="GEOMETRY")
    await backend.entity_create_circle(60.0, 40.0, 12.0, layer="GEOMETRY")
    await backend.dimension_linear(0, 0, 120, 0, 60, -15, layer="DIM")
    await backend.dimension_linear(0, 0, 0, 80, -15, 40, 90, layer="DIM")
    issues = await backend.drawing_critique(None)
    wall_ms = (time.perf_counter() - started) * 1000.0
    return WorkloadResult(
        "premium_pass",
        "Plate with hole: ISO layers, geometry, dimensions and full critique",
        round(wall_ms, 1),
        "critique_issues",
        float(len(issues)),
        {"entities": (await backend.drawing_info()).entity_count},
    )


async def run_suite(scratch: Path) -> dict:
    backend = EzdxfBackend()
    await backend.connect()
    try:
        results = [
            await workload_create_lines_2k(backend),
            await workload_roundtrip_10k(backend, scratch),
            await workload_region_query_10k(backend),
            await workload_premium_pass(backend),
        ]
    finally:
        await backend.disconnect()
    return {
        "schema_version": "perf/1.0",
        "backend": "ezdxf",
        "environment": {
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "workloads": [asdict(item) for item in results],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--out", type=Path, default=None, help="Also write the report to a file")
    parser.add_argument("--scratch", type=Path, default=Path("benchmarks/results/perf-scratch"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.scratch.mkdir(parents=True, exist_ok=True)
    report = asyncio.run(run_suite(args.scratch))
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    if args.json:
        print(rendered)
    else:
        for item in report["workloads"]:
            print(
                f"{item['workload_id']:>18}  {item['wall_ms']:>10.1f} ms   "
                f"{item['metric']}={item['metric_value']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
