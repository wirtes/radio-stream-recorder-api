# Radio Stream Recorder API Documentation

## Overview

The Radio Stream Recorder API is a RESTful service that provides endpoints for recording radio streams, processing audio files, and managing the complete workflow from stream capture to remote file transfer.

**Base URL:** `http://localhost:8000`  
**API Version:** 1.0.0  
**Content-Type:** `application/json`

## Authentication

Currently, the API does not require authentication. For production deployments, consider implementing appropriate authentication mechanisms.

## Rate Limiting

The API supports concurrent recordings with a configurable limit (default: 3 concurrent recordings). Additional requests will be queued or rejected based on system capacity.

## Error Handling

The API uses standard HTTP status codes and returns structured error responses:

```json
{
  "error": "ValidationError",
  "message": "Show 'invalid-show' not found in configuration",
  "details": "Available shows: super-sonido, morning-show"
}
```

### HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad Request - Invalid parameters or configuration |
| 500 | Internal Server Error - Processing failure |
| 503 | Service Unavailable - System at capacity or not ready |

## Endpoints

### POST /record

Records a radio stream for the specified show and duration.

**Request Body:**
```json
{
  "show": "super-sonido",
  "duration_minutes": 60
}
```

**Parameters:**

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `show` | string | Yes | Must exist in config | Show key from config_shows.json |
| `duration_minutes` | integer | Yes | 1-480 | Recording duration in minutes (max 8 hours) |

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Recording completed successfully",
  "recording_id": "rec_abc123def456",
  "estimated_completion": "2024-01-15T15:30:00Z"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Whether the recording was successful |
| `message` | string | Status or error message |
| `recording_id` | string | Unique identifier for the recording |
| `estimated_completion` | datetime | ISO 8601 timestamp of completion |

**Error Responses:**

**400 Bad Request - Invalid Show:**
```json
{
  "detail": "Show 'invalid-show' not found in configuration"
}
```

**400 Bad Request - Invalid Duration:**
```json
{
  "detail": "Duration must be between 1 and 480 minutes"
}
```

**503 Service Unavailable - System at Capacity:**
```json
{
  "detail": "Maximum concurrent recordings reached. Please try again later."
}
```

**500 Internal Server Error - Processing Failure:**
```json
{
  "detail": "Recording failed: stream_recording"
}
```

**Example cURL Request:**
```bash
curl -X POST "http://localhost:8000/record" \
  -H "Content-Type: application/json" \
  -d '{
    "show": "super-sonido",
    "duration_minutes": 60
  }'
```

### GET /healthz

Health check endpoint for monitoring service availability.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T14:30:00Z",
  "version": "1.0.0"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Health status: "healthy", "degraded", or "unhealthy" |
| `timestamp` | datetime | Current server timestamp |
| `version` | string | Application version |

**Health Status Values:**
- `healthy`: All systems operational
- `degraded`: System functional but with warnings (e.g., high resource usage)
- `unhealthy`: System not functioning properly

**Example cURL Request:**
```bash
curl http://localhost:8000/healthz
```

### GET /status

Detailed system status including active recordings and statistics.

**Response (200 OK):**
```json
{
  "timestamp": "2024-01-15T14:30:00Z",
  "service_status": "running",
  "active_recordings": [
    {
      "recording_id": "rec_abc123def456",
      "show": "super-sonido",
      "started_at": "2024-01-15T14:00:00Z",
      "estimated_completion": "2024-01-15T15:00:00Z",
      "current_step": "stream_recording",
      "progress_percentage": 45.5
    }
  ],
  "statistics": {
    "total_recordings": 42,
    "successful_recordings": 40,
    "failed_recordings": 2,
    "average_duration_minutes": 65.3,
    "total_processing_time_hours": 28.5
  },
  "system_resources": {
    "cpu_usage_percent": 15.2,
    "memory_usage_percent": 32.1,
    "disk_usage_percent": 67.8,
    "available_recording_slots": 2
  }
}
```

**Example cURL Request:**
```bash
curl http://localhost:8000/status
```

