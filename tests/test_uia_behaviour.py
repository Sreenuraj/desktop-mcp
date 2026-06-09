"""UIA adapter behaviour tests.

Covers the three behaviours that directly affect agent reliability:

1. Empty snapshot detection (Phase 1.1)
   - SnapshotEmptyError is raised with a structured hint when UIA returns
     no interactive controls for a visible window.
   - Zero-size (minimised/hidden) windows do NOT raise — they're genuinely empty.
   - uia_state is "denied" when children() raises, "empty" when it returns [].

2. Pattern-first interaction dispatch (Phase 2.1)
   - Buttons use InvokePattern (required_foreground=False).
   - CheckBoxes use TogglePattern.
   - Edit controls use ValuePattern.SetValue.
   - Fallback to click_input when the pattern raises.
   - Result always carries method, required_foreground, foreground_taken, took_ms.

3. Phase 3 helpers
   - _is_uwp_host detects ApplicationFrameWindow class names.
   - _z_order_prewarm is a no-op when win32gui is None (safe on macOS).
   - get_window uses UWP child fallback when first snapshot is empty.
   - get_window uses foreground-retry fallback when Z-order prewarm fails.

All tests use mocks — no Windows dependencies required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import desktop_mcp.adapters.windows.uia_adapter as uia_mod
from desktop_mcp.adapters.windows.uia_adapter import (
    WindowsUIAutomationAdapter,
    _controls_are_structural_only,
    _is_uwp_host,
    _z_order_prewarm,
)
from desktop_mcp.errors import ControlDisabledError, SnapshotEmptyError
from desktop_mcp.models.control import Control


# ---------------------------------------------------------------------------
# Fixtures — patch Windows globals for every test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_win32(monkeypatch):
    win32gui = MagicMock()
    win32gui.GetForegroundWindow.return_value = 0
    win32gui.GetWindowText.return_value = ""
    win32gui.GetClassName.return_value = ""
    win32con = MagicMock()
    win32con.SW_SHOW = 5
    monkeypatch.setattr(uia_mod, "win32gui", win32gui)
    monkeypatch.setattr(uia_mod, "win32con", win32con)
    monkeypatch.setattr(uia_mod, "win32process", MagicMock())
    monkeypatch.setattr(uia_mod, "ctypes_mod", MagicMock())
    monkeypatch.setattr(uia_mod, "PyWinApplication", MagicMock())
    monkeypatch.setattr(uia_mod, "PyWinDesktop", MagicMock())
    monkeypatch.setattr(uia_mod, "psutil", MagicMock())
    monkeypatch.setattr(uia_mod, "ImageGrab", MagicMock())
    monkeypatch.setattr(uia_mod, "pywinauto_mouse", MagicMock())
    return win32gui


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_win(
    handle=12345,
    title="Calculator",
    rect_w=400,
    rect_h=300,
    children=None,
    descendants=None,
    minimized=False,
):
    win = MagicMock()
    win.handle = handle
    win.window_text.return_value = title
    win.process_id.return_value = 9999
    win.is_minimized.return_value = minimized
    rect = MagicMock()
    rect.width.return_value = rect_w
    rect.height.return_value = rect_h
    win.rectangle.return_value = rect
    win.children.return_value = children or []
    win.descendants.return_value = descendants or []
    win.set_focus = MagicMock()
    return win


def _make_element(name="OK", ctrl_type="Button", enabled=True):
    el = MagicMock()
    el.element_info.name = name
    el.element_info.control_type = ctrl_type
    el.element_info.automation_id = f"id_{name}"
    el.element_info.runtime_id = [1, 2, id(el) % 10000]
    el.element_info.focused = False
    el.is_enabled.return_value = enabled
    el.is_visible.return_value = True
    rect = MagicMock()
    rect.left, rect.top = 0, 0
    rect.width.return_value = 80
    rect.height.return_value = 30
    el.rectangle.return_value = rect
    el.children.return_value = []
    el.window_text.return_value = name
    el.get_value = MagicMock(return_value=None)
    return el


def _adapter_with_window(win_wrapper, monkeypatch):
    adapter = WindowsUIAutomationAdapter()
    monkeypatch.setattr(adapter, "_check_platform", lambda: None)
    monkeypatch.setattr(adapter, "_resolve_window", lambda _: win_wrapper)
    return adapter


def _adapter_with_control(el, monkeypatch):
    adapter = WindowsUIAutomationAdapter()
    monkeypatch.setattr(adapter, "_check_platform", lambda: None)
    monkeypatch.setattr(adapter, "_resolve_control", lambda _: el)
    return adapter


# ===========================================================================
# 1. Empty snapshot detection
# ===========================================================================

class TestSnapshotEmptyDetection:

    def test_raises_snapshot_empty_for_visible_window_with_no_controls(self, monkeypatch):
        win = _make_win(children=[], descendants=[])
        adapter = _adapter_with_window(win, monkeypatch)
        with pytest.raises(SnapshotEmptyError) as exc:
            adapter.get_window("win_12345")
        assert exc.value.code == "SNAPSHOT_EMPTY"

    def test_error_details_include_hint_with_recovery_steps(self, monkeypatch):
        win = _make_win(children=[], descendants=[])
        adapter = _adapter_with_window(win, monkeypatch)
        with pytest.raises(SnapshotEmptyError) as exc:
            adapter.get_window("win_12345")
        hint = exc.value.details["hint"]
        assert "activate_window" in hint
        assert "capture_window" in hint

    def test_uia_state_is_denied_when_children_raises(self, monkeypatch):
        win = _make_win()
        win.children.side_effect = Exception("Access denied")
        win.descendants.return_value = []
        adapter = _adapter_with_window(win, monkeypatch)
        with pytest.raises(SnapshotEmptyError) as exc:
            adapter.get_window("win_12345")
        assert exc.value.details["uia_state"] == "denied"

    def test_uia_state_is_empty_when_children_returns_nothing(self, monkeypatch):
        win = _make_win(children=[], descendants=[])
        adapter = _adapter_with_window(win, monkeypatch)
        with pytest.raises(SnapshotEmptyError) as exc:
            adapter.get_window("win_12345")
        assert exc.value.details["uia_state"] == "empty"

    def test_zero_size_window_does_not_raise(self, monkeypatch):
        """Minimised/hidden windows have zero bounds — not an error."""
        win = _make_win(children=[], descendants=[], rect_w=0, rect_h=0)
        adapter = _adapter_with_window(win, monkeypatch)
        result = adapter.get_window("win_12345")
        assert result.controls == []

    def test_success_attaches_snapshot_metadata(self, monkeypatch):
        btn = _make_element("Seven", "Button")
        win = _make_win(children=[btn])
        adapter = _adapter_with_window(win, monkeypatch)
        result = adapter.get_window("win_12345")
        meta = getattr(result, "_snapshot_meta", None)
        assert meta is not None
        assert meta["uia_state"] == "live"
        assert meta["controls_count"] > 0
        assert "capture_method" in meta


# ===========================================================================
# 2. Pattern-first interaction dispatch
# ===========================================================================

class TestPatternFirstDispatch:

    def test_button_click_uses_invoke_pattern(self, monkeypatch):
        el = _make_element("OK", "Button")
        el.invoke = MagicMock()
        adapter = _adapter_with_control(el, monkeypatch)
        result = adapter.interact("click", "ctrl_1")
        el.invoke.assert_called_once()
        assert result["method"] == "uia_invoke"
        assert result["required_foreground"] is False

    def test_button_invoke_failure_falls_back_to_click_input(self, monkeypatch):
        el = _make_element("OK", "Button")
        el.invoke = MagicMock(side_effect=Exception("COM error"))
        el.top_level_parent = MagicMock(return_value=_make_win())
        adapter = _adapter_with_control(el, monkeypatch)
        result = adapter.interact("click", "ctrl_1")
        el.click_input.assert_called_once()
        assert result["method"] == "click_input"

    def test_checkbox_click_uses_toggle_pattern(self, monkeypatch):
        el = _make_element("Accept", "CheckBox")
        el.toggle = MagicMock()
        adapter = _adapter_with_control(el, monkeypatch)
        result = adapter.interact("click", "ctrl_1")
        el.toggle.assert_called_once()
        assert result["method"] == "uia_toggle"
        assert result["required_foreground"] is False

    def test_edit_enter_text_uses_value_pattern(self, monkeypatch):
        el = _make_element("Name", "Edit")
        el.set_edit_text = MagicMock()
        adapter = _adapter_with_control(el, monkeypatch)
        result = adapter.interact("enter_text", "ctrl_1", value="hello")
        el.set_edit_text.assert_called_once_with("hello")
        assert result["method"] == "uia_value"
        assert result["required_foreground"] is False

    def test_list_item_click_uses_select_pattern(self, monkeypatch):
        el = _make_element("Option A", "ListItem")
        el.select = MagicMock()
        adapter = _adapter_with_control(el, monkeypatch)
        result = adapter.interact("click", "ctrl_1")
        el.select.assert_called_once()
        assert result["method"] == "uia_select"

    def test_disabled_control_raises_control_disabled(self, monkeypatch):
        el = _make_element("OK", "Button", enabled=False)
        adapter = _adapter_with_control(el, monkeypatch)
        with pytest.raises(ControlDisabledError):
            adapter.interact("click", "ctrl_1")

    def test_result_always_has_required_fields(self, monkeypatch):
        el = _make_element("OK", "Button")
        el.invoke = MagicMock()
        adapter = _adapter_with_control(el, monkeypatch)
        result = adapter.interact("click", "ctrl_1")
        for field in ("action", "control_id", "method", "required_foreground",
                      "foreground_taken", "foreground_restored", "took_ms"):
            assert field in result, f"Missing field: {field}"

    def test_restore_foreground_false_skips_restore(self, monkeypatch):
        el = _make_element("OK", "Button")
        el.invoke = MagicMock()
        adapter = _adapter_with_control(el, monkeypatch)
        result = adapter.interact("click", "ctrl_1", restore_foreground=False)
        assert result["foreground_restored"] is False


# ===========================================================================
# 3. Phase 3 helpers
# ===========================================================================

class TestPhase3Helpers:

    def test_is_uwp_host_detects_application_frame_window(self, monkeypatch):
        monkeypatch.setattr(uia_mod, "win32gui", MagicMock(
            GetClassName=MagicMock(return_value="ApplicationFrameWindow")
        ))
        assert _is_uwp_host(12345) is True

    def test_is_uwp_host_returns_false_for_normal_window(self, monkeypatch):
        monkeypatch.setattr(uia_mod, "win32gui", MagicMock(
            GetClassName=MagicMock(return_value="Chrome_WidgetWin_1")
        ))
        assert _is_uwp_host(12345) is False

    def test_z_order_prewarm_is_safe_when_win32gui_is_none(self, monkeypatch):
        monkeypatch.setattr(uia_mod, "win32gui", None)
        # Must not raise
        _z_order_prewarm(12345)

    def test_get_window_uses_uwp_child_when_host_is_empty(self, monkeypatch):
        """When the UWP host returns no controls, the real child is snapshotted."""
        # Host window: empty
        host = _make_win(handle=1000, children=[], descendants=[])
        # Real child window: has a button
        btn = _make_element("Seven", "Button")
        child = _make_win(handle=2000, children=[btn])

        adapter = WindowsUIAutomationAdapter()
        monkeypatch.setattr(adapter, "_check_platform", lambda: None)
        monkeypatch.setattr(adapter, "_resolve_window", lambda _: host)

        # Make _is_uwp_host return True for the host handle
        monkeypatch.setattr(uia_mod, "_is_uwp_host", lambda hwnd: hwnd == 1000)
        # Make _find_uwp_real_child return the child wrapper
        monkeypatch.setattr(uia_mod, "_find_uwp_real_child", lambda _: child)

        result = adapter.get_window("win_1000")
        assert len(result.controls) > 0
        assert result._snapshot_meta["capture_method"].startswith("uwp_child_")

    def test_get_window_uses_foreground_retry_when_prewarm_fails(self, monkeypatch):
        """When Z-order prewarm yields nothing, a foreground retry succeeds.

        _snapshot_wrapper calls children() once per pass.  The first pass
        (prewarm) calls children() → returns [] → then calls descendants() →
        returns [].  The second pass (fg retry) calls children() → returns [btn].
        So children() is called twice total: call 1 = empty, call 2 = [btn].
        """
        btn = _make_element("Seven", "Button")
        call_count = {"n": 0}

        def _children_side_effect():
            call_count["n"] += 1
            if call_count["n"] == 1:
                return []   # first pass (prewarm): empty
            return [btn]    # second pass (fg retry): has button

        win = _make_win(handle=3000)
        win.children.side_effect = _children_side_effect
        win.descendants.return_value = []

        adapter = WindowsUIAutomationAdapter()
        monkeypatch.setattr(adapter, "_check_platform", lambda: None)
        monkeypatch.setattr(adapter, "_resolve_window", lambda _: win)
        monkeypatch.setattr(uia_mod, "_is_uwp_host", lambda _: False)

        result = adapter.get_window("win_3000")
        assert len(result.controls) > 0
        assert "fg_retry" in result._snapshot_meta["capture_method"]
