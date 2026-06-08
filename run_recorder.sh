#!/bin/bash
set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "\033[36mSetting up Desktop MCP Codegen Recorder...\033[0m"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "\033[31mError: Python3 is not installed or not in PATH.\033[0m"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo -e "\033[32mCreating virtual environment in .venv...\033[0m"
    python3 -m venv .venv
fi

# Install dependencies
echo -e "\033[32mEnsuring dependencies are installed...\033[0m"
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"

# Run the recorder
echo -e "\n\033[33m====================================================\033[0m"
echo -e "\033[33mStarting the Codegen Interaction Recorder...\033[0m"
echo -e "\033[33m====================================================\033[0m\n"

.venv/bin/python -m desktop_mcp.recorder "$@"
