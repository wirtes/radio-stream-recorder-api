"""Performance monitoring and resource management for the Radio Stream Recorder API."""

import asyncio
import logging
import os
import psutil
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from collections import deque
import threading
from pathlib import Path

from src.utils.logging_config import get_performance_logger, log_performance_metric


@dataclass
class ResourceMetrics:
    """Container for system resource metrics."""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_available_mb: float
    disk_usage_percent: float
    disk_free_gb: float
    active_recordings: int
    queue_size: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'cpu_percent': self.cpu_percent,
            'memory_percent': self.memory_percent,
            'memory_used_mb': self.memory_used_mb,
            'memory_available_mb': self.memory_available_mb,
            'disk_usage_percent': self.disk_usage_percent,
            'disk_free_gb': self.disk_free_gb,
            'active_recordings': self.active_recordings,
            'queue_size': self.queue_size
        }


@dataclass
class RecordingMetrics:
    """Container for recording-specific performance metrics."""
    recording_id: str
    show_key: str
    started_at: datetime
    duration_minutes: int
    current_step: str = "not_started"
    steps_completed: List[str] = field(default_factory=list)
    step_timings: Dict[str, float] = field(default_factory=dict)
    file_sizes: Dict[str, int] = field(default_factory=dict)
    error_count: int = 0
    last_activity: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            'recording_id': self.recording_id,
            'show_key': self.show_key,
            'started_at': self.started_at.isoformat(),
            'duration_minutes': self.duration_minutes,
            'current_step': self.current_step,
            'steps_completed': self.steps_completed,
            'step_timings': self.step_timings,
            'file_sizes': self.file_sizes,
            'error_count': self.error_count,
            'last_activity': self.last_activity.isoformat(),
            'elapsed_time': (datetime.now() - self.started_at).total_seconds()
        }


