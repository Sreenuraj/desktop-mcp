import re

with open("desktop_mcp/server/mcp_server.py", "r") as f:
    content = f.read()

# 1. Replace the tools dict
tools_dict_str = """        self._tools: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "create_session": self.create_session,
            "close_session": self.close_session,
            "launch_application": self.launch_application,
            "attach_application": self.attach_application,
            "close_application": self.close_application,
            "list_windows": self.list_windows,
            "activate_window": self.activate_window,
            "wait_for_window": self.wait_for_window,
            "close_window": self.close_window,
            "window_snapshot": self.window_snapshot,
            "control_tree": self.control_tree,
            "click": self.click,
            "click_at": self.click_at,
            "drag_drop": self.drag_drop,
            "enter_text": self.enter_text,
            "press_keys": self.press_keys,
            "read_text": self.read_text,
            "select_item": self.select_item,
            "read_table": self.read_table,
            "capture_window": self.capture_window,
            "capture_desktop": self.capture_desktop,
            "start_recording": self.start_recording,
            "stop_recording": self.stop_recording,
            "generate_report": self.generate_report,
        }"""
content = re.sub(r'        self\._tools.*?\n        }', tools_dict_str, content, flags=re.DOTALL)

# 2. Add press_keys and select_item methods, modify click
new_methods = """
    def click(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action", "left"))
        return self._interaction(action, payload)

    def press_keys(self, payload: dict[str, Any]) -> dict[str, Any]:
        keys = self._required(payload, "keys")
        control_id = payload.get("control_id")
        if control_id:
            return self.adapter.interact("press_keys", control_id, keys=keys)
        else:
            return self.adapter.interact("press_keys", "", keys=keys)

    def select_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._interaction("select_item", payload, value=self._required(payload, "value"))
"""

# Let's just remove the old interaction methods and insert the new ones.
# Find where click is defined
content = re.sub(r'    def click\(self.*?def click_at\(self', '    def click_at(self', content, flags=re.DOTALL)
content = re.sub(r'    def double_click\(self.*?def click_at\(self', '    def click_at(self', content, flags=re.DOTALL)
# It's safer to just do string replacements for the methods we want to remove.
methods_to_remove = [
    "maximize_window", "minimize_window", "restore_window", "desktop_snapshot",
    "find_control", "find_controls", "get_control",
    "double_click", "right_click", "hover", "focus",
    "append_text", "clear_text", "select_dropdown", "select_tab", "select_radio", "check", "uncheck",
    "find_row", "select_row", "edit_cell", "read_cell", "read_tree", "expand_node", "collapse_node", "select_node",
    "detect_dialog", "wait_for_dialog", "accept_dialog", "dismiss_dialog", "control_exists", "wait_for_control",
    "assert_text", "assert_control_state", "assert_table_row", "wait_for_browser", "attach_browser_window"
]

for method in methods_to_remove:
    # Pattern to match the method definition and its body until the next def or end of class
    pattern = rf'    def {method}\(self, payload: dict\[str, Any\]\) -> dict\[str, Any\]:.*?(?=    def |\Z)'
    content = re.sub(pattern, '', content, flags=re.DOTALL)

# Insert the new methods after control_tree
parts = content.split('    def _flatten_controls')
if len(parts) == 2:
    part1, part2 = parts
    # Find end of control_tree
    part2_parts = part2.split('    def click_at(self')
    if len(part2_parts) == 2:
        new_part2 = part2_parts[0] + new_methods + '    def click_at(self' + part2_parts[1]
        content = part1 + '    def _flatten_controls' + new_part2

with open("desktop_mcp/server/mcp_server.py", "w") as f:
    f.write(content)
