@echo off
setlocal
rem Owner Daily one-click without a resident PowerShell host: cmd -> Python host -> Owner.
rem The host refuses unless this interpreter is the active production Python binding.
set "OWNER_DAILY_PYTHON=%~dp0..\..\environments\core-313\Scripts\python.exe"
if defined STOCK_LOOKUP_PYTHON set "OWNER_DAILY_PYTHON=%STOCK_LOOKUP_PYTHON%"
if not exist "%OWNER_DAILY_PYTHON%" (
    echo Active Python unavailable: %OWNER_DAILY_PYTHON% 1>&2
    exit /b 1
)
"%OWNER_DAILY_PYTHON%" -I -X utf8 -B "%~dp0owner_daily_host.py" %*
exit /b %errorlevel%
