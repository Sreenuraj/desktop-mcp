#!/usr/bin/env python3
"""Thin wrapper for running the Desktop MCP Interaction Recorder.

This script delegates to the refactored `desktop_mcp.recorder` package
to keep custom entry points and execution scripts backward-compatible.
"""

from desktop_mcp.recorder.main import main

if __name__ == "__main__":
    main()
