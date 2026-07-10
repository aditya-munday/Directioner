#===============================================================================
# Directioner Dockerfile
#
# Build: docker build -t directioner .
# Run:   docker run -it --device /dev/snd -e DISCORD_BOT_TOKEN=xxx directioner
#===============================================================================

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    portaudio \
    libportaudio2 \
    libsndfile1 \
    ffmpeg \
    cmake \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Set HF transfer for faster model downloads
ENV HF_HUB_ENABLE_HF_TRANSFER=1

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt requirements-voice.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-voice.txt

# Copy source code
COPY . .

# Build C++ extension
RUN pip install -e .

# Create non-root user
RUN useradd -m -u 1000 directioner && \
    chown -R directioner:directioner /app
USER directioner

# Default command
CMD ["python", "-m", "directioner.app"]
