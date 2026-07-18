@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul

set "NO_LAUNCH=0"
set "SKIP_INSTALL=0"
for %%A in (%*) do (
    if /I "%%~A"=="--no-launch" set "NO_LAUNCH=1"
    if /I "%%~A"=="--skip-install" set "SKIP_INSTALL=1"
)

if not exist "logs" mkdir "logs"
set "PIP_LOG=%CD%\logs\pip-install.log"
set "DIAG_LOG=%CD%\logs\setup-diagnostics.log"

echo ============================================================
echo FlipCapture setup
echo ============================================================
echo.

set "PYTHON_LAUNCHER="
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import platform, sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12), (3, 13)) and platform.architecture()[0] == '64bit' else 1)" >nul 2>&1
    if not errorlevel 1 set "PYTHON_LAUNCHER=py -3"
)
if not defined PYTHON_LAUNCHER (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import platform, sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12), (3, 13)) and platform.architecture()[0] == '64bit' else 1)" >nul 2>&1
        if not errorlevel 1 set "PYTHON_LAUNCHER=python"
    )
)
if not defined PYTHON_LAUNCHER goto python_error

for /f "delims=" %%V in ('%PYTHON_LAUNCHER% --version 2^>^&1') do echo Found %%V

if exist ".venv\Scripts\python.exe" (
    echo Reusing the existing virtual environment.
    ".venv\Scripts\python.exe" -c "import platform, sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12), (3, 13)) and platform.architecture()[0] == '64bit' else 1)" >nul 2>&1
    if errorlevel 1 goto venv_error
) else (
    echo Creating the virtual environment...
    %PYTHON_LAUNCHER% -m venv .venv
    if errorlevel 1 goto setup_error
)

if "%SKIP_INSTALL%"=="1" goto diagnostics

echo Updating pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip --log "%PIP_LOG%"
if errorlevel 1 goto install_error

echo Installing FlipCapture libraries. This can take several minutes...
".venv\Scripts\python.exe" -m pip install -r requirements.txt --log "%PIP_LOG%"
if errorlevel 1 goto install_error

echo Checking installed package consistency...
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto install_error

:diagnostics
echo.
echo Running FlipCapture diagnostics...
".venv\Scripts\python.exe" -m flipcapture.diagnostics > "%DIAG_LOG%" 2>&1
set "DIAG_RESULT=%ERRORLEVEL%"
type "%DIAG_LOG%"
if not "%DIAG_RESULT%"=="0" goto diagnostic_error

echo.
echo ============================================================
echo Setup completed successfully.
echo ============================================================
echo Pip log: %PIP_LOG%
echo Diagnostic log: %DIAG_LOG%

if "%NO_LAUNCH%"=="1" exit /b 0
echo.
choice /C YN /N /M "Start FlipCapture now? [Y/N]: "
if errorlevel 2 exit /b 0
start "" ".venv\Scripts\pythonw.exe" -m flipcapture gui
exit /b 0

:python_error
echo [ERROR] Python 3.11, 3.12, or 3.13 (64-bit) was not found.
echo Install 64-bit Python from https://www.python.org/downloads/windows/
echo Enable "Add python.exe to PATH" during installation, then run setup.bat again.
goto failed

:venv_error
echo [ERROR] The existing .venv uses an unsupported or broken Python installation.
echo Rename or remove the .venv folder, then run setup.bat again.
goto failed

:install_error
echo [ERROR] Library installation failed.
echo Review the pip log: %PIP_LOG%
goto failed

:diagnostic_error
echo [ERROR] One or more required components failed diagnostics.
echo Review the diagnostic log: %DIAG_LOG%
goto failed

:setup_error
echo [ERROR] The virtual environment could not be created.

:failed
if "%NO_LAUNCH%"=="1" exit /b 1
echo.
pause
exit /b 1
