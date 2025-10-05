#!/bin/bash

# Radio Stream Recorder API - Native Installation Script

set -e

echo "🎵 Radio Stream Recorder API - Native Installation"
echo "=================================================="

# Check if Python 3.11+ is available
echo "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.11 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.11"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "❌ Python $PYTHON_VERSION found, but Python $REQUIRED_VERSION or higher is required."
    exit 1
fi

echo "✅ Python $PYTHON_VERSION found"

# Check system dependencies
echo "Checking system dependencies..."

# Check for ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ ffmpeg is not installed."
    echo "Please install ffmpeg:"
    echo "  Ubuntu/Debian: sudo apt-get install ffmpeg"
    echo "  macOS: brew install ffmpeg"
    echo "  CentOS/RHEL/Fedora: sudo dnf install ffmpeg"
    exit 1
fi
echo "✅ ffmpeg found"

# Check for ssh/scp
if ! command -v scp &> /dev/null; then
    echo "❌ scp is not installed."
    echo "Please install openssh-client:"
    echo "  Ubuntu/Debian: sudo apt-get install openssh-client"
    echo "  macOS: brew install openssh"
    echo "  CentOS/RHEL/Fedora: sudo dnf install openssh-clients"
    exit 1
fi
echo "✅ scp found"

# Create virtual environment
echo "Creating Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ Python dependencies installed"

# Create necessary directories
echo "Creating directories..."
mkdir -p work/logs
mkdir -p config/artwork
echo "✅ Directories created"

# Copy example configuration files if they don't exist
if [ ! -f "config/config_shows.json" ] && [ -f "config/config_shows.json.example" ]; then
    cp config/config_shows.json.example config/config_shows.json
    echo "✅ Example show configuration copied"
fi

if [ ! -f "config/config_stations.json" ] && [ -f "config/config_stations.json.example" ]; then
    cp config/config_stations.json.example config/config_stations.json
    echo "✅ Example station configuration copied"
fi

# Check SSH key
echo "Checking SSH key..."
SSH_KEY_PATH="${APP_SSH_KEY:-$HOME/.ssh/id_rsa}"
if [ -f "$SSH_KEY_PATH" ]; then
    # Check permissions
    PERMS=$(stat -c "%a" "$SSH_KEY_PATH" 2>/dev/null || stat -f "%A" "$SSH_KEY_PATH" 2>/dev/null)
    if [ "$PERMS" != "600" ]; then
        echo "⚠️  SSH key permissions are $PERMS, should be 600"
        echo "Run: chmod 600 $SSH_KEY_PATH"
    else
        echo "✅ SSH key found with correct permissions"
    fi
else
    echo "⚠️  SSH key not found at $SSH_KEY_PATH"
    echo "Please ensure you have an SSH key set up for SCP transfers"
fi

echo ""
echo "🎉 Installation completed successfully!"
echo ""
echo "Next steps:"
echo "1. Edit configuration files:"
echo "   - config/config_shows.json"
echo "   - config/config_stations.json"
echo "2. Add artwork files to config/artwork/"
echo "3. Start the application:"
echo "   source .venv/bin/activate"
echo "   python main.py"
echo ""
echo "Or run in development mode with auto-reload:"
echo "   source .venv/bin/activate"
echo "   uvicorn main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "Test the API:"
echo "   curl http://localhost:8000/healthz"