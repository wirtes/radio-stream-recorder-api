# 📝 Spec Prompt for Kiro IDE

**Title:** Python API to Record Radio Streams, Convert to MP3, and SCP
to Remote Directory

**Goal:**\
Develop a Python-based API that runs natively on the host system. This API
records radio streams defined in JSON config files, converts them to MP3
with rich metadata (including artwork), and SCPs the resulting MP3 files
to a structured remote directory path based on configuration.

------------------------------------------------------------------------

## 1. API Functionality

-   **Trigger:**
    -   API endpoint will accept an external POST request with:
        -   `show`: the key name from `config_shows.json` (e.g.,
            `"super-sonido"`).
        -   `duration_minutes`: the total number of minutes to record.
-   **Behavior:**
    -   On receiving the request:
        -   Look up the show details in `config_shows.json`.
        -   Look up the corresponding `station` URL in
            `config_stations.json`.
        -   Immediately begin recording the stream for the specified
            duration.
        -   After recording:
            -   If file is not MP3, convert it to MP3.
            -   Apply MP3 metadata (artist, album artist, album, track
                number, date, and embedded artwork).
            -   Compute the output filename as `"YYYY-MM-DD Show"`
                (local host time only---**never UTC**).
            -   SCP the resulting MP3 file to the remote destination
                directory described in section 4. SCP Transfer Rules.

------------------------------------------------------------------------

## 2. Configuration Files

-   **Shows Configuration (`config_shows.json`):**

``` json
{
  "super-sonido": {
    "show": "Super Sonido",
    "station": "KUVO",
    "artwork-file": "/home/pi/recordings/art/super-sonido.jpg",
    "remote-directory": "alwirtes@plex-server.lan:/Volumes/External_12tb/Plex/Radio\ Rips/",
    "frequency": "weekly",
    "playlist-db-slug": "Super Sonido"
  }
}
```

-   **show**: Name of the show. Used for `Artist` and `Album Artist`
    tags.

-   **station**: Key to look up in `config_stations.json` for the actual
    stream URL.

-   **artwork-file**: Path to image used as embedded album artwork.

-   **remote-directory**: Base remote directory for SCP transfer.

-   **frequency**: `"daily"` or `"weekly"`. Determines track number
    logic.

-   **playlist-db-slug**: Slug for playlist DB entry.

-   **Stations Configuration (`config_stations.json`):**

``` json
{
  "KUVO": "http://kuvo-ice.streamguys.org/kuvo-aac-128",
  "thedrop": "http://kuvo-ice.streamguys.org/kuvohd2-aac-128",
  "coloradosound": "http://ais-sa1.streamon.fm/7891_96k.aac",
  "radio1190": "http://kvcu.streamguys1.com/live"
}
```

------------------------------------------------------------------------

## 3. MP3 Metadata Rules

-   **File Name:** `"YYYY-MM-DD Show"` (local time).\
-   **Artist & Album Artist:** from `"show"` element.\
-   **Album Tag:** `"show"` + current year.\
-   **Track Number:**
    -   `"daily"` → days since Jan 1.\
    -   `"weekly"` → weeks since Jan 1.\
-   **Artwork:** Embed `artwork-file` into MP3 metadata.

------------------------------------------------------------------------

## 4. SCP Transfer Rules

-   Base path: `"remote-directory"` from `config_shows.json`.\
-   Append `"show"` and then the `"Album"` value as subdirectories.\
-   Place the final MP3 file inside that path.\
-   Use SSH private key from the host system to authenticate SCP
    transfer. 

Example target path:

    <remote-directory>/<show>/<Album>/<YYYY-MM-DD Show>.mp3

------------------------------------------------------------------------

## 5. Native Deployment Requirements

-   The Python API will run natively on the host system.
-   Use local directories for:
    -   Configuration files.
    -   Working directories for temporary recordings.
    -   SSH private key for SCP authentication.
-   Enforce proper permissions for the SSH private key.
-   Provide installation and deployment instructions.

------------------------------------------------------------------------

## 6. Implementation Outline

-   **Framework:** FastAPI preferred.\
-   **Recording:** ffmpeg to record stream to temp file.\
-   **Conversion:** ffmpeg to MP3 if needed.\
-   **Metadata:** mutagen or eyed3 for tags + artwork.\
-   **SCP:** subprocess scp with SSH key.\
-   **Timezone:** use system's local timezone.

POST `/record` with `{"show":"super-sonido","duration_minutes":60}`.\
Validate, record, convert, tag, SCP, clean temp files.

------------------------------------------------------------------------

## 7. Native Installation Requirements

### System Dependencies
- Python 3.11 or higher
- ffmpeg (for audio recording and conversion)
- openssh-client (for SCP transfers)

### Python Dependencies (`requirements.txt`)

``` text
fastapi
uvicorn[standard]
mutagen
```

### Installation Steps

1. **Install system dependencies**
   ```bash
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install python3 python3-pip python3-venv ffmpeg openssh-client
   
   # macOS
   brew install python ffmpeg openssh
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set environment variables**
   ```bash
   export TZ=America/Denver
   export APP_CONFIG_DIR=./config
   export APP_WORK_DIR=./work
   export APP_SSH_KEY=~/.ssh/id_rsa
   export APP_PORT=8000
   ```

------------------------------------------------------------------------

## 8. Project Structure

**Directory Layout:**

    project-root/
    ├─ main.py
    ├─ requirements.txt
    ├─ setup.py
    ├─ config/
    │  ├─ config_shows.json
    │  ├─ config_stations.json
    │  └─ artwork/
    │     └─ *.jpg
    ├─ work/  # temp/output workspace
    │  └─ logs/
    └─ src/
       ├─ __init__.py
       ├─ models/
       │  ├─ __init__.py
       │  ├─ api.py
       │  └─ config.py
       ├─ services/
       │  ├─ __init__.py
       │  ├─ config_manager.py
       │  ├─ recording_service.py
       │  ├─ stream_recorder.py
       │  ├─ metadata_processor.py
       │  └─ transfer_service.py
       └─ utils/
          ├─ __init__.py
          └─ logging_config.py

### Running the Application

```bash
# Development mode
python main.py

# Production mode with uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000

# Background service
nohup python main.py > app.log 2>&1 &
```
