"""Main entry point for the Radio Stream Recorder API."""

import os
import logging
import uuid
import time
from datetime import datetime
from fastapi import FastAPI, HTTPException, status, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from src.models.config import AppConfig
from src.models.api import RecordRequest, RecordResponse, HealthResponse, ErrorResponse
from src.services.config_manager import ConfigManager, ConfigurationError
from src.utils.logging_config import (
    setup_logging, 
    log_api_request, 
    log_api_response, 
    get_request_logger,
    log_performance_metric
)

# Initialize structured logging
setup_logging(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_dir=os.getenv("APP_LOG_DIR", "./work/logs"),
    enable_console=True,
    enable_file=True,
    enable_structured=True
)

logger = logging.getLogger(__name__)

# Initialize application configuration
app_config = AppConfig(
    config_dir=os.getenv("APP_CONFIG_DIR", "./config"),
    work_dir=os.getenv("APP_WORK_DIR", "./work"),
    ssh_key_path=os.getenv("APP_SSH_KEY", os.path.expanduser("~/.ssh/id_rsa")),
    port=int(os.getenv("APP_PORT", "8000")),
    timezone=os.getenv("TZ", "America/Denver")
)

# Initialize FastAPI application
app = FastAPI(
    title="Radio Stream Recorder API",
    description="API for recording radio streams with metadata processing and file transfer",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Add trusted host middleware for security
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Configure appropriately for production
)

