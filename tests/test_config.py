"""
Tests for configuration management system.

This module contains unit tests for the configuration schema,
manager, and CLI functionality.
"""

import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.config.schema import VoiceAgentConfig, SIPConfig, AudioConfig, AIProviderConfig
from src.config.manager import ConfigManager
from src.config.cli import interactive_setup


class TestSIPConfig:
    """Test SIP configuration schema."""
    
    def test_default_sip_config(self):
        """Test default SIP configuration values."""
        config = SIPConfig()
        assert config.host == "voiprnd.nemtclouddispatch.com"
        assert config.port == 5060
        assert config.extension == "3000"
        assert config.password == "AIAgent2025"
        assert config.transport == "udp"
        assert config.codecs == ["PCMU", "PCMA", "G722"]
        assert config.rtp_port_range == (10000, 20000)
        assert config.nat_traversal is True
    
    def test_sip_config_validation(self):
        """Test SIP configuration validation."""
        # Valid configuration
        config = SIPConfig(
            host="test.example.com",
            port=5061,
            extension="1001",
            password="testpass",
            transport="tls"
        )
        assert config.host == "test.example.com"
        assert config.port == 5061
        
        # Invalid port
        with pytest.raises(ValueError):
            SIPConfig(port=0)
        
        with pytest.raises(ValueError):
            SIPConfig(port=70000)
    
    def test_sip_config_serialization(self):
        """Test SIP configuration serialization."""
        config = SIPConfig(host="test.com", port=5060)
        data = config.dict()
        assert data["host"] == "test.com"
        assert data["port"] == 5060


class TestAudioConfig:
    """Test audio configuration schema."""
    
    def test_default_audio_config(self):
        """Test default audio configuration values."""
        config = AudioConfig()
        assert config.sample_rate == 8000
        assert config.channels == 1
        assert config.frame_size == 160
        assert config.vad_enabled is True
        assert config.noise_suppression is True
        assert config.echo_cancellation is True
        assert config.vad_aggressiveness == 2
    
    def test_audio_config_validation(self):
        """Test audio configuration validation."""
        # Valid configuration
        config = AudioConfig(sample_rate=16000, channels=2)
        assert config.sample_rate == 16000
        assert config.channels == 2
        
        # Invalid sample rate
        with pytest.raises(ValueError):
            AudioConfig(sample_rate=4000)
        
        with pytest.raises(ValueError):
            AudioConfig(sample_rate=96000)
    
    def test_audio_config_serialization(self):
        """Test audio configuration serialization."""
        config = AudioConfig(sample_rate=16000, vad_enabled=False)
        data = config.dict()
        assert data["sample_rate"] == 16000
        assert data["vad_enabled"] is False


class TestAIProviderConfig:
    """Test AI provider configuration schema."""
    
    def test_default_ai_provider_config(self):
        """Test default AI provider configuration values."""
        config = AIProviderConfig(api_key="test-key")
        assert config.provider == "openai"
        assert config.api_key == "test-key"
        assert config.model == "gpt-4o"
        assert config.voice == "alloy"
        assert config.language == "en-US"
        assert config.temperature == 0.7
        assert config.max_tokens == 150
        assert config.timeout == 30
        assert config.retry_attempts == 3
    
    def test_ai_provider_config_validation(self):
        """Test AI provider configuration validation."""
        # Valid configuration
        config = AIProviderConfig(
            provider="azure",
            api_key="azure-key",
            azure_endpoint="https://test.cognitiveservices.azure.com/",
            azure_region="eastus"
        )
        assert config.provider == "azure"
        assert config.azure_endpoint == "https://test.cognitiveservices.azure.com/"
        
        # Missing API key
        with pytest.raises(ValueError):
            AIProviderConfig(api_key="")
        
        # Azure without endpoint
        with pytest.raises(ValueError):
            AIProviderConfig(
                provider="azure",
                api_key="test-key",
                azure_endpoint=None
            )
    
    def test_ai_provider_config_serialization(self):
        """Test AI provider configuration serialization."""
        config = AIProviderConfig(api_key="test-key", model="gpt-3.5-turbo")
        data = config.dict()
        assert data["api_key"] == "test-key"
        assert data["model"] == "gpt-3.5-turbo"


class TestVoiceAgentConfig:
    """Test main voice agent configuration schema."""
    
    def test_default_voice_agent_config(self):
        """Test default voice agent configuration values."""
        config = VoiceAgentConfig()
        assert config.integration_mode == "sip"
        assert config.asterisk_version == "16"
        assert config.debug is False
        assert isinstance(config.sip, SIPConfig)
        assert isinstance(config.audio, AudioConfig)
        assert isinstance(config.ai_provider, AIProviderConfig)
    
    def test_voice_agent_config_validation(self):
        """Test voice agent configuration validation."""
        # Valid configuration
        config = VoiceAgentConfig(
            integration_mode="sip",
            asterisk_version="16",
            debug=True
        )
        assert config.integration_mode == "sip"
        assert config.debug is True
        
        # Invalid integration mode
        with pytest.raises(ValueError):
            VoiceAgentConfig(integration_mode="invalid")
    
    def test_voice_agent_config_serialization(self):
        """Test voice agent configuration serialization."""
        config = VoiceAgentConfig(debug=True)
        data = config.dict()
        assert data["debug"] is True
        assert "sip" in data
        assert "audio" in data
        assert "ai_provider" in data
    
    def test_get_ai_provider_config(self):
        """Test getting AI provider configuration."""
        config = VoiceAgentConfig()
        provider_config = config.get_ai_provider_config()
        
        assert "api_key" in provider_config
        assert "model" in provider_config
        assert "provider" in provider_config
    
    def test_is_secure_mode(self):
        """Test secure mode detection."""
        config = VoiceAgentConfig()
        assert config.is_secure_mode() is False
        
        # Enable security features
        config.security.tls_enabled = True
        config.security.srtp_enabled = True
        config.security.jwt_secret = "test-secret"
        assert config.is_secure_mode() is True


