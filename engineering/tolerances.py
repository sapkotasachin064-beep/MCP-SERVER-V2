"""ISO 129-1 dimension tolerance helpers.

A production drawing without ±/limit callouts is not manufacturable — this was
the dossier's "biggest functional gap". These helpers turn a small, explicit
tolerance spec into the ezdxf/AutoCAD dimension-variable (DIMVAR) overrides that
render tolerances, so `dimension_linear/radius/diameter` can emit toleranced
dims on both backends.

Scope (intentionally CI-testable): explicit upper/lower deviations with
symmetric / deviation / limit / basic display modes, plus a free-form text
override. The full ISO 286 fit table (H7/g6 …) is a large authored dataset and
is deferred to a follow-up; callers can already pass the resolved deviations.
"""

from __future__ import annotations

TOL_MODES = ("none", "symmetric", "deviation", "limit", "basic")


def build_dim_override(
    tol_upper: float | None = None,
    tol_lower: float | None = None,
    tol_mode: str = "none",
    text_override: str | None = None,
) -> tuple[dict, str | None]:
    """Return ``(dimvar_override, text)`` for an ezdxf ``add_*_dim`` call.

    - ``tol_mode="symmetric"``: a single ± value (uses ``tol_upper``; ``±tol``).
    - ``tol_mode="deviation"``: distinct upper/lower deviations (e.g. +0.02/-0.01).
    - ``tol_mode="limit"``: upper/lower limits stacked instead of ± (DIMLIM).
    - ``tol_mode="basic"``: theoretically-exact (boxed) dimension, no tolerance.
    - ``tol_mode="none"``: no tolerance (default) — empty override.
    - ``text_override``: replaces the measured text ("<>" keeps the measurement).

    Raises ValueError for an unknown mode or a mode missing its required values.
    """
    mode = (tol_mode or "none").strip().lower()
    if mode not in TOL_MODES:
        raise ValueError(
            f"build_dim_override: unknown tol_mode {tol_mode!r}. Use one of {TOL_MODES}."
        )

    override: dict = {}

    if mode == "symmetric":
        if tol_upper is None:
            raise ValueError("tol_mode='symmetric' requires tol_upper (the ± value).")
        t = abs(float(tol_upper))
        override.update({"dimtol": 1, "dimlim": 0, "dimtp": t, "dimtm": t})
    elif mode == "deviation":
        if tol_upper is None or tol_lower is None:
            raise ValueError("tol_mode='deviation' requires tol_upper and tol_lower.")
        # DIMTM convention: the displayed lower deviation is -DIMTM. Callers
        # pass tol_lower as the magnitude of the minus deviation (0.01 means
        # -0.01, legacy contract); a *negative* tol_lower expresses a plus
        # lower deviation, which double-positive ISO 286 fits (e.g. p6
        # +0.035/+0.022) require.
        override.update(
            {
                "dimtol": 1,
                "dimlim": 0,
                "dimtp": float(tol_upper),
                "dimtm": float(tol_lower),
            }
        )
    elif mode == "limit":
        if tol_upper is None or tol_lower is None:
            raise ValueError("tol_mode='limit' requires tol_upper and tol_lower.")
        override.update(
            {
                "dimlim": 1,
                "dimtol": 0,
                "dimtp": float(tol_upper),
                "dimtm": float(tol_lower),
            }
        )
    elif mode == "basic":
        # Theoretically-exact dimension: a box around the text. In AutoCAD a
        # negative DIMGAP draws that box.
        override.update({"dimgap": -1.0})

    text = text_override if text_override not in (None, "") else None
    return override, text
