"""Main entry point for the MCP client."""
import asyncio
import logging
import os
import sys
from typing import Dict, Any, Optional

from prompt_toolkit.formatted_text import HTML
from rich.console import Console

from .config import Configuration
from .console import ConsoleInterface
from .mcp import ServerManager


def setup_logging() -> None:
    """Set up logging configuration."""
    log_level = os.environ.get("MCP_LOG_LEVEL", "INFO").upper()
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stderr),
        ]
    )


async def handle_command(
    interface: ConsoleInterface,
    cmd: str,
    args: str
) -> None:
    """Handle a command from the user.
    
    Args:
        interface: The console interface.
        cmd: The command to handle.
        args: The command arguments.
    """
    cmd = cmd.lower()
    
    if cmd not in interface.commands:
        print(f"Unknown command: {cmd}")
        print("Type 'help' to see available commands")
        return
    
    try:
        handler = interface.commands[cmd]["handler"]
        await handler(args)
    except Exception as e:
        logging.error(f"Error executing command {cmd}: {e}")
        interface.console.print(f"[red]Error executing command: {str(e)}[/red]")


async def run_client() -> None:
    """Run the MCP client."""
    console = Console()
    
    try:
        # Load configuration
        config = Configuration()
        
        # Create server manager
        server_manager = ServerManager(config)
        
        # Create console interface
        interface = ConsoleInterface(config, server_manager)
        
        # Display welcome message
        console.print(
            "\n[bold green]Welcome to MCP Client[/bold green]\n"
            "Type [bold cyan]help[/bold cyan] to see available commands\n"
        )
        
        # If there's a default server, try to connect
        default_server = config.config.default_server
        if default_server:
            console.print(f"Connecting to default server: {default_server}...")
            await server_manager.connect_server(default_server)
        
        # Main command loop
        while True:
            try:
                # Get user input
                user_input = await interface.session.prompt_async(
                    HTML("<ansicyan><b>MCP></b></ansicyan> "),
                    style=interface.style
                )
                
                user_input = user_input.strip()
                if not user_input:
                    continue
                
                # Parse command and arguments
                parts = user_input.split(" ", 1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                
                # Handle command
                await handle_command(interface, cmd, args)
                
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Exiting...[/yellow]")
                break
    
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        console.print(f"[red]Unexpected error: {str(e)}[/red]")
    
    finally:
        # Clean up
        try:
            if 'server_manager' in locals():
                await server_manager.disconnect_all()
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")


def main() -> None:
    """Main entry point for the client."""
    setup_logging()
    asyncio.run(run_client())


if __name__ == "__main__":
    main()
