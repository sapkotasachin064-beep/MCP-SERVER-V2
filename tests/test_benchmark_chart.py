import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "benchmarks" / "source_review.json"


def _renderer_api() -> tuple[Callable[[Path], dict[str, Any]], Callable[..., None]]:
    try:
        from benchmarks.render_chart import load_benchmark, render_chart
    except ModuleNotFoundError:
        pytest.fail("benchmarks.render_chart is not implemented")
    return load_benchmark, render_chart


def test_source_review_contract_is_complete() -> None:
    load_benchmark, _ = _renderer_api()
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    data = load_benchmark(DATA_PATH)

    assert data == raw
    assert data["schema_version"] == "1.0"
    assert sum(item["weight"] for item in data["rubric"]) == 100
    assert data["evidence_boundary"] == "source_review_not_shared_live_run"

    projects = data["projects"]
    repositories = [item["repository"] for item in projects]
    assert len(repositories) == len(set(repositories))
    assert "U-C4N/Autocad-MCP" in repositories
    assert "varavista/autocad-mcp" in repositories
    assert "beiming183-cloud/AutoCAD-MCP" in repositories
    assert "AnCode666/multiCAD-mcp" in repositories
    assert "puran-water/autocad-mcp" in repositories
    assert "NCO-1986/AutoCAD_mcp" in repositories
    assert all(0 <= item["score"] <= 100 for item in projects)
    assert all(item["evidence_grade"] in {"A", "B", "C"} for item in projects)


def test_load_benchmark_rejects_duplicate_repositories(tmp_path: Path) -> None:
    load_benchmark, _ = _renderer_api()
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    payload["projects"].append(payload["projects"][0].copy())
    invalid = tmp_path / "duplicate.json"
    invalid.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate repository"):
        load_benchmark(invalid)


def test_render_chart_writes_readable_svg(tmp_path: Path) -> None:
    load_benchmark, render_chart = _renderer_api()
    pytest.importorskip("matplotlib")
    data = load_benchmark(DATA_PATH)
    output = tmp_path / "benchmark.svg"

    render_chart(data, output)

    svg = output.read_text(encoding="utf-8")
    assert svg.lstrip().startswith("<?xml")
    assert "Source-reviewed capability benchmark" in svg
    assert "U-C4N/Autocad-MCP" in svg
    assert "Shared live-run results are not implied" in svg
    assert all(line == line.rstrip() for line in svg.splitlines())
