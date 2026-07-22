#!/usr/bin/env bash
# Directioner - One-command setup and run script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

show_help() {
    cat << EOF
Directioner - Discord Text AI Assistant

Usage: ./run.sh [COMMAND]

Commands:
    setup       Build and install the project (builds Rust, installs Python deps)
    check       Run configuration and health checks
    health      Run comprehensive health check with JSON output
    test        Run the test suite
    run         Start the Discord bot
    clean       Clean build artifacts
    help        Show this help message

Examples:
    ./run.sh setup     # First time setup
    ./run.sh check     # Verify configuration
    ./run.sh health    # Detailed health check
    ./run.sh run       # Start the bot

EOF
}

setup() {
    log_info "Setting up Directioner..."

    # Check Python version
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    REQUIRED_VERSION="3.11"
    if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
        log_error "Python $REQUIRED_VERSION+ required, found $PYTHON_VERSION"
        exit 1
    fi
    log_info "Python $PYTHON_VERSION detected"

    # Check for Rust
    if ! command -v rustc &> /dev/null; then
        log_warn "Rust not found. Installing via rustup..."
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
        source "$HOME/.cargo/env"
    fi
    log_info "Rust $(rustc --version | cut -d' ' -f2) detected"

    # Create virtual environment if it doesn't exist
    if [ ! -d ".venv" ]; then
        log_info "Creating virtual environment..."
        python3 -m venv .venv
    fi

    # Activate virtual environment
    source .venv/bin/activate

    # Upgrade pip
    log_info "Upgrading pip..."
    pip install --upgrade pip > /dev/null 2>&1

    # Install maturin
    log_info "Installing maturin..."
    pip install maturin > /dev/null 2>&1

    # Build Rust native extension
    log_info "Building Rust native extension..."
    maturin build --manifest-path native/rust/Cargo.toml --out dist 2>&1 | tail -3

    # Install native wheel
    NATIVE_WHL=$(find dist -name "*.whl" | head -1)
    if [ -n "$NATIVE_WHL" ]; then
        log_info "Installing native wheel: $(basename $NATIVE_WHL)"
        pip install "$NATIVE_WHL" > /dev/null 2>&1
    fi

    # Install Python dependencies
    log_info "Installing Python dependencies..."
    pip install -e . > /dev/null 2>&1

    # Install test dependencies
    log_info "Installing test dependencies..."
    pip install pytest pytest-asyncio > /dev/null 2>&1

    log_info "Setup complete! Run './run.sh check' to verify."
}

check() {
    source .venv/bin/activate 2>/dev/null || true
    export PYTHONPATH="${SCRIPT_DIR}/src"
    
    log_info "Running configuration check..."
    python3 -m directioner.app check
    
    echo ""
    log_info "Running health check..."
    python3 -m directioner.app health-check
}

health() {
    source .venv/bin/activate 2>/dev/null || true
    export PYTHONPATH="${SCRIPT_DIR}/src"
    
    log_info "Running comprehensive health check..."
    python3 -m directioner.app health-check
}

test() {
    source .venv/bin/activate 2>/dev/null || true
    export PYTHONPATH="${SCRIPT_DIR}/src"
    
    log_info "Running test suite..."
    python3 -m pytest tests/ -v --tb=short
}

run_bot() {
    source .venv/bin/activate 2>/dev/null || true
    export PYTHONPATH="${SCRIPT_DIR}/src"
    
    # Check for config
    if [ ! -f "configs/app.yaml" ]; then
        if [ -f "configs/app.example.yaml" ]; then
            log_warn "No config found. Copying example config..."
            cp configs/app.example.yaml configs/app.yaml
            log_warn "Please edit configs/app.yaml and add your Discord bot token."
        else
            log_error "No configuration found!"
            exit 1
        fi
    fi
    
    log_info "Starting Directioner bot..."
    python3 -m directioner.app run --config configs/app.yaml
}

clean() {
    log_info "Cleaning build artifacts..."
    rm -rf .venv
    rm -rf dist/
    rm -rf build/
    rm -rf "native/rust/target/release/"*.so 2>/dev/null || true
    rm -rf "native/rust/target/debug/"*.so 2>/dev/null || true
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -name "*.pyc" -delete 2>/dev/null || true
    log_info "Clean complete."
}

# Main command dispatcher
case "${1:-help}" in
    setup)  setup ;;
    check)  check ;;
    health) health ;;
    test)   test ;;
    run)    run_bot ;;
    clean)  clean ;;
    help|--help|-h) show_help ;;
    *)      log_error "Unknown command: $1" ;;
esac
