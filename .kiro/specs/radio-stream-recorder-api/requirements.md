# Requirements Document

## Introduction

This feature involves developing a Python-based API that runs natively on the host system to record radio streams, converts them to MP3 format with rich metadata including artwork, and transfers the resulting files to a remote directory via SCP. The API will be triggered by external POST requests and will handle the entire workflow from stream recording to file transfer automatically.

## Requirements

### Requirement 1

**User Story:** As an external system, I want to trigger radio stream recordings via API, so that I can automate the capture of radio shows at specific times.

#### Acceptance Criteria

1. WHEN a POST request is sent to `/record` endpoint with `show` and `duration_minutes` parameters THEN the system SHALL validate the show exists in configuration
2. WHEN the show configuration is found THEN the system SHALL immediately begin recording the specified radio stream
3. WHEN the duration_minutes parameter is provided THEN the system SHALL record for exactly that duration
4. IF the show key does not exist in config_shows.json THEN the system SHALL return a 400 error with descriptive message

### Requirement 2

**User Story:** As a system administrator, I want radio shows and stations to be configurable via JSON files, so that I can easily manage different shows and their associated metadata without code changes.

#### Acceptance Criteria

1. WHEN the system starts THEN it SHALL load show configurations from config_shows.json
2. WHEN the system starts THEN it SHALL load station configurations from config_stations.json
3. WHEN a show is requested THEN the system SHALL lookup the station URL using the station key from the show configuration
4. IF configuration files are malformed or missing THEN the system SHALL log errors and fail gracefully

### Requirement 3

**User Story:** As a content curator, I want recorded streams to be automatically converted to MP3 with proper metadata, so that the files are properly organized and tagged for media libraries.

#### Acceptance Criteria

1. WHEN a stream recording completes THEN the system SHALL convert the file to MP3 format if not already MP3
2. WHEN converting to MP3 THEN the system SHALL apply metadata tags including Artist, Album Artist, Album, Track Number, and Date
3. WHEN applying metadata THEN the system SHALL embed the artwork file specified in the show configuration
4. WHEN generating the filename THEN the system SHALL use format "YYYY-MM-DD Show" based on local time
5. WHEN calculating track numbers THEN the system SHALL use days since Jan 1 for daily shows and weeks since Jan 1 for weekly shows

### Requirement 4

**User Story:** As a media library manager, I want recorded files to be automatically transferred to a remote directory structure, so that they are immediately available in the organized media collection.

#### Acceptance Criteria

1. WHEN MP3 processing completes THEN the system SHALL transfer the file via SCP to the remote directory
2. WHEN transferring files THEN the system SHALL create directory structure as remote-directory/show/Album/
3. WHEN authenticating SCP transfers THEN the system SHALL use the mounted SSH private key
4. WHEN SCP transfer completes successfully THEN the system SHALL clean up temporary files
5. IF SCP transfer fails THEN the system SHALL log the error and retain temporary files for manual recovery

### Requirement 5

**User Story:** As a system operator, I want the API to run natively on the system with proper health checks, so that it can be deployed and monitored reliably.

#### Acceptance Criteria

1. WHEN the application starts THEN it SHALL expose the API on the configured port (default 8000)
2. WHEN health checks are performed THEN the system SHALL respond to /healthz endpoint
3. WHEN the application runs in production THEN it SHALL use non-root user for security
4. WHEN configuration is needed THEN the system SHALL read from local directories for config files, work directory, and SSH keys
5. WHEN timezone handling is required THEN the system SHALL use the host system's local timezone, never UTC

### Requirement 6

**User Story:** As a developer, I want proper error handling and logging throughout the recording process, so that I can troubleshoot issues and monitor system health.

#### Acceptance Criteria

1. WHEN any step in the recording process fails THEN the system SHALL log detailed error information
2. WHEN API requests are received THEN the system SHALL log request details and processing status
3. WHEN file operations occur THEN the system SHALL handle permission errors gracefully
4. WHEN network operations fail THEN the system SHALL provide meaningful error responses to API clients
5. WHEN the system encounters configuration errors THEN it SHALL fail fast with clear error messages

### Requirement 7

**User Story:** As a system administrator, I want the recording process to handle concurrent requests appropriately, so that multiple recordings can be managed without conflicts.

#### Acceptance Criteria

1. WHEN multiple recording requests are received THEN the system SHALL handle them concurrently without file conflicts
2. WHEN temporary files are created THEN the system SHALL use unique identifiers to prevent collisions
3. WHEN system resources are limited THEN the system SHALL queue requests appropriately
4. WHEN long-running recordings are in progress THEN the system SHALL remain responsive to health checks and new requests