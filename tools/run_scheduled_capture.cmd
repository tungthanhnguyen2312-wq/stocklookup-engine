@echo off
setlocal
rem Scheduled same-day market capture. Independent of Owner Daily; shares its writer lease.
set "CAPTURE_PYTHON=%~dp0..\..\environments\core-313\Scripts\python.exe"
if defined STOCK_LOOKUP_PYTHON set "CAPTURE_PYTHON=%STOCK_LOOKUP_PYTHON%"
if not exist "%CAPTURE_PYTHON%" (
    echo Active Python unavailable: %CAPTURE_PYTHON% 1>&2
    exit /b 1
)
"%CAPTURE_PYTHON%" -X utf8 -B "%~dp0run_scheduled_capture.py" %*
exit /b %errorlevel%
