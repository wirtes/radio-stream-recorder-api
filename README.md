# Radio Stream Recorder API

A Python-based API service that automates the recording, processing, and distribution of radio streams. The system records radio streams, converts them to MP3 format with rich metadata including artwork, and transfers the resulting files to remote storage via SCP.

## Features

- **Automated Stream Recording**: Record radio streams for specified durations via REST API
- **Rich Metadata Processing**: Convert audio to MP3 with embedded artwork and ID3 tags
- **Remote File Transfer**: Automatically transfer processed files via SCP to remote directories
- **Concurrent Recording Support**: Handle multiple simultaneous recording requests
- **Docker Containerized**: Fully containerized with health checks and monitoring
- **Comprehensive Logging**: Structured logging with performance monitoring
- **Configuration-Driven**: JSON-based configuration for shows and stations

## Quick Start

### Prerequisites

- Docker and Docker Compose
- SSH key for remote file transfers
- Radio stream URLs and artwork files

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd radio-stream-recorder-api
   ```

2. **Create configuration files**
   ```bash
   # Copy example configurations
   cp config/config_shows.json.example config/config_shows.json
   cp config/config_stations.json.example config/config_stations.json
   
   # Edit configurations with your shows and stations
   nano config/config_shows.json
   nano config/config_stations.json
   ```

3. **Set up SSH key for transfers**
   ```bash
   # Copy your SSH private key
   mkdir -p ssh
   cp ~/.ssh/id_rsa ssh/
   chmod 600 ssh/id_rsa
   ```

4. **Create working directory**
   ```bash
   mkdir -p work
   ```

5. **Start the service**
   ```bash
   docker-compose up -d
   ```

6. **Verify the service is running**
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
    "artwork-file": "/config/artwork/super-sonido.jpg",
    "remote-directory": "user@server.lan:/path/to/radio/rips/",
    "frequency": "weekly",
    "playlist-db-slug": "Super Sonido"
  },
  "morning-show": {
    "show": "Morning Show",
    "station": "LOCAL_FM",
    "artwork-file": "/config/artwork/morning-show.jpg",
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
| `APP_CONFIG_DIR` | `/config` | Configuration files directory |
| `APP_WORK_DIR` | `/work` | Working directory for temporary files |
| `APP_SSH_KEY` | `/ssh/id_rsa` | SSH private key path |
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

## Docker Deployment

### Using Docker Compose (Recommended)

```yaml
version: '3.8'

services:
  radio-recorder-api:
    build: .
    container_name: radio-recorder-api
    ports:
      - "8000:8000"
    volumes:
      - ./config:/config:ro
      - ./work:/work
      - ./ssh:/ssh:ro
      - /etc/localtime:/etc/localtime:ro
      - /etc/timezone:/etc/timezone:ro
    environment:
      - TZ=America/Denver
      - APP_CONFIG_DIR=/config
      - APP_WORK_DIR=/work
      - APP_SSH_KEY=/ssh/id_rsa
      - APP_PORT=8000
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
```

### Using Docker Run

```bash
docker build -t radio-recorder-api .

docker run -d \
  --name radio-recorder-api \
  -p 8000:8000 \
  -v $(pwd)/config:/config:ro \
  -v $(pwd)/work:/work \
  -v $(pwd)/ssh:/ssh:ro \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  -e TZ=America/Denver \
  -e APP_CONFIG_DIR=/config \
  -e APP_WORK_DIR=/work \
  -e APP_SSH_KEY=/ssh/id_rsa \
  radio-recorder-api
```

## Development Setup

### Local Development

1. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Install system dependencies**
   ```bash
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install ffmpeg openssh-client curl
   
   # macOS
   brew install ffmpeg openssh curl
   ```

3. **Set up configuration**
   ```bash
   export APP_CONFIG_DIR=./config
   export APP_WORK_DIR=./work
   export APP_SSH_KEY=./ssh/id_rsa
   export TZ=America/Denver
   ```

4. **Run the application**
   ```bash
   python main.py
   ```

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
- Ensure SCP is available in container

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
# View logs
docker logs radio-recorder-api

# Follow logs in real-time
docker logs -f radio-recorder-api

# View logs with timestamps
docker logs -t radio-recorder-api
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
- Use non-root user in container (UID 10001)
- Mount configuration files as read-only
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