import re

with open("desktop_mcp/adapters/windows/uia_adapter.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update get_window robust focus loop
get_window_old = """            try:
                if win_wrapper.is_minimized():
                    win_wrapper.restore()
                    import time
                    time.sleep(0.15)

                import ctypes
                import win32gui
                import win32con

                win32gui.ShowWindow(handle, win32con.SW_SHOW)
                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                win32gui.SetForegroundWindow(handle)
                ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
                import time
                time.sleep(0.15)

                if hasattr(win_wrapper, "set_focus"):
                    win_wrapper.set_focus()
            except Exception:
                pass"""

get_window_new = """            try:
                if win_wrapper.is_minimized():
                    win_wrapper.restore()
                    import time
                    time.sleep(0.15)

                import ctypes
                import win32gui
                import win32con
                import time

                win32gui.ShowWindow(handle, win32con.SW_SHOW)
                
                # Robust retry loop to bypass focus stealing
                for _ in range(10):
                    if win32gui.GetForegroundWindow() == handle:
                        break
                    ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                    win32gui.SetForegroundWindow(handle)
                    ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
                    time.sleep(0.15)

                if hasattr(win_wrapper, "set_focus"):
                    win_wrapper.set_focus()
            except Exception:
                pass"""
content = content.replace(get_window_old, get_window_new)

# 2. Update interact method
interact_old_pattern = r'    def interact\(self, action: str, control_id: str, \*\*kwargs: Any\) -> dict:.*?    def read_table'
interact_new = """    def interact(self, action: str, control_id: str, **kwargs: Any) -> dict:
        self._check_platform()
        
        # If no control ID is provided and the action is press_keys on the active window
        if not control_id and action == "press_keys":
            import pywinauto.keyboard
            keys = kwargs.get("keys", "")
            pywinauto.keyboard.send_keys(keys, with_spaces=True, with_tabs=True)
            return {"action": action, "control_id": control_id}
            
        el = self._resolve_control(control_id)
        if not el.is_enabled():
            raise ControlDisabledError(f"Control is disabled: {control_id}")

        def ensure_focus() -> None:
            try:
                if hasattr(el, "top_level_parent"):
                    parent = el.top_level_parent()
                    if hasattr(parent, "is_minimized") and parent.is_minimized():
                        parent.restore()
                        import time
                        time.sleep(0.1)

                    if hasattr(parent, "handle"):
                        hwnd = parent.handle
                        import ctypes
                        import win32gui
                        import win32con
                        import time

                        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

                        # Robust retry loop
                        for _ in range(10):
                            if win32gui.GetForegroundWindow() == hwnd:
                                break
                            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                            win32gui.SetForegroundWindow(hwnd)
                            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
                            time.sleep(0.15)

                    if hasattr(parent, "set_focus"):
                        parent.set_focus()
            except Exception:
                pass

        ensure_focus()

        try:
            if action in ("left", "click"):
                if hasattr(el, "invoke") and el.element_info.control_type == "Button":
                    try:
                        el.invoke()
                    except Exception:
                        ensure_focus()
                        el.click_input()
                elif hasattr(el, "select") and el.element_info.control_type in ("ListItem", "MenuItem", "TabItem", "RadioButton", "TreeViewItem"):
                    try:
                        el.select()
                    except Exception:
                        ensure_focus()
                        el.click_input()
                else:
                    ensure_focus()
                    el.click_input()
            elif action == "double":
                ensure_focus()
                if hasattr(el, "double_click_input"):
                    el.double_click_input()
                else:
                    el.click_input()
                    el.click_input()
            elif action == "right":
                ensure_focus()
                el.right_click_input()
            elif action == "hover":
                ensure_focus()
                el.move_mouse_input()
            elif action == "enter_text":
                val = kwargs.get("value", "")
                if hasattr(el, "set_edit_text"):
                    try:
                        el.set_edit_text(val)
                    except Exception:
                        ensure_focus()
                        el.type_keys(val, with_spaces=True, with_tabs=True)
                else:
                    ensure_focus()
                    el.type_keys(val, with_spaces=True, with_tabs=True)
            elif action == "press_keys":
                val = kwargs.get("keys", "")
                ensure_focus()
                el.set_focus()
                el.type_keys(val, with_spaces=True, with_tabs=True)
            elif action == "select_item":
                val = str(kwargs.get("value", ""))
                if hasattr(el, "select"):
                    try:
                        el.select(val)
                    except Exception:
                        ensure_focus()
                        el.click_input()
                else:
                    ensure_focus()
                    el.click_input()
            else:
                raise UnsupportedControlError(f"Unsupported action {action}")

            return {"action": action, "control_id": control_id}
        except DesktopMCPError:
            raise
        except Exception as exc:
            raise DesktopMCPError(f"Interaction {action} failed: {exc}") from exc

    def read_table"""
content = re.sub(interact_old_pattern, interact_new, content, flags=re.DOTALL)

# 3. Clean up wait/assert methods at the end if they exist
# In `desktop_mcp/adapters/windows/uia_adapter.py`, it didn't have assert methods (they were in mcp_server.py).
# It does have `wait_for_browser`, `attach_browser_window`, etc., which we should keep as they are browser specific.

with open("desktop_mcp/adapters/windows/uia_adapter.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Rewriting complete.")
