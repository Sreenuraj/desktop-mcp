@echo off
REM run_recorder.bat
REM Launch run_recorder.ps1 with ExecutionPolicy Bypass
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_recorder.ps1"
