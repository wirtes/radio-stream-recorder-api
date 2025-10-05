"""Structured logging configuration for the Radio Stream Recorder API."""

import logging
import logging.config
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import json


class StructuredFormatter(logging.Formatter):
    """Custom formatter that outputs structured JSON logs."""
    
    def __init__(self, include_extra_fields: bool = True):
        """Initialize the structured formatter.
        
        Args:
            include_extra_fields: Whether to include extra fields from log records
        """
        super().__init__()
        self.include_extra_fields = include_extra_fields
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON.
        
        Args:
            record: Log record to format
            
        Returns:
            JSON formatted log string
        """
        # Base log structure
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'process_id': os.getpid(),
            'thread_id': record.thread
        }
        
        # Add exception information if present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': self.formatException(record.exc_info) if record.exc_info else None
            }
        
        # Add extra fields if enabled
        if self.include_extra_fields:
            # Get extra fields from record (excluding standard fields)
            standard_fields = {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
                'module', 'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                'thread', 'threadName', 'processName', 'process', 'getMessage', 'exc_info',
                'exc_text', 'stack_info', 'message'
            }
            
            extra_fields = {}
            for key, value in record.__dict__.items():
                if key not in standard_fields and not key.startswith('_'):
                    # Convert non-serializable objects to strings
                    try:
                        json.dumps(value)  # Test if serializable
                        extra_fields[key] = value
                    except (TypeError, ValueError):
                        extra_fields[key] = str(value)
            
            if extra_fields:
                log_entry['extra'] = extra_fields
        
        return json.dumps(log_entry, ensure_ascii=False)


class RequestResponseFilter(logging.Filter):
    """Filter for API request/response logging."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log records for request/response logging.
        
        Args:
            record: Log record to filter
            
        Returns:
            True if record should be logged, False otherwise
        """
        # Only log records that have request/response context
        return hasattr(record, 'request_id') or hasattr(record, 'endpoint') or hasattr(record, 'method')


class PerformanceFilter(logging.Filter):
    """Filter for performance-related logging."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log records for performance logging.
        
        Args:
            record: Log record to filter
            
        Returns:
            True if record should be logged, False otherwise
        """
        # Log records with performance metrics
        return (hasattr(record, 'duration') or 
                hasattr(record, 'file_size') or 
                hasattr(record, 'recording_id') or
                'performance' in record.getMessage().lower())


def setup_logging(
    log_level: str = "INFO",
    log_dir: Optional[str] = None,
    enable_console: bool = True,
    enable_file: bool = True,
    enable_structured: bool = True,
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> None:
    """Set up comprehensive logging configuration.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files (defaults to /work/logs)
        enable_console: Whether to enable console logging
        enable_file: Whether to enable file logging
        enable_structured: Whether to use structured JSON logging
        max_file_size: Maximum size for log files before rotation
        backup_count: Number of backup files to keep
    """
    # Set default log directory
    if log_dir is None:
        log_dir = os.getenv("APP_LOG_DIR", "/work/logs")
    
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Base logging configuration
    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            },
            'detailed': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - [%(module)s.%(funcName)s:%(lineno)d] - PID:%(process)d - %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            },
            'structured': {
                '()': StructuredFormatter,
                'include_extra_fields': True
            }
        },
        'filters': {
            'request_response': {
                '()': RequestResponseFilter
            },
            'performance': {
                '()': PerformanceFilter
            }
        },
        'handlers': {},
        'loggers': {
            # Root logger
            '': {
                'level': numeric_level,
                'handlers': []
            },
            # Application loggers
            'src': {
                'level': numeric_level,
                'handlers': [],
                'propagate': False
            },
            'src.services': {
                'level': numeric_level,
                'handlers': [],
                'propagate': False
            },
            'src.services.recording_service': {
                'level': 'DEBUG',  # More detailed logging for recording service
                'handlers': [],
                'propagate': False
            },
            # FastAPI and uvicorn loggers
            'uvicorn': {
                'level': 'INFO',
                'handlers': [],
                'propagate': False
            },
            'uvicorn.access': {
                'level': 'INFO',
                'handlers': [],
                'propagate': False
            },
            'fastapi': {
                'level': 'INFO',
                'handlers': [],
                'propagate': False
            }
        }
    }
    
    handlers_to_add = []
    
    # Console handler
    if enable_console:
        console_handler = {
            'class': 'logging.StreamHandler',
            'level': numeric_level,
            'formatter': 'structured' if enable_structured else 'standard',
            'stream': 'ext://sys.stdout'
        }
        config['handlers']['console'] = console_handler
        handlers_to_add.append('console')
    
    # File handlers
    if enable_file:
        # Main application log
        main_log_handler = {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': numeric_level,
            'formatter': 'structured' if enable_structured else 'detailed',
            'filename': str(log_path / 'app.log'),
            'maxBytes': max_file_size,
            'backupCount': backup_count,
            'encoding': 'utf-8'
        }
        config['handlers']['main_file'] = main_log_handler
        handlers_to_add.append('main_file')
        
        # Recording-specific log
        recording_log_handler = {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'DEBUG',
            'formatter': 'structured' if enable_structured else 'detailed',
            'filename': str(log_path / 'recordings.log'),
            'maxBytes': max_file_size,
            'backupCount': backup_count,
            'encoding': 'utf-8'
        }
        config['handlers']['recording_file'] = recording_log_handler
        
        # API request/response log
        api_log_handler = {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'INFO',
            'formatter': 'structured' if enable_structured else 'detailed',
            'filename': str(log_path / 'api.log'),
            'maxBytes': max_file_size,
            'backupCount': backup_count,
            'encoding': 'utf-8',
            'filters': ['request_response']
        }
        config['handlers']['api_file'] = api_log_handler
        
        # Performance log
        performance_log_handler = {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'INFO',
            'formatter': 'structured' if enable_structured else 'detailed',
            'filename': str(log_path / 'performance.log'),
            'maxBytes': max_file_size,
            'backupCount': backup_count,
            'encoding': 'utf-8',
            'filters': ['performance']
        }
        config['handlers']['performance_file'] = performance_log_handler
        
        # Error-only log
        error_log_handler = {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'ERROR',
            'formatter': 'structured' if enable_structured else 'detailed',
            'filename': str(log_path / 'errors.log'),
            'maxBytes': max_file_size,
            'backupCount': backup_count,
            'encoding': 'utf-8'
        }
        config['handlers']['error_file'] = error_log_handler
        handlers_to_add.append('error_file')
    
    # Assign handlers to loggers
    for logger_name in config['loggers']:
        config['loggers'][logger_name]['handlers'] = handlers_to_add.copy()
    
    # Special handler assignments
    if enable_file:
        # Recording service gets its own log file
        config['loggers']['src.services.recording_service']['handlers'].append('recording_file')
        
        # API loggers get API-specific handlers
        config['loggers']['uvicorn.access']['handlers'].append('api_file')
        config['loggers']['fastapi']['handlers'].append('api_file')
        
        # Performance logging for all service loggers
        config['loggers']['src.services']['handlers'].append('performance_file')
    
    # Apply the configuration
    logging.config.dictConfig(config)
    
    # Log the configuration setup
    logger = logging.getLogger(__name__)
    logger.info("Logging configuration initialized", extra={
        'log_level': log_level,
        'log_dir': str(log_path),
        'enable_console': enable_console,
        'enable_file': enable_file,
        'enable_structured': enable_structured,
        'handlers_configured': list(config['handlers'].keys())
    })


def get_request_logger(request_id: str, endpoint: str, method: str) -> logging.LoggerAdapter:
    """Get a logger adapter for API request logging.
    
    Args:
        request_id: Unique request identifier
        endpoint: API endpoint path
        method: HTTP method
        
    Returns:
        LoggerAdapter with request context
    """
    logger = logging.getLogger('src.api.requests')
    
    return logging.LoggerAdapter(logger, {
        'request_id': request_id,
        'endpoint': endpoint,
        'method': method
    })


def get_performance_logger(component: str) -> logging.LoggerAdapter:
    """Get a logger adapter for performance logging.
    
    Args:
        component: Component name for performance tracking
        
    Returns:
        LoggerAdapter with performance context
    """
    logger = logging.getLogger('src.performance')
    
    return logging.LoggerAdapter(logger, {
        'component': component,
        'performance_log': True
    })


def get_recording_logger(recording_id: str, show_key: str) -> logging.LoggerAdapter:
    """Get a logger adapter for recording-specific logging.
    
    Args:
        recording_id: Unique recording identifier
        show_key: Show key being recorded
        
    Returns:
        LoggerAdapter with recording context
    """
    logger = logging.getLogger('src.services.recording_service')
    
    return logging.LoggerAdapter(logger, {
        'recording_id': recording_id,
        'show_key': show_key,
        'recording_log': True
    })


class LoggingContextManager:
    """Context manager for adding structured logging context."""
    
    def __init__(self, logger: logging.Logger, **context):
        """Initialize context manager.
        
        Args:
            logger: Logger to add context to
            **context: Context fields to add
        """
        self.logger = logger
        self.context = context
        self.original_extra = getattr(logger, '_extra_context', {})
    
    def __enter__(self):
        """Enter context and add fields."""
        # Store context in logger for use by handlers
        if not hasattr(self.logger, '_extra_context'):
            self.logger._extra_context = {}
        
        self.logger._extra_context.update(self.context)
        return self.logger
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and restore original state."""
        self.logger._extra_context = self.original_extra