### GET /recovery

Information about failed recordings for recovery purposes.

**Response (200 OK):**
```json
{
  "timestamp": "2024-01-15T14:30:00Z",
  "failed_recordings": [
    {
      "recording_id": "rec_def456ghi789",
      "show": "morning-show",
      "failed_at": "2024-01-15T10:30:00Z",
      "error_step": "file_transfer",
      "error_message": "SCP transfer failed: Permission denied",
      "temp_files": [
        "/work/temp/rec_def456ghi789/2024-01-15 Morning Show.mp3"
      ],
      "recovery_actions": [
        "Check SSH key permissions",
        "Verify remote directory access",
        "Retry transfer manually"
      ]
    }
  ],
  "recovery_statistics": {
    "total_failed_recordings": 3,
    "recoverable_recordings": 2,
    "temp_files_size_mb": 145.6
  }
}
```

**Example cURL Request:**
```bash
curl http://localhost:8000/recovery
```

### GET /

Root endpoint providing basic API information.

**Response (200 OK):**
```json
{
  "message": "Radio Stream Recorder API",
  "version": "1.0.0"
}
```

**Example cURL Request:**
```bash
curl http://localhost:8000/
```

## Interactive Documentation

The API provides interactive documentation through Swagger UI and ReDoc:

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI Schema:** `http://localhost:8000/openapi.json`

## Workflow Details

### Recording Workflow

When a recording request is submitted, the system executes the following steps:

1. **Validation**
   - Validate show exists in configuration
   - Validate duration parameters
   - Check system capacity

2. **Stream Recording**
   - Connect to radio stream URL
   - Record audio using ffmpeg
   - Monitor recording progress

3. **Audio Processing**
   - Convert to MP3 format if necessary
   - Apply metadata tags (Artist, Album, Track Number, Date)
   - Embed artwork from configuration

4. **File Transfer**
   - Transfer processed file via SCP
   - Create remote directory structure
   - Verify transfer completion

5. **Cleanup**
   - Remove temporary files on success
   - Retain files on failure for recovery

### File Naming Convention

Generated files follow the pattern: `YYYY-MM-DD Show.mp3`

Examples:
- `2024-01-15 Super Sonido.mp3`
- `2024-01-15 Morning Show.mp3`

### Remote Directory Structure

Files are organized on the remote server as:
```
<remote-directory>/<show>/<Album>/
```

Example:
```
/path/to/radio/rips/Super Sonido/Super Sonido 2024/2024-01-15 Super Sonido.mp3
```

### Metadata Tags

Applied ID3 tags include:

| Tag | Value | Example |
|-----|-------|---------|
| Artist | Show name | "Super Sonido" |
| Album Artist | Show name | "Super Sonido" |
| Album | Show + Year | "Super Sonido 2024" |
| Track Number | Calculated by frequency | 15 (15th day/week of year) |
| Date | Recording date | "2024-01-15" |
| Artwork | Embedded image | (Binary data from artwork file) |

### Track Number Calculation

- **Daily shows:** Days since January 1st of current year
- **Weekly shows:** Weeks since January 1st of current year

## Error Scenarios and Troubleshooting

### Configuration Errors

**Show Not Found:**
```json
{
  "detail": "Show 'invalid-show' not found in configuration"
}
```
**Solution:** Verify the show key exists in `config_shows.json`

**Station Not Found:**
```json
{
  "detail": "Station 'INVALID_STATION' not found in configuration"
}
```
**Solution:** Verify the station key exists in `config_stations.json`

### Recording Errors

**Stream Connection Failed:**
```json
{
  "detail": "Recording failed: stream_recording"
}
```
**Possible Causes:**
- Stream URL is unreachable
- Network connectivity issues
- Stream requires authentication

**Solution:** Check stream URL accessibility and network configuration

### Processing Errors

**Metadata Processing Failed:**
```json
{
  "detail": "Recording failed: metadata_processing"
}
```
**Possible Causes:**
- Artwork file not found or corrupted
- Audio file corruption
- Insufficient disk space

