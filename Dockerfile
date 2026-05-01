# The MIT License (MIT)
# Copyright (c) 2026 val-bittensor contributors

# Multi-stage Dockerfile for val-bittensor validator service.
# Stage 1 (builder): installs dependencies and runs optional linting/tests.
# Stage 2 (runtime): minimal image with just the validator and strategy tools.

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Builder
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Install build dependencies and project requirements
WORKDIR /build

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements files
COPY setup.py .
COPY requirements.txt .
COPY README.md .

# Copy template directory (needed for version in __init__.py)
COPY template/ ./template/

# Create requirements without torch (we'll install torch separately)
RUN grep -v "^torch" requirements.txt > requirements-no-torch.txt

# Install Python dependencies to a temporary location
# Install torch cpu-only first, then other requirements (excluding torch)
RUN pip install --no-cache-dir --prefix=/install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --prefix=/install -r requirements-no-torch.txt
RUN pip install --no-cache-dir --prefix=/install .

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Runtime
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r valbittensor -g 1000 && \
    useradd -r -g valbittensor -u 1000 -m -d /home/valbittensor valbittensor

# Set working directory
WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY neurons/ ./neurons/
COPY template/ ./template/
COPY strategy/ ./strategy/
COPY setup.py .
COPY README.md .

# Create Bittensor state directory (for wallet and state.npz)
RUN mkdir -p /home/valbittensor/.bittensor/wallets && \
    chown -R valbittensor:valbittensor /home/valbittensor

# Set up environment for Bittensor
ENV HOME=/home/valbittensor
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Switch to non-root user
USER valbittensor

# Health check (liveness probe)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD pgrep -f "python.*neurons/validator.py" || exit 1

# Default entrypoint (can be overridden via Helm command)
ENTRYPOINT ["python"]
CMD ["--help"]
