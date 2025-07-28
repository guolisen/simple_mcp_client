"""Main entry point for the MCP client."""
import asyncio
import logging
import os
import platform
import sys
import time
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box
from rich.status import Status
from rich.spinner import Spinner

from simple_mcp_client.config import Configuration
from simple_mcp_client.console import ConsoleInterface
from simple_mcp_client.console.tool_formatter import update_formatter_config
from simple_mcp_client.mcp import ServerManager

# Version information
__version__ = "1.0.10"

def display_welcome_message(console: Console, config: Configuration) -> None:
    """Display a colorful welcome message with elaborate ASCII art banner and additional information.
    
    Args:
        console: The Rich console instance.
        config: The application configuration.
    """
    # Large elaborate ASCII art banner for MINI MCP CLIENT
    ascii_art = [
        "███╗   ███╗██╗███╗   ██╗██╗    ███╗   ███╗ ██████╗██████╗      ██████╗██╗     ██╗███████╗███╗   ██╗████████╗",
        "████╗ ████║██║████╗  ██║██║    ████╗ ████║██╔════╝██╔══██╗    ██╔════╝██║     ██║██╔════╝████╗  ██║╚══██╔══╝",
        "██╔████╔██║██║██╔██╗ ██║██║    ██╔████╔██║██║     ██████╔╝    ██║     ██║     ██║█████╗  ██╔██╗ ██║   ██║   ",
        "██║╚██╔╝██║██║██║╚██╗██║██║    ██║╚██╔╝██║██║     ██╔═══╝     ██║     ██║     ██║██╔══╝  ██║╚██╗██║   ██║   ",
        "██║ ╚═╝ ██║██║██║ ╚████║██║    ██║ ╚═╝ ██║╚██████╗██║         ╚██████╗███████╗██║███████╗██║ ╚████║   ██║   ",
        "╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝    ╚═╝     ╚═╝ ╚═════╝╚═╝          ╚═════╝╚══════╝╚═╝╚══════╝╚═╝  ╚═══╝   ╚═╝   "
    ]
    
    # Create enhanced text for the ASCII art with a professional color scheme
    gradient_art = []
    
    # Define a professional blue color scheme
    # Using different shades of blue for a cohesive, professional look
    blue_colors = [
        "#0A2647",  # Dark navy blue
        "#144272",  # Deep blue
        "#205295",  # Medium blue
        "#2C74B3",  # Standard blue
        "#5499C7",  # Light blue
        "#7FB3D5",  # Pale blue
    ]
    
    # Apply the blue color scheme to the ASCII art
    for i, line in enumerate(ascii_art):
        # Use modulo to cycle through the colors
        color_index = i % len(blue_colors)
        gradient_art.append(f"[{blue_colors[color_index]}]{line}[/]")
    
    # Get enhanced system information
    python_version = platform.python_version()
    system_name = platform.system()
    system_version = platform.version()
    processor = platform.processor() or "Unknown"
    architecture = platform.architecture()[0]
    current_time = time.ctime()
    
    # Get memory information if available
    memory_info = "N/A"
    try:
        import psutil
        memory = psutil.virtual_memory()
        memory_info = f"{memory.percent}% used ({memory.used // (1024**2)} MB / {memory.total // (1024**2)} MB)"
    except (ImportError, Exception):
        # If psutil is not available or fails, use a fallback
        memory_info = "Module 'psutil' not available"
    
    # Count servers with enhanced metrics
    total_servers = len(config.config.mcpServers)
    enabled_servers = sum(1 for server in config.config.mcpServers.values() if server.enable)
    connected_servers = 0  # This would need to be updated with actual connected count
    
    # Get LLM provider info if available
    llm_provider = config.config.llm.provider if hasattr(config.config, "llm") and hasattr(config.config.llm, "provider") else "Not configured"
    llm_model = config.config.llm.model if hasattr(config.config, "llm") and hasattr(config.config.llm, "model") else "Not configured"
    
    # Create the main layout table with improved structure
    main_table = Table(
        show_header=False,
        box=None,
        padding=(0, 1),
        expand=True
    )
    
    main_table.add_column(ratio=1)
    
    # Create header with enhanced logo
    header_table = Table(
        show_header=False,
        box=None,
        padding=(0, 0),
        expand=True
    )
    
    header_table.add_column(ratio=1)
    
    # Add ASCII art centered
    for line in gradient_art:
        header_table.add_row(line)
    
    # Add version with enhanced styling using the blue theme
    version_text = Text()
    version_text.append("⚡ ", style="bright_white")
    version_text.append("Mini Model Context Protocol Client", style="bold bright_blue")
    version_text.append(" - ", style="bright_white")
    version_text.append("Connecting AI to the World", style="italic bright_cyan")
    version_text.append(f" v{__version__}", style="bright_white bold")
    version_text.append(" ⚡", style="bright_white")
    
    header_table.add_row("")
    header_table.add_row(version_text)
    
    # Create enhanced system info section
    system_table = Table(
        title="System Information",
        title_style="bold cyan",
        box=box.ROUNDED,
        padding=(0, 2),
        expand=True
    )
    
    system_table.add_column("Attribute", style="bright_cyan", justify="right")
    system_table.add_column("Value", style="bright_white")
    
    system_table.add_row("OS", f"{system_name} {system_version}")
    system_table.add_row("Architecture", f"{architecture} ({processor})")
    system_table.add_row("Python", f"{python_version}")
    system_table.add_row("Memory", memory_info)
    system_table.add_row("Time", current_time)
    
    # Create enhanced server status section with improved bar chart
    server_table = Table(
        title="Server Status",
        title_style="bold cyan",
        box=box.ROUNDED,
        padding=(0, 1),
        expand=True
    )
    
    server_table.add_column("Type", style="bright_white")
    server_table.add_column("Count", style="bright_green")
    server_table.add_column("Chart", style="bright_blue")
    
    # Create enhanced bar charts using Unicode block characters
    if total_servers > 0:
        enabled_bar = "█" * enabled_servers + "▒" * (total_servers - enabled_servers)
        server_table.add_row("Enabled", str(enabled_servers), enabled_bar)
        server_table.add_row("Total", str(total_servers), "█" * total_servers)
        
        # Add server details if available
        for name, server in config.config.mcpServers.items():
            status = "✓ Enabled" if server.enable else "✗ Disabled"
            server_type = server.type if hasattr(server, "type") else "Unknown"
            server_table.add_row(name, status, f"Type: {server_type}")
    else:
        server_table.add_row("Servers", "0", "None configured")
    
    # Create LLM information section
    llm_table = Table(
        title="LLM Configuration",
        title_style="bold magenta",
        box=box.ROUNDED,
        padding=(0, 1),
        expand=True
    )
    
    llm_table.add_column("Setting", style="bright_yellow")
    llm_table.add_column("Value", style="bright_green")
    
    llm_table.add_row("Provider", llm_provider)
    llm_table.add_row("Model", llm_model)
    
    # Create enhanced tips section
    tips_table = Table(
        title="Quick Start Guide",
        title_style="bold magenta",
        box=box.ROUNDED,
        padding=(0, 1),
        expand=True
    )
    
    tips_table.add_column("", style="bright_yellow", width=3)
    tips_table.add_column("Command", style="bright_cyan", width=15)
    tips_table.add_column("Description", style="bright_green")
    
    tips_table.add_row("1", "help", "View available commands")
    tips_table.add_row("2", "connect <server>", "Connect to an MCP server")
    tips_table.add_row("3", "servers", "List all configured servers")
    tips_table.add_row("4", "tools", "View available tools from connected servers")
    tips_table.add_row("5", "chat", "Start an interactive chat with LLM")
    tips_table.add_row("6", "resources", "List available resources")
    
    # Assemble all sections into the main table with improved layout
    main_table.add_row(Panel(header_table, box=box.ROUNDED, border_style="blue", padding=(1, 2)))
    
    # Create a row with two columns for system info and LLM info
    system_row = Table.grid(expand=True)
    system_row.add_column(ratio=3)
    system_row.add_column(ratio=2)
    system_row.add_row(system_table, llm_table)
    main_table.add_row(system_row)
    
    # Create a row with two columns for server status and tips
    info_columns = Table.grid(expand=True)
    info_columns.add_column(ratio=1)
    info_columns.add_column(ratio=1)
    info_columns.add_row(server_table, tips_table)
    main_table.add_row(info_columns)
    
    # Create enhanced footer with network stats
    footer_text = Text()
    footer_text.append("✨ ", style="bright_white")
    footer_text.append("Mini Model Context Protocol Client", style="bright_white bold")
    footer_text.append(" | ", style="dim")
    footer_text.append("Connecting AI to the World", style="italic bright_cyan")
    footer_text.append(" ✨", style="bright_white")
    
    # Create panel with the main table and enhanced styling
    panel = Panel(
        main_table,
        title="[bold white on #205295] Welcome to Mini MCP Client Network Hub [/]",
        subtitle=footer_text,
        border_style="#2C74B3",
        box=box.HEAVY,
        padding=(1, 2),
        expand=True
    )
    
    # Clear the screen for a cleaner display
    console.clear()
    
    # Print the welcome panel
    console.print(panel)

