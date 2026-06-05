from __future__ import annotations

import time
from unittest import mock

import pytest

from desktop_mcp.adapters.windows.uia_adapter import WindowsUIAutomationAdapter
from desktop_mcp.models.control import Control
from desktop_mcp.server.mcp_server import DesktopMCPServer


class MockElementInfo:
    def __init__(self, control_type: str, name: str = "", automation_id: str | None = None) -> None:
        self.control_type = control_type
        self.name = name
        self.automation_id = automation_id
        self.runtime_id = (42, id(self))
        self.focused = False


class MockElement:
    def __init__(
        self,
        control_type: str,
        name: str = "",
        automation_id: str | None = None,
        children: list[MockElement] | None = None,
        visible: bool = True,
        enabled: bool = True,
    ) -> None:
        self.element_info = MockElementInfo(control_type, name, automation_id)
        self._children = children or []
        self._visible = visible
        self._enabled = enabled

    def children(self) -> list[MockElement]:
        return self._children

    def is_visible(self) -> bool:
        return self._visible

    def is_enabled(self) -> bool:
        return self._enabled

    def rectangle(self) -> mock.Mock:
        rect = mock.Mock()
        rect.left = 10
        rect.top = 20
        rect.width = mock.Mock(return_value=100)
        rect.height = mock.Mock(return_value=50)
        return rect


def test_control_type_normalization():
    adapter = WindowsUIAutomationAdapter()
    
    # Test mapping standard UIA control types
    btn_element = MockElement("Button")
    btn_control = adapter._map_control(btn_element)
    assert btn_control.type == "Button"

    tab_element = MockElement("Tab")
    tab_control = adapter._map_control(tab_element)
    assert tab_control.type == "TabControl"

    edit_element = MockElement("Edit")
    edit_control = adapter._map_control(edit_element)
    assert edit_control.type == "Edit"


def test_should_include_control_filtering():
    adapter = WindowsUIAutomationAdapter()

    # Interactive elements should be included
    assert adapter._should_include_control(MockElement("Button")) is True
    assert adapter._should_include_control(MockElement("Edit")) is True

    # Anonymous layout panels should be filtered out
    assert adapter._should_include_control(MockElement("Pane", name="", automation_id=None)) is False
    assert adapter._should_include_control(MockElement("Group", name="", automation_id=None)) is False

    # Layout panels with automation ID or custom name should be included
    assert adapter._should_include_control(MockElement("Pane", name="MainPanel")) is True
    assert adapter._should_include_control(MockElement("Group", automation_id="group_settings")) is True


def test_recursive_tree_building_and_lifting():
    adapter = WindowsUIAutomationAdapter()

    # Create a hierarchy: Window -> Filtered Pane -> Button
    btn = MockElement("Button", name="Save")
    pane = MockElement("Pane", name="", automation_id=None, children=[btn])
    
    # Traverse starting from pane
    nodes = adapter._build_control_tree(pane)
    
    # Pane is filtered, so its child Button should be lifted up to the top level
    assert len(nodes) == 1
    assert nodes[0].name == "Save"
    assert nodes[0].type == "Button"


