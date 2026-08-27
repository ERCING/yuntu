@echo off
setlocal
set "PROJECT_ROOT=%~dp0"
set "PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Project virtual environment not found. Please run python -m venv .venv and .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)

"%PYTHON%" "%PROJECT_ROOT%himawari_ir_toolkit\himawari_gui.py"
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
