@echo off
::===============================================================================
:: Directioner Setup Script (Windows)
::
:: Usage:
::   setup.bat                 - Interactive setup
::   setup.bat minimal         - Core dependencies only
::   setup.bat voice           - With voice features
::   setup.bat full            - All dependencies
::===============================================================================

setlocal enabledelayedexpansion

set "VENV_DIR=.venv"
set "MODE=interactive"

:: Parse arguments
if "%~1" neq "" (
    if "%~1"=="--minimal" set "MODE=minimal"
    if "%~1"=="minimal" set "MODE=minimal"
    if "%~1"=="--voice" set "MODE=voice"
    if "%~1"=="voice" set "MODE=voice"
    if "%~1"=="--full" set "MODE=full"
    if "%~1"=="full" set "MODE=full"
    if "%~1"=="--help" goto :help
    if "%~1"=="-h" goto :help
)

echo ========================================
echo   Directioner Setup (Windows)
echo ========================================
echo.

:: Check Python
echo Checking Python version...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo Found Python %PYVER%

:: Extract major.minor
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set PYMAJOR=%%a
    set PYMINOR=%%b
)

if "%PYMAJOR%" LSS "3" (
    echo ERROR: Python 3.11+ required
    pause
    exit /b 1
)
if "%PYMAJOR%" EQU "3" if "%PYMINOR%" LSS "11" (
    echo ERROR: Python 3.11+ required
    pause
    exit /b 1
)

echo Python version OK
echo.

:: Check CUDA
echo Checking CUDA...
nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo CUDA not found - GPU acceleration disabled
) else (
    echo CUDA detected
)
echo.

:: Create virtual environment
echo Creating virtual environment...
if exist "%VENV_DIR%" (
    echo Removing existing virtual environment...
    rmdir /s /q "%VENV_DIR%"
)

python -m venv %VENV_DIR%
echo Virtual environment created
echo.

:: Activate virtual environment
echo Activating virtual environment...
call %VENV_DIR%\Scripts\activate.bat

:: Upgrade pip
python -m pip install --upgrade pip wheel setuptools
echo.

:: Install core dependencies
echo Installing core dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install core dependencies
    pause
    exit /b 1
)
echo.

:: Check mode
if "%MODE%"=="minimal" goto :minimal_done
if "%MODE%"=="voice" goto :install_voice
if "%MODE%"=="full" goto :install_full

:: Interactive mode
echo.
set /p INSTALL_VOICE="Install voice features (STT/TTS)? (y/N): "
if /i "!INSTALL_VOICE!"=="y" goto :install_voice

set /p INSTALL_DEV="Install development dependencies? (y/N): "
if /i "!INSTALL_DEV!"=="y" goto :install_dev

goto :build

:install_voice
echo.
echo Installing voice dependencies...
pip install -r requirements-voice.txt
if errorlevel 1 (
    echo WARNING: Some voice dependencies may have failed
)
goto :dev_prompt

:dev_prompt
set /p INSTALL_DEV="Install development dependencies? (y/N): "
if /i "!INSTALL_DEV!"=="y" goto :install_dev
goto :build

:install_dev
echo.
echo Installing development dependencies...
pip install -r requirements-dev.txt
goto :build

:install_full
echo.
echo Installing voice dependencies...
pip install -r requirements-voice.txt

echo.
echo Installing development dependencies...
pip install -r requirements-dev.txt

:minimal_done
echo Minimal installation complete
goto :build

:build
echo.
echo Building C++ extension...
if exist "native" (
    pip install .
    if errorlevel 1 (
        echo WARNING: C++ build may have failed
    )
) else (
    echo No native directory found, skipping C++ build
)

:env
echo.
echo Creating .env file...
if exist ".env" (
    echo .env already exists, skipping
) else (
    (
        echo # Directioner Environment Configuration
        echo # Copy this to .env and fill in your values
        echo.
        echo # Discord Bot Token ^(required^)
        echo DISCORD_BOT_TOKEN=your_discord_bot_token_here
        echo.
        echo # Groq API Key for LLM ^(required^)
        echo GROQ_API_KEY=your_groq_api_key_here
        echo.
        echo # Supabase Configuration ^(optional^)
        echo # DIRECTIONER_MEMORY_USE_SUPABASE=false
        echo # SUPABASE_URL=your_supabase_url
        echo # SUPABASE_KEY=your_supabase_key
        echo.
        echo # Parakeet Model Path ^(optional^)
        echo # PARAKEET_MODEL_PATH=C:\parakeet-onnx
    ) > .env
    echo .env created
)

:verify
echo.
echo Verifying installation...
python -c "import numpy" 2>nul && echo   numpy OK || echo   numpy FAILED
python -c "import torch" 2>nul && echo   torch OK || echo   torch FAILED
python -c "import sounddevice" 2>nul && echo   sounddevice OK || echo   sounddevice not installed
echo.

:next_steps
echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo Next steps:
echo.
echo 1. Activate the virtual environment:
echo    .venv\Scripts\activate.bat
echo.
echo 2. Configure your environment:
echo    copy .env.example .env
echo    notepad .env
echo.
echo 3. Run the bot:
echo    :: Text-only mode:
echo    python -m directioner.app --text
echo.
echo    :: Voice mode:
echo    python -m directioner.app --voice
echo.
echo    :: Full mode:
echo    python -m directioner.app
echo.
echo 4. Run tests:
echo    pytest tests/
echo.
pause
goto :eof

:help
echo Directioner Setup Script
echo.
echo Usage: %~nx0 [OPTIONS]
echo.
echo Options:
echo   minimal    Install core dependencies only
echo   voice      Install with voice features ^(STT/TTS^)
echo   full       Install all dependencies
echo   help       Show this help message
exit /b 0
