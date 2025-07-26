"""Formatter for MCP tool calls and results."""
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, Union

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown
from rich.box import ROUNDED, SIMPLE

from ..config import ToolFormattingConfig


class ToolCallFormatter:
    """Formatter for MCP tool calls and results."""
    
    def __init__(self, console: Optional[Console] = None, config: Optional[ToolFormattingConfig] = None):
        """Initialize the formatter.
        
        Args:
            console: Optional Rich console instance. If not provided, a new one will be created.
            config: Optional tool formatting configuration. If not provided, default values will be used.
        """
        self.console = console or Console()
        self.config = config or ToolFormattingConfig()
    
    def _format_json(self, data: Any, indent: int = 2, max_depth: Optional[int] = None, 
                    truncate_length: Optional[int] = None) -> str:
        """Format data as JSON with pretty printing and optional truncation.
        
        Args:
            data: The data to format.
            indent: Number of spaces for indentation.
            max_depth: Maximum depth for nested objects.
            truncate_length: Maximum length for string values.
            
        Returns:
            Formatted JSON string.
        """
        # Use config values or defaults
        max_depth = max_depth if max_depth is not None else self.config.max_depth
        truncate_length = truncate_length if truncate_length is not None else self.config.truncate_length
        
        class CustomEncoder(json.JSONEncoder):
            def __init__(self, *args, **kwargs):
                self.current_depth = 0
                super().__init__(*args, **kwargs)
            
            def encode(self, obj):
                if isinstance(obj, (dict, list)) and self.current_depth >= max_depth:
                    if isinstance(obj, dict):
                        return f"{{... Object with {len(obj)} keys ...}}"
                    else:
                        return f"[... Array with {len(obj)} items ...]"
                return super().encode(obj)
            
            def default(self, obj):
                # Handle non-serializable objects
                return f"[{type(obj).__name__}]"
        
        try:
            if isinstance(data, (dict, list)):
                return json.dumps(data, indent=indent, cls=CustomEncoder)
            return str(data)
        except Exception:
            return str(data)
    
    def format_tool_call(self, server_name: str, tool_name: str, arguments: Dict[str, Any],
                        start_time: Optional[datetime] = None) -> Panel:
        """Format a tool call for display.
        
        Args:
            server_name: The name of the server.
            tool_name: The name of the tool.
            arguments: The arguments passed to the tool.
            start_time: Optional start time of the tool call.
            
        Returns:
            Rich Panel containing the formatted tool call.
        """
        # Use different box style based on config
        box_style = ROUNDED
        if self.config.compact:
            box_style = SIMPLE
            
        table = Table(box=box_style, show_header=False, show_edge=False, pad_edge=False)
        table.add_column("Key", style="bold cyan")
        table.add_column("Value", style="green")
        
        # Add server and tool info
        table.add_row("Server", server_name)
        table.add_row("Tool", tool_name)
        
        # Add timestamp
        if start_time:
            timestamp = start_time.strftime("%Y-%m-%d %H:%M:%S")
            table.add_row("Time", timestamp)
        
        # Add horizontal separator
        table.add_row("", "")
        
        # Add arguments header
        table.add_row("Parameters", "")
        
        # Format arguments
        if arguments:
            args_str = self._format_json(arguments)
            table.add_row("", Text(args_str))
        else:
            table.add_row("", "No parameters")
        
        # Apply color only if enabled in config
        border_style = "blue" if self.config.color else None
        
        return Panel(
            table,
            title="MCP Tool Call",
            border_style=border_style,
            expand=False
        )
    
    def format_tool_result(self, server_name: str, tool_name: str, result: Any,
                         start_time: Optional[datetime] = None, 
                         end_time: Optional[datetime] = None,
                         success: bool = True) -> Panel:
        """Format a tool result for display.
        
        Args:
            server_name: The name of the server.
            tool_name: The name of the tool.
            result: The result of the tool execution.
            start_time: Optional start time of the tool call.
            end_time: Optional end time of the tool call.
            success: Whether the tool execution was successful.
            
        Returns:
            Rich Panel containing the formatted tool result.
        """
        # Use different box style based on config
        box_style = ROUNDED
        if self.config.compact:
            box_style = SIMPLE
            
        table = Table(box=box_style, show_header=False, show_edge=False, pad_edge=False)
        table.add_column("Key", style="bold cyan")
        table.add_column("Value")
        
        # Add server and tool info
        table.add_row("Server", server_name)
        table.add_row("Tool", tool_name)
        
        # Add status with color if enabled
        status_text = "✓ Success" if success else "✗ Failed"
        if self.config.color:
            status_style = "green" if success else "red"
            table.add_row("Status", Text(status_text, style=status_style))
        else:
            table.add_row("Status", status_text)
        
        # Add duration if available
        if start_time and end_time:
            duration = (end_time - start_time).total_seconds()
            table.add_row("Duration", f"{duration:.2f}s")
        
        # Add horizontal separator
        table.add_row("", "")
        
        # Add result header
        table.add_row("Result", "")
        
        # Format result
        if result is not None:
            if isinstance(result, str):
                # Check if it looks like JSON
                if result.strip().startswith(("{", "[")):
                    try:
                        parsed = json.loads(result)
                        result_str = self._format_json(parsed)
                        table.add_row("", Text(result_str))
                    except json.JSONDecodeError:
                        # Not valid JSON, display as-is
                        table.add_row("", result)
                else:
                    # Plain text
                    table.add_row("", result)
            else:
                # Try to format as JSON
                result_str = self._format_json(result)
                table.add_row("", Text(result_str))
        else:
            table.add_row("", "No result")
        
        # Apply color only if enabled in config
        border_style = None
        if self.config.color:
            border_style = "green" if success else "red"
            
        return Panel(
            table,
            title="MCP Tool Result",
            border_style=border_style,
            expand=False
        )
    
    def print_tool_call(self, server_name: str, tool_name: str, arguments: Dict[str, Any],
                       start_time: Optional[datetime] = None) -> None:
        """Print a formatted tool call to the console.
        
        Args:
            server_name: The name of the server.
            tool_name: The name of the tool.
            arguments: The arguments passed to the tool.
            start_time: Optional start time of the tool call.
        """
        # Only print if formatting is enabled
        if not self.config.enabled:
            return
            
        panel = self.format_tool_call(server_name, tool_name, arguments, start_time)
        self.console.print(panel)
    
    def print_tool_result(self, server_name: str, tool_name: str, result: Any,
                        start_time: Optional[datetime] = None, 
                        end_time: Optional[datetime] = None,
                        success: bool = True) -> None:
        """Print a formatted tool result to the console.
        
        Args:
            server_name: The name of the server.
            tool_name: The name of the tool.
            result: The result of the tool execution.
            start_time: Optional start time of the tool call.
            end_time: Optional end time of the tool call.
            success: Whether the tool execution was successful.
        """
        # Only print if formatting is enabled
        if not self.config.enabled:
            return
            
        panel = self.format_tool_result(server_name, tool_name, result, 
                                      start_time, end_time, success)
        self.console.print(panel)


