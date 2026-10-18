"""Render the headless performance suite as a deterministic SVG.

Input: the report produced by ``benchmarks.perf_suite --out ...``
(default: ``benchmarks/results/published/perf-ezdxf.json``).
Output: a GitHub-readable log-scale wall-time chart per workload.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "benchmarks" / "results" / "published" / "perf-ezdxf.json"
DEFAULT_OUTPUT = ROOT / "docs" / "assets" / "autocad-mcp-perf.svg"

_LABELS = {
    "create_lines_2k": "Create 2,000 lines (individual calls)",
    "roundtrip_10k": "10,000 lines: build + DXF export + reopen",
    "region_query_10k": "Region query over 10,000 entities",
    "premium_pass": "Premium pass: layers + part + dims + full critique",
}


def load_report(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "perf/1.0":
        raise ValueError("unsupported perf report schema_version")
    if not data.get("workloads"):
        raise ValueError("perf report contains no workloads")
    return data


def _annotation(item: dict[str, Any]) -> str:
    wall_s = item["wall_ms"] / 1000.0
    if item["metric"] == "entities_per_second":
        return f"{wall_s:.2f} s  ·  {item['metric_value']:,.0f} entities/s"
    if item["metric"] == "entities_matched":
        return f"{wall_s:.2f} s  ·  {item['metric_value']:,.0f} matched"
    if item["metric"] == "critique_issues":
        return f"{wall_s:.2f} s  ·  {item['metric_value']:.0f} issues"
    return f"{wall_s:.2f} s"


def render_chart(data: dict[str, Any], output: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit(
            'Matplotlib is required. Install it with: pip install -e ".[pdf]"'
        ) from exc

    matplotlib.rcParams["svg.hashsalt"] = "autocad-mcp-perf-v1"
    workloads = sorted(data["workloads"], key=lambda item: item["wall_ms"])
    labels = [_LABELS.get(item["workload_id"], item["workload_id"]) for item in workloads]
    values = [item["wall_ms"] for item in workloads]

    fig, ax = plt.subplots(figsize=(12, 4.6), constrained_layout=True)
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#0d1117")
    bars = ax.barh(labels, values, color="#58a6ff", height=0.58)

    ax.set_xscale("log")
    ax.set_xlabel("Wall time in ms (log scale) — lower is better", color="#e6edf3", labelpad=10)
    ax.set_title(
        "Headless performance — ezdxf engine",
        loc="left",
        fontsize=18,
        fontweight="bold",
        color="#e6edf3",
        pad=28,
    )
    env = data.get("environment", {})
    ax.text(
        0,
        1.02,
        f"Fixed workloads via the same backend methods the MCP tools call · "
        f"Python {env.get('python', '?')} · {env.get('platform', '?')}",
        transform=ax.transAxes,
        color="#8b949e",
        fontsize=9,
    )

    for bar, item in zip(bars, workloads, strict=True):
        ax.text(
            bar.get_width() * 1.12,
            bar.get_y() + bar.get_height() / 2,
            _annotation(item),
            va="center",
            color="#e6edf3",
            fontweight="bold",
            fontsize=9,
        )

    ax.set_xlim(right=max(values) * 8)
    ax.text(
        0,
        -0.24,
        "Self-measurement only: competitor servers would pay extra stdio serialization cost in-process runs do not. "
        "Reproduce: python -m benchmarks.perf_suite",
        transform=ax.transAxes,
        color="#8b949e",
        fontsize=9,
    )
    ax.grid(axis="x", color="#30363d", linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", colors="#8b949e")
    ax.tick_params(axis="y", colors="#e6edf3", length=0, pad=8)
    for spine in ax.spines.values():
        spine.set_visible(False)

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        output,
        format="svg",
        facecolor=fig.get_facecolor(),
        metadata={"Creator": "AutoCAD MCP Pro perf renderer", "Date": None},
    )
    plt.close(fig)

    svg = output.read_text(encoding="utf-8")
    normalized = "\n".join(line.rstrip() for line in svg.splitlines()) + "\n"
    output.write_text(normalized, encoding="utf-8", newline="\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    render_chart(load_report(args.input), args.output)
    print(f"Rendered perf chart: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
