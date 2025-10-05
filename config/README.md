# Configuration Guide

This directory contains configuration files for the Radio Stream Recorder API. The system uses JSON configuration files to define radio shows and station stream URLs.

## Configuration Files

### `config_shows.json` - Show Configuration

Defines radio shows with their metadata and transfer settings. Each show is identified by a unique key.

#### Required Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `show` | string | Display name for the radio show (used in MP3 metadata) | `"Super Sonido"` |
| `station` | string | Station key that references `config_stations.json` | `"KUVO"` |
| `artwork-file` | string | Absolute path to artwork image file (JPG/PNG) | `"/config/artwork/show.jpg"` |
| `remote-directory` | string | SCP destination or local path for file transfer | `"user@host:/path/"` |
| `frequency` | string | Recording frequency: `"daily"` or `"weekly"` | `"weekly"` |
| `playlist-db-slug` | string | Database identifier for playlist management | `"Super Sonido"` |

#### Field Details

**`show`**
- Used as Artist and Album Artist in MP3 metadata
- Combined with year for Album name (e.g., "Super Sonido 2024")
- Must be non-empty string

**`station`**
- Must match a key in `config_stations.json`
- Used to lookup the actual stream URL
- Case-sensitive

**`artwork-file`**
- Path to image file (JPG, PNG supported)
- Image will be embedded in MP3 files
- Path must be accessible from the application
- Recommended: Place in `./config/artwork/` directory

**`remote-directory`**
- SCP format: `user@hostname:/path/to/directory/`
- Local path format: `/local/path/to/directory/`
- Must end with `/` for proper path construction
- SSH key authentication required for remote paths

**`frequency`**
- `"daily"`: Track numbers calculated as days since January 1st
- `"weekly"`: Track numbers calculated as weeks since January 1st
- Affects MP3 metadata track numbering

**`playlist-db-slug`**
- Identifier for external playlist database integration
- Can contain spaces and special characters
- Used for future playlist management features

#### Example Configuration

```json
{
  "my-show": {
    "show": "My Radio Show",
    "station": "LOCAL_FM",
    "artwork-file": "./config/artwork/my-show.jpg",
    "remote-directory": "user@server.lan:/media/radio/",
    "frequency": "weekly",
    "playlist-db-slug": "My Radio Show"
  }
}
```

### `config_stations.json` - Station Configuration

Maps station keys to their stream URLs.

#### Format

```json
{
  "STATION_KEY": "https://stream-url.com/live.mp3"
}
```

#### Requirements

- **Station Key**: Unique identifier (referenced by shows)
- **Stream URL**: Must start with `http://` or `https://`
- **Stream Format**: Any format supported by ffmpeg (MP3, AAC, OGG, FLAC)

#### Example Configuration

```json
{
  "LOCAL_FM": "http://local-radio.com:8000/stream.mp3",
  "JAZZ_STATION": "https://jazz-stream.example.com/live.aac"
}
```

## File Naming and Metadata

### Generated Filenames

Format: `YYYY-MM-DD Show.mp3`

- Uses local timezone (configured via environment variables)
- Example: `2024-03-15 Super Sonido.mp3`

### MP3 Metadata Tags

| Tag | Source | Example |
|-----|--------|---------|
| Artist | `show` field | `"Super Sonido"` |
| Album Artist | `show` field | `"Super Sonido"` |
| Album | `show` + current year | `"Super Sonido 2024"` |
| Track Number | Calculated from `frequency` | `12` (12th week/day) |
| Date | Current date | `"2024-03-15"` |
| Artwork | `artwork-file` | Embedded image |

### Remote Directory Structure

Files are transferred to: `<remote-directory>/<show>/<Album>/`

Example: `user@server:/media/radio/Super Sonido/Super Sonido 2024/2024-03-15 Super Sonido.mp3`

## Validation Rules

### Show Configuration Validation

- All fields are required and must be non-empty
- `frequency` must be exactly `"daily"` or `"weekly"`
- `station` must exist in `config_stations.json`
- `artwork-file` path will be validated at runtime
- `remote-directory` format validated for SCP syntax

### Station Configuration Validation

- URLs must start with `http://` or `https://`
- Stream must be accessible and compatible with ffmpeg
- No duplicate station keys allowed

## Directory Structure

Organize configuration files in the project directory:

```
project-root/
├─ config/
│  ├─ config_shows.json
│  ├─ config_stations.json
│  └─ artwork/
│     ├─ show1.jpg
│     └─ show2.jpg
└─ work/
   └─ logs/
```

## Troubleshooting

### Common Configuration Errors

1. **Show not found**: Check that show key exists in `config_shows.json`
2. **Station not found**: Verify station key exists in `config_stations.json`
3. **Artwork not found**: Ensure artwork file path is correct and accessible
4. **SCP transfer fails**: Check SSH key permissions and remote directory access
5. **Invalid frequency**: Must be exactly `"daily"` or `"weekly"` (case-sensitive)

### Testing Configuration

Use the API health check to verify configuration loading:

```bash
curl http://localhost:8000/healthz
```

Check application logs for configuration validation errors:

```bash
tail -f work/logs/app.log
```

## Security Considerations

- Configuration files should be read-only in production
- SSH keys must have proper permissions (600)
- Artwork directory should be read-only
- Remote directories should use dedicated user accounts
- Stream URLs should use HTTPS when possible

## Performance Notes

- Configuration is loaded at startup and cached in memory
- Large artwork files will increase MP3 processing time
- Remote transfers depend on network bandwidth and SSH performance
- Consider artwork file size optimization (recommended: < 1MB)