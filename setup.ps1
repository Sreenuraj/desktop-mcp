# setup.ps1
# Get the directory of the script
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (!$ScriptDir) { $ScriptDir = Get-Location }
Set-Location -Path $ScriptDir

Write-Host "Setting up Desktop MCP..." -ForegroundColor Cyan

# Check Python
$PythonCmd = "python"
try {
    $null = & python --version 2>&1
} catch {
    try {
        $null = & py --version 2>&1
        $PythonCmd = "py"
    } catch {
        Write-Host "Error: Python is not installed or not in PATH." -ForegroundColor Red
        Exit 1
    }
}

Write-Host "Creating virtual environment in .venv..." -ForegroundColor Green
& $PythonCmd -m venv .venv

Write-Host "Installing dependencies..." -ForegroundColor Green
$VenvPython = "$ScriptDir\.venv\Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e ".[dev,windows]"

$EscapedCwd = $ScriptDir -replace '\\', '\\'
$EscapedPython = $VenvPython -replace '\\', '\\'

$SettingsJson = @"
{
  "mcpServers": {
    "desktop-mcp": {
      "command": "$EscapedPython",
      "args": ["-m", "desktop_mcp.server.stdio"],
      "cwd": "$EscapedCwd"
    }
  }
}
"@

Write-Host "`n====================================================" -ForegroundColor Yellow
Write-Host "Setup Complete! Copy/paste the configuration below:" -ForegroundColor Yellow
Write-Host "====================================================`n" -ForegroundColor Yellow
Write-Host $SettingsJson -ForegroundColor Green
Write-Host "`n====================================================" -ForegroundColor Yellow
