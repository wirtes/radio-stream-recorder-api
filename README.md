# Radio Stream Recorder API

A Python-based API service that automates the recording, processing, and distribution of radio streams. The system records radio streams, converts them to MP3 format with rich metadata including artwork, and transfers the resulting files to remote storage via SCP.

## Features

- **Automated Stream Recording**: Record radio streams for specified durations via REST API
- **Rich Metadata Processing**: Convert audio to MP3 with embedded artwork and ID3 tags
- **Remote File Transfer**: Automatically transfer processed files via SCP to remote directories
- **Concurrent Recording Support**: Handle multiple simultaneous recording requests
- **Native Python Application**: Runs directly on your system with minimal dependencies
- **Comprehensive Logging**: Structured logging with performance monitoring
- **Configuration-Driven**: JSON-based configuration for shows and stations

## Quick Start

### Prerequisites

- Python 3.11 or higher
- ffmpeg (for audio recording and conversion)
- openssh-client (for SCP transfers)
- SSH key for remote file transfers
- Radio stream URLs and artwork files

### Installation

#### Automated Installation (Recommended)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd radio-stream-recorder-api
   ```

2. **Run the installation script**
   ```bash
   ./install.sh
   ```

3. **Configure your shows and stations**
   ```bash
   # Edit configurations with your shows and stations
   nano config/config_shows.json
   nano config/config_stations.json
   ```

4. **Start the service**
   ```bash
   ./start.sh
   
   # Or for development with auto-reload:
   ./start.sh --dev
   ```

5. **Verify the service is running**
   ```bash
   curl http://localhost:8000/healthz
   ```

#### Manual Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd radio-stream-recorder-api
   ```

2. **Install system dependencies**
   ```bash
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install ffmpeg openssh-client curl
   
   # macOS
   brew install ffmpeg openssh curl
   
   # CentOS/RHEL/Fedora
   sudo dnf install ffmpeg openssh-clients curl
   ```

3. **Create Python virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

4. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Create configuration files**
   ```bash
   # Copy example configurations
   cp config/config_shows.json.example config/config_shows.json
   cp config/config_stations.json.example config/config_stations.json
   
   # Edit configurations with your shows and stations
   nano config/config_shows.json
   nano config/config_stations.json
   ```

6. **Set up SSH key for transfers**
   ```bash
   # Ensure your SSH key has proper permissions
   chmod 600 ~/.ssh/id_rsa
   ```

7. **Create working directory**
   ```bash
   mkdir -p work/logs
   ```

8. **Start the service**
   ```bash
   source .venv/bin/activate
   python main.py
   
   # Or use the startup script:
   ./start.sh
   ```

9. **Verify the service is running**
   ```bash
   curl http://localhost:8000/healthz
   ```

## Configuration

### Show Configuration (`config/config_shows.json`)

Configure your radio shows with metadata and transfer settings:

```json
{
  "super-sonido": {
    "show": "Super Sonido",
    "station": "KUVO",
    "artwork-file": "./config/artwork/super-sonido.jpg",
    "remote-directory": "user@server.lan:/path/to/radio/rips/",
    "frequency": "weekly",
    "playlist-db-slug": "Super Sonido"
  },
  "morning-show": {
    "show": "Morning Show",
    "station": "LOCAL_FM",
    "artwork-file": "./config/artwork/morning-show.jpg",
    "remote-directory": "user@server.lan:/path/to/radio/rips/",
    "frequency": "daily",
    "playlist-db-slug": "Morning Show"
  }
}
```

**Configuration Fields:**
- `show`: Display name for the show (used in metadata)
- `station`: Station key referencing `config_stations.json`
- `artwork-file`: Path to artwork image file (JPG/PNG)
- `remote-directory`: SCP destination in format `user@host:/path/`
- `frequency`: Either `"daily"` or `"weekly"` (affects track numbering)
- `playlist-db-slug`: Identifier for playlist database integration

### Station Configuration (`config/config_stations.json`)

Define radio station stream URLs:

```json
{
  "KUVO": "http://kuvo-ice.streamguys.org/kuvo-aac-128",
  "LOCAL_FM": "http://example-stream.com/stream.mp3",
  "JAZZ_STATION": "http://jazz-stream.example.com/live"
}
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TZ` | `America/Denver` | Timezone for file naming and metadata |
| `APP_CONFIG_DIR` | `./config` | Configuration files directory |
| `APP_WORK_DIR` | `./work` | Working directory for temporary files |
| `APP_SSH_KEY` | `~/.ssh/id_rsa` | SSH private key path |
| `APP_PORT` | `8000` | API server port |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## API Usage

### Record a Show

Start recording a radio show for a specified duration:

```bash
curl -X POST "http://localhost:8000/record" \
  -H "Content-Type: application/json" \
  -d '{
    "show": "super-sonido",
    "duration_minutes": 60
  }'
```

**Request Parameters:**
- `show` (string): Show key from `config_shows.json`
- `duration_minutes` (integer): Recording duration (1-480 minutes)

**Response Example:**
```json
{
  "success": true,
  "message": "Recording completed successfully",
  "recording_id": "rec_abc123def456",
  "estimated_completion": "2024-01-15T15:30:00Z"
}
```

### Health Check

Check service health and status:

```bash
curl http://localhost:8000/healthz
```

