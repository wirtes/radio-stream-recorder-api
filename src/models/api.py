"""API request and response models for the radio stream recorder."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class RecordRequest(BaseModel):
    """Request model for recording a radio stream."""
    
    show: str = Field(..., description="Show key from config_shows.json")
    duration_minutes: int = Field(
        ..., 
        gt=0, 
        le=480, 
        description="Recording duration in minutes (max 8 hours)"
    )


class RecordResponse(BaseModel):
    """Response model for recording requests."""
    
    success: bool = Field(..., description="Whether the recording was successful")
    message: str = Field(..., description="Status or error message")
    recording_id: Optional[str] = Field(None, description="Unique identifier for the recording")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""
    
    status: str = Field(..., description="Health status")
    timestamp: datetime = Field(..., description="Current timestamp")
    version: str = Field(..., description="Application version")


class ErrorResponse(BaseModel):
    """Standard error response model."""
    
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[str] = Field(None, description="Additional error details")