with open("desktop_mcp/server/mcp_server.py", "r") as f:
    content = f.read()

drag_drop_method = """
    def drag_drop(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = self._required(payload, "source_control_id")
        target = self._required(payload, "target_control_id")
        return {
            "action": "drag_drop",
            "source_control_id": source,
            "target_control_id": target,
        }

    def click_at(self"""

content = content.replace("    def click_at(self", drag_drop_method)

with open("desktop_mcp/server/mcp_server.py", "w") as f:
    f.write(content)
