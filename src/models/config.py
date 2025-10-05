"""Configuration data models for the radio stream recorder API."""

import os
from typing import Dict, Optional
from pydantic import BaseModel, Field, validator, root_validator
from pathlib import Path


class ShowConfig(BaseModel):
    """Configuration model for a radio show."""
    
    show: str = Field(..., min_length=1, description="Name of the radio show")
    station: str = Field(..., min_length=1, description="Station key to lookup stream URL")
    artwork_file: str = Field(..., alias="artwork-file", description="Path to artwork file")
    remote_directory: str = Field(..., alias="remote-directory", min_length=1, description="Remote SCP destination")
    frequency: str = Field(..., description="Recording frequency: 'daily' or 'weekly'")
    playlist_db_slug: str = Field(..., alias="playlist-db-slug", min_length=1, description="Database slug for playlist")
    
    @validator('frequency')
    def validate_frequency(cls, v):
        """Validate frequency is either 'daily' or 'weekly'."""
        if v not in ['daily', 'weekly']:
            raise ValueError("frequency must be either 'daily' or 'weekly'")
        return v
    
    @validator('artwork_file')
    def validate_artwork_file(cls, v):
        """Validate artwork file path exists and is readable."""
        if not v:
            raise ValueError("artwork_file cannot be empty")
        # Note: File existence validation will be done at runtime by ConfigManager
        return v
    
    @validator('remote_directory')
    def validate_remote_directory(cls, v):
        """Validate remote directory format."""
        if not v:
            raise ValueError("remote_directory cannot be empty")
        # Basic validation for SCP format (user@host:path or just path)
        if ':' in v and '@' not in v.split(':')[0]:
            # If there's a colon but no @ before it, it might be a Windows path
            pass
        return v
    
    class Config:
        populate_by_name = True
        allow_population_by_field_name = True


class StationConfig(BaseModel):
    """Configuration model for a single radio station."""
    
    url: str = Field(..., min_length=1, description="Stream URL for the station")
    
    @validator('url')
    def validate_url(cls, v):
        """Validate URL format."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError("Station URL must start with http:// or https://")
        return v


class AppConfig(BaseModel):
    """Application configuration model."""
    
    config_dir: str = Field(default="/config", description="Configuration directory path")
    work_dir: str = Field(default="/work", description="Working directory for temporary files")
    ssh_key_path: str = Field(default="/ssh/id_rsa", description="SSH private key path")
    port: int = Field(default=8000, ge=1, le=65535, description="API server port")
    timezone: str = Field(default="America/Denver", description="Application timezone")
    
    @validator('config_dir', 'work_dir')
    def validate_directories(cls, v):
        """Validate directory paths."""
        if not v:
            raise ValueError("Directory path cannot be empty")
        return v
    
    @validator('ssh_key_path')
    def validate_ssh_key_path(cls, v):
        """Validate SSH key path format."""
        if not v:
            raise ValueError("SSH key path cannot be empty")
        return v