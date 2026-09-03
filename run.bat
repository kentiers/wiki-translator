@echo off
setlocal enabledelayedexpansion

:: Check if uv is available
where uv >nul 2>&1
if %ERRORLEVEL% equ 0 (
    uv run python "%~dp0main.py" %*
    exit /b %ERRORLEVEL%
)

:: Check if user-local uv exists
if exist "%USERPROFILE%\.local\bin\uv.exe" (
    "%USERPROFILE%\.local\bin\uv.exe" run python "%~dp0main.py" %*
    exit /b %ERRORLEVEL%
)

:: Check known uv installed Python directories
for /d %%D in ("%APPDATA%\uv\python\cpython-*") do (
    if exist "%%D\python.exe" (
        "%%D\python.exe" "%~dp0main.py" %*
        exit /b %ERRORLEVEL%
    )
)

:: Check standard LocalAppData Python installations
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    if exist "%%D\python.exe" (
        "%%D\python.exe" "%~dp0main.py" %*
        exit /b %ERRORLEVEL%
    )
)

:: Fallback to python in PATH
python "%~dp0main.py" %*
exit /b %ERRORLEVEL%