#os.environ['LANGCHAIN_TRACING_V2'] = "true"
#os.environ['LANGCHAIN_ENDPOINT'] = "https://api.smith.langchain.com"
#os.environ['LANGCHAIN_API_KEY'] = "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"
#os.environ['LANGCHAIN_PROJECT'] = "pr-silver-bank-1"

def setup_logging(config: Configuration) -> None:
    """Set up logging configuration."""
    from logging.handlers import RotatingFileHandler
    
    # Get log path from config or use default
    log_path = None
    if hasattr(config.config, "logging") and config.config.logging.log_path:
        log_path = config.config.logging.log_path
    
    # If no log path specified, use default in the same directory as config file
    if not log_path:
        # Get config directory
        config_dir = os.path.dirname(config.config_path)
        # Create logs directory in the same directory as config file
        log_dir = os.path.join(config_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "mcp_client.log")
    else:
        # If log path is a directory, append default filename
        if os.path.isdir(log_path) or not os.path.splitext(log_path)[1]:
            os.makedirs(log_path, exist_ok=True)
            log_path = os.path.join(log_path, "mcp_client.log")
        else:
            # Ensure directory exists for the log file
            log_dir = os.path.dirname(log_path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
    
    log_level = os.environ.get("MCP_LOG_LEVEL", "INFO").upper()
    log_format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    
    # Configure logging with a file handler instead of stream handler
    logging.basicConfig(
        level=getattr(logging, log_level),
        format=log_format,
        handlers=[
            # Use RotatingFileHandler to prevent log files from growing too large
            RotatingFileHandler(
                log_path,
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            ),
        ]
    )
    
    # Log startup information
    logging.info("Logging configured to write to %s", log_path)


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


async def display_server_connection_message(
    console: Console, 
    server_manager: ServerManager, 
    server_name: str
) -> bool:
    """Display a nicely formatted server connection message and attempt connection.
    
    Args:
        console: The Rich console instance.
        server_manager: The server manager.
        server_name: The name of the server to connect to.
        
    Returns:
        True if the connection was successful, False otherwise.
    """
    # Get server configuration
    server = server_manager.get_server(server_name)
    if not server:
        console.print(f"[red]Error: Server '{server_name}' not found[/red]")
        return False
    
    # Get server config details
    server_type = server.config.type
    server_url = server.config.url or "N/A"
    server_command = server.config.command or "N/A"
    
    # Get console width for proper sizing
    console_width = console.width or 100
    
    # Create a table for server info
    table = Table(
        box=box.ROUNDED,
        show_header=False,
        show_edge=False,
        pad_edge=False,
        width=console_width - 4  # Account for panel borders
    )
    
    # Add columns
    table.add_column("Key", style="bold cyan", width=15, justify="right")
    table.add_column("Value", style="bright_white", ratio=3)
    
    # Add server info
    table.add_row(
        Text("Server", style="bold cyan"),
        Text(server_name, style="bright_blue bold")
    )
    table.add_row(
        Text("Type", style="bold cyan"),
        Text(server_type, style="bright_white")
    )
    
    # Add URL or command based on server type
    if server_type.lower() == "sse":
        table.add_row(
            Text("URL", style="bold cyan"),
            Text(server_url, style="bright_white")
        )
    else:
        table.add_row(
            Text("Command", style="bold cyan"),
            Text(server_command, style="bright_white")
        )
    
    # Create the initial panel
    panel = Panel(
        table,
        title="[bold white on #205295] MCP Server Connection [/]",
        border_style="#2C74B3",
        box=box.HEAVY,
        padding=(0, 1),
        expand=True
    )
    
    # Display the panel
    console.print(panel)
    
    # Record start time
    start_time = datetime.now()
    
    # Create a status for the connection process
    with console.status(
        f"[bold bright_blue]Connecting to {server_name}...[/]", 
        spinner="dots", 
        spinner_style="bright_blue"
    ) as status:
        # Attempt to connect
        success = await server_manager.connect_server(server_name)
    
    # Record end time
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Create result table
    result_table = Table(
        box=box.ROUNDED,
        show_header=False,
        show_edge=False,
        pad_edge=False,
        width=console_width - 4  # Account for panel borders
    )
    
    # Add columns
    result_table.add_column("Key", style="bold cyan", width=15, justify="right")
    result_table.add_column("Value", style="bright_white", ratio=3)
    
    # Add server info
    result_table.add_row(
        Text("Server", style="bold cyan"),
        Text(server_name, style="bright_blue bold")
    )
    
    # Add status with appropriate icon and color
    status_icon = "✓ " if success else "✗ "
    status_text = f"{status_icon}Connected" if success else f"{status_icon}Failed"
    status_style = "green bold" if success else "red bold"
    
    result_table.add_row(
        Text("Status", style="bold cyan"),
        Text(status_text, style=status_style)
    )
    
    # Add duration
    duration_style = "green"
    if duration > 1.0:
        duration_style = "yellow"
    if duration > 3.0:
        duration_style = "red"
    
    result_table.add_row(
        Text("Duration", style="bold cyan"),
        Text(f"{duration:.2f}s", style=f"{duration_style} bold")
    )
    
    # Add server details if connection was successful
    if success:
        server_obj = server_manager.get_server(server_name)
        if server_obj and server_obj.server_info:
            info = server_obj.server_info
            if hasattr(info, "name") and hasattr(info, "version"):
                result_table.add_row(
                    Text("Server Info", style="bold cyan"),
                    Text(f"{info.name} v{info.version}", style="bright_white")
                )
        
        # Add tool count
        tools_count = len(server.tools) if server.tools else 0
        result_table.add_row(
            Text("Available Tools", style="bold cyan"),
            Text(str(tools_count), style="bright_white")
        )
    
    # Create the result panel with appropriate styling
    title_style = "bold white on green" if success else "bold white on red"
    border_style = "green" if success else "red"
    
    result_panel = Panel(
        result_table,
        title=f"[{title_style}] MCP Server Connection Result [/]",
        border_style=border_style,
        box=box.HEAVY,
        padding=(0, 1),
        expand=True
    )
    
    # Display the result panel
    console.print(result_panel)
    
    return success

async def run_client() -> None:
    """Run the MCP client."""
    console = Console()
    
    try:
        # Load configuration (already loaded in main())
        config = Configuration()
        
        # Initialize tool formatter with configuration
        if hasattr(config.config, "console") and hasattr(config.config.console, "tool_formatting"):
            update_formatter_config(config.config.console.tool_formatting)
            logging.info("Tool formatter configured from settings")
        
        # Create server manager
        server_manager = ServerManager(config)
        
        # Create console interface
        interface = ConsoleInterface(config, server_manager)
        
        # Display colorful welcome message with ASCII art
        display_welcome_message(console, config)
        
        # Connect to all enabled servers with enhanced formatting
        for server_name, server_config in config.config.mcpServers.items():
            if server_config.enable:
                await display_server_connection_message(console, server_manager, server_name)
        
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
    # Load configuration
    config = Configuration()
    
    # Setup logging with configuration
    setup_logging(config)
    
    asyncio.run(run_client())


if __name__ == "__main__":
    main()
