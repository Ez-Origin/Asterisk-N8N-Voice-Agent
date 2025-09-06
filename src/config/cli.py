"""
Command-line interface for configuration management.

This module provides CLI commands for configuration validation,
environment checks, and interactive setup.
"""

import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import print as rprint

from .manager import config_manager, get_config
from .schema import VoiceAgentConfig, DEFAULT_CONFIG


app = typer.Typer(
    name="config",
    help="Configuration management for Asterisk AI Voice Agent",
    no_args_is_help=True
)
console = Console()


@app.command()
def validate(
    config_file: Optional[str] = typer.Option(None, "--file", "-f", help="Configuration file to validate")
) -> None:
    """Validate configuration file and environment variables."""
    console.print("\n[bold blue]🔍 Validating Configuration[/bold blue]\n")
    
    try:
        if config_file:
            # Load specific config file
            config_path = Path(config_file)
            if not config_path.exists():
                console.print(f"[red]❌ Configuration file not found: {config_file}[/red]")
                sys.exit(1)
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            config = VoiceAgentConfig(**config_data)
        else:
            # Use current config
            config = get_config()
        
        # Validate configuration
        is_valid, errors = config_manager.validate_config()
        
        if is_valid:
            console.print("[green]✅ Configuration is valid![/green]")
            
            # Show configuration summary
            show_config_summary(config)
        else:
            console.print("[red]❌ Configuration validation failed:[/red]")
            for error in errors:
                console.print(f"  • {error}")
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[red]❌ Error validating configuration: {e}[/red]")
        sys.exit(1)


@app.command()
def show(
    include_secrets: bool = typer.Option(False, "--secrets", "-s", help="Include secret values")
) -> None:
    """Show current configuration."""
    console.print("\n[bold blue]📋 Current Configuration[/bold blue]\n")
    
    config = get_config()
    show_config_summary(config, include_secrets)


@app.command()
def init(
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", help="Interactive setup")
) -> None:
    """Initialize configuration file with default values."""
    console.print("\n[bold blue]🚀 Initializing Configuration[/bold blue]\n")
    
    config_file = Path("config/engine.json")
    
    if config_file.exists():
        if not Confirm.ask(f"Configuration file {config_file} already exists. Overwrite?"):
            console.print("Configuration initialization cancelled.")
            return
    
    if interactive:
        config = interactive_setup()
    else:
        config = DEFAULT_CONFIG
    
    # Save configuration
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config.dict(), f, indent=2, ensure_ascii=False)
    
    console.print(f"[green]✅ Configuration initialized: {config_file}[/green]")


@app.command()
def check() -> None:
    """Check system environment and dependencies."""
    console.print("\n[bold blue]🔧 Environment Check[/bold blue]\n")
    
    # Check Python version
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    console.print(f"Python version: {python_version}")
    
    # Check required packages
    required_packages = [
        "pydantic",
        "typer",
        "rich",
        "watchdog",
        "websockets",
        "aiortc",
        "webrtcvad"
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
            console.print(f"✅ {package}")
        except ImportError:
            console.print(f"❌ {package}")
            missing_packages.append(package)
    
    if missing_packages:
        console.print(f"\n[red]Missing packages: {', '.join(missing_packages)}[/red]")
        console.print("Install with: pip install " + " ".join(missing_packages))
    else:
        console.print("\n[green]✅ All required packages are installed![/green]")
    
    # Check environment variables
    env_vars = config_manager.get_environment_variables()
    if env_vars:
        console.print(f"\n[blue]Environment variables found: {len(env_vars)}[/blue]")
        for key, value in env_vars.items():
            console.print(f"  {key} = {'*' * len(value) if 'key' in key.lower() or 'secret' in key.lower() else value}")


@app.command()
def export(
    output_file: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    include_secrets: bool = typer.Option(False, "--secrets", "-s", help="Include secret values")
) -> None:
    """Export configuration to JSON file."""
    console.print("\n[bold blue]📤 Exporting Configuration[/bold blue]\n")
    
    config_dict = config_manager.export_config(include_secrets=include_secrets)
    
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)
        
        console.print(f"[green]✅ Configuration exported to: {output_path}[/green]")
    else:
        console.print(json.dumps(config_dict, indent=2, ensure_ascii=False))


