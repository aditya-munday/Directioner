@echo off
::===============================================================================
:: Directioner Run Script (Windows)
::
:: Usage:
::   run.bat              - Full mode
::   run.bat text         - Text-only mode
::   run.bat voice        - Voice mode
::   run.bat mic          - Test microphone
::   run.bat test         - Run tests
::===============================================================================

setlocal

set "MODE=full"

:: Parse arguments
if "%~1" neq "" (
    if "%~1"=="--text" set "MODE=text"
    if "%~1"=="text" set "MODE=text"
    if "%~1"=="--voice" set "MODE=voice"
    if "%~1"=="voice" set "MODE=voice"
    if "%~1"=="--mic" set "MODE=mic"
    if "%~1"=="mic" set "MODE=mic"
    if "%~1"=="--test" set "MODE=test"
    if "%~1"=="test" set "MODE=test"
    if "%~1"=="--help" goto :help
    if "%~1"=="-h" goto :help
)

:: Activate venv
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

echo ========================================
echo   Directioner
echo ========================================
echo.

:: Check environment
goto :check_%MODE%

:check_full
:check_text
:check_voice
echo Checking environment...
if not exist ".env" (
    echo WARNING: .env not found
    echo Copy .env.example to .env and configure your API keys
    echo.
)

if "%DISCORD_BOT_TOKEN%"=="" (
    echo ERROR: DISCORD_BOT_TOKEN not set
    echo Set DISCORD_BOT_TOKEN in .env or environment
    pause
    exit /b 1
)

if "%GROQ_API_KEY%"=="" (
    echo ERROR: GROQ_API_KEY not set
    echo Set GROQ_API_KEY in .env or environment
    pause
    exit /b 1
)
echo Environment check passed
echo.
goto :run_%MODE%

:: Run modes
:run_test
echo Running tests...
pytest tests/ -v --tb=short
goto :eof

:run_mic
echo Testing microphone...
echo This will listen for 5 seconds. Speak into your microphone!
echo.
python -c "
import asyncio
import os
os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '1'

async def main():
    from directioner.stt.parakeet_stream import MicrophoneTranscriber
    
    def on_transcript(text):
        print(f'You said: {text}')
    
    transcriber = MicrophoneTranscriber(on_transcript)
    
    try:
        await asyncio.wait_for(transcriber.start(), timeout=5.0)
    except asyncio.TimeoutError:
        print('\nTime''s up!')

asyncio.run(main())
"
goto :eof

:run_text
echo Starting Directioner ^(text mode^)...
python -m directioner.app --text
goto :eof

:run_voice
echo Starting Directioner ^(voice mode^)...
python -m directioner.app --voice
goto :eof

:run_full
echo Starting Directioner...
python -m directioner.app
goto :eof

:help
echo Directioner Run Script
echo.
echo Usage: %~nx0 [OPTIONS]
echo.
echo Options:
echo   text    Text-only mode
echo   voice   Voice mode
echo   mic     Test microphone
echo   test    Run tests
echo   help    Show this help
exit /b 0
