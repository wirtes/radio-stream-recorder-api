#!/bin/bash

# Radio Stream Recorder API - Startup Script

set -e

echo "🎵 Starting Radio Stream Recorder API..."

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Please run ./install.sh first."
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Check if configuration files exist
if [ ! -f "config/config_shows.json" ]; then
    echo "❌ config/config_shows.json not found. Please create configuration files."
    exit 1
fi

if [ ! -f "config/config_stations.json" ]; then
    echo "❌ config/config_stations.json not found. Please create configuration files."
    exit 1
fi

# Set default environment variables if not set
export TZ=${TZ:-America/Denver}
export APP_CONFIG_DIR=${APP_CONFIG_DIR:-./config}
export APP_WORK_DIR=${APP_WORK_DIR:-./work}
export APP_SSH_KEY=${APP_SSH_KEY:-$HOME/.ssh/id_rsa}
export APP_PORT=${APP_PORT:-8000}
export LOG_LEVEL=${LOG_LEVEL:-INFO}

# Create work directory if it doesn't exist
mkdir -p work/logs

echo "✅ Environment configured:"
echo "   - Config Dir: $APP_CONFIG_DIR"
echo "   - Work Dir: $APP_WORK_DIR"
echo "   - SSH Key: $APP_SSH_KEY"
echo "   - Port: $APP_PORT"
echo "   - Timezone: $TZ"
echo ""

# Check if running in development mode
if [ "$1" = "--dev" ] || [ "$1" = "-d" ]; then
    echo "🚀 Starting in development mode with auto-reload..."
    uvicorn main:app --reload --host 0.0.0.0 --port $APP_PORT
else
    echo "🚀 Starting in production mode..."
    python main.py
fi