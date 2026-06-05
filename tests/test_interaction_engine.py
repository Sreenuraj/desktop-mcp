from __future__ import annotations

from unittest import mock
import pytest

from desktop_mcp.adapters.windows.uia_adapter import WindowsUIAutomationAdapter
from desktop_mcp.errors import ControlDisabledError, UnsupportedControlError


class MockInteractiveElement:
    def __init__(self, name: str = "", control_type: str = "Button", enabled: bool = True) -> None:
        self.element_info = mock.Mock()
        self.element_info.name = name
        self.element_info.control_type = control_type
        self.element_info.automation_id = f"id_{name}"
        self.element_info.runtime_id = (42, id(self))
        self.element_info.focused = False
        
        self._enabled = enabled
        self._visible = True
        self._value = ""

        self.click_input = mock.Mock()
        self.double_click_input = mock.Mock()
        self.right_click_input = mock.Mock()
        self.move_mouse_input = mock.Mock()
        self.set_focus = mock.Mock()
        self.type_keys = mock.Mock()

    def is_enabled(self) -> bool:
        return self._enabled

    def is_visible(self) -> bool:
        return self._visible

    def rectangle(self) -> mock.Mock:
        rect = mock.Mock()
        rect.left = 10
        rect.top = 20
        rect.width = mock.Mock(return_value=100)
        rect.height = mock.Mock(return_value=50)
        return rect


@pytest.fixture
def adapter():
    a = WindowsUIAutomationAdapter()
    a._check_platform = mock.Mock()
    return a


def test_interact_raises_control_disabled(adapter):
    el = MockInteractiveElement(enabled=False)
    adapter._resolve_control = mock.Mock(return_value=el)

    with pytest.raises(ControlDisabledError):
        adapter.interact("click", "ctrl_123")


def test_interact_click_invoke_pattern(adapter):
    el = MockInteractiveElement(control_type="Button")
    el.invoke = mock.Mock()
    adapter._resolve_control = mock.Mock(return_value=el)

    adapter.interact("click", "ctrl_123")
    el.invoke.assert_called_once()
    el.click_input.assert_not_called()


def test_interact_click_fallback_to_click_input_when_invoke_fails(adapter):
    el = MockInteractiveElement(control_type="Button")
    el.invoke = mock.Mock(side_effect=Exception("COM Error"))
    adapter._resolve_control = mock.Mock(return_value=el)

    adapter.interact("click", "ctrl_123")
    el.invoke.assert_called_once()
    el.click_input.assert_called_once()


def test_interact_click_input_used_when_invoke_missing(adapter):
    el = MockInteractiveElement(control_type="Hyperlink")
    adapter._resolve_control = mock.Mock(return_value=el)

    adapter.interact("click", "ctrl_123")
    el.click_input.assert_called_once()


def test_interact_double_click(adapter):
    el = MockInteractiveElement()
    adapter._resolve_control = mock.Mock(return_value=el)

    adapter.interact("double_click", "ctrl_123")
    el.double_click_input.assert_called_once()


def test_interact_double_click_fallback_when_missing(adapter):
    el = MockInteractiveElement()
    del el.double_click_input
    adapter._resolve_control = mock.Mock(return_value=el)

    adapter.interact("double_click", "ctrl_123")
    assert el.click_input.call_count == 2


def test_interact_right_click_and_hover(adapter):
    el = MockInteractiveElement()
    adapter._resolve_control = mock.Mock(return_value=el)

    adapter.interact("right_click", "ctrl_123")
    el.right_click_input.assert_called_once()

    adapter.interact("hover", "ctrl_123")
    el.move_mouse_input.assert_called_once()


def test_interact_focus(adapter):
    el = MockInteractiveElement()
    adapter._resolve_control = mock.Mock(return_value=el)

    adapter.interact("focus", "ctrl_123")
    el.set_focus.assert_called_once()


def test_interact_enter_text_value_pattern(adapter):
    el = MockInteractiveElement(control_type="Edit")
    el.set_edit_text = mock.Mock()
    adapter._resolve_control = mock.Mock(return_value=el)

    adapter.interact("enter_text", "ctrl_123", value="Hello")
    el.set_edit_text.assert_called_once_with("Hello")
    el.type_keys.assert_not_called()


def test_interact_enter_text_fallback(adapter):
    el = MockInteractiveElement(control_type="Edit")
    adapter._resolve_control = mock.Mock(return_value=el)

    adapter.interact("enter_text", "ctrl_123", value="Hello")
    el.type_keys.assert_called_once_with("Hello", with_spaces=True, with_tabs=True)


def test_interact_append_text(adapter):
    el = MockInteractiveElement(control_type="Edit")
    el.set_edit_text = mock.Mock()
    el.get_value = mock.Mock(return_value="Existing ")
    adapter._resolve_control = mock.Mock(return_value=el)

    adapter.interact("append_text", "ctrl_123", value="New")
    el.get_value.assert_called_once()
    el.set_edit_text.assert_called_once_with("Existing New")


def test_interact_clear_text(adapter):
    el = MockInteractiveElement(control_type="Edit")
    el.set_edit_text = mock.Mock()
    adapter._resolve_control = mock.Mock(return_value=el)

    adapter.interact("clear_text", "ctrl_123")
    el.set_edit_text.assert_called_once_with("")


def test_interact_checkbox_toggle(adapter):
    el = MockInteractiveElement(control_type="CheckBox")
    el.check = mock.Mock()
    el.uncheck = mock.Mock()
    adapter._resolve_control = mock.Mock(return_value=el)

    adapter.interact("check", "ctrl_123")
    el.check.assert_called_once()

    adapter.interact("uncheck", "ctrl_123")
    el.uncheck.assert_called_once()


def test_interact_dropdown_selection(adapter):
    el = MockInteractiveElement(control_type="ComboBox")
    el.select = mock.Mock()
    adapter._resolve_control = mock.Mock(return_value=el)

    adapter.interact("select_dropdown", "ctrl_123", value="Option B")
    el.select.assert_called_once_with("Option B")


def test_interact_unsupported_action(adapter):
    el = MockInteractiveElement()
    adapter._resolve_control = mock.Mock(return_value=el)

    with pytest.raises(UnsupportedControlError):
        adapter.interact("unsupported_action_name", "ctrl_123")
