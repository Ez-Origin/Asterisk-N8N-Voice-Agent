"""
Configuration module for Asterisk AI Voice Agent.

This module provides configuration management functionality including:
- Schema validation with Pydantic v2
- Hot-reload capability
- Environment variable support
- CLI tools for configuration management
"""

from .schema import VoiceAgentConfig, DEFAULT_CONFIG, SIPConfig, AudioConfig, AIProviderConfig, SecurityConfig, MonitoringConfig, MCPConfig
from .manager import ConfigManager, config_manager, get_config, reload_config, save_config

__all__ = [
    "VoiceAgentConfig",
    "DEFAULT_CONFIG", 
    "SIPConfig",
    "AudioConfig", 
    "AIProviderConfig",
    "SecurityConfig",
    "MonitoringConfig",
    "MCPConfig",
    "ConfigManager",
    "config_manager",
    "get_config",
    "reload_config", 
    "save_config"
]