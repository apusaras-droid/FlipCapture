@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m flipcapture gui
) else (
    py -3 -m flipcapture gui
)
if errorlevel 1 pause

