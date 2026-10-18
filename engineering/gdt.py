"""2D GD&T (ISO 1101 / ASME Y14.5) feature control frames + datum features.

This is the single biggest "no competitor has this" capability: no surveyed
text-to-CAD product or competing CAD MCP ships 2D geometric-tolerance authoring
*with validation*. Frames are composed from plain LINE + TEXT primitives (not
ezdxf's native TOLERANCE entity, which renders blank through the matplotlib
frontend), so the exact same output lands on both the COM and ezdxf backends.

The layout math here is pure/deterministic and unit-tested without a backend;
the async drawing orchestration lives on `AutoCADBackend` (base.py) so both
engines inherit identical behaviour.
"""

from __future__ import annotations

# ISO 1101 geometric characteristic symbols (Unicode glyph per characteristic).
# ASCII keys keep the tool schema legible; the glyph is what lands in the DXF.
GEOMETRIC_SYMBOLS: dict[str, str] = {
    "straightness": "\u23e4",  # ⏤
    "flatness": "\u23e5",  # ⏥
    "circularity": "\u25cb",  # ○
    "cylindricity": "\u232d",  # ⌭
    "profile_line": "\u2312",  # ⌒  profile of a line
    "profile_surface": "\u2313",  # ⌓  profile of a surface
    "angularity": "\u2220",  # ∠
    "perpendicularity": "\u27c2",  # ⟂
    "parallelism": "\u2225",  # ∥
    "position": "\u2316",  # ⌖
    "concentricity": "\u25ce",  # ◎
    "symmetry": "\u232f",  # ⌯
    "circular_runout": "\u2197",  # ↗
    "total_runout": "\u2913",  # ⤓ (double-arrow stand-in for total runout)
}

# Which characteristics are legal *without* a datum reference (form tolerances).
# Everything else (orientation / location / runout) requires at least one datum.
FORM_TOLERANCES: frozenset[str] = frozenset(
    {"straightness", "flatness", "circularity", "cylindricity", "profile_line", "profile_surface"}
)

# Material-condition modifiers (ASME Y14.5): circled M / L / S.
MATERIAL_MODIFIERS: dict[str, str] = {
    "M": "\u24c2",  # Ⓜ maximum material condition
    "L": "\u24c1",  # Ⓛ least material condition
    "S": "\u24c8",  # Ⓢ regardless of feature size
}

# Diameter prefix for cylindrical tolerance zones (true position of a hole, …).
DIAMETER_PREFIX = "\u2300"  # ⌀


def _tolerance_text(tolerance: str | float, diameter: bool, modifier: str | None) -> str:
    """Build the tolerance compartment string: optional ⌀, value, optional Ⓜ/Ⓛ/Ⓢ."""
    if isinstance(tolerance, (int, float)):
        # Trim a trailing ".0" so 0.10 -> "0.1", 5.0 -> "5".
        tol = f"{float(tolerance):g}"
    else:
        tol = str(tolerance).strip()
    parts = ""
    if diameter:
        parts += DIAMETER_PREFIX
    parts += tol
    if modifier:
        mod = modifier.strip().upper()
        if mod not in MATERIAL_MODIFIERS:
            raise ValueError(
                f"gdt: unknown material modifier {modifier!r}. "
                f"Use one of {sorted(MATERIAL_MODIFIERS)}."
            )
        parts += MATERIAL_MODIFIERS[mod]
    return parts


def fcf_compartments(
    symbol: str,
    tolerance: str | float,
    datums: list[str] | None = None,
    *,
    diameter: bool = False,
    modifier: str | None = None,
) -> list[str]:
    """Return the ordered compartment strings of a feature control frame.

    ``[symbol_glyph, tolerance, datum1, datum2, …]``. Raises ValueError for an
    unknown characteristic, or for an orientation/location/runout characteristic
    given no datum (that combination is meaningless per ISO 1101).
    """
    key = symbol.strip().lower()
    if key not in GEOMETRIC_SYMBOLS:
        raise ValueError(
            f"gdt: unknown characteristic {symbol!r}. Use one of {sorted(GEOMETRIC_SYMBOLS)}."
        )
    datums = [d.strip().upper() for d in (datums or []) if str(d).strip()]
    if key not in FORM_TOLERANCES and not datums:
        raise ValueError(
            f"gdt: characteristic '{key}' is an orientation/location/runout "
            "control and requires at least one datum reference."
        )
    comps = [GEOMETRIC_SYMBOLS[key], _tolerance_text(tolerance, diameter, modifier)]
    comps.extend(datums)
    return comps


def fcf_layout(
    compartments: list[str],
    origin_x: float,
    origin_y: float,
    height: float,
) -> dict:
    """Deterministic geometry for a feature-control frame.

    Given the compartment strings and a bottom-left origin, returns::

        {
          "box": [(x, y), …, (x0, y0)],       # closed outer rectangle
          "dividers": [((x, y0), (x, y1)), …],# internal vertical separators
          "labels": [(text, cx, cy), …],      # centred text per compartment
          "width": float, "height": float,
        }

    Widths: symbol + datum compartments are square (``height`` wide); the
    tolerance compartment grows with its text so it never clips.
    """
    h = float(height)
    x = float(origin_x)
    y0 = float(origin_y)
    y1 = y0 + h
    text_h = h * 0.6

    widths: list[float] = []
    for i, text in enumerate(compartments):
        if i == 1:  # tolerance compartment — size to content
            widths.append(max(h * 1.6, len(text) * text_h * 0.75 + h * 0.5))
        else:
            widths.append(h)

    labels: list[tuple[str, float, float]] = []
    dividers: list[tuple[tuple[float, float], tuple[float, float]]] = []
    cx = x
    for i, (text, w) in enumerate(zip(compartments, widths, strict=True)):
        labels.append((text, cx + w / 2.0, y0 + h / 2.0))
        cx += w
        if i < len(compartments) - 1:
            dividers.append(((cx, y0), (cx, y1)))
    total_w = sum(widths)

    box = [
        (x, y0),
        (x + total_w, y0),
        (x + total_w, y1),
        (x, y1),
        (x, y0),
    ]
    return {
        "box": box,
        "dividers": dividers,
        "labels": labels,
        "width": total_w,
        "height": h,
        "text_height": text_h,
    }


def datum_triangle(
    x: float, y: float, size: float, *, down: bool = True
) -> list[tuple[float, float]]:
    """Filled datum triangle (closed 3-point path) with apex at (x, y)."""
    s = float(size)
    if down:
        return [(x, y), (x - s / 2.0, y - s), (x + s / 2.0, y - s), (x, y)]
    return [(x, y), (x - s / 2.0, y + s), (x + s / 2.0, y + s), (x, y)]
