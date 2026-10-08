@echo off
cd /d "%~dp0"
echo ==== MSFS App Launcher: build ====
echo.

set "PY=python"
python --version >nul 2>&1
if not errorlevel 1 goto have_python
set "PY=py"
py --version >nul 2>&1
if not errorlevel 1 goto have_python

echo Python was not found.
echo.
echo 1. Download Python from https://www.python.org/downloads/
echo 2. In the installer, tick "Add python.exe to PATH" on the first screen.
echo 3. Run this file again.
echo.
pause
exit /b 1

:have_python
echo Using: %PY%
%PY% --version
echo.
echo Installing the build tool (PyInstaller)...
%PY% -m pip install --upgrade pyinstaller
if errorlevel 1 goto failed

echo.
echo Building the exe...
%PY% -m PyInstaller --noconfirm --onedir --noconsole --name MSFSLauncher launcher.py
if errorlevel 1 goto failed

echo.
echo Done. Your exe is here:
echo   %~dp0dist\MSFSLauncher\MSFSLauncher.exe
echo Keep the _internal folder next to the exe.
echo.
pause
exit /b 0

:failed
echo.
echo The build failed. Scroll up to see the error message.
echo.
pause
exit /b 1
