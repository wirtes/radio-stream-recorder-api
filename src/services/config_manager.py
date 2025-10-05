"""Configuration manager for loading and managing radio stream recorder configurations."""

import json
import logging
import threading
from pathlib import Path
from typing import Dict, Optional

from ..models.config import ShowConfig, StationConfig, AppConfig

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Exception raised for configuration-related errors."""
    pass


class ConfigManager:
    """Thread-safe configuration manager for radio stream recorder."""
    
    def __init__(self, config_dir: str = "/config"):
        """Initialize ConfigManager with configuration directory.
        
        Args:
            config_dir: Path to directory containing configuration files
        """
        self.config_dir = Path(config_dir)
        self._shows_config: Dict[str, ShowConfig] = {}
        self._stations_config: Dict[str, StationConfig] = {}
        self._config_lock = threading.RLock()
        self._loaded = False
        
    def load_configurations(self) -> None:
        """Load all configuration files.
        
        Raises:
            ConfigurationError: If configuration files cannot be loaded or are invalid
        """
        with self._config_lock:
            try:
                self._load_shows_config()
                self._load_stations_config()
                self._validate_show_station_references()
                self._loaded = True
                logger.info("Configuration loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load configuration: {e}")
                raise ConfigurationError(f"Configuration loading failed: {e}")
    
    def _load_shows_config(self) -> None:
        """Load shows configuration from config_shows.json."""
        shows_file = self.config_dir / "config_shows.json"
        
        if not shows_file.exists():
            raise ConfigurationError(f"Shows configuration file not found: {shows_file}")
        
        try:
            with open(shows_file, 'r', encoding='utf-8') as f:
                shows_data = json.load(f)
            
            if not isinstance(shows_data, dict):
                raise ConfigurationError("Shows configuration must be a JSON object")
            
            self._shows_config = {}
            for show_key, show_data in shows_data.items():
                # Skip metadata fields that start with underscore
                if show_key.startswith('_'):
                    continue
                    
                try:
                    show_config = ShowConfig(**show_data)
                    self._shows_config[show_key] = show_config
                except Exception as e:
                    raise ConfigurationError(f"Invalid show configuration for '{show_key}': {e}")
            
            logger.info(f"Loaded {len(self._shows_config)} show configurations")
            
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in shows configuration: {e}")
        except IOError as e:
            raise ConfigurationError(f"Error reading shows configuration file: {e}")
    
    def _load_stations_config(self) -> None:
        """Load stations configuration from config_stations.json."""
        stations_file = self.config_dir / "config_stations.json"
        
        if not stations_file.exists():
            raise ConfigurationError(f"Stations configuration file not found: {stations_file}")
        
        try:
            with open(stations_file, 'r', encoding='utf-8') as f:
                stations_data = json.load(f)
            
            if not isinstance(stations_data, dict):
                raise ConfigurationError("Stations configuration must be a JSON object")
            
            self._stations_config = {}
            for station_key, station_url in stations_data.items():
                # Skip metadata fields that start with underscore
                if station_key.startswith('_'):
                    continue
                    
                try:
                    station_config = StationConfig(url=station_url)
                    self._stations_config[station_key] = station_config
                except Exception as e:
                    raise ConfigurationError(f"Invalid station configuration for '{station_key}': {e}")
            
            logger.info(f"Loaded {len(self._stations_config)} station configurations")
            
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in stations configuration: {e}")
        except IOError as e:
            raise ConfigurationError(f"Error reading stations configuration file: {e}")
    
    def _validate_show_station_references(self) -> None:
        """Validate that all shows reference valid stations."""
        for show_key, show_config in self._shows_config.items():
            if show_config.station not in self._stations_config:
                raise ConfigurationError(
                    f"Show '{show_key}' references unknown station '{show_config.station}'"
                )
    
    def get_show_config(self, show_key: str) -> Optional[ShowConfig]:
        """Get configuration for a specific show.
        
        Args:
            show_key: Key identifying the show
            
        Returns:
            ShowConfig if found, None otherwise
            
        Raises:
            ConfigurationError: If configurations haven't been loaded
        """
        with self._config_lock:
            if not self._loaded:
                raise ConfigurationError("Configuration not loaded. Call load_configurations() first.")
            
            return self._shows_config.get(show_key)
    
    def get_station_url(self, station_key: str) -> Optional[str]:
        """Get stream URL for a specific station.
        
        Args:
            station_key: Key identifying the station
            
        Returns:
            Station URL if found, None otherwise
            
        Raises:
            ConfigurationError: If configurations haven't been loaded
        """
        with self._config_lock:
            if not self._loaded:
                raise ConfigurationError("Configuration not loaded. Call load_configurations() first.")
            
            station_config = self._stations_config.get(station_key)
            return station_config.url if station_config else None
    
    def get_all_shows(self) -> Dict[str, ShowConfig]:
        """Get all show configurations.
        
        Returns:
            Dictionary mapping show keys to ShowConfig objects
            
        Raises:
            ConfigurationError: If configurations haven't been loaded
        """
        with self._config_lock:
            if not self._loaded:
                raise ConfigurationError("Configuration not loaded. Call load_configurations() first.")
            
            return self._shows_config.copy()
    
    def get_all_stations(self) -> Dict[str, str]:
        """Get all station configurations.
        
        Returns:
            Dictionary mapping station keys to URLs
            
        Raises:
            ConfigurationError: If configurations haven't been loaded
        """
        with self._config_lock:
            if not self._loaded:
                raise ConfigurationError("Configuration not loaded. Call load_configurations() first.")
            
            return {key: config.url for key, config in self._stations_config.items()}
    
    def reload_configurations(self) -> None:
        """Reload all configuration files.
        
        Raises:
            ConfigurationError: If configuration files cannot be reloaded
        """
        with self._config_lock:
            self._loaded = False
            self._shows_config.clear()
            self._stations_config.clear()
            self.load_configurations()
            logger.info("Configuration reloaded successfully")
    
    def is_loaded(self) -> bool:
        """Check if configurations have been loaded.
        
        Returns:
            True if configurations are loaded, False otherwise
        """
        with self._config_lock:
            return self._loaded