def test_server_flat_snapshot_vs_hierarchical_tree():
    # Setup mock adapter returning hierarchical controls
    mock_adapter = mock.Mock()
    
    # Create top level controls: TabControl (with child TabItem -> Button)
    btn = Control(id="btn_ok", name="OK", type="Button")
    tab_item = Control(id="tab_item_1", name="Tab 1", type="TabItem", children=[btn])
    tab_ctrl = Control(id="tab_ctrl", name="Tabs", type="TabControl", children=[tab_item])
    
    mock_window = mock.Mock()
    mock_window.window_id = "win_123"
    mock_window.title = "Test Window"
    mock_window.application_id = "app_123"
    mock_window.active = True
    mock_window.controls = [tab_ctrl]
    
    # Stub Window serialization
    def to_dict_mock(include_controls=False):
        return {
            "window_id": "win_123",
            "title": "Test Window",
            "application_id": "app_123",
            "active": True,
        }
    mock_window.to_dict = to_dict_mock

    mock_adapter.get_window.return_value = mock_window

    server = DesktopMCPServer(adapter=mock_adapter)
    server.call_tool("create_session", {})

    # 1. Test window_snapshot - should be flat
    response = server.call_tool("window_snapshot", {"session_id": "session_001", "window_id": "win_123"})
    assert response["success"] is True
    controls = response["data"]["controls"]
    # Should contain all 3 controls in flat form
    assert len(controls) == 3
    assert controls[0]["id"] == "tab_ctrl"
    assert controls[1]["id"] == "tab_item_1"
    assert controls[2]["id"] == "btn_ok"

    # 2. Test control_tree - should be hierarchical
    # Mock to_dict on control models to behave like actual implementation
    tab_ctrl.to_dict = lambda include_children=False: {
        "id": "tab_ctrl", "name": "Tabs", "type": "TabControl",
        **({"children": [tab_item.to_dict(include_children=True)]} if include_children else {})
    }
    tab_item.to_dict = lambda include_children=False: {
        "id": "tab_item_1", "name": "Tab 1", "type": "TabItem",
        **({"children": [btn.to_dict(include_children=True)]} if include_children else {})
    }
    btn.to_dict = lambda include_children=False: {
        "id": "btn_ok", "name": "OK", "type": "Button",
        **({"children": []} if include_children else {})
    }

    tree_response = server.call_tool("control_tree", {"session_id": "session_001", "window_id": "win_123"})
    assert tree_response["success"] is True
    tree = tree_response["data"]["tree"]
    # Only the root tab_ctrl is top-level
    assert len(tree) == 1
    assert tree[0]["id"] == "tab_ctrl"
    assert tree[0]["children"][0]["id"] == "tab_item_1"
    assert tree[0]["children"][0]["children"][0]["id"] == "btn_ok"


def test_snapshot_performance():
    adapter = WindowsUIAutomationAdapter()

    # Generate a deeply nested, large tree structure: 100 elements
    root = MockElement("Pane", name="RootPanel")
    current = root
    for i in range(99):
        child = MockElement("Pane" if i % 2 == 0 else "Button", name=f"Element_{i}")
        current._children.append(child)
        current = child

    start_time = time.perf_counter()
    nodes = adapter._build_control_tree(root)
    elapsed = (time.perf_counter() - start_time) * 1000

    # Ensure traversal is extremely fast (well under the 500ms target)
    print(f"Elapsed time for 100 nodes traversal: {elapsed:.2f}ms")
    assert elapsed < 100.0


def test_find_controls_on_adapter():
    from desktop_mcp.errors import ControlNotFoundError
    adapter = WindowsUIAutomationAdapter()
    adapter._check_platform = mock.Mock()

    # Setup mock window with hierarchical controls
    mock_window = mock.Mock()
    mock_window.window_id = "win_123"

    # Hierarchical controls: TabControl with child Button
    btn = Control(id="btn_1", name="Submit", type="Button")
    tab = Control(id="tab_1", name="Main", type="TabControl", children=[btn])
    mock_window.controls = [tab]

    adapter.get_window = mock.Mock(return_value=mock_window)

    # 1. find_controls without type (should return all flat controls: tab and btn)
    controls = adapter.find_controls("win_123")
    assert len(controls) == 2
    assert controls[0].id == "tab_1"
    assert controls[1].id == "btn_1"

    # 2. find_controls with type Button
    btn_controls = adapter.find_controls("win_123", type="Button")
    assert len(btn_controls) == 1
    assert btn_controls[0].id == "btn_1"


def test_find_control_on_adapter():
    from desktop_mcp.errors import ControlNotFoundError
    adapter = WindowsUIAutomationAdapter()
    adapter._check_platform = mock.Mock()

    mock_window = mock.Mock()
    btn = Control(id="btn_1", name="Submit Button", type="Button")
    mock_window.controls = [btn]
    adapter.get_window = mock.Mock(return_value=mock_window)

    # find_control matching text
    ctrl = adapter.find_control("win_123", text="Submit", type="Button")
    assert ctrl.id == "btn_1"

    # find_control raises ControlNotFoundError if not matched
    with pytest.raises(ControlNotFoundError):
        adapter.find_control("win_123", text="Save")
