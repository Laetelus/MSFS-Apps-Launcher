@echo off
cd /d "%~dp0"
set "NOPAUSE="
if /i "%~1"=="nopause" set "NOPAUSE=1"

rem Builds dist\MSFSLauncher\MSFSLauncher.exe. Add "nopause" to not wait for a key at the end.

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
goto failed_quiet

:have_python
echo Using: %PY%
%PY% --version
echo.
echo Installing build tools and libraries...
%PY% -m pip install --upgrade pyinstaller pywebview pystray pillow SimConnect
if errorlevel 1 goto failed

echo.
echo Generating the app icon...
%PY% src\generate_icon.py
if errorlevel 1 goto failed

echo.
echo Building the exe...
set "KEEP=%TEMP%\MSFSLauncher-apps.json.keep"
if exist "dist\MSFSLauncher\apps.json" copy /y "dist\MSFSLauncher\apps.json" "%KEEP%" >nul
%PY% -m PyInstaller --noconfirm --clean MSFSLauncher.spec
if errorlevel 1 goto failed
if exist "%KEEP%" (
    copy /y "%KEEP%" "dist\MSFSLauncher\apps.json" >nul
    del "%KEEP%"
    echo Kept your existing apps.json.
)

:done
echo.
echo Done.
echo   %~dp0dist\MSFSLauncher\MSFSLauncher.exe
echo Keep the _internal folder next to the exe.
echo.
if not defined NOPAUSE pause
exit /b 0

:failed
echo.
echo The build failed. Scroll up to see the error message.
echo.
:failed_quiet
if not defined NOPAUSE pause
exit /b 1