class TestConfigManager:
    """Test configuration manager functionality."""
    
    def test_config_manager_initialization(self):
        """Test configuration manager initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "test_config.json"
            manager = ConfigManager(str(config_file))
            
            # Should load default config when file doesn't exist
            config = manager.get_config()
            assert isinstance(config, VoiceAgentConfig)
    
    def test_load_config_from_file(self):
        """Test loading configuration from file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "test_config.json"
            
            # Create test configuration file
            test_config = {
                "debug": True,
                "sip": {
                    "host": "test.example.com",
                    "port": 5061
                }
            }
            
            with open(config_file, 'w') as f:
                json.dump(test_config, f)
            
            manager = ConfigManager(str(config_file))
            config = manager.get_config()
            
            assert config.debug is True
            assert config.sip.host == "test.example.com"
            assert config.sip.port == 5061
    
    def test_save_config(self):
        """Test saving configuration to file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "test_config.json"
            manager = ConfigManager(str(config_file))
            
            # Modify configuration
            config = manager.get_config()
            config.debug = True
            config.sip.host = "test.example.com"
            
            # Save configuration
            success = manager.save_config(config)
            assert success is True
            
            # Verify file was created
            assert config_file.exists()
            
            # Load and verify
            with open(config_file, 'r') as f:
                saved_data = json.load(f)
            
            assert saved_data["debug"] is True
            assert saved_data["sip"]["host"] == "test.example.com"
    
    def test_validate_config(self):
        """Test configuration validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "test_config.json"
            manager = ConfigManager(str(config_file))
            
            # Valid configuration
            is_valid, errors = manager.validate_config()
            assert is_valid is True
            assert len(errors) == 0
    
    def test_export_config(self):
        """Test configuration export."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "test_config.json"
            manager = ConfigManager(str(config_file))
            
            # Export without secrets
            config_dict = manager.export_config(include_secrets=False)
            assert "ai_provider" in config_dict
            assert config_dict["ai_provider"]["api_key"] == "***MASKED***"
            
            # Export with secrets
            config_dict = manager.export_config(include_secrets=True)
            assert "ai_provider" in config_dict
            assert config_dict["ai_provider"]["api_key"] != "***MASKED***"
    
    def test_update_config(self):
        """Test configuration updates."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "test_config.json"
            manager = ConfigManager(str(config_file))
            
            # Update configuration
            updates = {
                "debug": True,
                "sip": {
                    "host": "updated.example.com"
                }
            }
            
            success = manager.update_config(updates)
            assert success is True
            
            # Verify updates
            config = manager.get_config()
            assert config.debug is True
            assert config.sip.host == "updated.example.com"
    
    def test_callback_functionality(self):
        """Test configuration change callbacks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "test_config.json"
            manager = ConfigManager(str(config_file))
            
            callback_called = False
            callback_config = None
            
            def test_callback(config):
                nonlocal callback_called, callback_config
                callback_called = True
                callback_config = config
            
            # Add callback
            manager.add_callback(test_callback)
            
            # Update configuration
            updates = {"debug": True}
            manager.update_config(updates)
            
            # Callback should have been called
            assert callback_called is True
            assert callback_config is not None
            assert callback_config.debug is True
            
            # Remove callback
            manager.remove_callback(test_callback)
            callback_called = False
            
            # Update again
            manager.update_config({"debug": False})
            
            # Callback should not have been called
            assert callback_called is False


class TestConfigCLI:
    """Test configuration CLI functionality."""
    
    def test_interactive_setup(self):
        """Test interactive configuration setup."""
        # Mock user inputs
        with patch('src.config.cli.Prompt.ask') as mock_prompt, \
             patch('src.config.cli.Confirm.ask') as mock_confirm:
            
            # Configure mock responses
            mock_prompt.side_effect = [
                "test.example.com",  # SIP host
                "5060",              # SIP port
                "3000",              # SIP extension
                "testpass",          # SIP password
                "udp",               # SIP transport
                "openai",            # AI provider
                "test-api-key",      # API key
                "gpt-4o",            # Model
                "alloy",             # Voice
                "en-US",             # Language
                "8000",              # Sample rate
            ]
            
            mock_confirm.side_effect = [
                True,  # VAD enabled
                True,  # Noise suppression
                True,  # Echo cancellation
                False, # TLS enabled
                False, # SRTP enabled
                True,  # Audit logging
            ]
            
            config = interactive_setup()
            
            assert config.sip.host == "test.example.com"
            assert config.sip.port == 5060
            assert config.sip.extension == "3000"
            assert config.sip.password == "testpass"
            assert config.ai_provider.provider == "openai"
            assert config.ai_provider.api_key == "test-api-key"
            assert config.audio.sample_rate == 8000
            assert config.audio.vad_enabled is True
            assert config.security.tls_enabled is False


if __name__ == "__main__":
    pytest.main([__file__])


