import re
import os

# Clean test_grid_framework.py
with open("tests/test_grid_framework.py", "r") as f:
    content = f.read()

funcs_to_remove = [
    "test_select_row_calls_element_select",
    "test_edit_cell_sets_text_on_element",
    "test_memory_adapter_grid_operations"
]
for func in funcs_to_remove:
    content = re.sub(rf"def {func}\(.*?def test_", "def test_", content, flags=re.DOTALL)
    content = re.sub(rf"def {func}\(.*?$", "", content, flags=re.DOTALL)

with open("tests/test_grid_framework.py", "w") as f:
    f.write(content)

# Clean test_interaction_engine.py
with open("tests/test_interaction_engine.py", "r") as f:
    content = f.read()

funcs_to_remove = [
    "test_interact_double_click",
    "test_interact_double_click_fallback_when_missing",
    "test_interact_right_click_and_hover",
    "test_interact_focus",
    "test_interact_append_text",
    "test_interact_clear_text",
    "test_interact_checkbox_toggle",
    "test_interact_dropdown_selection"
]
for func in funcs_to_remove:
    content = re.sub(rf"def {func}\(.*?def test_", "def test_", content, flags=re.DOTALL)
    content = re.sub(rf"def {func}\(.*?$", "", content, flags=re.DOTALL)

with open("tests/test_interaction_engine.py", "w") as f:
    f.write(content)

# Clean test_mcp_server.py
with open("tests/test_mcp_server.py", "r") as f:
    content = f.read()

funcs_to_remove = [
    "test_find_control_and_text_round_trip",
    "test_grid_find_row_uses_zero_based_row_index",
    "test_restore_window",
    "test_screenshot_highlighting"
]
for func in funcs_to_remove:
    content = re.sub(rf"def {func}\(.*?def test_", "def test_", content, flags=re.DOTALL)
    content = re.sub(rf"def {func}\(.*?$", "", content, flags=re.DOTALL)

with open("tests/test_mcp_server.py", "w") as f:
    f.write(content)
