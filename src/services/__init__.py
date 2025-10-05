# Services module

from .interfaces import (
    ConfigManagerInterface,
    StreamRecorderInterface,
    MetadataProcessorInterface,
    TransferServiceInterface,
    RecordingServiceInterface
)
from .config_manager import ConfigManager
from .stream_recorder import StreamRecorder
from .metadata_processor import MetadataProcessor

__all__ = [
    "ConfigManagerInterface",
    "StreamRecorderInterface", 
    "MetadataProcessorInterface",
    "TransferServiceInterface",
    "RecordingServiceInterface",
    "ConfigManager",
    "StreamRecorder",
    "MetadataProcessor"
]