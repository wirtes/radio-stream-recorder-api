"""Metadata processing service for audio files."""

import os
import subprocess
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TPE2, TALB, TRCK, TDAT, TYER, TDRC
from mutagen.id3._util import ID3NoHeaderError

from src.models.config import ShowConfig


logger = logging.getLogger(__name__)


class MetadataProcessor:
    """Handles audio file conversion to MP3 and metadata application."""
    
    def __init__(self, work_dir: str = "/work"):
        """Initialize the metadata processor.
        
        Args:
            work_dir: Working directory for temporary files
        """
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
    
    def process_audio_file(self, input_path: str, show_config: ShowConfig) -> str:
        """Process audio file with metadata and return final MP3 path.
        
        Args:
            input_path: Path to the input audio file
            show_config: Configuration for the show
            
        Returns:
            Path to the processed MP3 file
            
        Raises:
            RuntimeError: If conversion or metadata processing fails
        """
        input_file = Path(input_path)
        
        if not input_file.exists():
            raise RuntimeError(f"Input file does not exist: {input_path}")
        
        # Generate output filename with proper format
        output_filename = self._generate_filename(show_config.show)
        output_path = self.work_dir / output_filename
        
        try:
            # Convert to MP3 if not already MP3
            if input_file.suffix.lower() != '.mp3':
                logger.info(f"Converting {input_path} to MP3 format")
                if not self._convert_to_mp3(str(input_file), str(output_path)):
                    raise RuntimeError(f"Failed to convert {input_path} to MP3")
            else:
                # If already MP3, copy to output location with proper name
                import shutil
                shutil.copy2(str(input_file), str(output_path))
                logger.info(f"Copied MP3 file to {output_path}")
            
            # Apply metadata tags
            logger.info(f"Applying metadata to {output_path}")
            self._apply_metadata(str(output_path), show_config)
            
            # Embed artwork if specified
            if show_config.artwork_file:
                logger.info(f"Embedding artwork from {show_config.artwork_file}")
                self._embed_artwork(str(output_path), show_config.artwork_file)
            
            logger.info(f"Successfully processed audio file: {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error processing audio file {input_path}: {e}")
            # Clean up output file if it was created
            if output_path.exists():
                output_path.unlink()
            raise RuntimeError(f"Failed to process audio file: {e}")
    
    def _convert_to_mp3(self, input_path: str, output_path: str) -> bool:
        """Convert audio file to MP3 format using ffmpeg.
        
        Args:
            input_path: Path to input audio file
            output_path: Path for output MP3 file
            
        Returns:
            True if conversion successful, False otherwise
        """
        try:
            # Build ffmpeg command for MP3 conversion
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-codec:a', 'libmp3lame',
                '-b:a', '192k',  # 192 kbps bitrate
                '-y',  # Overwrite output file
                output_path
            ]
            
            logger.debug(f"Running ffmpeg command: {' '.join(cmd)}")
            
            # Run ffmpeg conversion
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully converted {input_path} to MP3")
                return True
            else:
                logger.error(f"ffmpeg conversion failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"ffmpeg conversion timed out for {input_path}")
            return False
        except Exception as e:
            logger.error(f"Error during MP3 conversion: {e}")
            return False
    
    def _apply_metadata(self, mp3_path: str, show_config: ShowConfig) -> None:
        """Apply ID3 metadata tags to MP3 file.
        
        Args:
            mp3_path: Path to MP3 file
            show_config: Configuration for the show
        """
        try:
            # Load or create ID3 tags
            try:
                audio = MP3(mp3_path, ID3=ID3)
                audio.add_tags()
            except ID3NoHeaderError:
                audio = MP3(mp3_path)
                audio.add_tags()
            
            # Get current date for metadata
            current_date = datetime.now()
            current_year = current_date.year
            
            # Calculate track number based on frequency
            track_number = self._calculate_track_number(show_config.frequency)
            
            # Apply metadata tags
            audio.tags.add(TIT2(encoding=3, text=show_config.show))  # Title
            audio.tags.add(TPE1(encoding=3, text=show_config.show))  # Artist
            audio.tags.add(TPE2(encoding=3, text=show_config.show))  # Album Artist
            audio.tags.add(TALB(encoding=3, text=f"{show_config.show} {current_year}"))  # Album
            audio.tags.add(TRCK(encoding=3, text=str(track_number)))  # Track Number
            audio.tags.add(TDRC(encoding=3, text=current_date.strftime('%Y-%m-%d')))  # Recording Date
            
            # Save the tags
            audio.save()
            logger.info(f"Applied metadata tags to {mp3_path}")
            
        except Exception as e:
            logger.error(f"Error applying metadata to {mp3_path}: {e}")
            raise RuntimeError(f"Failed to apply metadata: {e}")
    
    def _calculate_track_number(self, frequency: str) -> int:
        """Calculate track number based on frequency and current date.
        
        Args:
            frequency: 'daily' or 'weekly'
            
        Returns:
            Track number as integer
        """
        current_date = datetime.now()
        year_start = datetime(current_date.year, 1, 1)
        
        if frequency == 'daily':
            # Days since January 1st
            delta = current_date - year_start
            return delta.days + 1
        elif frequency == 'weekly':
            # Weeks since January 1st
            delta = current_date - year_start
            return (delta.days // 7) + 1
        else:
            logger.warning(f"Unknown frequency '{frequency}', defaulting to 1")
            return 1
    
    def _generate_filename(self, show_name: str) -> str:
        """Generate filename in format 'YYYY-MM-DD Show.mp3' using local timezone.
        
        Args:
            show_name: Name of the show
            
        Returns:
            Generated filename with sanitized show name
        """
        # Use local timezone for filename (never UTC as per requirements)
        current_date = datetime.now()
        date_str = current_date.strftime('%Y-%m-%d')
        
        # Sanitize show name for filesystem compatibility
        sanitized_show_name = self._sanitize_filename(show_name)
        
        return f"{date_str} {sanitized_show_name}.mp3"
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename by removing or replacing invalid characters.
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename safe for filesystem use
        """
        # Characters that are invalid in filenames on most filesystems
        invalid_chars = '<>:"/\\|?*'
        
        # Replace invalid characters with underscores
        sanitized = filename
        for char in invalid_chars:
            sanitized = sanitized.replace(char, '_')
        
        # Remove leading/trailing whitespace and dots
        sanitized = sanitized.strip(' .')
        
        # Ensure filename is not empty after sanitization
        if not sanitized:
            sanitized = "Unknown_Show"
        
        # Limit length to reasonable filesystem limits (255 chars minus date and extension)
        max_show_length = 255 - len("YYYY-MM-DD .mp3")  # ~240 chars
        if len(sanitized) > max_show_length:
            sanitized = sanitized[:max_show_length].rstrip()
        
        return sanitized
    
    def _embed_artwork(self, mp3_path: str, artwork_path: str) -> None:
        """Embed artwork into MP3 file.
        
        Args:
            mp3_path: Path to MP3 file
            artwork_path: Path to artwork image file
        """
        try:
            artwork_file = Path(artwork_path)
            
            # Validate artwork file exists
            if not artwork_file.exists():
                logger.warning(f"Artwork file not found: {artwork_path}")
                return
            
            # Validate artwork file is readable
            if not os.access(artwork_path, os.R_OK):
                logger.warning(f"Artwork file is not readable: {artwork_path}")
                return
            
            # Validate file size (reasonable limits)
            file_size = artwork_file.stat().st_size
            if file_size == 0:
                logger.warning(f"Artwork file is empty: {artwork_path}")
                return
            if file_size > 10 * 1024 * 1024:  # 10MB limit
                logger.warning(f"Artwork file too large ({file_size} bytes): {artwork_path}")
                return
            
            # Determine MIME type based on file extension
            mime_type = self._get_image_mime_type(artwork_file.suffix.lower())
            if not mime_type:
                logger.warning(f"Unsupported artwork format: {artwork_file.suffix}")
                return
            
            # Read and validate artwork data
            try:
                with open(artwork_path, 'rb') as f:
                    artwork_data = f.read()
                
                # Basic validation - check for common image file signatures
                if not self._validate_image_data(artwork_data, artwork_file.suffix.lower()):
                    logger.warning(f"Invalid image data in artwork file: {artwork_path}")
                    return
                    
            except (IOError, OSError) as e:
                logger.warning(f"Failed to read artwork file {artwork_path}: {e}")
                return
            
            # Load MP3 file
            audio = MP3(mp3_path, ID3=ID3)
            
            # Remove existing artwork to avoid duplicates
            audio.tags.delall('APIC')
            
            # Add artwork as APIC frame
            audio.tags.add(
                APIC(
                    encoding=3,  # UTF-8
                    mime=mime_type,
                    type=3,  # Cover (front)
                    desc='Cover',
                    data=artwork_data
                )
            )
            
            # Save the file
            audio.save()
            logger.info(f"Successfully embedded artwork from {artwork_path}")
            
        except Exception as e:
            logger.error(f"Error embedding artwork: {e}")
            # Don't raise exception for artwork errors - it's not critical
            logger.warning("Continuing without artwork embedding")
    
    def _get_image_mime_type(self, file_extension: str) -> Optional[str]:
        """Get MIME type for image file extension.
        
        Args:
            file_extension: File extension (including dot)
            
        Returns:
            MIME type string or None if unsupported
        """
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp'
        }
        return mime_types.get(file_extension.lower())
    
    def _validate_image_data(self, data: bytes, file_extension: str) -> bool:
        """Validate image data by checking file signatures.
        
        Args:
            data: Image file data
            file_extension: File extension (including dot)
            
        Returns:
            True if data appears to be valid image data
        """
        if len(data) < 4:
            return False
        
        # Check common image file signatures
        signatures = {
            '.jpg': [b'\xff\xd8\xff'],
            '.jpeg': [b'\xff\xd8\xff'],
            '.png': [b'\x89\x50\x4e\x47'],
            '.gif': [b'GIF87a', b'GIF89a'],
            '.bmp': [b'BM']
        }
        
        expected_sigs = signatures.get(file_extension.lower(), [])
        for sig in expected_sigs:
            if data.startswith(sig):
                return True
        
        return False