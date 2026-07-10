#!/bin/bash
#===============================================================================
# Directioner Setup Script
# 
# This script sets up a complete development environment for Directioner.
# Supports Linux, macOS, and WSL.
#
# Usage:
#   ./scripts/setup.sh                    # Interactive setup
#   ./scripts/setup.sh --minimal         # Core dependencies only
#   ./scripts/setup.sh --voice           # With voice features
#   ./scripts/setup.sh --full            # All dependencies
#   ./scripts/setup.sh --help            # Show help
#===============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Defaults
PYTHON_MIN="3.11"
VENV_DIR=".venv"
MODE="interactive"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --minimal)
            MODE="minimal"
            shift
            ;;
        --voice)
            MODE="voice"
            shift
            ;;
        --full)
            MODE="full"
            shift
            ;;
        --help|-h)
            echo "Directioner Setup Script"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --minimal    Install core dependencies only"
            echo "  --voice      Install with voice features (STT/TTS)"
            echo "  --full       Install all dependencies (dev + voice)"
            echo "  --help, -h   Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Directioner Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if grep -qEi "(Microsoft|WSL)" /proc/version 2>/dev/null; then
            echo "wsl"
        else
            echo "linux"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        echo "windows"
    else
        echo "unknown"
    fi
}

OS=$(detect_os)
echo -e "${GREEN}Detected OS: $OS${NC}"

# Check Python version
check_python() {
    echo -n "Checking Python version... "
    if command -v python3 &> /dev/null; then
        PYVER=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
        PYMAJOR=$(echo $PYVER | cut -d. -f1)
        PYMINOR=$(echo $PYVER | cut -d. -f2)
        
        if [[ "$PYMAJOR" -eq 3 && "$PYMINOR" -ge 11 ]]; then
            echo -e "${GREEN}Python $PYVER ✓${NC}"
            return 0
        else
            echo -e "${RED}Python $PYVER - requires 3.11+${NC}"
            return 1
        fi
    else
        echo -e "${RED}Python 3 not found${NC}"
        return 1
    fi
}

# Check for CUDA
check_cuda() {
    echo -n "Checking CUDA... "
    if command -v nvidia-smi &> /dev/null; then
        if nvidia-smi &> /dev/null; then
            CUDA_VER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)
            echo -e "${GREEN}CUDA $CUDA_VER ✓${NC}"
            return 0
        fi
    fi
    echo -e "${YELLOW}CUDA not found (GPU acceleration disabled)${NC}"
    return 1
}

# Create virtual environment
create_venv() {
    echo ""
    echo -e "${BLUE}Creating virtual environment...${NC}"
    
    if [ -d "$VENV_DIR" ]; then
        echo -e "${YELLOW}Virtual environment already exists. Removing...${NC}"
        rm -rf "$VENV_DIR"
    fi
    
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}Virtual environment created at $VENV_DIR${NC}"
}

# Activate virtual environment
activate_venv() {
    echo ""
    echo -e "${BLUE}Activating virtual environment...${NC}"
    
    if [[ "$OS" == "windows" ]]; then
        source "$VENV_DIR/Scripts/activate"
    else
        source "$VENV_DIR/bin/activate"
    fi
    
    # Upgrade pip
    pip install --upgrade pip wheel setuptools
    echo -e "${GREEN}Virtual environment activated${NC}"
}

# Install system dependencies
install_system_deps() {
    echo ""
    echo -e "${BLUE}Installing system dependencies...${NC}"
    
    case $OS in
        linux)
            echo "Installing system packages (requires sudo)..."
            if command -v apt-get &> /dev/null; then
                sudo apt-get update
                sudo apt-get install -y \
                    python3-dev \
                    python3-pip \
                    libportaudio0 \
                    libportaudio2 \
                    portaudio19-dev \
                    libsndfile1 \
                    libsndfile1-dev \
                    ffmpeg \
                    cmake \
                    build-essential
            elif command -v dnf &> /dev/null; then
                sudo dnf install -y \
                    python3-devel \
                    portaudio-devel \
                    libsndfile \
                    ffmpeg \
                    cmake \
                    gcc-c++
            elif command -v pacman &> /dev/null; then
                sudo pacman -S --noconfirm \
                    python \
                    portaudio \
                    libsndfile \
                    ffmpeg \
                    cmake \
                    base-devel
            fi
            ;;
        macos)
            echo "Checking Homebrew..."
            if ! command -v brew &> /dev/null; then
                echo "Installing Homebrew..."
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            fi
            brew install portaudio libsndfile ffmpeg cmake
            ;;
        wsl)
            echo "WSL detected - install dependencies in Windows or use Docker"
            echo "For WSL, consider using Docker for CUDA support"
            ;;
    esac
    
    echo -e "${GREEN}System dependencies installed${NC}"
}