def show_config_summary(config: VoiceAgentConfig, include_secrets: bool = False) -> None:
    """Show configuration summary in a formatted table."""
    
    # SIP Configuration
    sip_table = Table(title="SIP Configuration")
    sip_table.add_column("Setting", style="cyan")
    sip_table.add_column("Value", style="green")
    
    sip_table.add_row("Host", config.sip.host)
    sip_table.add_row("Port", str(config.sip.port))
    sip_table.add_row("Extension", config.sip.extension)
    sip_table.add_row("Password", "***" if not include_secrets else config.sip.password)
    sip_table.add_row("Transport", config.sip.transport)
    sip_table.add_row("Codecs", ", ".join(config.sip.codecs))
    
    console.print(sip_table)
    
    # AI Provider Configuration
    ai_table = Table(title="AI Provider Configuration")
    ai_table.add_column("Setting", style="cyan")
    ai_table.add_column("Value", style="green")
    
    ai_table.add_row("Provider", config.ai_provider.provider)
    ai_table.add_row("Model", config.ai_provider.model)
    ai_table.add_row("Voice", config.ai_provider.voice)
    ai_table.add_row("Language", config.ai_provider.language)
    ai_table.add_row("API Key", "***" if not include_secrets else config.ai_provider.api_key)
    ai_table.add_row("Temperature", str(config.ai_provider.temperature))
    
    console.print(ai_table)
    
    # Audio Configuration
    audio_table = Table(title="Audio Configuration")
    audio_table.add_column("Setting", style="cyan")
    audio_table.add_column("Value", style="green")
    
    audio_table.add_row("Sample Rate", str(config.audio.sample_rate))
    audio_table.add_row("Channels", str(config.audio.channels))
    audio_table.add_row("VAD Enabled", "Yes" if config.audio.vad_enabled else "No")
    audio_table.add_row("Noise Suppression", "Yes" if config.audio.noise_suppression else "No")
    audio_table.add_row("Echo Cancellation", "Yes" if config.audio.echo_cancellation else "No")
    
    console.print(audio_table)


def interactive_setup() -> VoiceAgentConfig:
    """Interactive configuration setup."""
    console.print("[bold blue]Interactive Configuration Setup[/bold blue]\n")
    
    # SIP Configuration
    console.print("[bold]SIP Configuration[/bold]")
    sip_host = Prompt.ask("SIP Host", default="voiprnd.nemtclouddispatch.com")
    sip_port = int(Prompt.ask("SIP Port", default="5060"))
    sip_extension = Prompt.ask("SIP Extension", default="3000")
    sip_password = Prompt.ask("SIP Password", default="AIAgent2025")
    sip_transport = Prompt.ask("SIP Transport", choices=["udp", "tcp", "tls"], default="udp")
    
    # AI Provider Configuration
    console.print("\n[bold]AI Provider Configuration[/bold]")
    ai_provider = Prompt.ask("AI Provider", choices=["openai", "azure", "deepgram", "ollama"], default="openai")
    ai_api_key = Prompt.ask("API Key", password=True)
    ai_model = Prompt.ask("Model", default="gpt-4o")
    ai_voice = Prompt.ask("Voice", default="alloy")
    ai_language = Prompt.ask("Language", default="en-US")
    
    # Audio Configuration
    console.print("\n[bold]Audio Configuration[/bold]")
    audio_sample_rate = int(Prompt.ask("Sample Rate", default="8000"))
    audio_vad = Confirm.ask("Enable Voice Activity Detection", default=True)
    audio_noise_suppression = Confirm.ask("Enable Noise Suppression", default=True)
    audio_echo_cancellation = Confirm.ask("Enable Echo Cancellation", default=True)
    
    # Security Configuration
    console.print("\n[bold]Security Configuration[/bold]")
    security_tls = Confirm.ask("Enable TLS", default=False)
    security_srtp = Confirm.ask("Enable SRTP", default=False)
    security_audit = Confirm.ask("Enable Audit Logging", default=True)
    
    # Create configuration
    config_data = {
        "sip": {
            "host": sip_host,
            "port": sip_port,
            "extension": sip_extension,
            "password": sip_password,
            "transport": sip_transport
        },
        "ai_provider": {
            "provider": ai_provider,
            "api_key": ai_api_key,
            "model": ai_model,
            "voice": ai_voice,
            "language": ai_language
        },
        "audio": {
            "sample_rate": audio_sample_rate,
            "vad_enabled": audio_vad,
            "noise_suppression": audio_noise_suppression,
            "echo_cancellation": audio_echo_cancellation
        },
        "security": {
            "tls_enabled": security_tls,
            "srtp_enabled": security_srtp,
            "audit_logging": security_audit
        }
    }
    
    return VoiceAgentConfig(**config_data)


if __name__ == "__main__":
    app()


