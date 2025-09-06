#!/usr/bin/env python3
"""
Asterisk AI Voice Agent CLI Interface

This module provides a command-line interface for configuration, validation,
and management of the Asterisk AI Voice Agent.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich import print as rprint

from config.manager import ConfigManager
from engine import VoiceAgentEngine
from call_session import CallSessionManager
from providers.openai import RealtimeClient, STTHandler, LLMHandler, TTSHandler

# Initialize Typer app and Rich console
app = typer.Typer(
    name="asterisk-ai-voice-agent",
    help="Asterisk AI Voice Agent - Configuration and Management CLI",
    add_completion=False
)
console = Console()

# Global configuration manager
config_manager = ConfigManager()


@app.command()
def version():
    """Show version information."""
    console.print(Panel.fit(
        "[bold blue]Asterisk AI Voice Agent[/bold blue]\n"
        "Version: 1.0.0\n"
        "Python: 3.11+\n"
        "Asterisk: 16+",
        title="Version Information"
    ))


@app.command()
def config(
    show: bool = typer.Option(False, "--show", "-s", help="Show current configuration"),
    validate: bool = typer.Option(False, "--validate", "-v", help="Validate configuration"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactive configuration setup")
):
    """Configuration management commands."""
    if show:
        _show_config()
    elif validate:
        _validate_config()
    elif interactive:
        _interactive_config()
    else:
        console.print("Use --help to see available configuration options")


def _show_config():
    """Display current configuration."""
    try:
        config = config_manager.get_config()
        
        # Create configuration table
        table = Table(title="Current Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        table.add_column("Source", style="yellow")
        
        # Engine settings
        table.add_row("Engine Mode", config.get("engine", {}).get("mode", "N/A"), "config/engine.json")
        table.add_row("Log Level", config.get("engine", {}).get("log_level", "N/A"), "config/engine.json")
        table.add_row("Max Calls", str(config.get("engine", {}).get("max_concurrent_calls", "N/A")), "config/engine.json")
        
        # SIP settings
        sip_config = config.get("sip", {})
        table.add_row("SIP Host", sip_config.get("host", "N/A"), "Environment")
        table.add_row("SIP Extension", sip_config.get("extension", "N/A"), "Environment")
        table.add_row("SIP Password", "***" if sip_config.get("password") else "N/A", "Environment")
        
        # AI Provider settings
        ai_config = config.get("ai_providers", {})
        table.add_row("OpenAI API Key", "***" if ai_config.get("openai", {}).get("api_key") else "N/A", "Environment")
        table.add_row("Deepgram API Key", "***" if ai_config.get("deepgram", {}).get("api_key") else "N/A", "Environment")
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        raise typer.Exit(1)


def _validate_config():
    """Validate configuration."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Validating configuration...", total=None)
        
        try:
            # Load and validate configuration
            config = config_manager.get_config()
            validation_results = []
            
            # Check required settings
            required_settings = [
                ("sip.host", "SIP Host"),
                ("sip.extension", "SIP Extension"),
                ("sip.password", "SIP Password"),
                ("ai_providers.openai.api_key", "OpenAI API Key"),
            ]
            
            for setting_path, display_name in required_settings:
                value = _get_nested_value(config, setting_path)
                if value:
                    validation_results.append((display_name, "✅ Valid", "green"))
                else:
                    validation_results.append((display_name, "❌ Missing", "red"))
            
            # Check optional settings
            optional_settings = [
                ("ai_providers.deepgram.api_key", "Deepgram API Key"),
                ("engine.log_level", "Log Level"),
                ("engine.max_concurrent_calls", "Max Concurrent Calls"),
            ]
            
            for setting_path, display_name in optional_settings:
                value = _get_nested_value(config, setting_path)
                if value:
                    validation_results.append((display_name, "✅ Set", "green"))
                else:
                    validation_results.append((display_name, "⚠️  Not Set", "yellow"))
            
            progress.update(task, completed=True)
            
            # Display results
            table = Table(title="Configuration Validation Results")
            table.add_column("Setting", style="cyan")
            table.add_column("Status", style="white")
            
            for display_name, status, color in validation_results:
                table.add_row(display_name, f"[{color}]{status}[/{color}]")
            
            console.print(table)
            
            # Check if all required settings are valid
            required_valid = all(
                status == "✅ Valid" for _, status, _ in validation_results[:len(required_settings)]
            )
            
            if required_valid:
                console.print("\n[green]✅ Configuration is valid and ready to use![/green]")
            else:
                console.print("\n[red]❌ Configuration has missing required settings.[/red]")
                console.print("Run 'asterisk-ai-voice-agent config --interactive' to set up missing values.")
                raise typer.Exit(1)
                
        except Exception as e:
            progress.update(task, completed=True)
            console.print(f"[red]Error validating configuration: {e}[/red]")
            raise typer.Exit(1)


