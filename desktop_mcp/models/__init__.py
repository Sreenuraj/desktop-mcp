"""Shared Desktop MCP models."""

from desktop_mcp.models.application import Application
from desktop_mcp.models.control import Control
from desktop_mcp.models.response import MCPError, MCPResponse
from desktop_mcp.models.session import Session
from desktop_mcp.models.window import Window

__all__ = [
    "Application",
    "Control",
    "MCPError",
    "MCPResponse",
    "Session",
    "Window",
]
