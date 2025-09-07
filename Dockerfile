# Multi-stage Dockerfile for Asterisk AI Voice Agent
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    pkg-config \
    libasound2-dev \
    libpulse-dev \
    libsndfile1-dev \
    libfftw3-dev \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswresample-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage
FROM python:3.11-slim

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y \
    libasound2 \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 voiceagent && \
    mkdir -p /app && \
    chown -R voiceagent:voiceagent /app

# Set working directory
WORKDIR /app

# Copy Python packages from builder to user directory
COPY --from=builder /root/.local /home/voiceagent/.local
RUN chown -R voiceagent:voiceagent /home/voiceagent/.local

# Copy application code
COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/
COPY test_*.py ./

# Set Python path
ENV PATH=/home/voiceagent/.local/bin:$PATH
ENV PYTHONPATH=/app

# Switch to non-root user
USER voiceagent

# Expose ports for SIP and RTP
EXPOSE 5060/udp 10000-20000/udp 8000/tcp

# No health check for now

# Default command
CMD ["python", "-m", "src.engine"]
