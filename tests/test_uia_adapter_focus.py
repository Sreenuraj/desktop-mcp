"""Tests for Phase 1.1 + 1.2 — UIA adapter empty-result detection and
enriched action results.

All tests use mocks so they run on macOS/Linux without pywinauto.

Covers:
- SnapshotEmptyError is raised when UIA returns an empty tree for a
  window with non-trivial bounds.
- SnapshotEmptyError details include window_id, title, is_foreground,
  uia_state, took_ms, hint.
- Windows with zero-size bounds do NOT raise SnapshotEmptyError (they
  are genuinely invisible/minimised).
- interact() returns method, required_foreground, foreground_taken,
  took_ms on success.
- activate_window() returns the full observable-state dict.
- _controls_are_structural_only() helper works correctly.
- _has_non_trivial_bounds() helper works correctly.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock
import sys
import types

import pytest

# ---------------------------------------------------------------------------
# Patch Windows-only imports so the module loads on macOS
# ---------------------------------------------------------------------------

def _make_win32_stubs():
    """Return a minimal set of win32 stubs so uia_adapter imports cleanly."""
    win32gui = MagicMock()
    win32gui.GetForegroundWindow.return_value = 0
    win32gui.GetWindowText.return_value = ""
    win32con = MagicMock()
    win32con.SW_SHOW = 5
    return win32gui, win32con


@pytest.fixture(autouse=True)
def patch_win32(monkeypatch):
    """Ensure win32 globals in uia_adapter are set to mocks for every test."""
    import desktop_mcp.adapters.windows.uia_adapter as mod

    win32gui, win32con = _make_win32_stubs()
    monkeypatch.setattr(mod, "win32gui", win32gui)
    monkeypatch.setattr(mod, "win32con", win32con)
    monkeypatch.setattr(mod, "PyWinApplication", MagicMock())
    monkeypatch.setattr(mod, "PyWinDesktop", MagicMock())
    monkeypatch.setattr(mod, "psutil", MagicMock())
    monkeypatch.setattr(mod, "ImageGrab", MagicMock())
    monkeypatch.setattr(mod, "pywinauto_mouse", MagicMock())
    # Force platform check to pass
    monkeypatch.setattr(mod, "_check_platform_override", None, raising=False)
    return win32gui, win32con


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _make_element(
    name: str = "Button1",
    control_type: str = "Button",
    automation_id: str = "btn1",
    enabled: bool = True,
    visible: bool = True,
    focused: bool = False,
    runtime_id: list | None = None,
    rect_left: int = 0,
    rect_top: int = 0,
    rect_width: int = 100,
    rect_height: int = 30,
    children: list | None = None,
) -> MagicMock:
    el = MagicMock()
    info = MagicMock()
    info.name = name
    info.control_type = control_type
    info.automation_id = automation_id
    info.focused = focused
    info.runtime_id = runtime_id or [1, 2, 3]
    el.element_info = info
    el.is_enabled.return_value = enabled
    el.is_visible.return_value = visible

    rect = MagicMock()
    rect.left = rect_left
    rect.top = rect_top
    rect.width.return_value = rect_width
    rect.height.return_value = rect_height
    rect.right = rect_left + rect_width
    rect.bottom = rect_top + rect_height
    el.rectangle.return_value = rect

    el.children.return_value = children or []
    el.window_text.return_value = name
    el.get_value = MagicMock(return_value=None)
    return el


def _make_window_wrapper(
    handle: int = 12345,
    title: str = "Calculator",
    process_id: int = 9999,
    rect_width: int = 400,
    rect_height: int = 300,
    children: list | None = None,
    descendants: list | None = None,
    is_minimized: bool = False,
) -> MagicMock:
    win = MagicMock()
    win.handle = handle
    win.window_text.return_value = title
    win.process_id.return_value = process_id
    win.is_minimized.return_value = is_minimized

    rect = MagicMock()
    rect.left = 0
    rect.top = 0
    rect.width.return_value = rect_width
    rect.height.return_value = rect_height
    win.rectangle.return_value = rect

    win.children.return_value = children or []
    win.descendants.return_value = descendants or []
    win.set_focus = MagicMock()
    return win


# ---------------------------------------------------------------------------
# Import the module under test (after patching)
# ---------------------------------------------------------------------------

import desktop_mcp.adapters.windows.uia_adapter as uia_mod
from desktop_mcp.adapters.windows.uia_adapter import (
    WindowsUIAutomationAdapter,
    _controls_are_structural_only,
    _has_non_trivial_bounds,
)
from desktop_mcp.errors import SnapshotEmptyError
from desktop_mcp.models.control import Control


# ---------------------------------------------------------------------------
# _controls_are_structural_only helper
# ---------------------------------------------------------------------------

class TestControlsAreStructuralOnly:
    def test_empty_list_is_structural_only(self):
        assert _controls_are_structural_only([]) is True

    def test_pane_only_is_structural(self):
        c = Control(id="c1", name="", type="Pane")
        assert _controls_are_structural_only([c]) is True

    def test_window_only_is_structural(self):
        c = Control(id="c1", name="", type="Window")
        assert _controls_are_structural_only([c]) is True

    def test_button_is_not_structural(self):
        c = Control(id="c1", name="OK", type="Button")
        assert _controls_are_structural_only([c]) is False

    def test_mixed_structural_and_button_is_not_structural(self):
        controls = [
            Control(id="c1", name="", type="Pane"),
            Control(id="c2", name="OK", type="Button"),
        ]
        assert _controls_are_structural_only(controls) is False

    def test_group_and_custom_are_structural(self):
        controls = [
            Control(id="c1", name="", type="Group"),
            Control(id="c2", name="", type="Custom"),
            Control(id="c3", name="", type="Separator"),
        ]
        assert _controls_are_structural_only(controls) is True

    def test_edit_is_not_structural(self):
        c = Control(id="c1", name="Name", type="Edit")
        assert _controls_are_structural_only([c]) is False


# ---------------------------------------------------------------------------
# _has_non_trivial_bounds helper
# ---------------------------------------------------------------------------

class TestHasNonTrivialBounds:
    def test_normal_window_has_non_trivial_bounds(self):
        win = _make_window_wrapper(rect_width=400, rect_height=300)
        assert _has_non_trivial_bounds(win) is True

    def test_zero_width_is_trivial(self):
        win = _make_window_wrapper(rect_width=0, rect_height=300)
        assert _has_non_trivial_bounds(win) is False

    def test_zero_height_is_trivial(self):
        win = _make_window_wrapper(rect_width=400, rect_height=0)
        assert _has_non_trivial_bounds(win) is False

    def test_zero_both_is_trivial(self):
        win = _make_window_wrapper(rect_width=0, rect_height=0)
        assert _has_non_trivial_bounds(win) is False

    def test_exception_returns_true(self):
        """If rectangle() raises, assume non-trivial (conservative)."""
        win = MagicMock()
        win.rectangle.side_effect = Exception("COM error")
        assert _has_non_trivial_bounds(win) is True


# ---------------------------------------------------------------------------
# get_window — SnapshotEmptyError detection (Phase 1.1)
# ---------------------------------------------------------------------------

class TestGetWindowSnapshotEmptyError:
    def _make_adapter(self, win_wrapper, monkeypatch):
        adapter = WindowsUIAutomationAdapter()
        monkeypatch.setattr(adapter, "_check_platform", lambda: None)
        monkeypatch.setattr(adapter, "_resolve_window", lambda wid: win_wrapper)
        return adapter

    def test_raises_snapshot_empty_when_children_empty_and_has_bounds(self, monkeypatch):
        win = _make_window_wrapper(children=[], descendants=[], rect_width=400, rect_height=300)
        adapter = self._make_adapter(win, monkeypatch)

        with pytest.raises(SnapshotEmptyError) as exc_info:
            adapter.get_window("win_12345")

        assert exc_info.value.code == "SNAPSHOT_EMPTY"

    def test_snapshot_empty_details_include_window_id(self, monkeypatch):
        win = _make_window_wrapper(children=[], descendants=[], rect_width=400, rect_height=300)
        adapter = self._make_adapter(win, monkeypatch)

        with pytest.raises(SnapshotEmptyError) as exc_info:
            adapter.get_window("win_12345")

        assert exc_info.value.details["window_id"] == "win_12345"

    def test_snapshot_empty_details_include_title(self, monkeypatch):
        win = _make_window_wrapper(
            title="Calculator", children=[], descendants=[], rect_width=400, rect_height=300
        )
        adapter = self._make_adapter(win, monkeypatch)

        with pytest.raises(SnapshotEmptyError) as exc_info:
            adapter.get_window("win_12345")

        assert exc_info.value.details["title"] == "Calculator"

    def test_snapshot_empty_details_include_uia_state(self, monkeypatch):
        win = _make_window_wrapper(children=[], descendants=[], rect_width=400, rect_height=300)
        adapter = self._make_adapter(win, monkeypatch)

        with pytest.raises(SnapshotEmptyError) as exc_info:
            adapter.get_window("win_12345")

        assert exc_info.value.details["uia_state"] in ("empty", "denied")

    def test_snapshot_empty_details_include_hint(self, monkeypatch):
        win = _make_window_wrapper(children=[], descendants=[], rect_width=400, rect_height=300)
        adapter = self._make_adapter(win, monkeypatch)

        with pytest.raises(SnapshotEmptyError) as exc_info:
            adapter.get_window("win_12345")

        hint = exc_info.value.details.get("hint", "")
        assert "activate_window" in hint

    def test_snapshot_empty_details_include_took_ms(self, monkeypatch):
        win = _make_window_wrapper(children=[], descendants=[], rect_width=400, rect_height=300)
        adapter = self._make_adapter(win, monkeypatch)

        with pytest.raises(SnapshotEmptyError) as exc_info:
            adapter.get_window("win_12345")

        assert "took_ms" in exc_info.value.details
        assert isinstance(exc_info.value.details["took_ms"], int)

    def test_no_error_when_window_has_zero_bounds(self, monkeypatch):
        """Zero-size window (minimised/hidden) should NOT raise SnapshotEmptyError."""
        win = _make_window_wrapper(children=[], descendants=[], rect_width=0, rect_height=0)
        adapter = self._make_adapter(win, monkeypatch)

        # Should not raise — just return a Window with empty controls
        result = adapter.get_window("win_12345")
        assert result.controls == []

    def test_no_error_when_controls_present(self, monkeypatch):
        """When UIA returns real controls, no error should be raised."""
        btn = _make_element(name="Seven", control_type="Button")
        win = _make_window_wrapper(children=[btn], rect_width=400, rect_height=300)
        adapter = self._make_adapter(win, monkeypatch)

        result = adapter.get_window("win_12345")
        assert len(result.controls) > 0

    def test_uia_state_is_denied_when_children_raises(self, monkeypatch):
        """If children() raises an exception, uia_state should be 'denied'."""
        win = _make_window_wrapper(rect_width=400, rect_height=300)
        win.children.side_effect = Exception("Access denied")
        win.descendants.return_value = []
        adapter = self._make_adapter(win, monkeypatch)

        with pytest.raises(SnapshotEmptyError) as exc_info:
            adapter.get_window("win_12345")

        assert exc_info.value.details["uia_state"] == "denied"

    def test_snapshot_meta_attached_on_success(self, monkeypatch):
        """On success, _snapshot_meta should be attached to the Window object."""
        btn = _make_element(name="Seven", control_type="Button")
        win = _make_window_wrapper(children=[btn], rect_width=400, rect_height=300)
        adapter = self._make_adapter(win, monkeypatch)

        result = adapter.get_window("win_12345")
        meta = getattr(result, "_snapshot_meta", None)
        assert meta is not None
        assert "controls_count" in meta
        assert "capture_method" in meta
        assert "uia_state" in meta
        assert meta["uia_state"] == "live"
        assert "took_ms" in meta


# ---------------------------------------------------------------------------
# activate_window — observable state (Phase 1.2)
# ---------------------------------------------------------------------------

class TestActivateWindowObservableState:
    def _make_adapter(self, win_wrapper, monkeypatch, fg_hwnd=0):
        adapter = WindowsUIAutomationAdapter()
        monkeypatch.setattr(adapter, "_check_platform", lambda: None)
        monkeypatch.setattr(adapter, "_resolve_window", lambda wid: win_wrapper)
        # Make win32gui return the window as foreground after first attempt
        uia_mod.win32gui.GetForegroundWindow.return_value = win_wrapper.handle
        uia_mod.win32gui.GetWindowText.return_value = win_wrapper.window_text()
        return adapter

    def test_returns_dict_not_none(self, monkeypatch):
        win = _make_window_wrapper(handle=99999)
        adapter = self._make_adapter(win, monkeypatch)
        result = adapter.activate_window("win_99999")
        assert isinstance(result, dict)

    def test_result_has_window_id(self, monkeypatch):
        win = _make_window_wrapper(handle=99999)
        adapter = self._make_adapter(win, monkeypatch)
        result = adapter.activate_window("win_99999")
        assert result["window_id"] == "win_99999"

    def test_result_has_is_foreground(self, monkeypatch):
        win = _make_window_wrapper(handle=99999)
        adapter = self._make_adapter(win, monkeypatch)
        result = adapter.activate_window("win_99999")
        assert "is_foreground" in result

    def test_result_has_became_foreground(self, monkeypatch):
        win = _make_window_wrapper(handle=99999)
        adapter = self._make_adapter(win, monkeypatch)
        result = adapter.activate_window("win_99999")
        assert "became_foreground" in result

    def test_result_has_attempts(self, monkeypatch):
        win = _make_window_wrapper(handle=99999)
        adapter = self._make_adapter(win, monkeypatch)
        result = adapter.activate_window("win_99999")
        assert "attempts" in result
        assert isinstance(result["attempts"], int)

    def test_result_has_total_ms(self, monkeypatch):
        win = _make_window_wrapper(handle=99999)
        adapter = self._make_adapter(win, monkeypatch)
        result = adapter.activate_window("win_99999")
        assert "total_ms" in result
        assert isinstance(result["total_ms"], int)

    def test_result_has_foreground_title(self, monkeypatch):
        win = _make_window_wrapper(handle=99999, title="Calculator")
        adapter = self._make_adapter(win, monkeypatch)
        result = adapter.activate_window("win_99999")
        assert "foreground_title" in result

    def test_result_has_foreground_window_id(self, monkeypatch):
        win = _make_window_wrapper(handle=99999)
        adapter = self._make_adapter(win, monkeypatch)
        result = adapter.activate_window("win_99999")
        assert "foreground_window_id" in result


# ---------------------------------------------------------------------------
# interact() — enriched result (Phase 1.2)
# ---------------------------------------------------------------------------

class TestInteractEnrichedResult:
    def _make_adapter_with_control(self, el, monkeypatch):
        adapter = WindowsUIAutomationAdapter()
        monkeypatch.setattr(adapter, "_check_platform", lambda: None)
        monkeypatch.setattr(adapter, "_resolve_control", lambda cid: el)
        return adapter

    def test_click_button_via_invoke_returns_uia_invoke_method(self, monkeypatch):
        el = _make_element(control_type="Button")
        el.invoke = MagicMock()
        adapter = self._make_adapter_with_control(el, monkeypatch)

        result = adapter.interact("click", "ctrl_1_2_3")

        assert result["method"] == "uia_invoke"
        assert result["required_foreground"] is False

    def test_click_button_via_invoke_has_took_ms(self, monkeypatch):
        el = _make_element(control_type="Button")
        el.invoke = MagicMock()
        adapter = self._make_adapter_with_control(el, monkeypatch)

        result = adapter.interact("click", "ctrl_1_2_3")

        assert "took_ms" in result
        assert isinstance(result["took_ms"], int)

    def test_click_button_fallback_to_click_input_when_invoke_fails(self, monkeypatch):
        el = _make_element(control_type="Button")
        el.invoke = MagicMock(side_effect=Exception("COM error"))
        el.top_level_parent = MagicMock(return_value=_make_window_wrapper())
        adapter = self._make_adapter_with_control(el, monkeypatch)

        result = adapter.interact("click", "ctrl_1_2_3")

        assert result["method"] == "click_input"

    def test_enter_text_via_set_edit_text_returns_uia_value(self, monkeypatch):
        el = _make_element(control_type="Edit")
        el.set_edit_text = MagicMock()
        adapter = self._make_adapter_with_control(el, monkeypatch)

        result = adapter.interact("enter_text", "ctrl_1_2_3", value="hello")

        assert result["method"] == "uia_value"
        assert result["required_foreground"] is False

    def test_enter_text_fallback_to_type_keys_when_set_edit_text_fails(self, monkeypatch):
        el = _make_element(control_type="Edit")
        el.set_edit_text = MagicMock(side_effect=Exception("not supported"))
        el.type_keys = MagicMock()
        el.top_level_parent = MagicMock(return_value=_make_window_wrapper())
        adapter = self._make_adapter_with_control(el, monkeypatch)

        result = adapter.interact("enter_text", "ctrl_1_2_3", value="hello")

        assert result["method"] == "type_keys"

    def test_result_always_has_action_and_control_id(self, monkeypatch):
        el = _make_element(control_type="Button")
        el.invoke = MagicMock()
        adapter = self._make_adapter_with_control(el, monkeypatch)

        result = adapter.interact("click", "ctrl_abc")

        assert result["action"] == "click"
        assert result["control_id"] == "ctrl_abc"

    def test_result_has_foreground_taken_field(self, monkeypatch):
        el = _make_element(control_type="Button")
        el.invoke = MagicMock()
        adapter = self._make_adapter_with_control(el, monkeypatch)

        result = adapter.interact("click", "ctrl_1_2_3")

        assert "foreground_taken" in result

    def test_select_item_via_select_returns_uia_select(self, monkeypatch):
        el = _make_element(control_type="ListItem")
        el.select = MagicMock()
        adapter = self._make_adapter_with_control(el, monkeypatch)

        result = adapter.interact("select_item", "ctrl_1_2_3", value="Option A")

        assert result["method"] == "uia_select"
        assert result["required_foreground"] is False
