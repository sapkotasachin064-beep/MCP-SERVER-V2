# Release & Distribution Runbook (v1.4.0+)

The code side of a release is fully automated; three account-bound steps need
a human once, plus the directory submissions. Track them here.

## One-time setup (owner action)

- [ ] **PyPI trusted publisher** — on <https://pypi.org/manage/account/publishing/>
  add a *pending publisher* for project `autocad-mcp-pro`:
  repository `U-C4N/Autocad-MCP`, workflow `release.yml`, environment `pypi`.
  (No API token is stored anywhere; `release.yml` uses OIDC.)
- [ ] **GitHub environment** — create the `pypi` environment in the repo
  settings (Settings → Environments) so the publish job can bind to it.
- [ ] **MCP registry login** — install `mcp-publisher`, then
  `mcp-publisher login github` (authenticates the `io.github.u-c4n` namespace).

## Every release

1. Bump `pyproject.toml` + `server.json` versions, add the CHANGELOG section,
   update the README snapshot line — `tests/test_release_consistency.py`
   enforces all of it.
2. Push `main`, wait for CI to go green (lint, linux, windows, package,
   docker, registry-validate).
3. Tag and push: `git tag v1.4.0 && git push origin v1.4.0`.
   `release.yml` runs the test gate, verifies tag == package version, builds,
   publishes to PyPI via trusted publishing and cuts the GitHub Release.
4. Verify: `pip install autocad-mcp-pro==<version>` in a clean venv;
   `uvx autocad-mcp-pro --help`.
5. Publish the registry manifest: `mcp-publisher publish` (validates
   `server.json`, checks the `mcp-name` marker in the PyPI README).

## Directory listings (submit once, then keep fresh)

- [ ] Glama — <https://glama.ai/mcp/servers> (auto-indexes GitHub; claim the
  server page and verify metadata).
- [ ] mcpservers.org — submit via their GitHub repo PR flow.
- [ ] awesome-mcp-servers — PR adding the server under CAD/engineering.
- [ ] Smithery — optional; requires a `smithery.yaml` (evaluate demand first).

## Benchmark refresh (per release)

```bash
python -m benchmarks.run_competitors --server autocad-mcp-pro --backend ezdxf
python -m benchmarks.run_competitors --server puran-water-autocad-mcp --backend ezdxf
python -m benchmarks.run_competitors --server beiming183-autocad-mcp --backend ezdxf
# sanitize + copy reports into benchmarks/results/published/, then:
python -m benchmarks.render_live_chart
```

Bump the competitor pins in `benchmarks/competitors.yaml` deliberately (new
SHA = re-read their tool contracts before trusting the mappings).
