"""
Configuration manager with hot-reload capability.

This module provides the main configuration management functionality,
including loading from files, environment variables, and hot-reload support.
"""

import json
import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, Callable, List
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging
from datetime import datetime

from .schema import VoiceAgentConfig, SIPConfig, AIProviderConfig


logger = logging.getLogger(__name__)


class ConfigFileHandler(FileSystemEventHandler):
    """File system event handler for configuration file changes."""
    
    def __init__(self, config_manager: 'ConfigManager'):
        self.config_manager = config_manager
        self.last_modified = 0
    
    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return
            
        # Check if it's the config file
        if event.src_path == self.config_manager.config_file_path:
            # Avoid multiple triggers for the same change
            current_time = datetime.now().timestamp()
            if current_time - self.last_modified < 1.0:  # 1 second debounce
                return
            self.last_modified = current_time
            
            logger.info(f"Configuration file changed: {event.src_path}")
            asyncio.create_task(self.config_manager.reload_config())


class ConfigManager:
    """
    Configuration manager with hot-reload support.
    
    This class manages the application configuration, including:
    - Loading from JSON files and environment variables
    - Hot-reload when configuration files change
    - Validation and error handling
    - Callback notifications for configuration changes
    """
    
    def __init__(self, config_file: str = "config/engine.json"):
        self.config_file_path = Path(config_file)
        self.config: VoiceAgentConfig = None  # Will be loaded in load_config()
        self.observers: List[Observer] = []
        self.callbacks: List[Callable[[VoiceAgentConfig], None]] = []
        self._lock = asyncio.Lock()
        self._is_observing = False
        
        # Load initial configuration
        self.load_config()
    
    def load_config(self) -> VoiceAgentConfig:
        """
        Load configuration from file and environment variables.
        
        Returns:
            VoiceAgentConfig: The loaded configuration
        """
        try:
            # Load from file if it exists
            if self.config_file_path.exists():
                with open(self.config_file_path, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
            else:
                file_config = {}
            
            # Remove config_file from file_config to avoid duplicate parameter
            file_config.pop('config_file', None)
            
            # Create configuration - VoiceAgentConfig will handle environment variables
            # through its root_validator
            self.config = VoiceAgentConfig(
                config_file=str(self.config_file_path),
                **file_config
            )
            
            logger.info(f"Configuration loaded from {self.config_file_path}")
            return self.config
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            logger.warning("Using default configuration")
            # Even when using default config, ensure environment variables are loaded
            try:
                self.config = VoiceAgentConfig()
                logger.info("Default configuration loaded with environment variables")
                return self.config
            except Exception as env_error:
                logger.error(f"Failed to load default configuration: {env_error}")
                # Create a minimal config as fallback
                self.config = VoiceAgentConfig(
                    sip=SIPConfig(host="localhost", extension="3000", password=""),
                    ai_provider=AIProviderConfig(provider="openai", api_key="")
                )
                return self.config
    
    async def reload_config(self) -> VoiceAgentConfig:
        """
        Reload configuration from file and notify callbacks.
        
        Returns:
            VoiceAgentConfig: The reloaded configuration
        """
        async with self._lock:
            try:
                old_config = self.config
                self.config = self.load_config()
                
                # Notify callbacks of configuration change
                for callback in self.callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(self.config)
                        else:
                            callback(self.config)
                    except Exception as e:
                        logger.error(f"Error in configuration callback: {e}")
                
                logger.info("Configuration reloaded successfully")
                return self.config
                
            except Exception as e:
                logger.error(f"Failed to reload configuration: {e}")
                return self.config
    
    def save_config(self, config: Optional[VoiceAgentConfig] = None) -> bool:
        """
        Save configuration to file.
        
        Args:
            config: Configuration to save. If None, saves current config.
            
        Returns:
            bool: True if saved successfully, False otherwise.
        """
        try:
            config_to_save = config or self.config
            
            # Ensure config directory exists
            self.config_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to dictionary and save
            config_dict = config_to_save.dict()
            
            with open(self.config_file_path, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Configuration saved to {self.config_file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            return False
    
    def add_callback(self, callback: Callable[[VoiceAgentConfig], None]) -> None:
        """
        Add a callback function to be called when configuration changes.
        
        Args:
            callback: Function to call with new configuration
        """
        self.callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[VoiceAgentConfig], None]) -> None:
        """
        Remove a callback function.
        
        Args:
            callback: Function to remove
        """
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    def start_hot_reload(self) -> None:
        """Start monitoring configuration file for changes."""
        if self._is_observing:
            return
        
        try:
            # Create observer for the config file directory
            observer = Observer()
            handler = ConfigFileHandler(self)
            observer.schedule(handler, str(self.config_file_path.parent), recursive=False)
            observer.start()
            
            self.observers.append(observer)
            self._is_observing = True
            
            logger.info(f"Started hot-reload monitoring for {self.config_file_path}")
            
        except Exception as e:
            logger.error(f"Failed to start hot-reload monitoring: {e}")
    
    def stop_hot_reload(self) -> None:
        """Stop monitoring configuration file for changes."""
        for observer in self.observers:
            observer.stop()
            observer.join()
        
        self.observers.clear()
        self._is_observing = False
        logger.info("Stopped hot-reload monitoring")
    
    def get_config(self) -> VoiceAgentConfig:
        """Get the current configuration."""
        return self.config
    
    def update_config(self, updates: Dict[str, Any]) -> bool:
        """
        Update configuration with new values.
        
        Args:
            updates: Dictionary of configuration updates
            
        Returns:
            bool: True if updated successfully, False otherwise.
        """
        try:
            # Create new configuration with updates
            current_dict = self.config.dict()
            current_dict.update(updates)
            
            new_config = VoiceAgentConfig(**current_dict)
            self.config = new_config
            
            # Save updated configuration
            self.save_config()
            
            logger.info("Configuration updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update configuration: {e}")
            return False
    
    def validate_config(self) -> tuple[bool, List[str]]:
        """
        Validate the current configuration.
        
        Returns:
            tuple: (is_valid, error_messages)
        """
        try:
            # Try to create a new instance to validate
            VoiceAgentConfig(**self.config.dict())
            return True, []
        except Exception as e:
            return False, [str(e)]
    
    def get_environment_variables(self) -> Dict[str, str]:
        """
        Get all environment variables that affect configuration.
        
        Returns:
            Dict[str, str]: Environment variables and their values
        """
        env_vars = {}
        prefix = "VOICE_AGENT_"
        
        for key, value in os.environ.items():
            if key.startswith(prefix):
                env_vars[key] = value
        
        return env_vars
    
    def export_config(self, include_secrets: bool = False) -> Dict[str, Any]:
        """
        Export configuration as a dictionary.
        
        Args:
            include_secrets: Whether to include secret values
            
        Returns:
            Dict[str, Any]: Configuration dictionary
        """
        config_dict = self.config.dict()
        
        if not include_secrets:
            # Remove or mask secret values
            if 'ai_provider' in config_dict:
                if 'api_key' in config_dict['ai_provider']:
                    config_dict['ai_provider']['api_key'] = "***MASKED***"
            
            if 'security' in config_dict:
                if 'jwt_secret' in config_dict['security'] and config_dict['security']['jwt_secret']:
                    config_dict['security']['jwt_secret'] = "***MASKED***"
        
        return config_dict
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop_hot_reload()


# Global configuration manager instance
config_manager = ConfigManager()


def get_config() -> VoiceAgentConfig:
    """Get the current configuration."""
    return config_manager.get_config()


def reload_config() -> VoiceAgentConfig:
    """Reload configuration from file."""
    return asyncio.run(config_manager.reload_config())


def save_config(config: Optional[VoiceAgentConfig] = None) -> bool:
    """Save configuration to file."""
    return config_manager.save_config(config)