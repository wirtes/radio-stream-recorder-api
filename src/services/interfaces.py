"""Base interfaces for service classes."""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Protocol, Any
from src.models.config import ShowConfig


class ConfigManagerInterface(Protocol):
    """Interface for configuration management."""
    
    def load_shows_config(self) -> Dict[str, ShowConfig]:
        """Load show configurations from JSON file."""
        ...
    
    def load_stations_config(self) -> Dict[str, str]:
        """Load station configurations from JSON file."""
        ...
    
    def get_show_config(self, show_key: str) -> Optional[ShowConfig]:
        """Get configuration for a specific show."""
        ...
    
    def get_station_url(self, station_key: str) -> Optional[str]:
        """Get stream URL for a specific station."""
        ...


class StreamRecorderInterface(Protocol):
    """Interface for stream recording functionality."""
    
    async def record_stream(self, url: str, output_path: str, duration_minutes: int) -> bool:
        """Record a stream to the specified output path."""
        ...


class MetadataProcessorInterface(Protocol):
    """Interface for metadata processing functionality."""
    
    def process_audio_file(self, input_path: str, show_config: ShowConfig) -> str:
        """Process audio file with metadata and return final MP3 path."""
        ...


class TransferServiceInterface(Protocol):
    """Interface for file transfer functionality."""
    
    def transfer_file(self, local_path: str, show_config: ShowConfig, filename: str) -> bool:
        """Transfer file to remote location via SCP."""
        ...


class RecordingServiceInterface(Protocol):
    """Interface for the main recording orchestration service."""
    
    async def record_show(self, show_key: str, duration_minutes: int) -> Dict[str, Any]:
        """Orchestrate the complete recording workflow."""
        ...
    
    async def get_active_recordings(self) -> Dict[str, Any]:
        """Get information about currently active recordings."""
        ...
    
    async def cancel_recording(self, recording_id: str) -> bool:
        """Cancel an active recording if possible."""
        ...
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check of the recording service."""
        ...
    
    async def get_recording_statistics(self) -> Dict[str, Any]:
        """Get statistics about recording service usage."""
        ...