def log_with_context(logger: logging.Logger, **context):
    """Create a context manager for structured logging.
    
    Args:
        logger: Logger to add context to
        **context: Context fields to add
        
    Returns:
        LoggingContextManager instance
    """
    return LoggingContextManager(logger, **context)


# Convenience functions for common logging patterns
def log_api_request(request_id: str, endpoint: str, method: str, **extra):
    """Log an API request with structured data.
    
    Args:
        request_id: Unique request identifier
        endpoint: API endpoint path
        method: HTTP method
        **extra: Additional fields to log
    """
    logger = get_request_logger(request_id, endpoint, method)
    logger.info(f"API request received: {method} {endpoint}", extra=extra)


def log_api_response(request_id: str, endpoint: str, method: str, status_code: int, duration: float, **extra):
    """Log an API response with structured data.
    
    Args:
        request_id: Unique request identifier
        endpoint: API endpoint path
        method: HTTP method
        status_code: HTTP status code
        duration: Request duration in seconds
        **extra: Additional fields to log
    """
    logger = get_request_logger(request_id, endpoint, method)
    logger.info(f"API response sent: {method} {endpoint} -> {status_code}", extra={
        'status_code': status_code,
        'duration': duration,
        **extra
    })


def log_performance_metric(component: str, operation: str, duration: float, **metrics):
    """Log a performance metric with structured data.
    
    Args:
        component: Component name
        operation: Operation name
        duration: Operation duration in seconds
        **metrics: Additional performance metrics
    """
    logger = get_performance_logger(component)
    logger.info(f"Performance: {component}.{operation}", extra={
        'operation': operation,
        'duration': duration,
        **metrics
    })


def log_recording_step(recording_id: str, show_key: str, step: str, status: str, **extra):
    """Log a recording workflow step with structured data.
    
    Args:
        recording_id: Unique recording identifier
        show_key: Show key being recorded
        step: Workflow step name
        status: Step status (started, completed, failed)
        **extra: Additional step data
    """
    logger = get_recording_logger(recording_id, show_key)
    
    level = logging.INFO
    if status == 'failed':
        level = logging.ERROR
    elif status == 'started':
        level = logging.DEBUG
    
    logger.log(level, f"Recording step {step}: {status}", extra={
        'step': step,
        'status': status,
        **extra
    })