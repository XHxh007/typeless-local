@echo off
rem Stop TypelessLocal so the next start picks up the latest code.
rem Changing the .py files does NOT affect an already-running pythonw process.
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   TypelessLocal stopper
echo ============================================
echo.

tasklist /FI "IMAGENAME eq pythonw.exe" | findstr /I pythonw >nul
if errorlevel 1 (
  echo No pythonw.exe process is running. Nothing to do.
  goto :done
)

echo Stopping pythonw.exe ...
taskkill /F /IM pythonw.exe >nul 2>&1

ping -n 3 127.0.0.1 >nul
tasklist /FI "IMAGENAME eq pythonw.exe" | findstr /I pythonw >nul
if errorlevel 1 (
  echo [OK] Stopped.
) else (
  echo [FAIL] Still running. Try again as Administrator.
)

:done
echo.
echo Note: this kills EVERY pythonw.exe, including unrelated Python apps.
echo.
echo Next: run start_typeless.bat to launch the latest code.
echo Press any key to close.
pause >nul
