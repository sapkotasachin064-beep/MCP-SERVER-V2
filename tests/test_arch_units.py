"""``engineering/arch/units.py``: the one feet-to-millimetre conversion a
residential spec built from a feet brief needs before any tool sees it."""

from __future__ import annotations

import pytest

from engineering.arch.units import MM_PER_FT, ft_to_mm


def test_one_foot_is_304_8_mm():
    assert ft_to_mm(1.0) == MM_PER_FT == 304.8


def test_a_40_by_30_ft_plot_in_mm():
    assert ft_to_mm(40.0) == pytest.approx(12192.0)
    assert ft_to_mm(30.0) == pytest.approx(9144.0)


def test_negative_and_zero_are_allowed_a_setback_offset_is_not_a_length():
    assert ft_to_mm(0.0) == 0.0
    assert ft_to_mm(-5.0) == pytest.approx(-1524.0)


def test_non_finite_is_refused():
    with pytest.raises(ValueError, match="must be finite"):
        ft_to_mm(float("nan"))
    with pytest.raises(ValueError, match="must be finite"):
        ft_to_mm(float("inf"))


def test_a_non_number_is_refused():
    with pytest.raises(ValueError):
        ft_to_mm("forty")
