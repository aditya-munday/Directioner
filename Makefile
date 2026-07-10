#===============================================================================
# Directioner Makefile
#
# Usage:
#   make setup           - Setup development environment
#   make install         - Install dependencies
#   make dev             - Install dev dependencies
#   make build           - Build C++ extension
#   make run             - Run the bot
#   make run-text        - Run text-only mode
#   make run-voice       - Run voice mode
#   make test            - Run tests
#   make test-watched    - Run tests with watch
#   make lint            - Run linter
#   make typecheck       - Run type checker
#   make clean           - Clean build artifacts
#   make docker-build    - Build Docker image
#   make docker-run      - Run Docker container
#   make docker-stop     - Stop Docker container
#===============================================================================

.PHONY: help setup install dev build run run-text run-voice test test-watched lint typecheck clean docker-build docker-run docker-stop

# Default target
help:
	@echo "Directioner Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  setup           Setup development environment"
	@echo "  install         Install dependencies"
	@echo "  dev             Install dev dependencies"
	@echo "  build           Build C++ extension"
	@echo "  run             Run the bot (full mode)"
	@echo "  run-text        Run text-only mode"
	@echo "  run-voice       Run voice mode"
	@echo "  test            Run tests"
	@echo "  test-watched    Run tests with watch mode"
	@echo "  lint            Run linter"
	@echo "  typecheck       Run type checker"
	@echo "  clean           Clean build artifacts"
	@echo "  docker-build     Build Docker image"
	@echo "  docker-run      Run Docker container"
	@echo "  docker-stop     Stop Docker container"

# Setup
setup:
	@echo "Setting up Directioner..."
	@if [ ! -d ".venv" ]; then \
		python -m venv .venv; \
		echo "Virtual environment created"; \
	fi
	@source .venv/bin/activate && pip install --upgrade pip wheel && \
		pip install -r requirements.txt && \
		pip install -r requirements-voice.txt && \
		pip install -r requirements-dev.txt
	@echo "Setup complete!"

# Install dependencies
install:
	@echo "Installing dependencies..."
	pip install -r requirements.txt

# Install dev dependencies
dev:
	@echo "Installing dev dependencies..."
	pip install -r requirements-dev.txt

# Build C++ extension
build:
	@echo "Building C++ extension..."
	pip install -e .

# Run modes
run:
	@echo "Running Directioner (full mode)..."
	python -m directioner.app

run-text:
	@echo "Running Directioner (text mode)..."
	python -m directioner.app --text

run-voice:
	@echo "Running Directioner (voice mode)..."
	python -m directioner.app --voice

run-mic:
	@echo "Testing microphone..."
	python -c "from directioner.stt.parakeet_stream import MicrophoneTranscriber; \
		import asyncio; \
		transcriber = MicrophoneTranscriber(lambda t: print(f'You said: {t}')); \
		asyncio.run(transcriber.start())"

# Testing
test:
	@echo "Running tests..."
	pytest tests/ -v

test-cov:
	@echo "Running tests with coverage..."
	pytest tests/ -v --cov=directioner --cov-report=html

test-watched:
	@echo "Installing pytest-watch..."
	pip install pytest-watch
	@echo "Running tests with watch..."
	ptw

# Linting
lint:
	@echo "Running linter..."
	ruff check src/

lint-fix:
	@echo "Running linter with auto-fix..."
	ruff check --fix src/

# Type checking
typecheck:
	@echo "Running type checker..."
	mypy src/

# Clean
clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/ dist/ *.egg-info/
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf htmlcov/ .coverage

# Docker
docker-build:
	@echo "Building Docker image..."
	docker build -t directioner:latest .

docker-build-gpu:
	@echo "Building GPU Docker image..."
	docker build -f Dockerfile.gpu -t directioner:gpu .

docker-run:
	@echo "Running Docker container..."
	docker run -it --device /dev/snd \
		-e DISCORD_BOT_TOKEN \
		-e GROQ_API_KEY \
		--name directioner \
		directioner:latest

docker-stop:
	@echo "Stopping Docker container..."
	docker stop directioner || true
	docker rm directioner || true

# Development helpers
fmt:
	@echo "Formatting code..."
	ruff format src/

check:
	@echo "Running all checks..."
	ruff check src/
	mypy src/
	pytest tests/

# Release
release: clean check test build
	@echo "Building release..."
	python -m build
