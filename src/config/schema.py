"""
Configuration schema definitions using Pydantic v2.

This module defines the configuration structure for the Asterisk AI Voice Agent,
including validation rules, default values, and environment variable mapping.
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, validator, root_validator
from pydantic_settings import BaseSettings
import os
from pathlib import Path


class SIPConfig(BaseSettings):
    """SIP/RTP configuration settings."""
    
    host: str = Field(default="voiprnd.nemtclouddispatch.com", description="Asterisk server hostname")
    port: int = Field(default=5060, ge=1, le=65535, description="SIP port")
    extension: str = Field(default="3000", description="SIP extension number")
    password: str = Field(default="AIAgent2025", description="SIP extension password")
    realm: Optional[str] = Field(default=None, description="SIP realm for authentication")
    transport: Literal["udp", "tcp", "tls"] = Field(default="udp", description="SIP transport protocol")
    codecs: List[str] = Field(default=["PCMU", "PCMA", "G722"], description="Supported audio codecs")
    rtp_port_range: tuple[int, int] = Field(default=(10000, 20000), description="RTP port range")
    nat_traversal: bool = Field(default=True, description="Enable NAT traversal")
    stun_server: Optional[str] = Field(default=None, description="STUN server for NAT traversal")
    
    class Config:
        env_prefix = "VOICE_AGENT_SIP_"


class AudioConfig(BaseModel):
    """Audio processing configuration."""
    
    sample_rate: int = Field(default=8000, ge=8000, le=48000, description="Audio sample rate")
    channels: int = Field(default=1, ge=1, le=2, description="Number of audio channels")
    frame_size: int = Field(default=160, ge=80, le=640, description="Audio frame size in samples")
    vad_enabled: bool = Field(default=True, description="Enable Voice Activity Detection")
    noise_suppression: bool = Field(default=True, description="Enable noise suppression")
    echo_cancellation: bool = Field(default=True, description="Enable echo cancellation")
    agc_enabled: bool = Field(default=True, description="Enable Automatic Gain Control")
    vad_aggressiveness: int = Field(default=2, ge=0, le=3, description="VAD aggressiveness level")


class AIProviderConfig(BaseSettings):
    """AI provider configuration."""
    
    provider: Literal["openai", "azure", "deepgram", "ollama"] = Field(default="openai", description="AI provider")
    api_key: Optional[str] = Field(default="", description="API key for the provider")
    model: str = Field(default="gpt-4o", description="AI model to use")
    voice: str = Field(default="alloy", description="Voice for TTS")
    language: str = Field(default="en-US", description="Language for STT/TTS")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="AI response temperature")
    max_tokens: int = Field(default=150, ge=1, le=4000, description="Maximum tokens per response")
    timeout: int = Field(default=30, ge=1, le=300, description="Request timeout in seconds")
    retry_attempts: int = Field(default=3, ge=0, le=10, description="Number of retry attempts")
    
    # Provider-specific settings
    openai_base_url: Optional[str] = Field(default=None, description="OpenAI base URL")
    azure_endpoint: Optional[str] = Field(default=None, description="Azure Speech endpoint")
    azure_region: Optional[str] = Field(default=None, description="Azure region")
    deepgram_model: Optional[str] = Field(default="nova-2", description="Deepgram model")
    ollama_base_url: Optional[str] = Field(default="http://localhost:11434", description="Ollama base URL")
    
    class Config:
        env_prefix = "VOICE_AGENT_AI_PROVIDER_"


class SecurityConfig(BaseModel):
    """Security configuration settings."""
    
    tls_enabled: bool = Field(default=False, description="Enable TLS for SIP")
    srtp_enabled: bool = Field(default=False, description="Enable SRTP for RTP")
    jwt_secret: Optional[str] = Field(default=None, description="JWT secret for authentication")
    allowed_ips: List[str] = Field(default=[], description="Allowed IP addresses")
    rate_limit_per_minute: int = Field(default=60, ge=1, le=1000, description="Rate limit per minute")
    audit_logging: bool = Field(default=True, description="Enable audit logging")
    data_retention_days: int = Field(default=30, ge=1, le=365, description="Data retention period in days")


class MonitoringConfig(BaseModel):
    """Monitoring and health check configuration."""
    
    health_check_port: int = Field(default=8000, ge=1024, le=65535, description="Health check port")
    metrics_enabled: bool = Field(default=True, description="Enable metrics collection")
    prometheus_port: int = Field(default=9090, ge=1024, le=65535, description="Prometheus metrics port")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO", description="Log level")
    log_format: Literal["json", "text"] = Field(default="json", description="Log format")
    log_file: Optional[str] = Field(default=None, description="Log file path")
    max_log_size_mb: int = Field(default=100, ge=1, le=1000, description="Maximum log file size in MB")
    log_retention_days: int = Field(default=7, ge=1, le=30, description="Log retention period in days")


class MCPConfig(BaseModel):
    """Model Context Protocol configuration."""
    
    enabled: bool = Field(default=False, description="Enable MCP tool integration")
    tools: List[str] = Field(default=[], description="Enabled MCP tools")
    safe_mode: bool = Field(default=True, description="Enable safe mode for tool execution")
    timeout: int = Field(default=30, ge=1, le=300, description="Tool execution timeout")


class VoiceAgentConfig(BaseSettings):
    """Main configuration class for the Voice Agent."""
    
    # Core settings
    integration_mode: Literal["sip", "audiosocket"] = Field(default="sip", description="Integration mode")
    asterisk_version: str = Field(default="16", description="Minimum Asterisk version")
    debug: bool = Field(default=False, description="Enable debug mode")
    
    # Component configurations
    sip: SIPConfig = Field(default_factory=SIPConfig, description="SIP configuration")
    audio: AudioConfig = Field(default_factory=AudioConfig, description="Audio configuration")
    ai_provider: AIProviderConfig = Field(default_factory=AIProviderConfig, description="AI provider configuration")
    security: SecurityConfig = Field(default_factory=SecurityConfig, description="Security configuration")
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig, description="Monitoring configuration")
    mcp: MCPConfig = Field(default_factory=MCPConfig, description="MCP configuration")
    
    @root_validator(pre=True)
    def load_environment_variables(cls, values):
        """Load environment variables for nested configurations."""
        # Load SIP configuration with environment variables
        sip_data = values.get('sip', {})
        sip_env_vars = {}
        for key, value in os.environ.items():
            if key.startswith('VOICE_AGENT_SIP_'):
                field_name = key.replace('VOICE_AGENT_SIP_', '').lower()
                sip_env_vars[field_name] = value
        
        # Merge file data with environment variables (env vars take precedence)
        sip_data.update(sip_env_vars)
        values['sip'] = sip_data
        
        # Load AI provider configuration with environment variables
        ai_data = values.get('ai_provider', {})
        ai_env_vars = {}
        for key, value in os.environ.items():
            if key.startswith('VOICE_AGENT_AI_PROVIDER_'):
                field_name = key.replace('VOICE_AGENT_AI_PROVIDER_', '').lower()
                ai_env_vars[field_name] = value
        
        # Merge file data with environment variables (env vars take precedence)
        ai_data.update(ai_env_vars)
        values['ai_provider'] = ai_data
        
        return values
    
    # File paths
    config_file: str = Field(default="config/engine.json", description="Configuration file path")
    log_dir: str = Field(default="logs", description="Log directory")
    data_dir: str = Field(default="data", description="Data directory")
    
    class Config:
        env_prefix = "VOICE_AGENT_"
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
    @validator('sip')
    def validate_sip_config(cls, v):
        """Validate SIP configuration."""
        if not v.host:
            raise ValueError("SIP host cannot be empty")
        if v.port < 1 or v.port > 65535:
            raise ValueError("SIP port must be between 1 and 65535")
        return v
    
    @validator('ai_provider')
    def validate_ai_provider(cls, v):
        """Validate AI provider configuration."""
        # Only validate if api_key is provided (not empty)
        if v.api_key and v.api_key.strip():
            # Provider-specific validation
            if v.provider == "azure" and not v.azure_endpoint:
                raise ValueError("Azure endpoint is required for Azure provider")
            if v.provider == "azure" and not v.azure_region:
                raise ValueError("Azure region is required for Azure provider")
            
        return v
    
    @root_validator(skip_on_failure=True)
    def validate_config(cls, values):
        """Root validation for the entire configuration."""
        # Ensure log directory exists
        log_dir = values.get('log_dir', 'logs')
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        
        # Ensure data directory exists
        data_dir = values.get('data_dir', 'data')
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        
        return values
    
    def get_ai_provider_config(self) -> Dict[str, Any]:
        """Get AI provider configuration as a dictionary."""
        config = self.ai_provider.dict()
        
        # Add provider-specific settings
        if self.ai_provider.provider == "openai":
            config.update({
                "base_url": self.ai_provider.openai_base_url,
                "api_key": self.ai_provider.api_key
            })
        elif self.ai_provider.provider == "azure":
            config.update({
                "endpoint": self.ai_provider.azure_endpoint,
                "region": self.ai_provider.azure_region,
                "api_key": self.ai_provider.api_key
            })
        elif self.ai_provider.provider == "deepgram":
            config.update({
                "api_key": self.ai_provider.api_key,
                "model": self.ai_provider.deepgram_model
            })
        elif self.ai_provider.provider == "ollama":
            config.update({
                "base_url": self.ai_provider.ollama_base_url,
                "model": self.ai_provider.model
            })
        
        return config
    
    def is_secure_mode(self) -> bool:
        """Check if the configuration is in secure mode."""
        return (
            self.security.tls_enabled and
            self.security.srtp_enabled and
            self.security.jwt_secret is not None
        )
    
    def get_log_config(self) -> Dict[str, Any]:
        """Get logging configuration."""
        return {
            "level": self.monitoring.log_level,
            "format": self.monitoring.log_format,
            "file": self.monitoring.log_file,
            "max_size_mb": self.monitoring.max_log_size_mb,
            "retention_days": self.monitoring.log_retention_days,
            "directory": self.log_dir
        }


# Default configuration instance
DEFAULT_CONFIG = VoiceAgentConfig()