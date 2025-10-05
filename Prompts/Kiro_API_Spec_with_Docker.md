# 📝 Spec Prompt for Kiro IDE

**Title:** Python API to Record Radio Streams, Convert to MP3, and SCP
to Remote Directory

**Goal:**\
Develop a Python-based API hosted in a Docker container. This API
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
-   Use SSH private key mounted into container to authenticate SCP
    transfer. 

Example target path:

    <remote-directory>/<show>/<Album>/<YYYY-MM-DD Show>.mp3

------------------------------------------------------------------------

## 5. Dockerization Requirements

-   The Python API will run inside a Docker container.
-   Mount local directories into the container for:
    -   Configuration files.
    -   Working directories for temporary recordings.
    -   SSH private key for SCP authentication.
-   Enforce proper permissions for the SSH private key.
-   Provide a Dockerfile and docker-compose.yml skeleton.

------------------------------------------------------------------------

## 6. Implementation Outline

-   **Framework:** FastAPI preferred.\
-   **Recording:** ffmpeg to record stream to temp file.\
-   **Conversion:** ffmpeg to MP3 if needed.\
-   **Metadata:** mutagen or eyed3 for tags + artwork.\
-   **SCP:** subprocess scp with SSH key.\
-   **Timezone:** use container's localtime (bind /etc/localtime).

POST `/record` with `{"show":"super-sonido","duration_minutes":60}`.\
Validate, record, convert, tag, SCP, clean temp files.

------------------------------------------------------------------------

## 7. Draft Dockerfile (Skeleton)

``` dockerfile
# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends       ffmpeg openssh-client tzdata tini     && rm -rf /var/lib/apt/lists/*

# Python deps
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source
COPY src/ ./src/
COPY gunicorn_conf.py ./gunicorn_conf.py

# Non-root user
RUN useradd -m -u 10001 appuser
USER appuser

ENV PYTHONUNBUFFERED=1     TZ=${TZ:-America/Denver}     APP_CONFIG_DIR=/config     APP_WORK_DIR=/work     APP_SSH_KEY=/ssh/id_ed25519     APP_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -qO- http://127.0.0.1:8000/healthz || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["gunicorn", "-c", "gunicorn_conf.py", "src.main:app"]
```

`requirements.txt` example:

``` text
fastapi
uvicorn[standard]
gunicorn
mutagen
```

`gunicorn_conf.py` example:

``` python
bind = "0.0.0.0:8000"
workers = 2
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 120
graceful_timeout = 30
```

------------------------------------------------------------------------

## 8. Draft docker-compose.yml (Skeleton)

``` yaml
version: "3.9"

services:
  radio-recorder-api:
    build:
      context: .
      dockerfile: Dockerfile
    image: radio-recorder-api:dev
    container_name: radio-recorder-api
    restart: unless-stopped
    environment:
      - TZ=America/Denver
      - APP_CONFIG_DIR=/config
      - APP_WORK_DIR=/work
      - APP_SSH_KEY=/ssh/id_ed25519
      - APP_PORT=8000
    ports:
      - "8000:8000"
    volumes:
      - ./config:/config:ro
      - ./work:/work
      - ~/.ssh/id_ed25519:/ssh/id_ed25519:ro
      - /etc/localtime:/etc/localtime:ro
      - /etc/timezone:/etc/timezone:ro
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
```

**Directory Layout:**

    project-root/
    ├─ Dockerfile
    ├─ docker-compose.yml
    ├─ requirements.txt
    ├─ gunicorn_conf.py
    ├─ config/
    │  ├─ config_shows.json
    │  └─ config_stations.json
    ├─ work/  # temp/output workspace
    └─ src/
       ├─ main.py
       ├─ recorder.py
       ├─ metadata.py
       ├─ transfer.py
       └─ util.py
