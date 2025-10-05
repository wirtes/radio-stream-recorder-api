"""Main recording service orchestrator for radio stream recording workflow."""

import asyncio
import logging
import os
import sys
import traceback
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from src.models.config import ShowConfig
from src.services.interfaces import (
    ConfigManagerInterface, 
    StreamRecorderInterface, 
    MetadataProcessorInterface, 
    TransferServiceInterface
)
from src.services.config_manager import ConfigManager, ConfigurationError
from src.services.stream_recorder import StreamRecorder, RecordingError as StreamRecordingError
from src.services.metadata_processor import MetadataProcessor
from src.services.transfer_service import TransferService
from src.utils.logging_config import (
    get_recording_logger, 
    log_recording_step, 
    log_performance_metric,
    log_with_context
)
from src.utils.performance_monitor import PerformanceMonitor, RequestQueue

# Get logger for this module
logger = logging.getLogger(__name__)


class RecordingStepError(Exception):
    """Base exception for recording step errors with enhanced context."""
    
    def __init__(
        self, 
        message: str, 
        step: str, 
        recording_id: str = None,
        show_key: str = None,
        retryable: bool = False,
        original_exception: Exception = None
    ):
        super().__init__(message)
        self.step = step
        self.recording_id = recording_id
        self.show_key = show_key
        self.retryable = retryable
        self.original_exception = original_exception
        self.timestamp = datetime.now()
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging and response."""
        return {
            'error_type': self.__class__.__name__,
            'message': str(self),
            'step': self.step,
            'recording_id': self.recording_id,
            'show_key': self.show_key,
            'retryable': self.retryable,
            'timestamp': self.timestamp.isoformat(),
            'original_exception': str(self.original_exception) if self.original_exception else None
        }


class ValidationError(RecordingStepError):
    """Exception for validation-related errors."""
    pass


class ConcurrencyError(RecordingStepError):
    """Exception for concurrency-related errors."""
    pass


class WorkflowError(RecordingStepError):
    """Exception for general workflow errors."""
    pass


class RecoveryManager:
    """Manages error recovery and graceful failure handling."""
    
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.recovery_log_file = work_dir / "recovery.log"
        
    def log_failure_for_recovery(
        self, 
        recording_id: str, 
        show_key: str, 
        temp_files: List[str], 
        error_info: Dict[str, Any]
    ) -> None:
        """Log failure information for manual recovery."""
        try:
            recovery_info = {
                'timestamp': datetime.now().isoformat(),
                'recording_id': recording_id,
                'show_key': show_key,
                'temp_files': temp_files,
                'error_info': error_info,
                'recovery_instructions': self._generate_recovery_instructions(temp_files, error_info)
            }
            
            # Append to recovery log
            with open(self.recovery_log_file, 'a', encoding='utf-8') as f:
                import json
                f.write(json.dumps(recovery_info, indent=2) + '\n---\n')
                
            logger.info(f"Recovery information logged for recording {recording_id}")
            
        except Exception as e:
            logger.error(f"Failed to log recovery information: {e}")
    
    def _generate_recovery_instructions(self, temp_files: List[str], error_info: Dict[str, Any]) -> List[str]:
        """Generate human-readable recovery instructions."""
        instructions = []
        
        if error_info.get('step') == 'file_transfer':
            instructions.append("File transfer failed - processed MP3 file should be ready for manual transfer")
            instructions.append(f"Look for MP3 files in: {self.work_dir}")
            instructions.append("Check network connectivity and SSH key permissions")
            
        elif error_info.get('step') == 'metadata_processing':
            instructions.append("Metadata processing failed - raw recording may be available")
            instructions.append("Check ffmpeg installation and audio file format")
            
        elif error_info.get('step') == 'stream_recording':
            instructions.append("Stream recording failed - check stream URL and network connectivity")
            instructions.append("Verify show and station configuration")
            
        instructions.append(f"Temporary files to check: {', '.join(temp_files)}")
        instructions.append(f"Recording ID for reference: {error_info.get('recording_id', 'unknown')}")
        
        return instructions


class RecordingService:
    """Main orchestrator for the complete recording workflow with comprehensive error handling."""
    
    def __init__(
        self,
        config_manager: ConfigManagerInterface,
        work_dir: str = "/work",
        ssh_key_path: str = "/ssh/id_rsa",
        max_concurrent_recordings: int = 3
    ):
        """Initialize the recording service.
        
        Args:
            config_manager: Configuration manager instance
            work_dir: Working directory for temporary files
            ssh_key_path: Path to SSH private key for transfers
            max_concurrent_recordings: Maximum number of concurrent recordings
        """
        self.config_manager = config_manager
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize service components with error handling
        try:
            self.stream_recorder = StreamRecorder()
            logger.debug("StreamRecorder initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize StreamRecorder: {e}")
            raise WorkflowError(
                "Failed to initialize stream recorder component",
                step="initialization",
                original_exception=e
            )
        
        try:
            self.metadata_processor = MetadataProcessor(work_dir=work_dir)
            logger.debug("MetadataProcessor initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MetadataProcessor: {e}")
            raise WorkflowError(
                "Failed to initialize metadata processor component",
                step="initialization",
                original_exception=e
            )
        
        try:
            self.transfer_service = TransferService(ssh_key_path=ssh_key_path)
            logger.debug("TransferService initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize TransferService: {e}")
            raise WorkflowError(
                "Failed to initialize transfer service component",
                step="initialization",
                original_exception=e
            )
        
        # Performance monitoring and resource management
        self.performance_monitor = PerformanceMonitor(
            work_dir=work_dir,
            max_concurrent_recordings=max_concurrent_recordings,
            max_queue_size=max_concurrent_recordings * 2  # Allow some queuing
        )
        
        # Legacy concurrency management (kept for compatibility)
        self.max_concurrent_recordings = max_concurrent_recordings
        self._active_recordings: Dict[str, Dict[str, Any]] = {}
        self._recording_lock = asyncio.Lock()
        
        # Thread pool for CPU-bound operations (metadata processing)
        self._thread_pool = ThreadPoolExecutor(max_workers=2)
        
        # Recovery manager for handling failures
        self.recovery_manager = RecoveryManager(self.work_dir)
        
        # Performance tracking
        self._recording_stats = {
            'total_recordings': 0,
            'successful_recordings': 0,
            'failed_recordings': 0,
            'last_reset': datetime.now()
        }
        
        logger.info(f"RecordingService initialized successfully")
        logger.info(f"Configuration: work_dir={work_dir}, max_concurrent={max_concurrent_recordings}")
        logger.info(f"Components: StreamRecorder, MetadataProcessor, TransferService, RecoveryManager, PerformanceMonitor")
    
    async def start_monitoring(self) -> None:
        """Start performance monitoring."""
        await self.performance_monitor.start()
        logger.info("Performance monitoring started")
    
    async def stop_monitoring(self) -> None:
        """Stop performance monitoring."""
        await self.performance_monitor.stop()
        logger.info("Performance monitoring stopped")
    
    async def get_active_recordings(self) -> List[Dict[str, Any]]:
        """Get list of currently active recordings with performance metrics.
        
        Returns:
            List of active recording information
        """
        return self.performance_monitor.request_queue.get_active_recordings()
    
    async def get_recording_statistics(self) -> Dict[str, Any]:
        """Get recording statistics and performance metrics.
        
        Returns:
            Dictionary with comprehensive recording statistics
        """
        performance_status = await self.performance_monitor.get_performance_status()
        
        return {
            'recording_stats': self._recording_stats,
            'performance_status': performance_status,
            'service_uptime': (datetime.now() - self._recording_stats['last_reset']).total_seconds(),
            'success_rate': (
                self._recording_stats['successful_recordings'] / 
                max(self._recording_stats['total_recordings'], 1)
            ) * 100
        }
    
    async def get_error_recovery_info(self) -> Dict[str, Any]:
        """Get information about failed recordings for recovery purposes.
        
        Returns:
            Dictionary with recovery information
        """
        try:
            recovery_info = {
                'recovery_log_exists': self.recovery_manager.recovery_log_file.exists(),
                'recovery_log_path': str(self.recovery_manager.recovery_log_file),
                'work_directory': str(self.work_dir),
                'temp_files_found': []
            }
            
            # Look for temporary files that might need recovery
            if self.work_dir.exists():
                temp_files = list(self.work_dir.glob("recording_*"))
                recovery_info['temp_files_found'] = [str(f) for f in temp_files]
            
            # Read recent recovery log entries if file exists
            if recovery_info['recovery_log_exists']:
                try:
                    with open(self.recovery_manager.recovery_log_file, 'r') as f:
                        content = f.read()
                        # Get last few entries (simple approach)
                        entries = content.split('---\n')
                        recovery_info['recent_failures'] = entries[-5:] if len(entries) > 5 else entries
                except Exception as e:
                    recovery_info['recovery_log_error'] = str(e)
            
            return recovery_info
            
        except Exception as e:
            logger.error(f"Error getting recovery info: {e}")
            return {
                'error': str(e),
                'recovery_log_path': str(self.recovery_manager.recovery_log_file)
            }
    
    @asynccontextmanager
    async def _recording_context(self, recording_id: str, show_key: str):
        """Context manager for recording lifecycle with comprehensive error handling."""
        self._recording_stats['total_recordings'] += 1
        context_logger = get_recording_logger(recording_id, show_key)
        
        try:
            context_logger.debug("Recording context started", extra={
                'context_phase': 'start',
                'total_recordings': self._recording_stats['total_recordings']
            })
            yield
            
            # If we get here, recording was successful
            self._recording_stats['successful_recordings'] += 1
            context_logger.debug("Recording context completed successfully", extra={
                'context_phase': 'success',
                'successful_recordings': self._recording_stats['successful_recordings']
            })
            
        except Exception as e:
            self._recording_stats['failed_recordings'] += 1
            context_logger.error("Recording context failed", extra={
                'context_phase': 'failed',
                'failed_recordings': self._recording_stats['failed_recordings'],
                'error': str(e),
                'error_type': type(e).__name__
            })
            raise
            
        finally:
            # Always unregister the recording
            await self._unregister_recording(recording_id)
            
            # Unregister from performance monitor
            await self.performance_monitor.request_queue.unregister_active_recording(recording_id)
            
            context_logger.debug("Recording context cleanup completed", extra={
                'context_phase': 'cleanup'
            })
    
    async def record_show(self, show_key: str, duration_minutes: int) -> Dict[str, Any]:
        """Orchestrate the complete recording workflow from stream to transfer.
        
        This method coordinates all steps of the recording process with comprehensive
        error handling, logging, and recovery mechanisms:
        
        1. Validate configuration and manage concurrency
        2. Generate unique temporary file paths
        3. Record the stream using StreamRecorder
        4. Process metadata and convert to MP3 using MetadataProcessor
        5. Transfer file to remote location using TransferService
        6. Clean up temporary files on success or retain on failure
        
        Args:
            show_key: Key identifying the show to record
            duration_minutes: Duration to record in minutes
            
        Returns:
            Dictionary containing comprehensive recording result details
            
        Raises:
            RecordingStepError: For various recording workflow errors with context
        """
        recording_id = self._generate_recording_id(show_key)
        
        # Initialize comprehensive recording result structure
        result = {
            'success': False,
            'recording_id': recording_id,
            'message': '',
            'show': show_key,
            'duration_minutes': duration_minutes,
            'started_at': datetime.now(),
            'completed_at': None,
            'steps_completed': [],
            'step_timings': {},
            'final_file_path': None,
            'remote_path': None,
            'temp_files_retained': False,
            'error_step': None,
            'error_details': None,
            'performance_metrics': {}
        }
        
        temp_files_to_cleanup = []
        step_start_time = datetime.now()
        
        # Check if system can accept the recording request
        acceptance_check = await self.performance_monitor.can_accept_recording(show_key, duration_minutes)
        if not acceptance_check['can_accept']:
            result['error_step'] = 'resource_check'
            result['message'] = f"Recording rejected: {', '.join(acceptance_check['reasons'])}"
            result['completed_at'] = datetime.now()
            result['error_details'] = {
                'reasons': acceptance_check['reasons'],
                'queue_status': acceptance_check['queue_status'],
                'resource_status': acceptance_check['resource_status']
            }
            
            logger.warning("Recording rejected due to resource constraints", extra={
                'recording_id': recording_id,
                'show': show_key,
                'reasons': acceptance_check['reasons'],
                'queue_status': acceptance_check['queue_status']
            })
            
            return result

        async with self._recording_context(recording_id, show_key):
            try:
                # Register with performance monitor
                await self.performance_monitor.request_queue.register_active_recording(
                    recording_id, show_key, duration_minutes
                )
                
                # Use structured logging for workflow start
                recording_logger = get_recording_logger(recording_id, show_key)
                recording_logger.info("Recording workflow started", extra={
                    'workflow_phase': 'start',
                    'duration_minutes': duration_minutes,
                    'started_at': result['started_at'].isoformat(),
                    'resource_status': acceptance_check['resource_status']['status']
                })
                
                # Step 1: Validation and Registration
                step_start_time = datetime.now()
                log_recording_step(recording_id, show_key, 'validation', 'started')
                
                try:
                    await self._validate_and_register_recording(recording_id, show_key, duration_minutes, result)
                    result['steps_completed'].append('validation')
                    result['step_timings']['validation'] = (datetime.now() - step_start_time).total_seconds()
                    
                    # Update performance monitor
                    await self.performance_monitor.request_queue.update_recording_progress(
                        recording_id, 'validation', step_timing=result['step_timings']['validation']
                    )
                    
                    log_recording_step(recording_id, show_key, 'validation', 'completed', 
                                     duration=result['step_timings']['validation'])
                    log_performance_metric('recording_service', 'validation', 
                                         result['step_timings']['validation'],
                                         recording_id=recording_id)
                    
                except Exception as e:
                    raise ValidationError(
                        f"Validation failed: {e}",
                        step="validation",
                        recording_id=recording_id,
                        show_key=show_key,
                        retryable=False,
                        original_exception=e
                    )
                
                # Get validated configuration
                show_config = self.config_manager.get_show_config(show_key)
                station_url = self.config_manager.get_station_url(show_config.station)
                
                recording_logger.info("Configuration validated", extra={
                    'station': show_config.station,
                    'station_url': station_url,
                    'remote_directory': show_config.remote_directory,
                    'frequency': show_config.frequency,
                    'artwork_file': show_config.artwork_file
                })
                
                # Step 2: Temporary File Path Generation
                step_start_time = datetime.now()
                log_recording_step(recording_id, show_key, 'temp_path_generation', 'started')
                
                try:
                    temp_recording_path = self._generate_unique_temp_path(recording_id, "recording")
                    temp_files_to_cleanup.append(temp_recording_path)
                    result['steps_completed'].append('temp_path_generation')
                    result['step_timings']['temp_path_generation'] = (datetime.now() - step_start_time).total_seconds()
                    
                    log_recording_step(recording_id, show_key, 'temp_path_generation', 'completed',
                                     temp_path=temp_recording_path,
                                     duration=result['step_timings']['temp_path_generation'])
                    
                except Exception as e:
                    raise WorkflowError(
                        f"Failed to generate temporary file path: {e}",
                        step="temp_path_generation",
                        recording_id=recording_id,
                        show_key=show_key,
                        retryable=False,
                        original_exception=e
                    )
                
                # Step 3: Stream Recording
                step_start_time = datetime.now()
                log_recording_step(recording_id, show_key, 'stream_recording', 'started',
                                 stream_url=station_url,
                                 output_path=temp_recording_path,
                                 duration_minutes=duration_minutes)
                
                try:
                    recording_success = await self.stream_recorder.record_stream(
                        url=station_url,
                        output_path=temp_recording_path,
                        duration_minutes=duration_minutes
                    )
                    
                    if not recording_success:
                        raise StreamRecordingError("Stream recording returned failure status")
                    
                    # Verify recorded file exists and has content
                    if not os.path.exists(temp_recording_path):
                        raise WorkflowError("Recording file was not created")
                    
                    file_size = os.path.getsize(temp_recording_path)
                    if file_size == 0:
                        raise WorkflowError("Recording file is empty")
                    
                    result['steps_completed'].append('stream_recording')
                    result['step_timings']['stream_recording'] = (datetime.now() - step_start_time).total_seconds()
                    result['performance_metrics']['recorded_file_size'] = file_size
                    
                    # Update performance monitor
                    await self.performance_monitor.request_queue.update_recording_progress(
                        recording_id, 'stream_recording', 
                        step_timing=result['step_timings']['stream_recording'],
                        file_size=file_size
                    )
                    
                    log_recording_step(recording_id, show_key, 'stream_recording', 'completed',
                                     file_size=file_size,
                                     duration=result['step_timings']['stream_recording'])
                    log_performance_metric('stream_recorder', 'record_stream',
                                         result['step_timings']['stream_recording'],
                                         file_size=file_size,
                                         recording_id=recording_id)
                    
                except Exception as e:
                    raise WorkflowError(
                        f"Stream recording failed: {e}",
                        step="stream_recording",
                        recording_id=recording_id,
                        show_key=show_key,
                        retryable=True,
                        original_exception=e
                    )
                
                # Step 4: Metadata Processing
                step_start_time = datetime.now()
                log_recording_step(recording_id, show_key, 'metadata_processing', 'started',
                                 input_file=temp_recording_path)
                
                try:
                    # Run metadata processing in thread pool to avoid blocking event loop
                    loop = asyncio.get_event_loop()
                    processed_file_path = await loop.run_in_executor(
                        self._thread_pool,
                        self._process_metadata_with_logging,
                        temp_recording_path,
                        show_config,
                        recording_id
                    )
                    
                    # Add processed file to cleanup list if different from original
                    if processed_file_path != temp_recording_path:
                        temp_files_to_cleanup.append(processed_file_path)
                    
                    # Verify processed file
                    if not os.path.exists(processed_file_path):
                        raise WorkflowError("Processed file was not created")
                    
                    processed_file_size = os.path.getsize(processed_file_path)
                    if processed_file_size == 0:
                        raise WorkflowError("Processed file is empty")
                    
                    result['steps_completed'].append('metadata_processing')
                    result['step_timings']['metadata_processing'] = (datetime.now() - step_start_time).total_seconds()
                    result['final_file_path'] = processed_file_path
                    result['performance_metrics']['processed_file_size'] = processed_file_size
                    
                    # Update performance monitor
                    await self.performance_monitor.request_queue.update_recording_progress(
                        recording_id, 'metadata_processing',
                        step_timing=result['step_timings']['metadata_processing'],
                        file_size=processed_file_size
                    )
                    
                    log_recording_step(recording_id, show_key, 'metadata_processing', 'completed',
                                     processed_file=processed_file_path,
                                     processed_file_size=processed_file_size,
                                     duration=result['step_timings']['metadata_processing'])
                    log_performance_metric('metadata_processor', 'process_audio_file',
                                         result['step_timings']['metadata_processing'],
                                         input_size=result['performance_metrics']['recorded_file_size'],
                                         output_size=processed_file_size,
                                         recording_id=recording_id)
                    
                except Exception as e:
                    raise WorkflowError(
                        f"Metadata processing failed: {e}",
                        step="metadata_processing",
                        recording_id=recording_id,
                        show_key=show_key,
                        retryable=False,
                        original_exception=e
                    )
                
                # Step 5: File Transfer
                step_start_time = datetime.now()
                filename = Path(processed_file_path).name
                log_recording_step(recording_id, show_key, 'file_transfer', 'started',
                                 local_file=processed_file_path,
                                 filename=filename,
                                 remote_directory=show_config.remote_directory)
                
                try:
                    # Run transfer in thread pool as it may involve network I/O
                    transfer_result = await loop.run_in_executor(
                        self._thread_pool,
                        self._transfer_file_with_logging,
                        processed_file_path,
                        show_config,
                        filename,
                        recording_id
                    )
                    
                    if not transfer_result['success']:
                        raise WorkflowError(f"File transfer failed: {transfer_result['message']}")
                    
                    result['steps_completed'].append('file_transfer')
                    result['step_timings']['file_transfer'] = (datetime.now() - step_start_time).total_seconds()
                    result['remote_path'] = transfer_result['remote_path']
                    result['temp_files_retained'] = transfer_result['local_file_retained']
                    
                    # Update performance monitor
                    await self.performance_monitor.request_queue.update_recording_progress(
                        recording_id, 'file_transfer',
                        step_timing=result['step_timings']['file_transfer']
                    )
                    
                    log_recording_step(recording_id, show_key, 'file_transfer', 'completed',
                                     remote_path=transfer_result['remote_path'],
                                     local_file_retained=transfer_result['local_file_retained'],
                                     duration=result['step_timings']['file_transfer'])
                    log_performance_metric('transfer_service', 'transfer_file',
                                         result['step_timings']['file_transfer'],
                                         file_size=processed_file_size,
                                         recording_id=recording_id)
                    
                except Exception as e:
                    raise WorkflowError(
                        f"File transfer failed: {e}",
                        step="file_transfer",
                        recording_id=recording_id,
                        show_key=show_key,
                        retryable=True,
                        original_exception=e
                    )
                
                # Step 6: Cleanup
                step_start_time = datetime.now()
                log_recording_step(recording_id, show_key, 'cleanup', 'started',
                                 temp_files_count=len(temp_files_to_cleanup),
                                 files_retained=result['temp_files_retained'])
                
                try:
                    # Clean up remaining temporary files if transfer was successful
                    if not result['temp_files_retained']:
                        cleanup_success = await self._cleanup_temp_files(temp_files_to_cleanup[:-1])  # Exclude processed file (cleaned by transfer)
                        if not cleanup_success:
                            recording_logger.warning("Some temporary files could not be cleaned up")
                    else:
                        recording_logger.warning("Temporary files retained due to transfer cleanup failure")
                    
                    result['steps_completed'].append('cleanup')
                    result['step_timings']['cleanup'] = (datetime.now() - step_start_time).total_seconds()
                    
                    log_recording_step(recording_id, show_key, 'cleanup', 'completed',
                                     duration=result['step_timings']['cleanup'])
                    
                except Exception as e:
                    # Cleanup failure is not critical - log but don't fail the recording
                    recording_logger.error("Cleanup failed", extra={
                        'error': str(e),
                        'error_type': type(e).__name__
                    })
                    result['temp_files_retained'] = True
                
                # Mark recording as successful
                result['success'] = True
                result['completed_at'] = datetime.now()
                total_duration = (result['completed_at'] - result['started_at']).total_seconds()
                result['performance_metrics']['total_duration'] = total_duration
                result['message'] = f"Recording completed successfully for show '{show_key}'"
                
                # Log successful completion with comprehensive metrics
                recording_logger.info("Recording workflow completed successfully", extra={
                    'workflow_phase': 'success',
                    'total_duration': total_duration,
                    'steps_completed': result['steps_completed'],
                    'step_timings': result['step_timings'],
                    'performance_metrics': result['performance_metrics'],
                    'final_file_path': result['final_file_path'],
                    'remote_path': result['remote_path'],
                    'temp_files_retained': result['temp_files_retained']
                })
                
                # Log overall performance metric
                log_performance_metric('recording_service', 'complete_workflow', total_duration,
                                     recording_id=recording_id,
                                     show_key=show_key,
                                     steps_count=len(result['steps_completed']),
                                     **result['performance_metrics'])
                
                return result
                
            except RecordingStepError as e:
                # Handle our custom recording errors with full context
                result['error_step'] = e.step
                result['error_details'] = e.to_dict()
                result['message'] = str(e)
                result['completed_at'] = datetime.now()
                
                # Log structured error information
                recording_logger.error("Recording workflow failed", extra={
                    'workflow_phase': 'failed',
                    'error_step': e.step,
                    'error_type': e.__class__.__name__,
                    'error_message': str(e),
                    'retryable': e.retryable,
                    'steps_completed': result['steps_completed'],
                    'step_timings': result['step_timings'],
                    'error_details': e.to_dict(),
                    'original_exception': str(e.original_exception) if e.original_exception else None
                })
                
                if e.original_exception:
                    recording_logger.debug("Original exception traceback", exc_info=e.original_exception)
                
                # Log failure for recovery
                self.recovery_manager.log_failure_for_recovery(
                    recording_id, show_key, temp_files_to_cleanup, result['error_details']
                )
                
                # Retain temporary files on failure for manual recovery
                result['temp_files_retained'] = True
                recording_logger.info("Temporary files retained for manual recovery", extra={
                    'temp_files': temp_files_to_cleanup,
                    'temp_files_count': len(temp_files_to_cleanup)
                })
                
                return result
                
            except Exception as e:
                # Handle unexpected errors
                result['error_step'] = 'unexpected'
                result['error_details'] = {
                    'error_type': e.__class__.__name__,
                    'message': str(e),
                    'traceback': traceback.format_exc()
                }
                result['message'] = f"Recording failed with unexpected error: {e}"
                result['completed_at'] = datetime.now()
                
                # Log structured unexpected error
                recording_logger.error("Recording workflow unexpected error", extra={
                    'workflow_phase': 'unexpected_error',
                    'error_type': e.__class__.__name__,
                    'error_message': str(e),
                    'steps_completed': result['steps_completed'],
                    'step_timings': result['step_timings'],
                    'error_details': result['error_details']
                })
                recording_logger.debug("Unexpected error traceback", exc_info=True)
                
                # Log failure for recovery
                self.recovery_manager.log_failure_for_recovery(
                    recording_id, show_key, temp_files_to_cleanup, result['error_details']
                )
                
                # Retain temporary files on unexpected failure
                result['temp_files_retained'] = True
                recording_logger.info("Temporary files retained due to unexpected error", extra={
                    'temp_files': temp_files_to_cleanup,
                    'temp_files_count': len(temp_files_to_cleanup)
                })
                
                return result
    
    def _process_metadata_with_logging(
        self, 
        input_path: str, 
        show_config: ShowConfig, 
        recording_id: str
    ) -> str:
        """Wrapper for metadata processing with detailed logging."""
        metadata_logger = logging.getLogger('src.services.metadata_processor')
        try:
            metadata_logger.info("Starting metadata processing", extra={
                'recording_id': recording_id,
                'input_path': input_path,
                'show': show_config.show,
                'frequency': show_config.frequency,
                'artwork_file': show_config.artwork_file
            })
            result = self.metadata_processor.process_audio_file(input_path, show_config)
            metadata_logger.info("Metadata processing completed", extra={
                'recording_id': recording_id,
                'output_path': result,
                'input_path': input_path
            })
            return result
        except Exception as e:
            metadata_logger.error("Metadata processing failed", extra={
                'recording_id': recording_id,
                'input_path': input_path,
                'error': str(e),
                'error_type': type(e).__name__
            })
            raise
    
    def _transfer_file_with_logging(
        self, 
        local_path: str, 
        show_config: ShowConfig, 
        filename: str, 
        recording_id: str
    ) -> Dict[str, Any]:
        """Wrapper for file transfer with detailed logging."""
        transfer_logger = logging.getLogger('src.services.transfer_service')
        try:
            transfer_logger.info("Starting file transfer", extra={
                'recording_id': recording_id,
                'local_path': local_path,
                'filename': filename,
                'remote_directory': show_config.remote_directory,
                'show': show_config.show
            })
            result = self.transfer_service.transfer_file_with_cleanup(local_path, show_config, filename)
            transfer_logger.info("File transfer completed", extra={
                'recording_id': recording_id,
                'success': result['success'],
                'remote_path': result.get('remote_path'),
                'local_file_retained': result.get('local_file_retained'),
                'message': result.get('message')
            })
            return result
        except Exception as e:
            transfer_logger.error("File transfer failed", extra={
                'recording_id': recording_id,
                'local_path': local_path,
                'error': str(e),
                'error_type': type(e).__name__
            })
            raise
    
    async def _validate_and_register_recording(
        self, 
        recording_id: str, 
        show_key: str, 
        duration_minutes: int,
        result: Dict[str, Any]
    ) -> None:
        """Validate recording request and register it for concurrency management.
        
        Performs comprehensive validation including:
        - Concurrency limits
        - Configuration existence and validity
        - Parameter validation
        - System resource checks
        
        Args:
            recording_id: Unique recording identifier
            show_key: Show key to validate
            duration_minutes: Duration to validate
            result: Result dictionary to update with validation info
            
        Raises:
            ConcurrencyError: If concurrency limits are exceeded
            ValidationError: If validation fails
            ConfigurationError: If configuration is invalid
        """
        async with self._recording_lock:
            logger.debug(f"Recording {recording_id}: Starting validation")
            
            # Check concurrency limits
            current_active = len(self._active_recordings)
            if current_active >= self.max_concurrent_recordings:
                logger.warning(f"Recording {recording_id}: Concurrency limit exceeded ({current_active}/{self.max_concurrent_recordings})")
                raise ConcurrencyError(
                    f"Maximum concurrent recordings ({self.max_concurrent_recordings}) exceeded. Currently active: {current_active}",
                    step="concurrency_check",
                    recording_id=recording_id,
                    show_key=show_key,
                    retryable=True
                )
            
            logger.debug(f"Recording {recording_id}: Concurrency check passed ({current_active}/{self.max_concurrent_recordings})")
            
            # Validate configuration manager is loaded
            try:
                if not self.config_manager.is_loaded():
                    logger.error(f"Recording {recording_id}: Configuration not loaded")
                    raise ValidationError(
                        "Configuration not loaded",
                        step="configuration_validation",
                        recording_id=recording_id,
                        show_key=show_key,
                        retryable=False
                    )
            except Exception as e:
                logger.error(f"Recording {recording_id}: Configuration manager error: {e}")
                raise ValidationError(
                    f"Configuration manager error: {e}",
                    step="configuration_validation",
                    recording_id=recording_id,
                    show_key=show_key,
                    retryable=False,
                    original_exception=e
                )
            
            # Validate show configuration exists
            try:
                show_config = self.config_manager.get_show_config(show_key)
                if show_config is None:
                    logger.error(f"Recording {recording_id}: Show '{show_key}' not found in configuration")
                    available_shows = list(self.config_manager.get_all_shows().keys())
                    raise ValidationError(
                        f"Show '{show_key}' not found in configuration. Available shows: {available_shows}",
                        step="configuration_validation",
                        recording_id=recording_id,
                        show_key=show_key,
                        retryable=False
                    )
                
                logger.debug(f"Recording {recording_id}: Show configuration found for '{show_key}'")
                
            except ConfigurationError as e:
                logger.error(f"Recording {recording_id}: Configuration error while getting show: {e}")
                raise ValidationError(
                    f"Configuration error: {e}",
                    step="configuration_validation",
                    recording_id=recording_id,
                    show_key=show_key,
                    retryable=False,
                    original_exception=e
                )
            
            # Validate station configuration exists
            try:
                station_url = self.config_manager.get_station_url(show_config.station)
                if station_url is None:
                    logger.error(f"Recording {recording_id}: Station '{show_config.station}' not found for show '{show_key}'")
                    available_stations = list(self.config_manager.get_all_stations().keys())
                    raise ValidationError(
                        f"Station '{show_config.station}' not found for show '{show_key}'. Available stations: {available_stations}",
                        step="configuration_validation",
                        recording_id=recording_id,
                        show_key=show_key,
                        retryable=False
                    )
                
                logger.debug(f"Recording {recording_id}: Station configuration found: {show_config.station} -> {station_url}")
                
            except ConfigurationError as e:
                logger.error(f"Recording {recording_id}: Configuration error while getting station: {e}")
                raise ValidationError(
                    f"Station configuration error: {e}",
                    step="configuration_validation",
                    recording_id=recording_id,
                    show_key=show_key,
                    retryable=False,
                    original_exception=e
                )
            
            # Validate duration parameter
            if not isinstance(duration_minutes, int):
                logger.error(f"Recording {recording_id}: Duration must be an integer, got {type(duration_minutes)}")
                raise ValidationError(
                    f"Duration must be an integer, got {type(duration_minutes).__name__}",
                    step="parameter_validation",
                    recording_id=recording_id,
                    show_key=show_key,
                    retryable=False
                )
            
            if duration_minutes <= 0:
                logger.error(f"Recording {recording_id}: Duration must be positive, got {duration_minutes}")
                raise ValidationError(
                    f"Duration must be positive, got {duration_minutes}",
                    step="parameter_validation",
                    recording_id=recording_id,
                    show_key=show_key,
                    retryable=False
                )
            
            if duration_minutes > 480:  # Max 8 hours
                logger.error(f"Recording {recording_id}: Duration too long: {duration_minutes} minutes (max 480)")
                raise ValidationError(
                    f"Duration too long: {duration_minutes} minutes (maximum 480 minutes / 8 hours)",
                    step="parameter_validation",
                    recording_id=recording_id,
                    show_key=show_key,
                    retryable=False
                )
            
            logger.debug(f"Recording {recording_id}: Duration validation passed: {duration_minutes} minutes")
            
            # Validate work directory is accessible
            try:
                test_file = self.work_dir / f"validation_test_{recording_id}.tmp"
                test_file.write_text("validation test")
                test_file.unlink()
                logger.debug(f"Recording {recording_id}: Work directory validation passed")
            except Exception as e:
                logger.error(f"Recording {recording_id}: Work directory not accessible: {e}")
                raise ValidationError(
                    f"Work directory not accessible: {e}",
                    step="system_validation",
                    recording_id=recording_id,
                    show_key=show_key,
                    retryable=False,
                    original_exception=e
                )
            
            # Check available disk space (warn if low, fail if critical)
            try:
                import shutil
                total, used, free = shutil.disk_usage(self.work_dir)
                free_gb = free / (1024**3)
                
                # Estimate space needed (rough calculation: 1MB per minute for MP3)
                estimated_space_mb = duration_minutes * 2  # 2MB per minute to be safe
                estimated_space_gb = estimated_space_mb / 1024
                
                if free_gb < 0.1:  # Less than 100MB free
                    logger.error(f"Recording {recording_id}: Critical disk space: {free_gb:.2f}GB free")
                    raise ValidationError(
                        f"Insufficient disk space: {free_gb:.2f}GB free (critical threshold)",
                        step="system_validation",
                        recording_id=recording_id,
                        show_key=show_key,
                        retryable=True
                    )
                elif free_gb < estimated_space_gb:
                    logger.warning(f"Recording {recording_id}: Low disk space: {free_gb:.2f}GB free, estimated need: {estimated_space_gb:.2f}GB")
                else:
                    logger.debug(f"Recording {recording_id}: Disk space check passed: {free_gb:.2f}GB free")
                    
            except Exception as e:
                logger.warning(f"Recording {recording_id}: Could not check disk space: {e}")
                # Don't fail validation for disk space check errors
            
            # Register recording as active
            estimated_completion = datetime.now() + timedelta(minutes=duration_minutes + 10)  # Add 10 min buffer for processing
            
            self._active_recordings[recording_id] = {
                'show': show_key,
                'duration_minutes': duration_minutes,
                'started_at': datetime.now(),
                'estimated_completion': estimated_completion,
                'show_config': show_config,
                'station_url': station_url
            }
            
            logger.info(f"Recording {recording_id}: Validation completed successfully")
            logger.info(f"Recording {recording_id}: Registered as active (total active: {len(self._active_recordings)})")
            logger.info(f"Recording {recording_id}: Estimated completion: {estimated_completion.isoformat()}")
    
    async def _unregister_recording(self, recording_id: str) -> None:
        """Remove recording from active tracking.
        
        Args:
            recording_id: Recording ID to unregister
        """
        async with self._recording_lock:
            if recording_id in self._active_recordings:
                del self._active_recordings[recording_id]
                logger.debug(f"Recording {recording_id}: Unregistered (active: {len(self._active_recordings)})")
    
    def _generate_recording_id(self, show_key: str) -> str:
        """Generate unique recording identifier.
        
        Args:
            show_key: Show key to include in ID
            
        Returns:
            Unique recording identifier
        """
        timestamp = int(datetime.now().timestamp())
        unique_id = str(uuid.uuid4())[:8]
        return f"rec_{show_key}_{timestamp}_{unique_id}"
    
    def _generate_unique_temp_path(self, recording_id: str, file_type: str) -> str:
        """Generate unique temporary file path to prevent conflicts.
        
        Args:
            recording_id: Unique recording identifier
            file_type: Type of file (e.g., 'recording', 'processed')
            
        Returns:
            Unique temporary file path
        """
        filename = f"{recording_id}_{file_type}.tmp"
        return str(self.work_dir / filename)
    
    async def _cleanup_temp_files(self, file_paths: list) -> bool:
        """Clean up temporary files.
        
        Args:
            file_paths: List of file paths to clean up
            
        Returns:
            True if all files cleaned up successfully, False otherwise
        """
        cleanup_success = True
        
        for file_path in file_paths:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.debug(f"Cleaned up temporary file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to clean up temporary file {file_path}: {e}")
                cleanup_success = False
        
        return cleanup_success
    
    async def get_active_recordings(self) -> Dict[str, Any]:
        """Get information about currently active recordings.
        
        Returns:
            Dictionary with active recording information
        """
        async with self._recording_lock:
            return {
                'count': len(self._active_recordings),
                'max_concurrent': self.max_concurrent_recordings,
                'recordings': dict(self._active_recordings)  # Return copy
            }
    
    async def cancel_recording(self, recording_id: str) -> bool:
        """Cancel an active recording (if supported by underlying services).
        
        Args:
            recording_id: Recording ID to cancel
            
        Returns:
            True if cancellation was attempted, False if recording not found
        """
        async with self._recording_lock:
            if recording_id not in self._active_recordings:
                logger.warning(f"Cannot cancel recording {recording_id}: not found in active recordings")
                return False
            
            logger.info(f"Cancellation requested for recording {recording_id}")
            # Note: Actual cancellation would require more complex process management
            # For now, just log the request - full implementation would need process tracking
            return True
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check of the recording service.
        
        Returns:
            Dictionary with health status information
        """
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now(),
            'active_recordings': len(self._active_recordings),
            'max_concurrent_recordings': self.max_concurrent_recordings,
            'work_directory_accessible': False,
            'components': {}
        }
        
        try:
            # Check work directory accessibility
            test_file = self.work_dir / f"health_check_{int(datetime.now().timestamp())}.tmp"
            test_file.write_text("health check")
            test_file.unlink()
            health_status['work_directory_accessible'] = True
        except Exception as e:
            logger.error(f"Work directory health check failed: {e}")
            health_status['status'] = 'unhealthy'
        
        # Check component health
        try:
            # Stream recorder health check
            stream_health = await self.stream_recorder.health_check()
            health_status['components']['stream_recorder'] = stream_health
            
            if stream_health['status'] != 'healthy':
                health_status['status'] = 'degraded'
        except Exception as e:
            logger.error(f"Stream recorder health check failed: {e}")
            health_status['components']['stream_recorder'] = {'status': 'unhealthy', 'error': str(e)}
            health_status['status'] = 'unhealthy'
        
        # Check configuration manager
        try:
            config_loaded = self.config_manager.is_loaded()
            health_status['components']['config_manager'] = {
                'status': 'healthy' if config_loaded else 'unhealthy',
                'loaded': config_loaded
            }
            
            if not config_loaded:
                health_status['status'] = 'unhealthy'
        except Exception as e:
            logger.error(f"Config manager health check failed: {e}")
            health_status['components']['config_manager'] = {'status': 'unhealthy', 'error': str(e)}
            health_status['status'] = 'unhealthy'
        
        return health_status
    
    async def get_recording_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics about recording service usage.
        
        Returns:
            Dictionary with detailed recording statistics and performance metrics
        """
        async with self._recording_lock:
            active_recordings = dict(self._active_recordings)
        
        # Calculate statistics
        now = datetime.now()
        long_running_count = 0
        overdue_count = 0
        
        for recording_info in active_recordings.values():
            duration = now - recording_info['started_at']
            expected_duration = recording_info['duration_minutes'] * 60 + 600  # 10 min buffer
            
            if duration.total_seconds() > expected_duration:
                long_running_count += 1
            
            if now > recording_info['estimated_completion']:
                overdue_count += 1
        
        # Calculate success rate
        total_recordings = self._recording_stats['total_recordings']
        success_rate = 0.0
        if total_recordings > 0:
            success_rate = (self._recording_stats['successful_recordings'] / total_recordings) * 100
        
        # Get disk space information
        disk_info = {}
        try:
            import shutil
            total, used, free = shutil.disk_usage(self.work_dir)
            disk_info = {
                'total_gb': total / (1024**3),
                'used_gb': used / (1024**3),
                'free_gb': free / (1024**3),
                'usage_percent': (used / total) * 100
            }
        except Exception as e:
            logger.warning(f"Could not get disk usage information: {e}")
            disk_info = {'error': str(e)}
        
        return {
            'timestamp': now.isoformat(),
            'active_recordings': len(active_recordings),
            'max_concurrent': self.max_concurrent_recordings,
            'utilization_percent': (len(active_recordings) / self.max_concurrent_recordings) * 100,
            'long_running_recordings': long_running_count,
            'overdue_recordings': overdue_count,
            'work_directory': str(self.work_dir),
            'thread_pool_size': self._thread_pool._max_workers,
            'performance_stats': {
                'total_recordings': self._recording_stats['total_recordings'],
                'successful_recordings': self._recording_stats['successful_recordings'],
                'failed_recordings': self._recording_stats['failed_recordings'],
                'success_rate_percent': success_rate,
                'stats_since': self._recording_stats['last_reset'].isoformat()
            },
            'disk_usage': disk_info,
            'active_recording_details': [
                {
                    'recording_id': rid,
                    'show': info['show'],
                    'duration_minutes': info['duration_minutes'],
                    'started_at': info['started_at'].isoformat(),
                    'estimated_completion': info['estimated_completion'].isoformat(),
                    'running_time_seconds': (now - info['started_at']).total_seconds()
                }
                for rid, info in active_recordings.items()
            ]
        }
    
    async def reset_statistics(self) -> None:
        """Reset performance statistics."""
        self._recording_stats = {
            'total_recordings': 0,
            'successful_recordings': 0,
            'failed_recordings': 0,
            'last_reset': datetime.now()
        }
        logger.info("Recording statistics reset")
    
    async def get_error_recovery_info(self) -> Dict[str, Any]:
        """Get information about failed recordings for recovery purposes.
        
        Returns:
            Dictionary with recovery information
        """
        recovery_info = {
            'recovery_log_exists': False,
            'recovery_log_path': str(self.recovery_manager.recovery_log_file),
            'temp_files_in_work_dir': [],
            'recommendations': []
        }
        
        try:
            # Check if recovery log exists
            if self.recovery_manager.recovery_log_file.exists():
                recovery_info['recovery_log_exists'] = True
                recovery_info['recovery_log_size'] = self.recovery_manager.recovery_log_file.stat().st_size
        except Exception as e:
            logger.warning(f"Could not check recovery log: {e}")
        
        try:
            # List temporary files in work directory
            temp_files = []
            for file_path in self.work_dir.glob("*.tmp"):
                try:
                    stat = file_path.stat()
                    temp_files.append({
                        'name': file_path.name,
                        'size': stat.st_size,
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
                except Exception:
                    continue
            
            recovery_info['temp_files_in_work_dir'] = temp_files
            
            # Generate recommendations
            if temp_files:
                recovery_info['recommendations'].append(
                    f"Found {len(temp_files)} temporary files that may need manual cleanup"
                )
            
            if recovery_info['recovery_log_exists']:
                recovery_info['recommendations'].append(
                    "Check recovery log for detailed failure information and recovery instructions"
                )
            
        except Exception as e:
            logger.warning(f"Could not scan work directory: {e}")
            recovery_info['scan_error'] = str(e)
        
        return recovery_info
    
    async def cleanup_old_temp_files(self, max_age_hours: int = 24) -> Dict[str, Any]:
        """Clean up old temporary files from the work directory.
        
        Args:
            max_age_hours: Maximum age of files to keep (default 24 hours)
            
        Returns:
            Dictionary with cleanup results
        """
        cleanup_result = {
            'files_scanned': 0,
            'files_removed': 0,
            'files_failed': 0,
            'space_freed_bytes': 0,
            'errors': []
        }
        
        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            
            for file_path in self.work_dir.glob("*.tmp"):
                cleanup_result['files_scanned'] += 1
                
                try:
                    stat = file_path.stat()
                    file_time = datetime.fromtimestamp(stat.st_mtime)
                    
                    if file_time < cutoff_time:
                        file_size = stat.st_size
                        file_path.unlink()
                        cleanup_result['files_removed'] += 1
                        cleanup_result['space_freed_bytes'] += file_size
                        logger.debug(f"Cleaned up old temp file: {file_path.name} ({file_size} bytes)")
                    
                except Exception as e:
                    cleanup_result['files_failed'] += 1
                    cleanup_result['errors'].append(f"Failed to remove {file_path.name}: {e}")
                    logger.warning(f"Failed to clean up temp file {file_path.name}: {e}")
            
            logger.info(f"Temp file cleanup completed: {cleanup_result['files_removed']} files removed, "
                       f"{cleanup_result['space_freed_bytes']} bytes freed")
            
        except Exception as e:
            cleanup_result['errors'].append(f"Cleanup scan failed: {e}")
            logger.error(f"Temp file cleanup failed: {e}")
        
        return cleanup_result
    
    def __del__(self):
        """Cleanup resources when service is destroyed."""
        try:
            if hasattr(self, '_thread_pool'):
                self._thread_pool.shutdown(wait=False)
        except Exception:
            pass  # Ignore cleanup errors during destruction