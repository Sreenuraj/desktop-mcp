from __future__ import annotations

from unittest import mock
import pytest

from desktop_mcp.adapters.memory import InMemoryDesktopAdapter
from desktop_mcp.adapters.windows.uia_adapter import WindowsUIAutomationAdapter
from desktop_mcp.server.mcp_server import DesktopMCPServer


class MockGridElement:
    def __init__(
        self, name: str, control_type: str = "DataGrid", children: list = None
    ) -> None:
        self.element_info = mock.Mock()
        self.element_info.name = name
        self.element_info.control_type = control_type
        self.element_info.automation_id = f"id_{name}"
        self.element_info.runtime_id = (42, id(self))
        self.element_info.focused = False

        self._children = children or []
        self._enabled = True
        self._visible = True

    def descendants(self) -> list:
        # Flatted list of all children recursively
        flat = []

        def helper(nodes):
            for n in nodes:
                flat.append(n)
                if hasattr(n, "_children") and not isinstance(n, mock.Mock):
                    helper(n._children)

        helper(self._children)
        return flat

    def is_enabled(self) -> bool:
        return self._enabled

    def is_visible(self) -> bool:
        return self._visible


class MockGridRow:
    def __init__(self, index: int, cells: list) -> None:
        self.element_info = mock.Mock()
        self.element_info.name = f"Row {index}"
        self.element_info.control_type = "DataItem"
        self.element_info.automation_id = f"row_{index}"
        self.element_info.runtime_id = (42, id(self))

        self._children = cells
        self.select = mock.Mock()
        self.click_input = mock.Mock()

    def descendants(self) -> list:
        return self._children


class MockGridCell:
    def __init__(self, value: str, column_name: str) -> None:
        self.element_info = mock.Mock()
        self.element_info.name = column_name
        self.element_info.control_type = "Edit"
        self.element_info.automation_id = f"cell_{column_name}"
        self.element_info.runtime_id = (42, id(self))

        self._value = value
        self.set_edit_text = mock.Mock()
        self.click_input = mock.Mock()
        self.type_keys = mock.Mock()

    def window_text(self) -> str:
        return self._value


@pytest.fixture
def adapter():
    a = WindowsUIAutomationAdapter()
    a._check_platform = mock.Mock()
    return a


def test_read_table_extracts_cells_by_headers(adapter):
    # Setup headers
    header_name = mock.Mock()
    header_name.element_info.name = "Name"
    header_name.element_info.control_type = "HeaderItem"

    header_status = mock.Mock()
    header_status.element_info.name = "Status"
    header_status.element_info.control_type = "HeaderItem"

    headers_container = mock.Mock()
    headers_container.element_info.control_type = "Header"
    headers_container.descendants.return_value = [header_name, header_status]

    # Setup cells
    cell_name = MockGridCell("Jane Doe", "Name")
    cell_status = MockGridCell("Pending", "Status")
    row = MockGridRow(0, [cell_name, cell_status])

    # Setup Grid
    grid = MockGridElement("Customers", children=[headers_container, row])
    adapter._resolve_control = mock.Mock(return_value=grid)

    table = adapter.read_table("ctrl_grid")
    assert table["columns"] == ["Name", "Status"]
    assert table["rows"] == [{"Name": "Jane Doe", "Status": "Pending"}]



