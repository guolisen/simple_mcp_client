"""Main entry point for the MCP client."""
import asyncio
import logging
import os
import sys
from typing import Dict, Any, Optional

from prompt_toolkit.formatted_text import HTML
from rich.console import Console

from simple_mcp_client.config import Configuration
from simple_mcp_client.console import ConsoleInterface
from simple_mcp_client.console.tool_formatter import update_formatter_config
from simple_mcp_client.mcp import ServerManager

#os.environ['LANGCHAIN_TRACING_V2'] = "true"
#os.environ['LANGCHAIN_ENDPOINT'] = "https://api.smith.langchain.com"
#os.environ['LANGCHAIN_API_KEY'] = "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"
#os.environ['LANGCHAIN_PROJECT'] = "pr-silver-bank-1"

def setup_logging() -> None:
    """Set up logging configuration."""
    from logging.handlers import RotatingFileHandler
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, "mcp_client.log")
    log_level = os.environ.get("MCP_LOG_LEVEL", "INFO").upper()
    log_format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    
    # Configure logging with a file handler instead of stream handler
    logging.basicConfig(
        level=getattr(logging, log_level),
        format=log_format,
        handlers=[
            # Use RotatingFileHandler to prevent log files from growing too large
            RotatingFileHandler(
                log_file,
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            ),
        ]
    )
    
    # Log startup information
    logging.info("Logging configured to write to %s", log_file)


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
        
        # Initialize tool formatter with configuration
        if hasattr(config.config, "console") and hasattr(config.config.console, "tool_formatting"):
            update_formatter_config(config.config.console.tool_formatting)
            logging.info("Tool formatter configured from settings")
        
        # Create server manager
        server_manager = ServerManager(config)
        
        # Create console interface
        interface = ConsoleInterface(config, server_manager)
        
        # Display welcome message
        console.print(
            "\n[bold green]Welcome to MCP Client[/bold green]\n"
            "Type [bold cyan]help[/bold cyan] to see available commands\n"
        )
        
        # Connect to all enabled servers
        for server_name, server_config in config.config.mcpServers.items():
            if server_config.enable:
                console.print(f"Connecting to enabled server: {server_name}...")
                await server_manager.connect_server(server_name)
        
        # Main command loop
        while True:
            try:
                # Get user input
                user_input = await interface.session.prompt_async(
                    #HTML("<ansicyan><b>MCP></b></ansicyan> "),
                    "MCP> ",
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