# Create a singleton instance for easy access - config will be loaded when used
default_formatter = ToolCallFormatter()

def update_formatter_config(config: ToolFormattingConfig) -> None:
    """Update the default formatter with new configuration.
    
    Args:
        config: The new tool formatting configuration.
    """
    default_formatter.config = config


def format_tool_call_markdown(server_name: str, tool_name: str, arguments: Dict[str, Any],
                            start_time: Optional[datetime] = None) -> str:
    """Format a tool call as Markdown text.
    
    Args:
        server_name: The name of the server.
        tool_name: The name of the tool.
        arguments: The arguments passed to the tool.
        start_time: Optional start time of the tool call.
        
    Returns:
        Markdown formatted string.
    """
    lines = []
    lines.append("### MCP Tool Call")
    lines.append(f"**Server:** {server_name}")
    lines.append(f"**Tool:** {tool_name}")
    
    if start_time:
        timestamp = start_time.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"**Time:** {timestamp}")
    
    lines.append("\n**Parameters:**")
    
    if arguments:
        args_str = json.dumps(arguments, indent=2)
        lines.append(f"```json\n{args_str}\n```")
    else:
        lines.append("*No parameters*")
    
    return "\n".join(lines)


def format_tool_result_markdown(server_name: str, tool_name: str, result: Any,
                              start_time: Optional[datetime] = None, 
                              end_time: Optional[datetime] = None,
                              success: bool = True) -> str:
    """Format a tool result as Markdown text.
    
    Args:
        server_name: The name of the server.
        tool_name: The name of the tool.
        result: The result of the tool execution.
        start_time: Optional start time of the tool call.
        end_time: Optional end time of the tool call.
        success: Whether the tool execution was successful.
        
    Returns:
        Markdown formatted string.
    """
    lines = []
    lines.append("### MCP Tool Result")
    lines.append(f"**Server:** {server_name}")
    lines.append(f"**Tool:** {tool_name}")
    
    status_text = "✓ Success" if success else "✗ Failed"
    lines.append(f"**Status:** {status_text}")
    
    if start_time and end_time:
        duration = (end_time - start_time).total_seconds()
        lines.append(f"**Duration:** {duration:.2f}s")
    
    lines.append("\n**Result:**")
    
    if result is not None:
        if isinstance(result, str):
            # Check if it looks like JSON
            if result.strip().startswith(("{", "[")):
                try:
                    parsed = json.loads(result)
                    result_str = json.dumps(parsed, indent=2)
                    lines.append(f"```json\n{result_str}\n```")
                except json.JSONDecodeError:
                    # Not valid JSON, display as-is
                    lines.append(result)
            else:
                # Plain text
                lines.append(result)
        else:
            # Try to format as JSON
            try:
                result_str = json.dumps(result, indent=2, default=str)
                lines.append(f"```json\n{result_str}\n```")
            except Exception:
                # Fallback to string representation
                lines.append(f"```\n{str(result)}\n```")
    else:
        lines.append("*No result*")
    
    return "\n".join(lines)
