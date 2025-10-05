FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    openssh-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with UID 10001
RUN groupadd -g 10001 appuser && \
    useradd -r -u 10001 -g appuser appuser

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories with proper permissions
RUN mkdir -p /config /work /ssh /work/logs && \
    chown -R appuser:appuser /app /config /work /ssh

# Set environment variables
ENV TZ=America/Denver
ENV APP_CONFIG_DIR=/config
ENV APP_WORK_DIR=/work
ENV APP_SSH_KEY=/ssh/id_rsa
ENV APP_PORT=8000
ENV PYTHONPATH=/app

# Configure volume mount points
VOLUME ["/config", "/work", "/ssh"]

# Switch to non-root user
USER appuser

# Expose the application port
EXPOSE 8000

# Health check configuration
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Start the application
CMD ["python", "main.py"]