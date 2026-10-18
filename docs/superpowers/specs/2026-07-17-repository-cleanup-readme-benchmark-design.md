# Repository Cleanup, README, and Benchmark Design

**Date:** 2026-07-17
**Status:** Approved for implementation

## Objective

Prepare AutoCAD MCP Pro for a polished public release by removing local drafts
and generated artifacts, replacing the oversized README with a concise English
product narrative, and presenting reproducible benchmark evidence through a
Python-generated chart that names relevant AutoCAD MCP alternatives.

The public presentation must be confident without declaring itself "the best."
It should earn that impression through architecture, capabilities, tests,
security controls, quality gates, and transparent benchmark methodology.

## Repository Cleanup

Delete private planning drafts and local/generated artifacts:

- Root drafts: `b.md` and `new.md` (and `p.md` only if it exists at implementation time).
- Test and release output: `.codex-pytest-temp/`, `.pytest_cache/`,
  `.release-*/`, and `.tdd-*/`.
- Tool and interpreter caches: `.ruff_cache/` and every `__pycache__/` directory.
- Build and run output: `dist/`, `out/`, and `.coverage`.
- Empty local tool state: `.firecrawl/` when it contains no user data.

Remove the draft-specific `b.md` and `new.md` entries from `.gitignore` after
the files are deleted. Keep or add general ignore rules for reproducible cache,
test, build, coverage, and generated CAD output so these directories do not
reappear in Git status.

Preserve all product code and current version 1.3 work, including modified and
untracked files in `backends/`, `engineering/`, `benchmarks/`, `tests/`, and the
repository root. No product source file may be deleted merely because it is
currently untracked.

## README Information Architecture

The README will be written in English and optimized for a new user evaluating
and installing the server. It will be substantially shorter than the current
document and use this order:

1. Hero: product name, one-sentence value proposition, essential badges, and a
   compact proof line.
2. Quickstart: the shortest headless install/run path plus the live AutoCAD path.
3. Benchmark evidence: generated chart, result interpretation, methodology
   boundary, and exact reproduction command.
4. Differentiators: dual backends, deterministic CAD operations, closed-loop
   quality, and auditable delivery/security.
5. Backend/capability comparison: make platform limitations explicit.
6. MCP client configuration and environment variables.
7. Tool discovery and representative workflows; avoid maintaining a fragile,
   exhaustive hardcoded catalog when runtime discovery is authoritative.
8. Architecture and security model.
9. Development, contributing, roadmap link or compact roadmap, author, and license.

Remove repeated claims, the long table of contents, inflated competitor language,
and hardcoded counts that cannot be verified from the current source or test run.
Retain the author's identity in a compact section rather than a long sales letter.

## Benchmark Visualization

Create a reproducible source-review benchmark presentation with three artifacts:

- `benchmarks/source_review.json`: dated, schema-versioned data containing the
  named projects, rubric totals or category values, evidence grade, source URL,
  and review boundary.
- `benchmarks/render_chart.py`: deterministic Matplotlib renderer.
- `docs/assets/autocad-mcp-benchmark.svg`: generated README asset.

The primary graphic will be a horizontal bar chart because it is readable on
GitHub, supports long repository names, and makes score differences easier to
compare than a radar chart. It will name at least:

- `U-C4N/Autocad-MCP`
- `varavista/autocad-mcp`
- `beiming183-cloud/AutoCAD-MCP`
- `AnCode666/multiCAD-mcp`
- `puran-water/autocad-mcp`
- `NCO-1986/AutoCAD_mcp`

The chart must display the review date, the 100-point rubric context, and evidence
quality. AutoCAD MCP Pro may receive a distinct accent color, but competitors
must remain legible and must not be visually disparaged.

The README must clearly separate two evidence types:

1. The Python task runner's real AutoCAD MCP Pro result, currently a local
   ten-task self-check.
2. The named cross-project source-review rubric used by the chart.

It must not imply that competitors ran the shared live task suite unless their
adapters were actually executed. The chart subtitle or adjacent text will say
that it is a source-reviewed capability benchmark rather than a shared live
AutoCAD run. Scores and claims will be rechecked against current evidence before
publication; stale values from the private draft will not be copied blindly.

The renderer should produce stable ordering and labels, use no network access,
and fail with an actionable message when Matplotlib is unavailable. SVG is the
canonical README format for sharp text at different display sizes.

## Verification

Implementation is complete only after these checks succeed:

- The intended generated/draft targets are absent and all resolved deletion
  targets were confined to the repository.
- `git status` contains no cache, release, build, coverage, CAD-output, or draft
  noise; pre-existing product changes remain intact.
- The chart regenerates from JSON using the documented Python command and the
  committed SVG matches the generated output.
- README local links and referenced files resolve.
- README capability, version, benchmark, and test claims match current code or
  fresh command output.
- Ruff, the relevant benchmark tests, the full test suite, and package build are
  run in proportion to environment availability; any external limitation is
  reported explicitly rather than hidden.

## Scope Boundaries

This work does not implement competitor runtime adapters, publish unexecuted
live benchmark scores, redesign product APIs, or refactor version 1.3 product
code. It only cleans the workspace, establishes honest benchmark presentation,
and rebuilds the public README around verified evidence.
