#!/bin/bash
#===============================================================================
# Directioner Run Script
#
# Usage:
#   ./scripts/run.sh                  # Full mode (text + voice)
#   ./scripts/run.sh --text           # Text-only mode
#   ./scripts/run.sh --voice          # Voice-only mode
#   ./scripts/run.sh --mic            # Test microphone directly
#   ./scripts/run.sh --test           # Run tests
#   ./scripts/run.sh --help           # Show help
#===============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Default mode
MODE="full"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --text)
            MODE="text"
            shift
            ;;
        --voice)
            MODE="voice"
            shift
            ;;
        --mic)
            MODE="mic"
            shift
            ;;
        --test)
            MODE="test"
            shift
            ;;
        --help|-h)
            echo "Directioner Run Script"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --text    Text-only mode (no voice)"
            echo "  --voice   Voice mode (text + voice)"
            echo "  --mic     Test microphone directly"
            echo "  --test    Run tests"
            echo "  --help    Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Activate venv if exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Check environment
check_env() {
    echo -e "${BLUE}Checking environment...${NC}"
    
    # Check .env
    if [ ! -f ".env" ]; then
        echo -e "${YELLOW}Warning: .env not found${NC}"
        echo "Copy .env.example to .env and configure your API keys"
    fi
    
    # Check required env vars
    if [ -z "$DISCORD_BOT_TOKEN" ]; then
        echo -e "${RED}Error: DISCORD_BOT_TOKEN not set${NC}"
        echo "Set DISCORD_BOT_TOKEN in .env or environment"
        exit 1
    fi
    
    if [ -z "$GROQ_API_KEY" ]; then
        echo -e "${RED}Error: GROQ_API_KEY not set${NC}"
        echo "Set GROQ_API_KEY in .env or environment"
        exit 1
    fi
    
    echo -e "${GREEN}Environment check passed${NC}"
}

# Run tests
run_tests() {
    echo -e "${BLUE}Running tests...${NC}"
    pytest tests/ -v --tb=short
}

# Test microphone
test_mic() {
    echo -e "${BLUE}Testing microphone...${NC}"
    echo "This will listen for 5 seconds. Speak into your microphone!"
    echo ""
    
    python3 << 'EOF'
import asyncio
import os
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

async def main():
    from directioner.stt.parakeet_stream import MicrophoneTranscriber
    
    transcripts = []
    
    def on_transcript(text):
        print(f"You said: {text}")
        transcripts.append(text)
    
    transcriber = MicrophoneTranscriber(on_transcript)
    
    try:
        await asyncio.wait_for(transcriber.start(), timeout=5.0)
    except asyncio.TimeoutError:
        print("\nTime's up!")
    
    if transcripts:
        print(f"\nTranscribed {len(transcripts)} utterances")
    else:
        print("\nNo speech detected")

asyncio.run(main())
EOF
}

# Run text mode
run_text() {
    check_env
    echo -e "${BLUE}Starting Directioner (text mode)...${NC}"
    python -m directioner.app --text
}

# Run voice mode
run_voice() {
    check_env
    echo -e "${BLUE}Starting Directioner (voice mode)...${NC}"
    python -m directioner.app --voice
}

# Run full mode
run_full() {
    check_env
    echo -e "${BLUE}Starting Directioner (full mode)...${NC}"
    python -m directioner.app
}

# Main
main() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Directioner${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    case $MODE in
        text)
            run_text
            ;;
        voice)
            run_voice
            ;;
        mic)
            test_mic
            ;;
        test)
            run_tests
            ;;
        full)
            run_full
            ;;
    esac
}

main
