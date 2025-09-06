#!/usr/bin/env python3
"""
Test script for the Asterisk AI Voice Agent CLI interface.
"""

import os
import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src directory to Python path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

from cli import app
from typer.testing import CliRunner

def test_cli_version():
    """Test CLI version command."""
    print("Testing CLI version command...")
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    
    assert result.exit_code == 0
    assert "Asterisk AI Voice Agent" in result.stdout
    assert "Version: 1.0.0" in result.stdout
    print("✅ Version command test passed")

def test_cli_help():
    """Test CLI help command."""
    print("Testing CLI help command...")
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    
    assert result.exit_code == 0
    assert "Asterisk AI Voice Agent" in result.stdout
    assert "Configuration and Management CLI" in result.stdout
    print("✅ Help command test passed")

def test_cli_config_show():
    """Test CLI config show command."""
    print("Testing CLI config show command...")
    runner = CliRunner()
    
    # Mock the config manager
    with patch('cli.config_manager') as mock_config_manager:
        mock_config_manager.get_config.return_value = {
            "engine": {
                "mode": "sip",
                "log_level": "INFO",
                "max_concurrent_calls": 10
            },
            "sip": {
                "host": "voiprnd.nemtclouddispatch.com",
                "extension": "3000",
                "password": "test_password"
            },
            "ai_providers": {
                "openai": {
                    "api_key": "test_api_key"
                },
                "deepgram": {
                    "api_key": "test_deepgram_key"
                }
            }
        }
        
        result = runner.invoke(app, ["config", "--show"])
        
        assert result.exit_code == 0
        assert "Current Configuration" in result.stdout
        assert "SIP Host" in result.stdout
        assert "OpenAI API Key" in result.stdout
        print("✅ Config show command test passed")

def test_cli_config_validate():
    """Test CLI config validate command."""
    print("Testing CLI config validate command...")
    runner = CliRunner()
    
    # Mock the config manager
    with patch('cli.config_manager') as mock_config_manager:
        mock_config_manager.get_config.return_value = {
            "engine": {
                "mode": "sip",
                "log_level": "INFO",
                "max_concurrent_calls": 10
            },
            "sip": {
                "host": "voiprnd.nemtclouddispatch.com",
                "extension": "3000",
                "password": "test_password"
            },
            "ai_providers": {
                "openai": {
                    "api_key": "test_api_key"
                }
            }
        }
        
        result = runner.invoke(app, ["config", "--validate"])
        
        assert result.exit_code == 0
        assert "Configuration Validation Results" in result.stdout
        assert "✅ Valid" in result.stdout
        print("✅ Config validate command test passed")

def test_cli_health():
    """Test CLI health command."""
    print("Testing CLI health command...")
    runner = CliRunner()
    
    result = runner.invoke(app, ["health"])
    
    assert result.exit_code == 0
    assert "System Health Check" in result.stdout
    assert "Python Version" in result.stdout
    print("✅ Health command test passed")

def test_cli_test_openai():
    """Test CLI test command for OpenAI."""
    print("Testing CLI test command for OpenAI...")
    runner = CliRunner()
    
    # Mock the config manager and OpenAI client
    with patch('cli.config_manager') as mock_config_manager, \
         patch('cli.RealtimeClient') as mock_realtime_client:
        
        mock_config_manager.get_config.return_value = {
            "ai_providers": {
                "openai": {
                    "api_key": "test_api_key"
                }
            }
        }
        
        result = runner.invoke(app, ["test", "--provider", "openai"])
        
        assert result.exit_code == 0
        assert "Testing openai provider" in result.stdout
        assert "✅ All OpenAI provider tests passed!" in result.stdout
        print("✅ Test OpenAI command test passed")

def test_cli_status():
    """Test CLI status command."""
    print("Testing CLI status command...")
    runner = CliRunner()
    
    result = runner.invoke(app, ["status"])
    
    assert result.exit_code == 0
    assert "Asterisk AI Voice Agent Status" in result.stdout
    print("✅ Status command test passed")

def test_cli_logs():
    """Test CLI logs command."""
    print("Testing CLI logs command...")
    runner = CliRunner()
    
    result = runner.invoke(app, ["logs"])
    
    assert result.exit_code == 0
    assert "Showing last 50 log lines" in result.stdout
    print("✅ Logs command test passed")

def test_cli_interactive_config():
    """Test CLI interactive config setup."""
    print("Testing CLI interactive config setup...")
    runner = CliRunner()
    
    # Mock user input for interactive config
    with patch('cli.Prompt.ask') as mock_prompt, \
         patch('cli.Confirm.ask') as mock_confirm, \
         patch('cli._save_interactive_config') as mock_save:
        
        mock_confirm.return_value = True
        mock_prompt.side_effect = [
            "voiprnd.nemtclouddispatch.com",  # SIP Host
            "3000",                           # SIP Extension
            "test_password",                  # SIP Password
            "test_openai_key",               # OpenAI API Key
            False,                           # Skip Deepgram
            "INFO",                          # Log Level
            "10"                             # Max Calls
        ]
        
        result = runner.invoke(app, ["config", "--interactive"])
        
        assert result.exit_code == 0
        assert "Interactive Configuration Setup" in result.stdout
        assert "Configuration saved successfully!" in result.stdout
        print("✅ Interactive config command test passed")

def run_all_tests():
    """Run all CLI tests."""
    print("Starting CLI Tests")
    print("=" * 50)
    
    try:
        test_cli_version()
        test_cli_help()
        test_cli_config_show()
        test_cli_config_validate()
        test_cli_health()
        test_cli_test_openai()
        test_cli_status()
        test_cli_logs()
        test_cli_interactive_config()
        
        print("\n" + "=" * 50)
        print("🎉 All CLI tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
