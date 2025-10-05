"""Stream recording service using ffmpeg."""

import asyncio
import logging
import subprocess
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
import signal
import time
import re

from src.services.interfaces import StreamRecorderInterface


logger = logging.getLogger(__name__)


class RecordingError(Exception):
    """Custom exception for recording-related errors."""
    
    def __init__(self, message: str, error_type: str = "unknown", retryable: bool = True):
        super().__init__(message)
        self.error_type = error_type
        self.retryable = retryable


class NetworkError(RecordingError):
    """Exception for network-related recording errors."""
    
    def __init__(self, message: str):
        super().__init__(message, error_type="network", retryable=True)


class StreamError(RecordingError):
    """Exception for stream-related recording errors."""
    
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message, error_type="stream", retryable=retryable)


class FileSystemError(RecordingError):
    """Exception for file system-related recording errors."""
    
    def __init__(self, message: str):
        super().__init__(message, error_type="filesystem", retryable=False)


class StreamRecorder(StreamRecorderInterface):
    """Service for recording radio streams using ffmpeg."""
    
    def __init__(self, max_retries: int = 3, retry_delay: int = 5):
        """Initialize the stream recorder.
        
        Args:
            max_retries: Maximum number of retry attempts for failed recordings
            retry_delay: Delay in seconds between retry attempts
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._active_processes = {}  # Track active recording processes
    
    async def record_stream(self, url: str, output_path: str, duration_minutes: int) -> bool:
        """Record a stream to the specified output path.
        
        Args:
            url: Stream URL to record from
            output_path: Local file path to save the recording
            duration_minutes: Duration to record in minutes
            
        Returns:
            bool: True if recording was successful, False otherwise
        """
        logger.info(f"Starting stream recording: {url} -> {output_path} ({duration_minutes} minutes)")
        
        # Validate inputs
        if not url or not url.startswith(('http://', 'https://')):
            logger.error(f"Invalid stream URL: {url}")
            return False
            
        if duration_minutes <= 0 or duration_minutes > 480:  # Max 8 hours
            logger.error(f"Invalid duration: {duration_minutes} minutes")
            return False
        
        # Ensure output directory exists
        try:
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create output directory {output_dir}: {e}")
            return False
        
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt}/{self.max_retries} for {url}")
                    # Exponential backoff for retries
                    delay = self.retry_delay * (2 ** (attempt - 1))
                    await asyncio.sleep(min(delay, 60))  # Cap at 60 seconds
                
                success = await self._execute_recording(url, output_path, duration_minutes)
                
                if success:
                    logger.info(f"Recording completed successfully: {output_path}")
                    return True
                else:
                    logger.warning(f"Recording attempt {attempt + 1} failed for {url}")
                    
            except RecordingError as e:
                last_error = e
                logger.error(f"Recording attempt {attempt + 1} failed: {e} (type: {e.error_type}, retryable: {e.retryable})")
                
                # Don't retry non-retryable errors
                if not e.retryable:
                    logger.error(f"Non-retryable error encountered, stopping attempts: {e}")
                    break
                    
            except Exception as e:
                last_error = e
                logger.error(f"Recording attempt {attempt + 1} failed with unexpected exception: {e}")
                
        logger.error(f"All recording attempts failed for {url}. Last error: {last_error}")
        return False
    
    async def _execute_recording(self, url: str, output_path: str, duration_minutes: int) -> bool:
        """Execute the actual recording process.
        
        Args:
            url: Stream URL to record from
            output_path: Local file path to save the recording
            duration_minutes: Duration to record in minutes
            
        Returns:
            bool: True if recording was successful, False otherwise
            
        Raises:
            RecordingError: For various recording-related errors
        """
        ffmpeg_cmd = self._build_ffmpeg_command(url, output_path, duration_minutes)
        
        logger.debug(f"Executing ffmpeg command: {' '.join(ffmpeg_cmd)}")
        
        try:
            # Start the ffmpeg process
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Store process for potential cleanup
            recording_id = f"{int(time.time())}_{os.getpid()}"
            self._active_processes[recording_id] = process
            
            logger.info(f"Started recording process {recording_id} for {url}")
            
            try:
                # Wait for the process to complete with timeout
                timeout_seconds = (duration_minutes + 2) * 60  # Add 2 minute buffer
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=timeout_seconds
                )
                
                # Decode output for analysis
                stderr_text = stderr.decode('utf-8', errors='ignore') if stderr else ""
                stdout_text = stdout.decode('utf-8', errors='ignore') if stdout else ""
                
                logger.debug(f"Recording process {recording_id} completed with return code {process.returncode}")
                
                # Analyze the process result
                if process.returncode == 0:
                    # Verify the output file was created and has content
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                        file_size = os.path.getsize(output_path)
                        logger.info(f"Recording completed successfully: {output_path} ({file_size} bytes)")
                        return True
                    else:
                        raise FileSystemError(f"Recording completed but output file is missing or empty: {output_path}")
                else:
                    # Analyze stderr to determine error type
                    error_info = self._analyze_ffmpeg_error(stderr_text, process.returncode)
                    raise error_info["exception"](error_info["message"])
                    
            except asyncio.TimeoutError:
                logger.error(f"Recording process {recording_id} timed out after {timeout_seconds} seconds")
                # Kill the process if it's still running
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    logger.warning(f"Force killing recording process {recording_id}")
                    process.kill()
                    await process.wait()
                raise StreamError(f"Recording timed out after {timeout_seconds} seconds")
                
            finally:
                # Clean up process tracking
                self._active_processes.pop(recording_id, None)
                
        except FileNotFoundError:
            raise FileSystemError("ffmpeg not found. Please ensure ffmpeg is installed and in PATH")
        except PermissionError as e:
            raise FileSystemError(f"Permission denied: {e}")
        except OSError as e:
            raise FileSystemError(f"System error during recording: {e}")
        except RecordingError:
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            logger.error(f"Unexpected error executing ffmpeg process: {e}")
            raise RecordingError(f"Unexpected error during recording: {e}")
    
    def _analyze_ffmpeg_error(self, stderr_text: str, return_code: int) -> Dict[str, Any]:
        """Analyze ffmpeg error output to determine error type and retryability.
        
        Args:
            stderr_text: ffmpeg stderr output
            return_code: Process return code
            
        Returns:
            Dict containing exception class and message
        """
        stderr_lower = stderr_text.lower()
        
        # Network-related errors (retryable)
        network_patterns = [
            r'connection.*refused',
            r'connection.*timed out',
            r'network.*unreachable',
            r'temporary failure in name resolution',
            r'no route to host',
            r'connection reset by peer',
            r'server returned 4\d\d',
            r'server returned 5\d\d',
            r'http error 4\d\d',
            r'http error 5\d\d'
        ]
        
        for pattern in network_patterns:
            if re.search(pattern, stderr_lower):
                return {
                    "exception": NetworkError,
                    "message": f"Network error during recording (code {return_code}): {stderr_text.strip()}"
                }
        
        # Stream-related errors
        stream_patterns = [
            r'invalid data found when processing input',
            r'stream.*not found',
            r'no such file or directory',
            r'protocol not found',
            r'invalid url'
        ]
        
        for pattern in stream_patterns:
            if re.search(pattern, stderr_lower):
                # URL/protocol errors are usually not retryable
                retryable = not re.search(r'(protocol not found|invalid url)', stderr_lower)
                return {
                    "exception": StreamError,
                    "message": f"Stream error during recording (code {return_code}): {stderr_text.strip()}"
                }
        
        # File system errors (not retryable)
        fs_patterns = [
            r'permission denied',
            r'no space left on device',
            r'read-only file system',
            r'file exists'
        ]
        
        for pattern in fs_patterns:
            if re.search(pattern, stderr_lower):
                return {
                    "exception": FileSystemError,
                    "message": f"File system error during recording (code {return_code}): {stderr_text.strip()}"
                }
        
        # Default to generic stream error for unknown issues
        return {
            "exception": StreamError,
            "message": f"Recording failed with return code {return_code}: {stderr_text.strip()}"
        }
    
    def _build_ffmpeg_command(self, url: str, output_path: str, duration_minutes: int) -> List[str]:
        """Build the ffmpeg command for stream recording.
        
        Args:
            url: Stream URL to record from
            output_path: Local file path to save the recording
            duration_minutes: Duration to record in minutes
            
        Returns:
            List[str]: ffmpeg command as list of arguments
        """
        duration_seconds = duration_minutes * 60
        
        cmd = [
            'ffmpeg',
            '-y',  # Overwrite output file if it exists
            '-i', url,  # Input stream URL
            '-t', str(duration_seconds),  # Duration in seconds
            '-c', 'copy',  # Copy streams without re-encoding when possible
            '-f', 'mp3',  # Force MP3 output format
            '-reconnect', '1',  # Enable reconnection on network errors
            '-reconnect_streamed', '1',  # Enable reconnection for streamed inputs
            '-reconnect_delay_max', '5',  # Maximum delay between reconnection attempts
            '-loglevel', 'warning',  # Reduce ffmpeg verbosity
            output_path
        ]
        
        return cmd
    
    async def stop_all_recordings(self) -> None:
        """Stop all active recording processes."""
        logger.info(f"Stopping {len(self._active_processes)} active recordings")
        
        for recording_id, process in list(self._active_processes.items()):
            try:
                if process.returncode is None:  # Process is still running
                    logger.info(f"Terminating recording process {recording_id}")
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        logger.warning(f"Force killing recording process {recording_id}")
                        process.kill()
                        await process.wait()
            except Exception as e:
                logger.error(f"Error stopping recording process {recording_id}: {e}")
            finally:
                self._active_processes.pop(recording_id, None)
    
    def get_active_recording_count(self) -> int:
        """Get the number of currently active recordings."""
        return len(self._active_processes)
    
    def get_recording_status(self) -> Dict[str, Any]:
        """Get detailed status of all active recordings.
        
        Returns:
            Dict containing recording status information
        """
        active_recordings = []
        
        for recording_id, process in self._active_processes.items():
            status = {
                "recording_id": recording_id,
                "pid": process.pid if process.pid else None,
                "return_code": process.returncode,
                "is_running": process.returncode is None
            }
            active_recordings.append(status)
        
        return {
            "active_count": len(self._active_processes),
            "recordings": active_recordings,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform a health check of the recording service.
        
        Returns:
            Dict containing health status information
        """
        try:
            # Check if ffmpeg is available
            process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-version',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
            
            ffmpeg_available = process.returncode == 0
            ffmpeg_version = None
            
            if ffmpeg_available and stdout:
                # Extract version from first line of output
                first_line = stdout.decode('utf-8', errors='ignore').split('\n')[0]
                version_match = re.search(r'ffmpeg version ([^\s]+)', first_line)
                if version_match:
                    ffmpeg_version = version_match.group(1)
            
        except (asyncio.TimeoutError, FileNotFoundError, Exception) as e:
            logger.warning(f"ffmpeg health check failed: {e}")
            ffmpeg_available = False
            ffmpeg_version = None
        
        return {
            "status": "healthy" if ffmpeg_available else "unhealthy",
            "ffmpeg_available": ffmpeg_available,
            "ffmpeg_version": ffmpeg_version,
            "active_recordings": self.get_active_recording_count(),
            "service_config": {
                "max_retries": self.max_retries,
                "retry_delay": self.retry_delay
            }
        }