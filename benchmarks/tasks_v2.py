"""Fixed v2 task matrix shared by all competitor adapters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    category: str
    description: str
    weight: float


TASKS_V2: tuple[TaskSpec, ...] = (
    TaskSpec("core_geometry", "creation", "Create and inspect deterministic geometry", 1.0),
    TaskSpec("modify_query", "editing", "Modify geometry and verify the result", 1.0),
    TaskSpec("layers_linetypes", "standards", "Apply standard layers and linetypes", 1.0),
    TaskSpec("dimensions", "annotation", "Create real associative dimensions", 1.0),
    TaskSpec("table_mleader", "annotation", "Create TABLE and MLEADER semantics", 1.0),
    TaskSpec("transactions", "reliability", "Rollback a bounded change", 1.0),
    TaskSpec("preflight", "planning", "Resolve and hash drawing requirements", 1.0),
    TaskSpec("quality_refiner", "quality", "Detect and repair a quality defect", 1.0),
    TaskSpec("dxf_roundtrip", "interoperability", "Save and re-open with structural parity", 1.0),
    TaskSpec("auditable_delivery", "delivery", "Produce a hashed validation manifest", 1.0),
)


def task_by_id(task_id: str) -> TaskSpec:
    for task in TASKS_V2:
        if task.task_id == task_id:
            return task
    raise KeyError(f"Unknown benchmark task: {task_id}")
