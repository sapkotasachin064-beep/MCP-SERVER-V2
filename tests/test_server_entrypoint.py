from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from unittest.mock import MagicMock

import server


def test_packaged_console_script_targets_callable_main():
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["scripts"]["autocad-mcp"] == "server:main"
    assert callable(server.main)


def test_main_starts_stdio_transport(monkeypatch):
    run = MagicMock()
    monkeypatch.setattr(server.mcp, "run", run)
    monkeypatch.setattr(sys, "argv", ["autocad-mcp"])

    server.main()

    run.assert_called_once_with()


def test_main_help_exits_without_starting_server(monkeypatch, capsys):
    run = MagicMock()
    monkeypatch.setattr(server.mcp, "run", run)
    monkeypatch.setattr(sys, "argv", ["autocad-mcp", "--help"])

    try:
        server.main()
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("--help must exit without starting the server")

    assert "usage:" in capsys.readouterr().out.lower()
    run.assert_not_called()
