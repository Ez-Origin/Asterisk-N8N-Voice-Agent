"""
CLI interface for testing SIP client functionality.
"""

import asyncio
import logging
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from typing import Optional

from src.sip_client import SIPClient, SIPConfig
from src.config import ConfigManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = typer.Typer()
console = Console()


@app.command()
def test_connection(
    host: str = typer.Option("voiprnd.nemtclouddispatch.com", help="SIP server host"),
    port: int = typer.Option(5060, help="SIP server port"),
    extension: str = typer.Option("3000", help="SIP extension number"),
    password: str = typer.Option("AIAgent2025", help="SIP extension password"),
    duration: int = typer.Option(30, help="Test duration in seconds")
):
    """Test SIP connection and registration with Asterisk."""
    
    # Create SIP configuration
    config = SIPConfig(
        host=host,
        port=port,
        extension=extension,
        password=password
    )
    
    # Create SIP client
    sip_client = SIPClient(config)
    
    async def run_test():
        """Run the SIP connection test."""
        try:
            console.print(Panel.fit(
                f"[bold blue]Testing SIP Connection[/bold blue]\n"
                f"Host: {host}\n"
                f"Port: {port}\n"
                f"Extension: {extension}\n"
                f"Duration: {duration}s",
                title="Test Configuration"
            ))
            
            # Start the SIP client
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Starting SIP client...", total=None)
                
                if not await sip_client.start():
                    console.print("[red]❌ Failed to start SIP client[/red]")
                    return
                
                progress.update(task, description="Registering with Asterisk...")
                
                # Wait for registration
                await asyncio.sleep(2)
                
                if sip_client.is_registered():
                    console.print("[green]✅ Successfully registered with Asterisk[/green]")
                    progress.update(task, description="Registration successful - monitoring...")
                else:
                    console.print("[red]❌ Failed to register with Asterisk[/red]")
                    return
                
                # Monitor for the specified duration
                for i in range(duration):
                    await asyncio.sleep(1)
                    remaining = duration - i - 1
                    progress.update(
                        task, 
                        description=f"Monitoring connection... ({remaining}s remaining)"
                    )
            
            console.print("[green]✅ SIP connection test completed successfully[/green]")
            
        except KeyboardInterrupt:
            console.print("\n[yellow]⚠️ Test interrupted by user[/yellow]")
        except Exception as e:
            console.print(f"[red]❌ Test failed: {e}[/red]")
        finally:
            # Stop the SIP client
            await sip_client.stop()
            console.print("[blue]SIP client stopped[/blue]")
    
    # Run the async test
    asyncio.run(run_test())


@app.command()
def make_call(
    destination: str = typer.Argument(..., help="Destination extension number"),
    host: str = typer.Option("voiprnd.nemtclouddispatch.com", help="SIP server host"),
    port: int = typer.Option(5060, help="SIP server port"),
    extension: str = typer.Option("3000", help="SIP extension number"),
    password: str = typer.Option("AIAgent2025", help="SIP extension password"),
    duration: int = typer.Option(10, help="Call duration in seconds")
):
    """Make a test call to the specified destination."""
    
    # Create SIP configuration
    config = SIPConfig(
        host=host,
        port=port,
        extension=extension,
        password=password
    )
    
    # Create SIP client
    sip_client = SIPClient(config)
    
    async def run_call():
        """Run the test call."""
        try:
            console.print(Panel.fit(
                f"[bold blue]Making Test Call[/bold blue]\n"
                f"From: {extension}\n"
                f"To: {destination}\n"
                f"Host: {host}\n"
                f"Duration: {duration}s",
                title="Call Configuration"
            ))
            
            # Start the SIP client
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Starting SIP client...", total=None)
                
                if not await sip_client.start():
                    console.print("[red]❌ Failed to start SIP client[/red]")
                    return
                
                progress.update(task, description="Registering with Asterisk...")
                await asyncio.sleep(2)
                
                if not sip_client.is_registered():
                    console.print("[red]❌ Failed to register with Asterisk[/red]")
                    return
                
                progress.update(task, description=f"Calling {destination}...")
                
                # Make the call
                call_id = await sip_client.make_call(destination)
                
                if call_id:
                    console.print(f"[green]✅ Call {call_id} established[/green]")
                    progress.update(task, description=f"Call active - {duration}s remaining...")
                    
                    # Wait for the specified duration
                    for i in range(duration):
                        await asyncio.sleep(1)
                        remaining = duration - i - 1
                        progress.update(
                            task,
                            description=f"Call active - {remaining}s remaining..."
                        )
                    
                    # End the call
                    progress.update(task, description="Ending call...")
                    await sip_client.end_call(call_id)
                    console.print("[green]✅ Call ended successfully[/green]")
                else:
                    console.print("[red]❌ Failed to establish call[/red]")
            
        except KeyboardInterrupt:
            console.print("\n[yellow]⚠️ Call interrupted by user[/yellow]")
        except Exception as e:
            console.print(f"[red]❌ Call failed: {e}[/red]")
        finally:
            # Stop the SIP client
            await sip_client.stop()
            console.print("[blue]SIP client stopped[/blue]")
    
    # Run the async call
    asyncio.run(run_call())


