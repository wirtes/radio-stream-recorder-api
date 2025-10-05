# Implementation Plan

- [x] 1. Set up project structure and core interfaces
  - Create directory structure for API, services, models, and utilities
  - Set up Python project with requirements.txt and proper package structure
  - Define base interfaces and data models for configuration and API requests
  - _Requirements: 5.4, 6.5_

- [x] 2. Implement configuration management system
  - [x] 2.1 Create configuration data models and validation
    - Implement ShowConfig and StationConfig Pydantic models
    - Add validation for required fields and data types
    - _Requirements: 2.1, 2.2, 2.4_
  
  - [x] 2.2 Implement ConfigManager class
    - Write JSON file loading and parsing logic
    - Add thread-safe configuration access methods
    - Implement error handling for malformed or missing config files
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  
  - [ ]* 2.3 Write unit tests for configuration management
    - Test configuration loading with valid and invalid JSON files
    - Test error handling for missing files and malformed data
    - _Requirements: 2.1, 2.2, 2.4_

- [x] 3. Create FastAPI application and request handling
  - [x] 3.1 Set up FastAPI application with request/response models
    - Create RecordRequest and RecordResponse Pydantic models
    - Implement basic FastAPI app structure with CORS and middleware
    - _Requirements: 1.1, 1.4, 5.1_
  
  - [x] 3.2 Implement /record endpoint with validation
    - Add POST endpoint that validates show existence in configuration
    - Implement request parameter validation and error responses
    - _Requirements: 1.1, 1.2, 1.4, 6.4_
  
  - [x] 3.3 Implement /healthz endpoint
    - Create health check endpoint that returns system status
    - _Requirements: 5.2_
  
  - [ ]* 3.4 Write API endpoint tests
    - Test /record endpoint with valid and invalid requests
    - Test /healthz endpoint functionality
    - _Requirements: 1.1, 1.4, 5.2_

- [x] 4. Implement stream recording functionality
  - [x] 4.1 Create StreamRecorder class with ffmpeg integration
    - Implement ffmpeg command building for stream recording
    - Add process management and monitoring for recording sessions
    - Handle recording duration and output file management
    - _Requirements: 1.2, 1.3, 6.1, 6.4_
  
  - [x] 4.2 Add error handling and retry logic for stream recording
    - Implement network error detection and retry mechanisms
    - Add logging for recording process status and errors
    - _Requirements: 6.1, 6.2, 6.4_
  
  - [ ]* 4.3 Write stream recording tests
    - Mock ffmpeg processes for testing recording logic
    - Test error handling and retry mechanisms
    - _Requirements: 1.2, 1.3, 6.1_

- [x] 5. Implement metadata processing and MP3 conversion
  - [x] 5.1 Create MetadataProcessor class
    - Implement audio file conversion to MP3 using ffmpeg
    - Add metadata tag application using mutagen library
    - Implement track number calculation based on frequency (daily/weekly)
    - _Requirements: 3.1, 3.2, 3.4, 3.5_
  
  - [x] 5.2 Implement artwork embedding functionality
    - Add artwork file reading and embedding into MP3 files
    - Handle artwork file validation and error cases
    - _Requirements: 3.3_
  
  - [x] 5.3 Add filename generation logic
    - Implement "YYYY-MM-DD Show" filename format using local timezone
    - _Requirements: 3.4, 5.5_
  
  - [ ]* 5.4 Write metadata processing tests
    - Test MP3 conversion and metadata application
    - Test track number calculation for daily and weekly shows
    - Test artwork embedding functionality
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 6. Implement file transfer service
  - [x] 6.1 Create TransferService class with SCP functionality
    - Implement SCP command building and execution
    - Add remote directory structure creation logic
    - Handle SSH key authentication and permissions
    - _Requirements: 4.1, 4.2, 4.3, 4.5_
  
  - [x] 6.2 Add transfer error handling and cleanup
    - Implement error detection for failed SCP transfers
    - Add temporary file cleanup on successful transfers
    - Retain files on transfer failure for manual recovery
    - _Requirements: 4.4, 4.5, 6.1_
  
  - [ ]* 6.3 Write file transfer tests
    - Mock SCP processes for testing transfer logic
    - Test remote path building and directory structure
    - Test error handling and cleanup mechanisms
    - _Requirements: 4.1, 4.2, 4.4, 4.5_

- [x] 7. Create main recording service orchestrator
  - [x] 7.1 Implement RecordingService class
    - Coordinate the complete recording workflow from stream to transfer
    - Manage temporary file lifecycle with unique identifiers
    - Handle concurrent recording requests without conflicts
    - _Requirements: 7.1, 7.2, 6.1_
  
  - [x] 7.2 Add comprehensive error handling and logging
    - Implement detailed logging for each step of the recording process
    - Add error recovery mechanisms and graceful failure handling
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  
  - [ ]* 7.3 Write integration tests for recording service
    - Test end-to-end recording workflow with mock dependencies
    - Test concurrent request handling and file conflict prevention
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 8. Create Docker container configuration
  - [x] 8.1 Create Dockerfile with proper security configuration
    - Set up non-root user execution (UID 10001)
    - Configure volume mounts for config, work directory, and SSH keys
    - Set up timezone handling and environment variables
    - _Requirements: 5.3, 5.4, 5.5_
  
  - [x] 8.2 Add Docker health check configuration
    - Configure health check using /healthz endpoint
    - Set appropriate intervals, timeouts, and retry counts
    - _Requirements: 5.2_
  
  - [x] 8.3 Create docker-compose.yml for development
    - Set up volume mounts and environment variables
    - Configure port mapping and network settings
    - _Requirements: 5.1, 5.4_

- [x] 9. Add logging and monitoring
  - [x] 9.1 Configure structured logging throughout the application
    - Set up logging configuration with appropriate levels
    - Add request/response logging for API endpoints
    - Implement detailed logging for each processing step
    - _Requirements: 6.1, 6.2, 6.5_
  
  - [x] 9.2 Add performance monitoring and resource management
    - Implement request queuing for resource management
    - Add monitoring for long-running recordings
    - _Requirements: 7.3, 7.4_

- [x] 10. Create project documentation
  - [x] 10.1 Write comprehensive README.md
    - Document installation and setup instructions
    - Provide curl examples for API usage
    - Include configuration file examples and explanations
    - _Requirements: All requirements for user guidance_
  
  - [x] 10.2 Create API documentation
    - Generate OpenAPI/Swagger documentation
    - Document all endpoints with request/response examples
    - Include error codes and troubleshooting guide
    - _Requirements: All API-related requirements_

- [-] 11. Final integration and deployment preparation
  - [x] 11.1 Create sample configuration files
    - Provide example config_shows.json and config_stations.json
    - Document all configuration options and their purposes
    - _Requirements: 2.1, 2.2_
  
  - [x] 11.2 Test complete Docker deployment
    - Build and test Docker container with all dependencies
    - Verify volume mounts and environment variable handling
    - Test health checks and container lifecycle
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_