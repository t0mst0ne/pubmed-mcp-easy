@echo off
REM Simple setup script for PubMed MCP API key and email

REM Make sure Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Python is required but not found. Please install Python first.
    exit /b 1
)

REM Run the Python setup script
python setup_api.py %*
