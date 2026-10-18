"""Mocked-COM regression tests for the Sprint-4 COM fixes.

These run without a live AutoCAD (and OS-agnostically) by:
  * patching the module-level ``_acad_app`` / ``_acad_doc`` with MagicMocks, and
  * forcing ``_WIN32_AVAILABLE`` True so the win32-guarded paths execute
    (no real win32 calls are made — every win32 attribute is mocked).
  * bypassing the STA executor (replace ``_run`` with a direct caller).

Covers: R28 (_find_autocad_hwnd prefers Application.HWND over EnumWindows),
S3 (block_list populates BlockInfo.description from the definition .Comments).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import backends.com_backend as cb
from backends.com_backend import ComBackend

pytestmark = pytest.mark.asyncio


def _backend_no_executor() -> ComBackend:
    b = ComBackend()

    async def _run(func, *args, **kwargs):  # bypass the ThreadPoolExecutor
        return func(*args, **kwargs)

    b._run = _run
    return b


# ── R28 — _find_autocad_hwnd prefers Application.HWND over EnumWindows ───────


async def test_find_hwnd_prefers_application_hwnd(monkeypatch):
    """The real main-frame handle from the COM app wins; EnumWindows is not
    consulted when the HWND read succeeds."""
    app = MagicMock()
    app.HWND = 0xABCD  # known int handle
    monkeypatch.setattr(cb, "_acad_app", lambda: app)
    monkeypatch.setattr(cb, "_WIN32_AVAILABLE", True)

    enum = MagicMock(side_effect=AssertionError("EnumWindows must not be called"))
    # raising=False: the win32gui module global only exists on Windows; the
    # mock must be injectable on the Linux CI leg as well.
    monkeypatch.setattr(cb, "win32gui", MagicMock(EnumWindows=enum), raising=False)

    assert cb._find_autocad_hwnd() == 0xABCD
    enum.assert_not_called()


async def test_find_hwnd_coerces_hwnd_to_int(monkeypatch):
    """A COM HWND that arrives as a numeric string is coerced to int."""
    app = MagicMock()
    app.HWND = "43981"  # COM can hand back a stringy handle
    monkeypatch.setattr(cb, "_acad_app", lambda: app)
    monkeypatch.setattr(cb, "_WIN32_AVAILABLE", True)
    monkeypatch.setattr(cb, "win32gui", MagicMock(), raising=False)

    result = cb._find_autocad_hwnd()
    assert result == 43981
    assert isinstance(result, int)


async def test_find_hwnd_falls_back_to_enumwindows(monkeypatch):
    """When the HWND read raises, the EnumWindows title scan is used as a
    fallback and its discovered handle is returned."""
    app = MagicMock()
    type(app).HWND = property(  # reading .HWND raises
        lambda self: (_ for _ in ()).throw(RuntimeError("no HWND"))
    )
    monkeypatch.setattr(cb, "_acad_app", lambda: app)
    monkeypatch.setattr(cb, "_WIN32_AVAILABLE", True)

    def _enum_windows(cb_fn, _extra):
        # Simulate one visible AutoCAD top-level window.
        cb_fn(0x1234, None)

    win32gui = MagicMock()
    win32gui.EnumWindows.side_effect = _enum_windows
    win32gui.GetWindowText.return_value = "AutoCAD 2025 - [Drawing1.dwg]"
    win32gui.IsWindowVisible.return_value = True
    monkeypatch.setattr(cb, "win32gui", win32gui, raising=False)

    assert cb._find_autocad_hwnd() == 0x1234
    win32gui.EnumWindows.assert_called_once()


async def test_find_hwnd_returns_none_when_win32_unavailable(monkeypatch):
    """Short-circuits to None on non-Windows without touching the COM app."""
    sentinel = MagicMock(side_effect=AssertionError("_acad_app must not be called"))
    monkeypatch.setattr(cb, "_acad_app", sentinel)
    monkeypatch.setattr(cb, "_WIN32_AVAILABLE", False)

    assert cb._find_autocad_hwnd() is None
    sentinel.assert_not_called()


# ── S3 — block_list populates BlockInfo.description from .Comments ───────────


class _Block:
    """Minimal stand-in for an AutoCAD block definition."""

    def __init__(self, name, comments="", count=0, is_xref=False, raise_comments=False):
        self.Name = name
        self._comments = comments
        self.Count = count
        self.IsXRef = is_xref
        self.Origin = (0.0, 0.0, 0.0)
        self._raise_comments = raise_comments

    @property
    def Comments(self):
        if self._raise_comments:
            raise RuntimeError("Comments not supported")
        return self._comments

    def Item(self, _j):  # no attribute definitions in these fixtures
        return MagicMock(ObjectName="AcDbEntity")


class _Blocks:
    def __init__(self, items):
        self._items = items
        self.Count = len(items)

    def Item(self, i):
        return self._items[i]


def _doc_with_blocks(items):
    doc = MagicMock()
    doc.Blocks = _Blocks(items)
    return doc


async def test_block_list_populates_description_from_comments(monkeypatch):
    doc = _doc_with_blocks([_Block("BOLT", comments="M8 hex bolt")])
    monkeypatch.setattr(cb, "_acad_doc", lambda: doc)

    b = _backend_no_executor()
    blocks = await b.block_list()

    assert len(blocks) == 1
    assert blocks[0].name == "BOLT"
    assert blocks[0].description == "M8 hex bolt"


async def test_block_list_description_defaults_empty_when_comments_raise(monkeypatch):
    doc = _doc_with_blocks([_Block("NUT", raise_comments=True)])
    monkeypatch.setattr(cb, "_acad_doc", lambda: doc)

    b = _backend_no_executor()
    blocks = await b.block_list()

    assert blocks[0].description == ""  # try/except default, not a crash


async def test_block_list_description_empty_when_comments_none(monkeypatch):
    doc = _doc_with_blocks([_Block("WASHER", comments=None)])
    monkeypatch.setattr(cb, "_acad_doc", lambda: doc)

    b = _backend_no_executor()
    blocks = await b.block_list()

    assert blocks[0].description == ""  # `Comments or ""` normalises None


async def test_block_list_skips_anonymous_layout_blocks(monkeypatch):
    doc = _doc_with_blocks(
        [
            _Block("*Model_Space", comments="ignored"),
            _Block("GEAR", comments="spur gear"),
        ]
    )
    monkeypatch.setattr(cb, "_acad_doc", lambda: doc)

    b = _backend_no_executor()
    blocks = await b.block_list()

    assert [blk.name for blk in blocks] == ["GEAR"]
    assert blocks[0].description == "spur gear"
