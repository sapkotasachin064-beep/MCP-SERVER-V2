"""Sprint-4 R27 regression tests for engineering.validator step 5.

R27: title/helix consistency must match SPUR / HELICAL as whole words (not
substrings) and scope the scan to title-block text where possible.
"""

import pytest

from engineering.layers import ensure_engineering_layers, ensure_standard_linetypes
from engineering.validator import DrawingValidator

pytestmark = pytest.mark.asyncio


def _codes(result) -> set[str]:
    return {f.code for f in result.findings}


async def _ensure_hidden_linetype(backend) -> None:
    """ezdxf doesn't ship a HIDDEN pattern; add a synthetic one."""
    doc = backend._require_doc()
    if "HIDDEN" not in doc.linetypes:
        doc.linetypes.add(
            "HIDDEN",
            pattern=[6.35, 5.0, -1.27],
            description="Hidden _ _ _ _ _ _",
        )


async def _bootstrap(backend):
    await ensure_standard_linetypes(backend)
    await _ensure_hidden_linetype(backend)
    await ensure_engineering_layers(backend)


async def test_spur_as_substring_does_not_false_match(backend, tmp_path):
    """R27: 'SPURIOUS' contains 'spur' but must NOT trip a SPUR mismatch."""
    await _bootstrap(backend)
    await backend.entity_create_text(
        text="SPURIOUS HELICAL GEAR",
        x=0,
        y=0,
        height=5,
        layer="TEXT",
    )
    await backend.drawing_save_as(str(tmp_path / "spurious.dxf"))
    result = await DrawingValidator().run(backend, expected={"helix_angle": 15})
    codes = _codes(result)
    assert "title_says_spur_for_helical" not in codes
    assert "title_helical_spur" not in codes


async def test_genuine_spur_title_flags_when_helical_expected(backend, tmp_path):
    """R27: a real 'SPUR GEAR' title still flags the mismatch when helix declared."""
    await _bootstrap(backend)
    await backend.entity_create_text(
        text="SPUR GEAR",
        x=0,
        y=0,
        height=5,
        layer="TEXT",
    )
    await backend.drawing_save_as(str(tmp_path / "spur.dxf"))
    result = await DrawingValidator().run(backend, expected={"helix_angle": 15})
    codes = _codes(result)
    assert "title_says_spur_for_helical" in codes
    assert result.ok is False


async def test_spur_word_in_titleblock_layer_flags(backend, tmp_path):
    """R27: title-block-scoped scan — SPUR on TITLEBLOCK layer still flags."""
    await _bootstrap(backend)
    await backend.entity_create_text(
        text="SPUR GEAR",
        x=0,
        y=0,
        height=5,
        layer="TITLEBLOCK",
    )
    await backend.drawing_save_as(str(tmp_path / "spur_tb.dxf"))
    result = await DrawingValidator().run(backend, expected={"helix_angle": 15})
    assert "title_says_spur_for_helical" in _codes(result)


async def test_substring_in_titleblock_layer_does_not_false_match(backend, tmp_path):
    """R27: 'SPURIOUS' on TITLEBLOCK layer must not trip a SPUR match either."""
    await _bootstrap(backend)
    await backend.entity_create_text(
        text="SPURIOUS NOTE",
        x=0,
        y=0,
        height=5,
        layer="TITLEBLOCK",
    )
    await backend.drawing_save_as(str(tmp_path / "spurious_tb.dxf"))
    result = await DrawingValidator().run(backend, expected={"helix_angle": 15})
    codes = _codes(result)
    assert "title_says_spur_for_helical" not in codes
    assert "title_helical_spur" not in codes


async def test_helical_spur_combo_still_flags_invalid(backend, tmp_path):
    """R27: both whole words present -> invalid combo error preserved."""
    await _bootstrap(backend)
    await backend.entity_create_text(
        text="HELICAL SPUR GEAR",
        x=0,
        y=0,
        height=5,
        layer="TEXT",
    )
    await backend.drawing_save_as(str(tmp_path / "combo.dxf"))
    result = await DrawingValidator().run(backend, expected={"helix_angle": 15})
    assert "title_helical_spur" in _codes(result)
    assert result.ok is False


async def test_no_helix_expected_skips_title_check(backend, tmp_path):
    """Gating preserved: without helix_angle, a SPUR title raises no title finding."""
    await _bootstrap(backend)
    await backend.entity_create_text(
        text="SPUR GEAR",
        x=0,
        y=0,
        height=5,
        layer="TEXT",
    )
    await backend.drawing_save_as(str(tmp_path / "nohelix.dxf"))
    result = await DrawingValidator().run(backend)
    codes = _codes(result)
    assert "title_says_spur_for_helical" not in codes
    assert "title_helical_spur" not in codes


async def test_titleblock_layer_takes_precedence_over_text_layer(backend, tmp_path):
    """R27 scoping: when title-block text exists, the TEXT-layer scan is not used.

    SPUR sits on the generic TEXT layer (a body note), while the title block on
    TITLEBLOCK is clean — the scoped scan should ignore the body note.
    """
    await _bootstrap(backend)
    await backend.entity_create_text(
        text="HELICAL GEAR",
        x=0,
        y=0,
        height=5,
        layer="TITLEBLOCK",
    )
    await backend.entity_create_text(
        text="SPUR TOOTH DETAIL NOTE",
        x=0,
        y=-20,
        height=3.5,
        layer="TEXT",
    )
    await backend.drawing_save_as(str(tmp_path / "scope.dxf"))
    result = await DrawingValidator().run(backend, expected={"helix_angle": 15})
    codes = _codes(result)
    assert "title_says_spur_for_helical" not in codes
    assert "title_helical_spur" not in codes