# Request/Response logging middleware
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Middleware for logging API requests and responses."""
    # Generate unique request ID
    request_id = str(uuid.uuid4())
    
    # Extract request information
    method = request.method
    endpoint = str(request.url.path)
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    
    # Log request
    start_time = time.time()
    log_api_request(
        request_id=request_id,
        endpoint=endpoint,
        method=method,
        client_ip=client_ip,
        user_agent=user_agent,
        query_params=dict(request.query_params) if request.query_params else None
    )
    
    # Process request
    try:
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Log response
        log_api_response(
            request_id=request_id,
            endpoint=endpoint,
            method=method,
            status_code=response.status_code,
            duration=duration
        )
        
        # Log performance metric
        log_performance_metric(
            component="api",
            operation=f"{method}_{endpoint.replace('/', '_')}",
            duration=duration,
            status_code=response.status_code
        )
        
        # Add request ID to response headers for tracing
        response.headers["X-Request-ID"] = request_id
        
        return response
        
    except Exception as e:
        # Calculate duration for failed requests
        duration = time.time() - start_time
        
        # Log error response
        request_logger = get_request_logger(request_id, endpoint, method)
        request_logger.error(f"Request failed: {e}", extra={
            'duration': duration,
            'error_type': type(e).__name__,
            'error_message': str(e)
        })
        
        # Re-raise the exception
        raise

# Initialize configuration manager
config_manager = ConfigManager(config_dir=app_config.config_dir)

# Initialize recording service (will be set up in startup event)
recording_service = None

# Application startup event
@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    global recording_service
    
    try:
        config_manager.load_configurations()
        logger.info("Configuration loaded successfully")
        
        # Initialize recording service
        from src.services.recording_service import RecordingService
        recording_service = RecordingService(
            config_manager=config_manager,
            work_dir=app_config.work_dir,
            ssh_key_path=app_config.ssh_key_path,
            max_concurrent_recordings=3
        )
        logger.info("Recording service initialized successfully")
        
        # Start performance monitoring
        await recording_service.start_monitoring()
        logger.info("Performance monitoring started")
        
        logger.info("Application started successfully")
    except ConfigurationError as e:
        logger.error(f"Failed to start application: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to initialize recording service: {e}")
        raise

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Radio Stream Recorder API", "version": "1.0.0"}

# Record endpoint
@app.post("/record", response_model=RecordResponse, responses={
    400: {"model": ErrorResponse, "description": "Bad Request"},
    500: {"model": ErrorResponse, "description": "Internal Server Error"},
    503: {"model": ErrorResponse, "description": "Service Unavailable"}
})
async def record_stream(request: RecordRequest) -> RecordResponse:
    """Record a radio stream for the specified show and duration.
    
    This endpoint triggers the complete recording workflow:
    1. Stream recording from the configured radio station
    2. Audio processing and metadata application
    3. File transfer to remote storage location
    
    Args:
        request: Recording request containing show key and duration
        
    Returns:
        RecordResponse with success status and details
        
    Raises:
        HTTPException: If validation fails, service unavailable, or other errors occur
    """
    if recording_service is None:
        logger.error("Recording service not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recording service not available"
        )
    
    try:
        logger.info("Recording request received", extra={
            'show': request.show,
            'duration_minutes': request.duration_minutes,
            'endpoint': '/record'
        })
        
        # Execute the complete recording workflow
        result = await recording_service.record_show(request.show, request.duration_minutes)
        
        if result['success']:
            logger.info("Recording completed successfully", extra={
                'recording_id': result['recording_id'],
                'show': request.show,
                'duration_minutes': request.duration_minutes,
                'total_duration': result.get('performance_metrics', {}).get('total_duration'),
                'steps_completed': result.get('steps_completed', []),
                'final_file_path': result.get('final_file_path'),
                'remote_path': result.get('remote_path')
            })
            return RecordResponse(
                success=True,
                message=result['message'],
                recording_id=result['recording_id'],
                estimated_completion=result['completed_at']
            )
        else:
            # Recording failed - determine appropriate HTTP status code
            error_step = result.get('error_step', 'unknown')
            
            if error_step in ['validation', 'configuration_validation', 'parameter_validation']:
                # Client error - bad request
                logger.warning("Recording validation failed", extra={
                    'show': request.show,
                    'duration_minutes': request.duration_minutes,
                    'error_step': error_step,
                    'error_message': result['message'],
                    'recording_id': result.get('recording_id')
                })
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=result['message']
                )
            elif error_step == 'concurrency_check':
                # Service temporarily unavailable
                logger.warning("Recording rejected due to concurrency", extra={
                    'show': request.show,
                    'duration_minutes': request.duration_minutes,
                    'error_step': error_step,
                    'error_message': result['message'],
                    'recording_id': result.get('recording_id')
                })
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=result['message']
                )
            else:
                # Server error - internal processing failed
                logger.error("Recording failed", extra={
                    'show': request.show,
                    'duration_minutes': request.duration_minutes,
                    'error_step': error_step,
                    'error_message': result['message'],
                    'recording_id': result.get('recording_id'),
                    'error_details': result.get('error_details'),
                    'steps_completed': result.get('steps_completed', [])
                })
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Recording failed: {result.get('error_step', 'unknown error')}"
                )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error during recording request: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

# Health check endpoint
@app.get("/healthz", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint for service monitoring.
    
    Performs comprehensive health checks including:
    - Configuration loading status
    - Recording service availability
    - Component health status
    
    Returns:
        HealthResponse with current system status
    """
    try:
        overall_status = "healthy"
        
        # Check if configuration is loaded
        is_config_loaded = config_manager.is_loaded()
        if not is_config_loaded:
            overall_status = "unhealthy"
        
        # Check recording service health if available
        service_details = {}
        if recording_service is not None:
            try:
                # Get performance status
                performance_status = await recording_service.performance_monitor.get_performance_status()
                service_details['performance'] = performance_status
                
                # Check if resource monitoring is healthy
                resource_status = performance_status.get('resource_status', {}).get('status', 'unknown')
                if resource_status == 'warning':
                    overall_status = 'degraded'
                elif resource_status not in ['healthy', 'no_data']:
                    overall_status = 'unhealthy'
                
                # Check queue status
                queue_status = performance_status.get('queue_status', {})
                if queue_status.get('available_slots', 0) <= 0 and queue_status.get('queue_size', 0) > 0:
                    if overall_status == 'healthy':
                        overall_status = 'degraded'  # System is working but at capacity
                
                service_details['queue_status'] = queue_status
                service_details['active_recordings'] = len(performance_status.get('active_recordings', []))
                
            except Exception as e:
                logger.error(f"Recording service health check failed: {e}")
                overall_status = "unhealthy"
                service_details['error'] = str(e)
        else:
            overall_status = "unhealthy"
        
        response = HealthResponse(
            status=overall_status,
            timestamp=datetime.now(),
            version="1.0.0"
        )
        
        # Log health check with performance details
        logger.info("Health check performed", extra={
            'health_status': overall_status,
            'service_details': service_details,
            'config_loaded': is_config_loaded
        })
        
        return response
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            timestamp=datetime.now(),
            version="1.0.0"
        )


# Additional monitoring endpoints
@app.get("/status")
async def get_status():
    """Get detailed system status including active recordings and statistics."""
    if recording_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recording service not available"
        )
    
    try:
        active_recordings = await recording_service.get_active_recordings()
        statistics = await recording_service.get_recording_statistics()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "service_status": "running",
            "active_recordings": active_recordings,
            "statistics": statistics
        }
    except Exception as e:
        logger.error(f"Status endpoint failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get system status"
        )


@app.get("/recovery")
async def get_recovery_info():
    """Get information about failed recordings for recovery purposes."""
    if recording_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recording service not available"
        )
    
    try:
        recovery_info = await recording_service.get_error_recovery_info()
        return recovery_info
    except Exception as e:
        logger.error(f"Recovery info endpoint failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get recovery information"
        )


# Application shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on application shutdown."""
    global recording_service
    
    try:
        if recording_service is not None:
            # Stop performance monitoring
            await recording_service.stop_monitoring()
            
            # Stop any active recordings gracefully
            await recording_service.stream_recorder.stop_all_recordings()
            logger.info("Recording service shutdown completed")
        
        logger.info("Application shutdown completed")
    except Exception as e:
        logger.error(f"Error during application shutdown: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=app_config.port)