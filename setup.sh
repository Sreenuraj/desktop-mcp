#!/bin/bash
set -e

# Get repo directory
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

echo -e "\033[36mSetting up Desktop MCP...\033[0m"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "\033[31mError: Python3 is not installed or not in PATH.\033[0m"
    exit 1
fi

echo -e "\033[32mCreating virtual environment in .venv...\033[0m"
python3 -m venv .venv

echo -e "\033[32mInstalling dependencies...\033[0m"
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"

# Build path and config
PYTHON_PATH="$REPO_DIR/.venv/bin/python"

SETTINGS_JSON=$(cat <<EOF
{
  "mcpServers": {
    "desktop-mcp": {
      "command": "$PYTHON_PATH",
      "args": ["-m", "desktop_mcp.server.stdio"],
      "cwd": "$REPO_DIR"
    }
  }
}
EOF
)

echo -e "\n\033[33m====================================================\033[0m"
echo -e "\033[33mSetup Complete! Copy/paste the configuration below:\033[0m"
echo -e "\033[33m====================================================\033[0m\n"
echo -e "\033[32m$SETTINGS_JSON\033[0m"
echo -e "\n\033[33m====================================================\033[0m"
