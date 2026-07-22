# =============================================================================
# Directioner Discord Bot - Production Dockerfile
# =============================================================================

FROM python:3.13-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install Python dependencies in a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# =============================================================================
# Production Stage
# =============================================================================

FROM python:3.13-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash directioner

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=directioner:directioner src/ ./src/
COPY --chown=directioner:directioner native/ ./native/
COPY --chown=directioner:directioner configs/ ./configs/
COPY --chown=directioner:directioner .env.example ./

# Create data directory
RUN mkdir -p /app/data/memory && chown directioner:directioner /app/data

# Switch to non-root user
USER directioner

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Default command
CMD ["python", "-m", "directioner.app", "run"]

# Expose port for health check (optional)
EXPOSE 8000

# Labels
LABEL org.opencontainers.image.title="Directioner"
LABEL org.opencontainers.image.description="AI-powered Discord text assistant"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.source="https://github.com/aditya-munday/Directioner"