# Install Python dependencies
install_python_deps() {
    echo ""
    echo -e "${BLUE}Installing Python dependencies...${NC}"
    
    # Core dependencies
    echo "Installing core dependencies..."
    pip install -r requirements.txt
    
    case $MODE in
        minimal)
            echo -e "${GREEN}Minimal installation complete${NC}"
            ;;
        voice)
            echo "Installing voice dependencies..."
            pip install -r requirements-voice.txt
            echo -e "${GREEN}Voice installation complete${NC}"
            ;;
        full)
            echo "Installing voice dependencies..."
            pip install -r requirements-voice.txt
            echo "Installing development dependencies..."
            pip install -r requirements-dev.txt
            echo -e "${GREEN}Full installation complete${NC}"
            ;;
        interactive)
            echo ""
            read -p "Install voice features (STT/TTS)? (y/N) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                pip install -r requirements-voice.txt
            fi
            
            echo ""
            read -p "Install development dependencies? (y/N) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                pip install -r requirements-dev.txt
            fi
            ;;
    esac
}

# Build C++ extension
build_cpp_extension() {
    echo ""
    echo -e "${BLUE}Building C++ extension...${NC}"
    
    if [ -d "native" ]; then
        echo "Building native extension..."
        pip install .
        echo -e "${GREEN}C++ extension built${NC}"
    else
        echo -e "${YELLOW}No native directory found, skipping C++ build${NC}"
    fi
}

# Create environment file
create_env_file() {
    echo ""
    echo -e "${BLUE}Creating .env file...${NC}"
    
    if [ -f ".env" ]; then
        echo -e "${YELLOW}.env already exists, skipping${NC}"
    else
        cat > .env << 'EOF'
# Directioner Environment Configuration
# Copy this to .env and fill in your values

# Discord Bot Token (required)
DISCORD_BOT_TOKEN=your_discord_bot_token_here

# Groq API Key for LLM (required)
GROQ_API_KEY=your_groq_api_key_here

# Supabase Configuration (optional - for long-term memory)
# DIRECTIONER_MEMORY_USE_SUPABASE=false
# SUPABASE_URL=your_supabase_url
# SUPABASE_KEY=your_supabase_key

# Parakeet Model Path (optional - for ONNX inference)
# PARAKEET_MODEL_PATH=C:\parakeet-onnx

# Audio Configuration
# AUDIO_SAMPLE_RATE=48000
# AUDIO_CHANNELS=2

# Voice Activity Detection
# VAD_THRESHOLD=0.5
# VAD_SILENCE_CHUNKS=20

# Wake Word
# WAKEWORD_MODEL=hey_jarvis
# WAKEWORD_THRESHOLD=0.5
EOF
        echo -e "${GREEN}.env created${NC}"
    fi
}

# Final verification
verify_installation() {
    echo ""
    echo -e "${BLUE}Verifying installation...${NC}"
    
    # Check Python
    if ! python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"; then
        echo -e "${RED}Python version check failed${NC}"
        return 1
    fi
    
    # Check key imports
    echo "Checking imports..."
    python -c "import numpy; print('  numpy:', numpy.__version__)" || echo -e "${RED}  numpy failed${NC}"
    python -c "import torch; print('  torch:', torch.__version__)" || echo -e "${RED}  torch failed${NC}"
    python -c "import sounddevice; print('  sounddevice: ok')" || echo -e "${YELLOW}  sounddevice not installed${NC}"
    
    echo -e "${GREEN}Verification complete${NC}"
}

# Print next steps
print_next_steps() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Setup Complete!${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo "Next steps:"
    echo ""
    echo "1. Activate the virtual environment:"
    echo "   source $VENV_DIR/bin/activate"
    echo ""
    echo "2. Configure your environment:"
    echo "   cp .env.example .env"
    echo "   nano .env  # Edit with your API keys"
    echo ""
    echo "3. Run the bot:"
    echo "   # Text-only mode:"
    echo "   python -m directioner.app --text"
    echo ""
    echo "   # Voice mode (requires audio devices):"
    echo "   python -m directioner.app --voice"
    echo ""
    echo "   # Full mode (text + voice):"
    echo "   python -m directioner.app"
    echo ""
    echo "4. Run tests:"
    echo "   pytest tests/"
    echo ""
}

# Main execution
main() {
    check_python
    check_cuda
    install_system_deps
    create_venv
    activate_venv
    install_python_deps
    build_cpp_extension
    create_env_file
    verify_installation
    print_next_steps
}

main