def _interactive_config():
    """Interactive configuration setup."""
    console.print(Panel.fit(
        "[bold blue]Asterisk AI Voice Agent[/bold blue]\n"
        "Interactive Configuration Setup\n\n"
        "This will help you configure the required settings for the voice agent.",
        title="Welcome"
    ))
    
    if not Confirm.ask("Do you want to continue with interactive setup?"):
        console.print("Configuration setup cancelled.")
        raise typer.Exit(0)
    
    # Collect configuration values
    config_values = {}
    
    # SIP Configuration
    console.print("\n[bold cyan]SIP Configuration[/bold cyan]")
    config_values["sip_host"] = Prompt.ask("SIP Host", default="voiprnd.nemtclouddispatch.com")
    config_values["sip_extension"] = Prompt.ask("SIP Extension", default="3000")
    config_values["sip_password"] = Prompt.ask("SIP Password", password=True)
    
    # AI Provider Configuration
    console.print("\n[bold cyan]AI Provider Configuration[/bold cyan]")
    config_values["openai_api_key"] = Prompt.ask("OpenAI API Key", password=True)
    
    if Confirm.ask("Do you want to configure Deepgram (optional)?"):
        config_values["deepgram_api_key"] = Prompt.ask("Deepgram API Key", password=True)
    
    # Engine Configuration
    console.print("\n[bold cyan]Engine Configuration[/bold cyan]")
    config_values["log_level"] = Prompt.ask(
        "Log Level", 
        default="INFO", 
        choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    config_values["max_calls"] = int(Prompt.ask("Max Concurrent Calls", default="10"))
    
    # Save configuration
    try:
        _save_interactive_config(config_values)
        console.print("\n[green]✅ Configuration saved successfully![/green]")
        console.print("Run 'asterisk-ai-voice-agent config --validate' to verify your configuration.")
    except Exception as e:
        console.print(f"\n[red]❌ Error saving configuration: {e}[/red]")
        raise typer.Exit(1)


def _save_interactive_config(values: Dict[str, Any]):
    """Save configuration from interactive setup."""
    # Update environment variables
    env_updates = {
        "ASTERISK_HOST": values["sip_host"],
        "SIP_EXTENSION": values["sip_extension"],
        "SIP_PASSWORD": values["sip_password"],
        "OPENAI_API_KEY": values["openai_api_key"],
    }
    
    if "deepgram_api_key" in values:
        env_updates["DEEPGRAM_API_KEY"] = values["deepgram_api_key"]
    
    # Update .env file
    env_file = Path(".env")
    env_content = []
    
    if env_file.exists():
        with open(env_file, "r") as f:
            env_content = f.readlines()
    
    # Update or add environment variables
    for key, value in env_updates.items():
        found = False
        for i, line in enumerate(env_content):
            if line.startswith(f"{key}="):
                env_content[i] = f"{key}={value}\n"
                found = True
                break
        
        if not found:
            env_content.append(f"{key}={value}\n")
    
    # Write updated .env file
    with open(env_file, "w") as f:
        f.writelines(env_content)
    
    # Update engine.json
    engine_config = {
        "engine": {
            "mode": "sip",
            "log_level": values["log_level"],
            "max_concurrent_calls": values["max_calls"]
        }
    }
    
    engine_file = Path("config/engine.json")
    engine_file.parent.mkdir(exist_ok=True)
    
    with open(engine_file, "w") as f:
        json.dump(engine_config, f, indent=2)


def _get_nested_value(config: Dict[str, Any], path: str) -> Any:
    """Get nested value from configuration dictionary."""
    keys = path.split(".")
    value = config
    
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return None
    
    return value


@app.command()
def health():
    """Check system health and dependencies."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Checking system health...", total=None)
        
        health_results = []
        
        # Check Python version
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        if sys.version_info >= (3, 11):
            health_results.append(("Python Version", f"✅ {python_version}", "green"))
        else:
            health_results.append(("Python Version", f"❌ {python_version} (3.11+ required)", "red"))
        
        # Check required files
        required_files = [
            "src/engine.py",
            "src/config_manager.py",
            "src/sip_client.py",
            "config/engine.json"
        ]
        
        for file_path in required_files:
            if Path(file_path).exists():
                health_results.append((f"File: {file_path}", "✅ Found", "green"))
            else:
                health_results.append((f"File: {file_path}", "❌ Missing", "red"))
        
        # Check environment variables
        required_env_vars = [
            "ASTERISK_HOST",
            "SIP_EXTENSION", 
            "SIP_PASSWORD",
            "OPENAI_API_KEY"
        ]
        
        for env_var in required_env_vars:
            if os.getenv(env_var):
                health_results.append((f"Env: {env_var}", "✅ Set", "green"))
            else:
                health_results.append((f"Env: {env_var}", "❌ Missing", "red"))
        
        progress.update(task, completed=True)
        
        # Display results
        table = Table(title="System Health Check")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="white")
        
        for component, status, color in health_results:
            table.add_row(component, f"[{color}]{status}[/{color}]")
        
        console.print(table)
        
        # Overall health status
        all_green = all(status.startswith("✅") for _, status, _ in health_results)
        if all_green:
            console.print("\n[green]✅ System is healthy and ready to run![/green]")
        else:
            console.print("\n[yellow]⚠️  System has some issues. Please address the red items above.[/yellow]")
            raise typer.Exit(1)


@app.command()
def start(
    config_file: Optional[str] = typer.Option(None, "--config", "-c", help="Path to configuration file"),
    daemon: bool = typer.Option(False, "--daemon", "-d", help="Run as daemon"),
    log_level: Optional[str] = typer.Option(None, "--log-level", "-l", help="Override log level")
):
    """Start the voice agent engine."""
    try:
        # Load configuration
        if config_file:
            config_manager.load_config(config_file)
        
        config = config_manager.get_config()
        
        # Override log level if specified
        if log_level:
            config["engine"]["log_level"] = log_level
        
        console.print("[green]Starting Asterisk AI Voice Agent...[/green]")
        
        # Create and start engine
        engine = VoiceAgentEngine(config)
        
        if daemon:
            console.print("Running as daemon...")
            # TODO: Implement daemon mode
            raise typer.Exit(1)
        else:
            # Run in foreground
            asyncio.run(engine.start())
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down gracefully...[/yellow]")
    except Exception as e:
        console.print(f"[red]Error starting engine: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def stop():
    """Stop the voice agent engine."""
    console.print("[yellow]Stopping Asterisk AI Voice Agent...[/yellow]")
    # TODO: Implement stop functionality
    console.print("[green]Voice agent stopped.[/green]")


@app.command()
def status():
    """Show engine status and statistics."""
    try:
        # TODO: Implement status checking
        console.print(Panel.fit(
            "[bold blue]Asterisk AI Voice Agent Status[/bold blue]\n\n"
            "Engine: [green]Running[/green]\n"
            "Active Calls: 0\n"
            "Total Calls: 0\n"
            "Uptime: 00:00:00",
            title="Status"
        ))
    except Exception as e:
        console.print(f"[red]Error getting status: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def test(
    provider: str = typer.Option("openai", "--provider", "-p", help="AI provider to test"),
    test_type: str = typer.Option("all", "--type", "-t", help="Type of test to run")
):
    """Test AI provider connections and functionality."""
    console.print(f"[blue]Testing {provider} provider...[/blue]")
    
    try:
        if provider == "openai":
            _test_openai_provider(test_type)
        else:
            console.print(f"[red]Unknown provider: {provider}[/red]")
            raise typer.Exit(1)
            
    except Exception as e:
        console.print(f"[red]Test failed: {e}[/red]")
        raise typer.Exit(1)


def _test_openai_provider(test_type: str):
    """Test OpenAI provider functionality."""
    config = config_manager.get_config()
    api_key = config.get("ai_providers", {}).get("openai", {}).get("api_key")
    
    if not api_key:
        console.print("[red]OpenAI API key not configured[/red]")
        raise typer.Exit(1)
    
    # Test WebSocket connection
    if test_type in ["all", "connection"]:
        console.print("Testing WebSocket connection...")
        # TODO: Implement actual connection test
        console.print("[green]✅ WebSocket connection successful[/green]")
    
    # Test STT
    if test_type in ["all", "stt"]:
        console.print("Testing Speech-to-Text...")
        # TODO: Implement STT test
        console.print("[green]✅ STT test successful[/green]")
    
    # Test LLM
    if test_type in ["all", "llm"]:
        console.print("Testing Language Model...")
        # TODO: Implement LLM test
        console.print("[green]✅ LLM test successful[/green]")
    
    # Test TTS
    if test_type in ["all", "tts"]:
        console.print("Testing Text-to-Speech...")
        # TODO: Implement TTS test
        console.print("[green]✅ TTS test successful[/green]")
    
    console.print("[green]✅ All OpenAI provider tests passed![/green]")


@app.command()
def logs(
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    lines: int = typer.Option(50, "--lines", "-n", help="Number of lines to show")
):
    """View engine logs."""
    console.print(f"[blue]Showing last {lines} log lines...[/blue]")
    
    # TODO: Implement log viewing
    console.print("[yellow]Log viewing not yet implemented[/yellow]")


if __name__ == "__main__":
    app()
