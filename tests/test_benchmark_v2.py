"""Fair benchmark v2 runner contract."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from unittest.mock import AsyncMock, patch

import pytest

from benchmarks.adapters.autocad_mcp_pro import AutoCADMCPProAdapter
from benchmarks.adapters.base import BenchmarkAdapter, TaskResult
from benchmarks.run_competitors import run_tasks
from benchmarks.tasks_v2 import TaskSpec


class FakeAdapter(BenchmarkAdapter):
    name = "fake"

    async def setup(self, artifact_dir):
        self.artifact_dir = artifact_dir

    async def run_task(self, task):
        if task.task_id == "slow":
            await asyncio.sleep(0.2)
        if task.task_id == "unsupported":
            return TaskResult(task_id=task.task_id, status="unsupported", score=0.0)
        return TaskResult(task_id=task.task_id, status="pass", score=100.0)

    async def cleanup(self):
        return None


@pytest.mark.asyncio
async def test_benchmark_timeout_does_not_stop_later_tasks(tmp_path):
    tasks = [
        TaskSpec("slow", "reliability", "Times out", 1.0),
        TaskSpec("next", "reliability", "Still runs", 1.0),
    ]

    report = await run_tasks(FakeAdapter(), tasks, tmp_path, timeout=0.01)

    assert [item["status"] for item in report["results"]] == ["timeout", "pass"]
    assert report["summary"]["attempted"] == 2
    assert report["summary"]["passed"] == 1
    assert report["git_sha"]
    assert report["environment"]["python"]


@pytest.mark.asyncio
async def test_unsupported_tasks_count_as_zero_in_fixed_matrix_score(tmp_path):
    tasks = [
        TaskSpec("supported", "coverage", "Implemented", 1.0),
        TaskSpec("unsupported", "coverage", "Not implemented", 9.0),
    ]

    report = await run_tasks(FakeAdapter(), tasks, tmp_path)

    assert report["summary"]["score"] == 10.0
    assert report["summary"]["supported"] == 1
    assert report["summary"]["coverage_percent"] == 10.0


def test_task_result_has_machine_readable_status():
    result = TaskResult(
        task_id="table",
        status="unsupported",
        score=0.0,
        message="TABLE is unavailable",
    )

    assert result.to_dict() == {
        "task_id": "table",
        "status": "unsupported",
        "score": 0.0,
        "message": "TABLE is unavailable",
        "duration_ms": 0.0,
        "artifacts": [],
        "metrics": {},
        "stdout_summary": "",
        "stderr_summary": "",
    }


@pytest.mark.asyncio
async def test_reference_adapter_selects_real_com_backend_class(tmp_path):
    with patch("backends.com_backend.ComBackend") as backend_class:
        backend_class.return_value.connect = AsyncMock()
        adapter = AutoCADMCPProAdapter(backend="com")

        await adapter.setup(tmp_path)

    backend_class.assert_called_once_with()
    assert adapter.backend is backend_class.return_value


@pytest.mark.parametrize("args", [[], ["--help"]])
def test_correctness_suite_help_is_not_a_traceback(args):
    completed = subprocess.run(
        [sys.executable, "benchmarks/correctness_suite.py", *args],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0
    assert "usage" in completed.stdout.lower()
