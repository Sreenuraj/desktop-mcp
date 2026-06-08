# run_recorder.ps1
# Self-elevation check: Elevate this PowerShell script to run as Administrator
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "This script needs to run as Administrator to listen to UIA events across all processes." -ForegroundColor Yellow
    Write-Host "Relaunching as Administrator..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    Exit
}

# Ensure we are in the directory of the script
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (!$ScriptDir) { $ScriptDir = Get-Location }
Set-Location -Path $ScriptDir

Write-Host "Starting Desktop MCP Codegen Recorder Setup..." -ForegroundColor Cyan

# Check Python installation
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

# Create virtual environment if it doesn't exist
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment in .venv..." -ForegroundColor Green
    & $PythonCmd -m venv .venv
}

# Install dependencies
Write-Host "Ensuring dependencies are installed..." -ForegroundColor Green
$VenvPython = "$ScriptDir\.venv\Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e ".[dev,windows]"

# Run the recorder
Write-Host "`n====================================================" -ForegroundColor Yellow
Write-Host "Starting the Codegen Interaction Recorder..." -ForegroundColor Green
Write-Host "====================================================`n" -ForegroundColor Yellow

& $VenvPython -m desktop_mcp.recorder.main $args
