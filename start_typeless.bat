@echo off
rem Switch this console to UTF-8 so Chinese log lines render correctly.
rem Without it the console uses GBK (936) and UTF-8 bytes turn into mojibake.
chcp 65001 >nul

setlocal

rem Work from this script's own directory, wherever the repo was cloned.
cd /d "%~dp0"

echo ============================================
echo   TypelessLocal launcher
echo ============================================
echo.

rem ---- Find a Python interpreter -------------------------------------------
rem Try in order: PATH, the py launcher, common install dirs. We need a full
rem Python with tkinter (the status pill is Tk-based); bare embeddable builds
rem do not ship tkinter and the UI will silently fall back to a no-op.
set "PYEXE="
for %%P in (python.exe) do if not defined PYEXE set "PYEXE=%%~$PATH:P"
if not defined PYEXE for %%P in (py.exe) do if not defined PYEXE set "PYEXE=%%~$PATH:P"

if not defined PYEXE (
  for %%D in (
    "C:\ProgramData\anaconda3\python.exe"
    "%USERPROFILE%\anaconda3\python.exe"
    "C:\ProgramData\miniconda3\python.exe"
    "%USERPROFILE%\miniconda3\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
  ) do if not defined PYEXE if exist %%D set "PYEXE=%%~D"
)

if not defined PYEXE (
  echo [ERROR] No Python found.
  echo.
  echo Install Python 3.9+ and make sure "python" is on your PATH, or edit
  echo this file and set PYEXE to your python.exe manually.
  echo Installer: https://www.python.org/downloads/
  echo.
  goto :done
)
echo Using Python: %PYEXE%
echo.

rem ---- Ollama (needed for text polishing) ----------------------------------
netstat -ano | findstr ":11434" >nul
if errorlevel 1 (
  echo [1/2] Ollama not running, trying to start it...
  for %%O in (ollama.exe) do if not defined OLLAMA_EXE set "OLLAMA_EXE=%%~$PATH:O"
  if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
  if defined OLLAMA_EXE (
    start "OllamaServe" /min "%OLLAMA_EXE%" serve
    ping -n 7 127.0.0.1 >nul
  ) else (
    echo       Ollama not found on PATH. Text polishing will be skipped and
    echo       raw transcription will be typed instead. Install it from
    echo       https://ollama.com then run: ollama pull qwen2.5:7b
  )
) else (
  echo [1/2] Ollama already running.
)

rem ---- Second-instance guard ------------------------------------------------
tasklist /FI "IMAGENAME eq pythonw.exe" | findstr /I pythonw >nul
if not errorlevel 1 (
  echo.
  echo [2/2] TypelessLocal is ALREADY running.
  echo       If the hotkey does not respond, that older process is probably
  echo       stale code. Run kill_typeless.bat, then this script again.
  echo.
  goto :done
)

echo [2/2] Starting TypelessLocal...
rem Must NOT use `start /b`: /b shares this cmd's console, and when this window
rem closes the child gets CTRL_CLOSE_EVENT and dies. launch_typeless.py uses
rem DETACHED_PROCESS so the app survives independently of this window.
"%PYEXE%" "%~dp0launch_typeless.py"

:done
echo.
echo Recent log:
echo --------------------------------------------
rem The log is UTF-8. Read it with Python rather than Get-Content: PowerShell's
rem default ANSI decoding turns the Chinese lines into mojibake, and Python
rem writes straight to the console via the Unicode API so it renders correctly.
if exist typeless.log (
  "%PYEXE%" -c "import io,sys; sys.stdout.reconfigure(encoding='utf-8',errors='replace'); L=io.open('typeless.log',encoding='utf-8',errors='replace').readlines(); print(''.join(L[-10:]),end='')"
) else (
  echo (no typeless.log yet)
)
echo --------------------------------------------
echo.
echo HOW TO READ THIS:
echo   - A [heartbeat] line every ~5 min  = process alive and healthy.
echo   - No new heartbeat for 10+ minutes  = it died, just start it again.
echo   - Look for HOOK_STATUS=right_alt_ok = only RIGHT Alt can trigger.
echo.
echo This window stays open so you can read the result.
echo Press any key to close.
pause >nul
