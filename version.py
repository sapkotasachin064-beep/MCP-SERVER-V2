"""Package version resolved from installed metadata or the source pyproject."""

from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def package_version() -> str:
    """Return the canonical project version without a duplicate constant."""
    try:
        return version("autocad-mcp-pro")
    except PackageNotFoundError:
        pyproject = Path(__file__).with_name("pyproject.toml")
        with pyproject.open("rb") as stream:
            return str(tomllib.load(stream)["project"]["version"])


__version__ = package_version()
