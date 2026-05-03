# syntax=docker/dockerfile:1.4
# The MIT License (MIT)
# Copyright (c) 2026 val-bittensor contributors

# Multi-stage Dockerfile for val-bittensor validator service.
# Stage 1 (builder): installs dependencies with BuildKit pip cache.
# Stage 2 (runtime): minimal image with just the validator and strategy tools.

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Builder
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY setup.py .
COPY requirements.txt .
COPY README.md .
COPY template/ ./template/

# Filter out torch from requirements (installed separately with CPU-only index)
RUN grep -v "^torch" requirements.txt > requirements-no-torch.txt

# Install torch CPU-only, then remaining deps.
# BuildKit cache mount avoids re-downloading on subsequent builds.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install torch --index-url https://download.pytorch.org/whl/cpu

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install -r requirements-no-torch.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install .

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Runtime
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r valbittensor -g 1000 && \
    useradd -r -g valbittensor -u 1000 -m -d /home/valbittensor valbittensor

WORKDIR /app

COPY --from=builder /install /usr/local

COPY neurons/ ./neurons/
COPY template/ ./template/
COPY strategy/ ./strategy/
COPY setup.py .
COPY README.md .

RUN mkdir -p /home/valbittensor/.bittensor/wallets && \
    chown -R valbittensor:valbittensor /home/valbittensor

ENV HOME=/home/valbittensor
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

USER valbittensor

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD pgrep -f "python.*neurons/validator.py" || exit 1

ENTRYPOINT ["python"]
CMD ["--help"]