@app.command()
def show_status():
    """Show current SIP client status and configuration."""
    
    # Load configuration
    config_manager = ConfigManager()
    config = config_manager.get_config()
    
    # Create SIP configuration from loaded config
    sip_config = SIPConfig(
        host=config.sip.host,
        port=config.sip.port,
        extension=config.sip.extension,
        password=config.sip.password,
        codecs=config.sip.codecs,
        transport=config.sip.transport
    )
    
    # Display configuration
    table = Table(title="SIP Client Configuration")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Host", sip_config.host)
    table.add_row("Port", str(sip_config.port))
    table.add_row("Extension", sip_config.extension)
    table.add_row("Password", "*" * len(sip_config.password))
    table.add_row("Transport", sip_config.transport)
    table.add_row("Codecs", ", ".join(sip_config.codecs))
    table.add_row("Local IP", sip_config.local_ip)
    table.add_row("Local Port", str(sip_config.local_port))
    table.add_row("RTP Port Range", f"{sip_config.rtp_port_range[0]}-{sip_config.rtp_port_range[1]}")
    table.add_row("Registration Interval", f"{sip_config.registration_interval}s")
    table.add_row("Call Timeout", f"{sip_config.call_timeout}s")
    
    console.print(table)


@app.command()
def monitor_calls(
    host: str = typer.Option("voiprnd.nemtclouddispatch.com", help="SIP server host"),
    port: int = typer.Option(5060, help="SIP server port"),
    extension: str = typer.Option("3000", help="SIP extension number"),
    password: str = typer.Option("AIAgent2025", help="SIP extension password")
):
    """Monitor incoming calls and display call information."""
    
    # Create SIP configuration
    config = SIPConfig(
        host=host,
        port=port,
        extension=extension,
        password=password
    )
    
    # Create SIP client
    sip_client = SIPClient(config)
    
    async def run_monitor():
        """Run the call monitor."""
        try:
            console.print(Panel.fit(
                f"[bold blue]SIP Call Monitor[/bold blue]\n"
                f"Extension: {extension}\n"
                f"Host: {host}\n"
                f"Press Ctrl+C to stop",
                title="Monitor Configuration"
            ))
            
            # Add registration handler
            def on_registration_change(registered: bool):
                if registered:
                    console.print("[green]✅ Registered with Asterisk[/green]")
                else:
                    console.print("[red]❌ Unregistered from Asterisk[/red]")
            
            sip_client.add_registration_handler(on_registration_change)
            
            # Start the SIP client
            if not await sip_client.start():
                console.print("[red]❌ Failed to start SIP client[/red]")
                return
            
            console.print("[blue]Monitoring for incoming calls...[/blue]")
            
            # Monitor calls
            while True:
                calls = sip_client.get_all_calls()
                
                if calls:
                    table = Table(title="Active Calls")
                    table.add_column("Call ID", style="cyan")
                    table.add_column("From", style="green")
                    table.add_column("To", style="green")
                    table.add_column("State", style="yellow")
                    table.add_column("Codec", style="blue")
                    table.add_column("Duration", style="magenta")
                    
                    for call_id, call_info in calls.items():
                        duration = int(asyncio.get_event_loop().time() - call_info.start_time)
                        table.add_row(
                            call_id,
                            call_info.from_user,
                            call_info.to_user,
                            call_info.state,
                            call_info.codec,
                            f"{duration}s"
                        )
                    
                    console.clear()
                    console.print(table)
                else:
                    console.print("[dim]No active calls[/dim]")
                
                await asyncio.sleep(1)
            
        except KeyboardInterrupt:
            console.print("\n[yellow]⚠️ Monitor stopped by user[/yellow]")
        except Exception as e:
            console.print(f"[red]❌ Monitor failed: {e}[/red]")
        finally:
            # Stop the SIP client
            await sip_client.stop()
            console.print("[blue]SIP client stopped[/blue]")
    
    # Run the async monitor
    asyncio.run(run_monitor())


if __name__ == "__main__":
    app()


