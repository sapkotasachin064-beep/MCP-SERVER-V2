"""Feet-to-millimetre conversion for building a spec from a feet-based brief.

Every tool in this repository takes and returns millimetres (the repository
rule in CLAUDE.md: "Every coordinate in or out of a tool is WCS", drawing
units mm by default). A residential brief given in feet (a 40x30 ft plot) is
converted once, here, before any wall/opening/room dict is built - no tool
accepts feet.
"""

from __future__ import annotations

#: 1 ft = 304.8 mm, exact (international foot).
MM_PER_FT = 304.8


def ft_to_mm(value_ft: float) -> float:
    """``value_ft`` feet as millimetres. Raises on a non-finite input."""
    number = float(value_ft)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"ft_to_mm: must be finite, got {value_ft!r}")
    return number * MM_PER_FT