class RequestQueue:
    """Async queue for managing recording requests with priority and resource limits."""
    
    def __init__(self, max_concurrent: int = 3, max_queue_size: int = 10):
        """Initialize request queue.
        
        Args:
            max_concurrent: Maximum number of concurrent recordings
            max_queue_size: Maximum number of queued requests
        """
        self.max_concurrent = max_concurrent
        self.max_queue_size = max_queue_size
        self._queue = asyncio.Queue(maxsize=max_queue_size)
        self._active_recordings: Dict[str, RecordingMetrics] = {}
        self._lock = asyncio.Lock()
        self._logger = get_performance_logger('request_queue')
    
    async def enqueue_request(self, recording_id: str, show_key: str, duration_minutes: int, priority: int = 0) -> bool:
        """Enqueue a recording request.
        
        Args:
            recording_id: Unique recording identifier
            show_key: Show key to record
            duration_minutes: Recording duration
            priority: Request priority (lower = higher priority)
            
        Returns:
            True if request was queued, False if queue is full
        """
        try:
            request_data = {
                'recording_id': recording_id,
                'show_key': show_key,
                'duration_minutes': duration_minutes,
                'priority': priority,
                'queued_at': datetime.now()
            }
            
            # Try to add to queue (non-blocking)
            self._queue.put_nowait(request_data)
            
            self._logger.info("Request queued", extra={
                'recording_id': recording_id,
                'show_key': show_key,
                'queue_size': self._queue.qsize(),
                'priority': priority
            })
            
            return True
            
        except asyncio.QueueFull:
            self._logger.warning("Request queue full", extra={
                'recording_id': recording_id,
                'show_key': show_key,
                'queue_size': self._queue.qsize(),
                'max_queue_size': self.max_queue_size
            })
            return False
    
    async def dequeue_request(self) -> Optional[Dict[str, Any]]:
        """Dequeue the next recording request.
        
        Returns:
            Request data dictionary or None if queue is empty
        """
        try:
            # Wait for a request with timeout
            request_data = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            
            self._logger.debug("Request dequeued", extra={
                'recording_id': request_data['recording_id'],
                'show_key': request_data['show_key'],
                'queue_size': self._queue.qsize(),
                'wait_time': (datetime.now() - request_data['queued_at']).total_seconds()
            })
            
            return request_data
            
        except asyncio.TimeoutError:
            return None
    
    async def register_active_recording(self, recording_id: str, show_key: str, duration_minutes: int) -> bool:
        """Register an active recording.
        
        Args:
            recording_id: Unique recording identifier
            show_key: Show key being recorded
            duration_minutes: Recording duration
            
        Returns:
            True if recording was registered, False if at capacity
        """
        async with self._lock:
            if len(self._active_recordings) >= self.max_concurrent:
                self._logger.warning("Maximum concurrent recordings reached", extra={
                    'recording_id': recording_id,
                    'active_count': len(self._active_recordings),
                    'max_concurrent': self.max_concurrent
                })
                return False
            
            metrics = RecordingMetrics(
                recording_id=recording_id,
                show_key=show_key,
                started_at=datetime.now(),
                duration_minutes=duration_minutes
            )
            
            self._active_recordings[recording_id] = metrics
            
            self._logger.info("Recording registered as active", extra={
                'recording_id': recording_id,
                'show_key': show_key,
                'active_count': len(self._active_recordings)
            })
            
            return True
    
    async def unregister_active_recording(self, recording_id: str) -> None:
        """Unregister an active recording.
        
        Args:
            recording_id: Recording identifier to unregister
        """
        async with self._lock:
            if recording_id in self._active_recordings:
                metrics = self._active_recordings.pop(recording_id)
                
                # Log final metrics
                total_time = (datetime.now() - metrics.started_at).total_seconds()
                self._logger.info("Recording unregistered", extra={
                    'recording_id': recording_id,
                    'show_key': metrics.show_key,
                    'total_time': total_time,
                    'steps_completed': len(metrics.steps_completed),
                    'active_count': len(self._active_recordings)
                })
    
    async def update_recording_progress(self, recording_id: str, step: str, **metrics) -> None:
        """Update progress for an active recording.
        
        Args:
            recording_id: Recording identifier
            step: Current step name
            **metrics: Additional metrics to update
        """
        async with self._lock:
            if recording_id in self._active_recordings:
                recording_metrics = self._active_recordings[recording_id]
                recording_metrics.current_step = step
                recording_metrics.last_activity = datetime.now()
                
                # Update step completion
                if step not in recording_metrics.steps_completed:
                    recording_metrics.steps_completed.append(step)
                
                # Update additional metrics
                for key, value in metrics.items():
                    if key == 'step_timing':
                        recording_metrics.step_timings[step] = value
                    elif key == 'file_size':
                        recording_metrics.file_sizes[step] = value
                    elif key == 'error':
                        recording_metrics.error_count += 1
    
    def get_active_recordings(self) -> List[Dict[str, Any]]:
        """Get list of active recordings with metrics.
        
        Returns:
            List of active recording metrics
        """
        return [metrics.to_dict() for metrics in self._active_recordings.values()]
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status.
        
        Returns:
            Dictionary with queue status information
        """
        return {
            'queue_size': self._queue.qsize(),
            'max_queue_size': self.max_queue_size,
            'active_recordings': len(self._active_recordings),
            'max_concurrent': self.max_concurrent,
            'available_slots': self.max_concurrent - len(self._active_recordings)
        }


class ResourceMonitor:
    """System resource monitoring with alerting."""
    
    def __init__(
        self,
        work_dir: str = "/work",
        monitoring_interval: int = 30,
        history_size: int = 100,
        cpu_threshold: float = 80.0,
        memory_threshold: float = 85.0,
        disk_threshold: float = 90.0
    ):
        """Initialize resource monitor.
        
        Args:
            work_dir: Working directory to monitor disk usage
            monitoring_interval: Monitoring interval in seconds
            history_size: Number of historical metrics to keep
            cpu_threshold: CPU usage threshold for alerts (%)
            memory_threshold: Memory usage threshold for alerts (%)
            disk_threshold: Disk usage threshold for alerts (%)
        """
        self.work_dir = Path(work_dir)
        self.monitoring_interval = monitoring_interval
        self.history_size = history_size
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.disk_threshold = disk_threshold
        
        self._metrics_history: deque = deque(maxlen=history_size)
        self._monitoring_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._logger = get_performance_logger('resource_monitor')
        
        # Alert state tracking
        self._alert_states = {
            'cpu': False,
            'memory': False,
            'disk': False
        }
    
    async def start_monitoring(self) -> None:
        """Start resource monitoring."""
        if self._monitoring_task is None or self._monitoring_task.done():
            self._stop_event.clear()
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
            self._logger.info("Resource monitoring started", extra={
                'monitoring_interval': self.monitoring_interval,
                'thresholds': {
                    'cpu': self.cpu_threshold,
                    'memory': self.memory_threshold,
                    'disk': self.disk_threshold
                }
            })
    
    async def stop_monitoring(self) -> None:
        """Stop resource monitoring."""
        if self._monitoring_task and not self._monitoring_task.done():
            self._stop_event.set()
            try:
                await asyncio.wait_for(self._monitoring_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._monitoring_task.cancel()
            
            self._logger.info("Resource monitoring stopped")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        while not self._stop_event.is_set():
            try:
                # Collect metrics
                metrics = await self._collect_metrics()
                
                # Store in history
                self._metrics_history.append(metrics)
                
                # Check thresholds and generate alerts
                await self._check_thresholds(metrics)
                
                # Log metrics periodically
                if len(self._metrics_history) % 10 == 0:  # Every 10 intervals
                    self._logger.info("Resource metrics", extra=metrics.to_dict())
                
                # Wait for next interval
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                self._logger.error("Error in monitoring loop", extra={
                    'error': str(e),
                    'error_type': type(e).__name__
                })
                await asyncio.sleep(self.monitoring_interval)
    
    async def _collect_metrics(self) -> ResourceMetrics:
        """Collect current system metrics."""
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_mb = memory.used / (1024 * 1024)
        memory_available_mb = memory.available / (1024 * 1024)
        
        # Disk usage for work directory
        disk_usage = psutil.disk_usage(str(self.work_dir))
        disk_usage_percent = (disk_usage.used / disk_usage.total) * 100
        disk_free_gb = disk_usage.free / (1024 * 1024 * 1024)
        
        return ResourceMetrics(
            timestamp=datetime.now(),
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_mb=memory_used_mb,
            memory_available_mb=memory_available_mb,
            disk_usage_percent=disk_usage_percent,
            disk_free_gb=disk_free_gb,
            active_recordings=0,  # Will be updated by caller
            queue_size=0  # Will be updated by caller
        )
    
    async def _check_thresholds(self, metrics: ResourceMetrics) -> None:
        """Check resource thresholds and generate alerts."""
        # CPU threshold check
        if metrics.cpu_percent > self.cpu_threshold:
            if not self._alert_states['cpu']:
                self._alert_states['cpu'] = True
                self._logger.warning("CPU usage threshold exceeded", extra={
                    'cpu_percent': metrics.cpu_percent,
                    'threshold': self.cpu_threshold,
                    'alert_type': 'cpu_high'
                })
        else:
            if self._alert_states['cpu']:
                self._alert_states['cpu'] = False
                self._logger.info("CPU usage returned to normal", extra={
                    'cpu_percent': metrics.cpu_percent,
                    'threshold': self.cpu_threshold,
                    'alert_type': 'cpu_normal'
                })
        
        # Memory threshold check
        if metrics.memory_percent > self.memory_threshold:
            if not self._alert_states['memory']:
                self._alert_states['memory'] = True
                self._logger.warning("Memory usage threshold exceeded", extra={
                    'memory_percent': metrics.memory_percent,
                    'memory_used_mb': metrics.memory_used_mb,
                    'threshold': self.memory_threshold,
                    'alert_type': 'memory_high'
                })
        else:
            if self._alert_states['memory']:
                self._alert_states['memory'] = False
                self._logger.info("Memory usage returned to normal", extra={
                    'memory_percent': metrics.memory_percent,
                    'threshold': self.memory_threshold,
                    'alert_type': 'memory_normal'
                })
        
        # Disk threshold check
        if metrics.disk_usage_percent > self.disk_threshold:
            if not self._alert_states['disk']:
                self._alert_states['disk'] = True
                self._logger.warning("Disk usage threshold exceeded", extra={
                    'disk_usage_percent': metrics.disk_usage_percent,
                    'disk_free_gb': metrics.disk_free_gb,
                    'threshold': self.disk_threshold,
                    'alert_type': 'disk_high'
                })
        else:
            if self._alert_states['disk']:
                self._alert_states['disk'] = False
                self._logger.info("Disk usage returned to normal", extra={
                    'disk_usage_percent': metrics.disk_usage_percent,
                    'threshold': self.disk_threshold,
                    'alert_type': 'disk_normal'
                })
    
    def get_current_metrics(self) -> Optional[ResourceMetrics]:
        """Get the most recent metrics.
        
        Returns:
            Latest ResourceMetrics or None if no metrics collected
        """
        return self._metrics_history[-1] if self._metrics_history else None
    
    def get_metrics_history(self, minutes: int = 30) -> List[ResourceMetrics]:
        """Get metrics history for the specified time period.
        
        Args:
            minutes: Number of minutes of history to return
            
        Returns:
            List of ResourceMetrics within the time period
        """
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return [
            metrics for metrics in self._metrics_history
            if metrics.timestamp >= cutoff_time
        ]
    
    def get_resource_summary(self) -> Dict[str, Any]:
        """Get summary of current resource status.
        
        Returns:
            Dictionary with resource summary
        """
        current = self.get_current_metrics()
        if not current:
            return {'status': 'no_data'}
        
        # Calculate averages over last 10 minutes
        recent_metrics = self.get_metrics_history(10)
        
        if recent_metrics:
            avg_cpu = sum(m.cpu_percent for m in recent_metrics) / len(recent_metrics)
            avg_memory = sum(m.memory_percent for m in recent_metrics) / len(recent_metrics)
        else:
            avg_cpu = current.cpu_percent
            avg_memory = current.memory_percent
        
        return {
            'status': 'healthy' if not any(self._alert_states.values()) else 'warning',
            'current': current.to_dict(),
            'averages_10min': {
                'cpu_percent': avg_cpu,
                'memory_percent': avg_memory
            },
            'alerts': self._alert_states.copy(),
            'thresholds': {
                'cpu': self.cpu_threshold,
                'memory': self.memory_threshold,
                'disk': self.disk_threshold
            }
        }


class PerformanceMonitor:
    """Main performance monitoring coordinator."""
    
    def __init__(
        self,
        work_dir: str = "/work",
        max_concurrent_recordings: int = 3,
        max_queue_size: int = 10,
        monitoring_interval: int = 30
    ):
        """Initialize performance monitor.
        
        Args:
            work_dir: Working directory path
            max_concurrent_recordings: Maximum concurrent recordings
            max_queue_size: Maximum queue size
            monitoring_interval: Resource monitoring interval in seconds
        """
        self.request_queue = RequestQueue(max_concurrent_recordings, max_queue_size)
        self.resource_monitor = ResourceMonitor(work_dir, monitoring_interval)
        self._logger = get_performance_logger('performance_monitor')
    
    async def start(self) -> None:
        """Start performance monitoring."""
        await self.resource_monitor.start_monitoring()
        self._logger.info("Performance monitoring started")
    
    async def stop(self) -> None:
        """Stop performance monitoring."""
        await self.resource_monitor.stop_monitoring()
        self._logger.info("Performance monitoring stopped")
    
    async def can_accept_recording(self, show_key: str, duration_minutes: int) -> Dict[str, Any]:
        """Check if system can accept a new recording request.
        
        Args:
            show_key: Show key to record
            duration_minutes: Recording duration
            
        Returns:
            Dictionary with acceptance status and details
        """
        # Check queue capacity
        queue_status = self.request_queue.get_queue_status()
        
        # Check resource status
        resource_summary = self.resource_monitor.get_resource_summary()
        
        # Determine if request can be accepted
        can_accept = True
        reasons = []
        
        if queue_status['available_slots'] <= 0 and queue_status['queue_size'] >= queue_status['max_queue_size']:
            can_accept = False
            reasons.append("Queue is full and no recording slots available")
        
        if resource_summary.get('status') == 'warning':
            # Check specific resource constraints
            current_metrics = resource_summary.get('current', {})
            
            # High memory usage - reject long recordings
            if current_metrics.get('memory_percent', 0) > 90 and duration_minutes > 60:
                can_accept = False
                reasons.append("High memory usage - rejecting long recordings")
            
            # Very high CPU usage
            if current_metrics.get('cpu_percent', 0) > 95:
                can_accept = False
                reasons.append("Very high CPU usage")
            
            # Low disk space
            if current_metrics.get('disk_free_gb', 0) < 1.0:
                can_accept = False
                reasons.append("Insufficient disk space")
        
        return {
            'can_accept': can_accept,
            'reasons': reasons,
            'queue_status': queue_status,
            'resource_status': resource_summary,
            'estimated_wait_time': self._estimate_wait_time(queue_status, duration_minutes)
        }
    
    def _estimate_wait_time(self, queue_status: Dict[str, Any], duration_minutes: int) -> Optional[float]:
        """Estimate wait time for a new recording request.
        
        Args:
            queue_status: Current queue status
            duration_minutes: Requested recording duration
            
        Returns:
            Estimated wait time in seconds, or None if immediate
        """
        if queue_status['available_slots'] > 0:
            return None  # Can start immediately
        
        # Estimate based on queue size and average recording time
        # This is a simple estimation - could be improved with historical data
        average_recording_time = 30 * 60  # 30 minutes average
        queue_wait_time = queue_status['queue_size'] * average_recording_time
        
        return queue_wait_time
    
    async def get_performance_status(self) -> Dict[str, Any]:
        """Get comprehensive performance status.
        
        Returns:
            Dictionary with complete performance information
        """
        return {
            'timestamp': datetime.now().isoformat(),
            'queue_status': self.request_queue.get_queue_status(),
            'active_recordings': self.request_queue.get_active_recordings(),
            'resource_status': self.resource_monitor.get_resource_summary(),
            'monitoring_active': self.resource_monitor._monitoring_task is not None and not self.resource_monitor._monitoring_task.done()
        }