**Response Example:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T14:30:00Z",
  "version": "1.0.0"
}
```

### System Status

Get detailed system information:

```bash
curl http://localhost:8000/status
```

**Response Example:**
```json
{
  "timestamp": "2024-01-15T14:30:00Z",
  "service_status": "running",
  "active_recordings": [
    {
      "recording_id": "rec_abc123def456",
      "show": "super-sonido",
      "started_at": "2024-01-15T14:00:00Z",
      "estimated_completion": "2024-01-15T15:00:00Z"
    }
  ],
  "statistics": {
    "total_recordings": 42,
    "successful_recordings": 40,
    "failed_recordings": 2
  }
}
```

### Recovery Information

Get information about failed recordings:

```bash
curl http://localhost:8000/recovery
```

## File Processing Workflow

1. **Stream Recording**: Records audio stream using ffmpeg
2. **Format Conversion**: Converts to MP3 if necessary
3. **Metadata Application**: Applies ID3 tags including:
   - Artist: Show name
   - Album: Show name + current year
   - Track Number: Calculated based on frequency
   - Date: Current date (YYYY-MM-DD)
   - Embedded Artwork: From configured artwork file
4. **File Naming**: Uses format `YYYY-MM-DD Show.mp3`
5. **Remote Transfer**: Uploads via SCP to `remote-directory/show/Album/`
6. **Cleanup**: Removes temporary files on successful transfer

## Production Deployment

### Using systemd (Linux)

Create a systemd service file for automatic startup and management:

1. **Copy and customize the service file**
   ```bash
   # Copy the template
   sudo cp radio-recorder-api.service /etc/systemd/system/
   
   # Edit the service file with your paths and user
   sudo nano /etc/systemd/system/radio-recorder-api.service
   ```
   
   Update the following fields in the service file:
   - `User=your-username` → Your actual username
   - `Group=your-group` → Your actual group
   - `/path/to/radio-stream-recorder-api` → Full path to your installation

3. **Enable and start service**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable radio-recorder-api
   sudo systemctl start radio-recorder-api
   ```

4. **Check service status**
   ```bash
   sudo systemctl status radio-recorder-api
   ```

### Using Process Manager (PM2)

For Node.js-style process management:

1. **Install PM2**
   ```bash
   npm install -g pm2
   ```

2. **Create ecosystem file**
   ```bash
   nano ecosystem.config.js
   ```
   
   ```javascript
   module.exports = {
     apps: [{
       name: 'radio-recorder-api',
       script: 'main.py',
       interpreter: './.venv/bin/python',
       cwd: '/path/to/radio-stream-recorder-api',
       env: {
         TZ: 'America/Denver',
         APP_CONFIG_DIR: './config',
         APP_WORK_DIR: './work',
         APP_SSH_KEY: process.env.HOME + '/.ssh/id_rsa'
       },
       restart_delay: 10000,
       max_restarts: 10
     }]
   }
   ```

3. **Start with PM2**
   ```bash
   pm2 start ecosystem.config.js
   pm2 save
   pm2 startup
   ```

## Development Setup

### Local Development

1. **Create virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install system dependencies**
   ```bash
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install ffmpeg openssh-client curl
   
   # macOS
   brew install ffmpeg openssh curl
   ```

4. **Set up configuration**
   ```bash
   export APP_CONFIG_DIR=./config
   export APP_WORK_DIR=./work
   export APP_SSH_KEY=~/.ssh/id_rsa
   export TZ=America/Denver
   ```

5. **Run the application**
   ```bash
   python main.py
   ```

### Development with Auto-reload

For development with automatic reloading on code changes:

```bash
# Using the startup script (recommended)
./start.sh --dev

# Or manually with uvicorn
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Helper Scripts

The project includes several helper scripts:

- `install.sh` - Automated installation and setup
- `start.sh` - Easy application startup with environment configuration
- `radio-recorder-api.service` - systemd service template for production

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest tests/ -v
```

## Troubleshooting

### Common Issues

**Configuration Errors**
- Verify JSON syntax in configuration files
- Ensure all referenced artwork files exist
- Check SSH key permissions (should be 600)

**Recording Failures**
- Verify stream URLs are accessible
- Check network connectivity
- Ensure ffmpeg is installed and accessible

**Transfer Failures**
- Verify SSH key has access to remote server
- Check remote directory permissions
- Ensure SCP is available on the system

**Performance Issues**
- Monitor disk space in work directory
- Check system resources during concurrent recordings
- Review logs for bottlenecks

### Log Analysis

Logs are structured and include:
- Request/response details
- Performance metrics
- Error details with context
- Recording workflow progress

```bash
# View application logs
tail -f work/logs/app.log

# View structured logs
tail -f work/logs/structured.log

# View logs with timestamps
journalctl -u radio-recorder-api -f  # If using systemd
```

### Health Monitoring

The service provides multiple monitoring endpoints:

- `/healthz` - Basic health check
- `/status` - Detailed system status
- `/recovery` - Failed recording information
- `/docs` - Interactive API documentation

## Security Considerations

- SSH keys should have restricted permissions (600)
- Configure CORS and trusted hosts for production
- Run service as non-root user in production
- Set configuration files as read-only in production
- Validate all input parameters
- Implement rate limiting for production use

## Performance Tuning

- Adjust `max_concurrent_recordings` based on system resources
- Monitor disk I/O during recordings
- Configure appropriate log levels for production
- Use SSD storage for work directory when possible
- Consider network bandwidth for concurrent streams

## License

[Add your license information here]

## Contributing

[Add contributing guidelines here]

## Support

[Add support contact information here]