**Solution:** Verify artwork files exist and check disk space

### Transfer Errors

**SCP Transfer Failed:**
```json
{
  "detail": "Recording failed: file_transfer"
}
```
**Possible Causes:**
- SSH key permissions incorrect
- Remote directory not accessible
- Network connectivity issues

**Solution:** Verify SSH key permissions (600) and remote server access

### System Capacity Errors

**Service Unavailable:**
```json
{
  "detail": "Maximum concurrent recordings reached. Please try again later."
}
```
**Solution:** Wait for current recordings to complete or increase system resources

## Performance Considerations

### Concurrent Recordings

- Default limit: 3 concurrent recordings
- Each recording consumes CPU, memory, and network bandwidth
- Monitor system resources during peak usage

### Disk Space Management

- Temporary files are created in the work directory
- Files are cleaned up after successful transfer
- Failed recordings retain temp files for recovery
- Monitor disk space regularly

### Network Bandwidth

- Each stream recording consumes bandwidth equal to the stream bitrate
- Multiple concurrent recordings multiply bandwidth usage
- Consider network capacity when planning concurrent recordings

### Memory Usage

- Each recording process requires memory for buffering
- Metadata processing requires additional memory
- Monitor memory usage with multiple concurrent recordings

## Security Considerations

### SSH Key Management

- SSH private key must have 600 permissions
- Key should be dedicated for this service
- Regularly rotate SSH keys

### Network Security

- Configure CORS appropriately for production
- Use trusted host middleware
- Consider implementing authentication for production use

### Container Security

- Service runs as non-root user (UID 10001)
- Configuration files mounted read-only
- Minimal container image with only required dependencies

## Monitoring and Logging

### Log Levels

- `DEBUG`: Detailed debugging information
- `INFO`: General operational messages
- `WARNING`: Warning conditions
- `ERROR`: Error conditions

### Log Format

Logs are structured JSON with the following fields:
- `timestamp`: ISO 8601 timestamp
- `level`: Log level
- `message`: Log message
- `component`: System component
- `request_id`: Unique request identifier
- Additional context fields

### Performance Metrics

The system tracks:
- Request/response times
- Recording durations
- Success/failure rates
- Resource utilization
- Queue statistics

### Health Monitoring

Regular health checks should monitor:
- `/healthz` endpoint response
- System resource usage
- Active recording count
- Error rates

## Integration Examples

### Cron Job Integration

Schedule recordings using cron:

```bash
# Record Super Sonido every Sunday at 2 PM for 2 hours
0 14 * * 0 curl -X POST "http://localhost:8000/record" \
  -H "Content-Type: application/json" \
  -d '{"show": "super-sonido", "duration_minutes": 120}'
```

### Monitoring Script

Basic monitoring script:

```bash
#!/bin/bash
HEALTH=$(curl -s http://localhost:8000/healthz | jq -r '.status')
if [ "$HEALTH" != "healthy" ]; then
  echo "API health check failed: $HEALTH"
  # Send alert
fi
```

### Python Client Example

```python
import requests
import json

def record_show(show, duration_minutes):
    url = "http://localhost:8000/record"
    payload = {
        "show": show,
        "duration_minutes": duration_minutes
    }
    
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print(f"Recording started: {result['recording_id']}")
        return result
    else:
        print(f"Recording failed: {response.text}")
        return None

# Record a show
result = record_show("super-sonido", 60)
```

## Version History

### v1.0.0
- Initial release
- Basic recording functionality
- Metadata processing
- SCP file transfer
- Docker containerization
- Health monitoring

## Support and Maintenance

### Log Analysis

For troubleshooting, examine logs for:
- Request/response patterns
- Error frequencies
- Performance bottlenecks
- Resource utilization trends

### Backup Considerations

Regularly backup:
- Configuration files
- SSH keys
- Failed recording temp files
- Application logs

### Updates and Maintenance

- Monitor for security updates
- Update base Docker images regularly
- Review and rotate SSH keys
- Clean up old log files
- Monitor disk space usage