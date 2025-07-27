"""Formatter for MCP tool calls and results."""
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, Union, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown
from rich.box import ROUNDED, SIMPLE, HORIZONTALS
from rich.style import Style
from rich.color import Color
from rich import box

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
    
    def _get_color_for_type(self, value: Any) -> str:
        """Get color based on value type.
        
        Args:
            value: The value to determine color for.
            
        Returns:
            Color string for the value type.
        """
        # Return plain style if syntax highlighting is disabled
        if not self.config.syntax_highlighting:
            return "white"
            
        # Apply color scheme based on configuration
        scheme = self.config.color_scheme.lower()
        
        if scheme == "monochrome":
            return "white"
            
        if scheme == "dark":
            if isinstance(value, bool):
                return "bright_yellow" if value else "bright_red"
            elif isinstance(value, (int, float)):
                return "bright_cyan"
            elif isinstance(value, str):
                if value.startswith(("http://", "https://", "ftp://")):
                    return "bright_blue underline"
                return "bright_green"
            elif value is None:
                return "dim italic"
            elif isinstance(value, (list, tuple)):
                return "bright_magenta"
            elif isinstance(value, dict):
                return "bright_blue"
            return "white"
            
        if scheme == "light":
            if isinstance(value, bool):
                return "yellow3" if value else "red3"
            elif isinstance(value, (int, float)):
                return "blue"
            elif isinstance(value, str):
                if value.startswith(("http://", "https://", "ftp://")):
                    return "blue underline"
                return "green4"
            elif value is None:
                return "grey58 italic"
            elif isinstance(value, (list, tuple)):
                return "purple3"
            elif isinstance(value, dict):
                return "blue"
            return "black"
            
        # Default scheme
        if isinstance(value, bool):
            return "yellow" if value else "red"
        elif isinstance(value, (int, float)):
            return "cyan"
        elif isinstance(value, str):
            if value.startswith(("http://", "https://", "ftp://")):
                return "blue underline"
            return "green"
        elif value is None:
            return "dim italic"
        elif isinstance(value, (list, tuple)):
            return "magenta"
        elif isinstance(value, dict):
            return "bright_blue"
        return "white"
    
    def _get_status_icon(self, success: bool) -> str:
        """Get status icon based on success state.
        
        Args:
            success: Whether the operation was successful.
            
        Returns:
            Icon string.
        """
        if not self.config.show_icons:
            return ""
            
        return "✓ " if success else "✗ "
    
    def _format_json(self, data: Any, indent: int = 2, max_depth: Optional[int] = None, 
                    truncate_length: Optional[Union[int, str]] = None) -> Text:
        """Format data as JSON with pretty printing and optional truncation.
        
        Args:
            data: The data to format.
            indent: Number of spaces for indentation.
            max_depth: Maximum depth for nested objects.
            truncate_length: Maximum length for string values or "all" for no truncation.
            
        Returns:
            Formatted JSON string.
        """
        # Use config values or defaults
        max_depth = max_depth if max_depth is not None else self.config.max_depth
        truncate_length = truncate_length if truncate_length is not None else self.config.truncate_length
        
        # Check if truncate_length is "all" - meaning no truncation
        should_truncate = truncate_length != "all" if isinstance(truncate_length, str) else True
        
        # Use truncate_length as an integer only if we should truncate
        int_truncate_length = int(truncate_length) if should_truncate and not isinstance(truncate_length, str) else None
        
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
                # Convert to JSON string
                json_str = json.dumps(data, indent=indent, ensure_ascii=False, cls=CustomEncoder)
                
                # Truncate the entire JSON string if needed
                if should_truncate and int_truncate_length and len(json_str) > int_truncate_length:
                    json_str = json_str[:int_truncate_length] + "...\n[Output truncated. Set truncate_length: \"all\" to see complete output]"
                
                # Create rich Text object with syntax highlighting
                result = Text()
                
                # Apply syntax highlighting only if enabled
                if self.config.syntax_highlighting:
                    # Simple syntax highlighting for JSON
                    in_string = False
                    in_key = False
                    buffer = ""
                    
                    for char in json_str:
                        if char == '"':
                            if in_string:
                                # End of string
                                if in_key:
                                    result.append(buffer, style="bold cyan")
                                    in_key = False
                                else:
                                    color = self._get_color_for_type(buffer)
                                    result.append(buffer, style=color)
                                buffer = '"'
                                in_string = False
                            else:
                                # Start of string
                                if buffer and buffer[-1] == ':':
                                    in_key = False
                                elif not in_key and not buffer.strip():
                                    in_key = True
                                result.append(buffer)
                                buffer = '"'
                                in_string = True
                        elif in_string:
                            buffer += char
                        else:
                            if char in "{}[],:":
                                result.append(buffer)
                                result.append(char, style="bold white")
                                buffer = ""
                            elif char in "0123456789":
                                buffer += char
                                if not any(c.isalpha() for c in buffer):
                                    result.append(buffer, style="cyan")
                                    buffer = ""
                            elif char.isspace():
                                result.append(buffer)
                                result.append(char)
                                buffer = ""
                            else:
                                buffer += char
                    
                    # Add any remaining buffer
                    if buffer:
                        result.append(buffer)
                else:
                    # No syntax highlighting, just add the plain text
                    result.append(json_str)
                
                return result
            
            # For non-dict/list values, return as text with appropriate color
            text_value = str(data)
            return Text(text_value, style=self._get_color_for_type(data))
        except Exception:
            # Fallback to plain string
            return Text(str(data))
    
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
        # Get console width for proper sizing
        console_width = self.console.width or 100
        
        # Use different box style based on config
        box_style = box.ROUNDED
        if self.config.compact:
            box_style = box.SIMPLE
            
        # Create a table with proper width settings
        table = Table(
            box=box_style, 
            show_header=False, 
            show_edge=False, 
            pad_edge=False,
            width=console_width - 4  # Account for panel borders
        )
        
        # Add columns with better proportions
        table.add_column("Key", style="bold cyan", width=15, justify="right")
        table.add_column("Value", style="white", ratio=3)
        
        # Add server and tool info with enhanced styling
        table.add_row(
            Text("Server", style="bold cyan"), 
            Text(server_name, style="bright_green bold")
        )
        table.add_row(
            Text("Tool", style="bold cyan"), 
            Text(tool_name, style="bright_yellow bold")
        )
        
        # Add timestamp with nice formatting
        if start_time:
            timestamp = start_time.strftime("%Y-%m-%d %H:%M:%S")
            table.add_row(
                Text("Time", style="bold cyan"),
                Text(timestamp, style="bright_blue")
            )
        
        # Add horizontal separator with distinct styling
        separator = Text("─" * (console_width - 8), style="dim")
        table.add_row("", separator)
        
        # Add arguments header with enhanced styling
        table.add_row(
            Text("Parameters", style="bold magenta underline"),
            ""
        )
        
        # Format arguments with syntax highlighting
        if arguments:
            args_formatted = self._format_json(arguments)
            table.add_row("", args_formatted)
        else:
            table.add_row("", Text("No parameters", style="dim italic"))
        
        # Apply enhanced border styling
        title_style = "bold white on blue"
        border_style = "blue" if self.config.color else None
        
        # Create panel with full width
        return Panel(
            table,
            title=Text("MCP Tool Call", style=title_style),
            border_style=border_style,
            expand=True,  # Make panel expand to full width
            padding=(0, 1)
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
        # Get console width for proper sizing
        console_width = self.console.width or 100
        
        # Use different box style based on config
        box_style = box.ROUNDED
        if self.config.compact:
            box_style = box.SIMPLE
            
        # Create a table with proper width settings
        table = Table(
            box=box_style, 
            show_header=False, 
            show_edge=False, 
            pad_edge=False,
            width=console_width - 4  # Account for panel borders
        )
        
        # Add columns with better proportions
        table.add_column("Key", style="bold cyan", width=15, justify="right")
        table.add_column("Value", style="white", ratio=3)
        
        # Add server and tool info with enhanced styling
        table.add_row(
            Text("Server", style="bold cyan"), 
            Text(server_name, style="bright_green bold")
        )
        table.add_row(
            Text("Tool", style="bold cyan"), 
            Text(tool_name, style="bright_yellow bold")
        )
        
        # Add status with enhanced styling
        status_icon = self._get_status_icon(success)
        status_text = f"{status_icon}Success" if success else f"{status_icon}Failed"
        status_style = "green bold" if success else "red bold"
        
        if self.config.color:
            table.add_row(
                Text("Status", style="bold cyan"),
                Text(status_text, style=status_style)
            )
        else:
            table.add_row("Status", status_text.replace("✓ ", "").replace("✗ ", ""))
        
        # Add duration if available with enhanced styling
        if start_time and end_time:
            duration = (end_time - start_time).total_seconds()
            duration_text = f"{duration:.2f}s"
            # Color based on duration - green for fast, yellow for medium, red for slow
            duration_style = "green"
            if duration > 1.0:
                duration_style = "yellow"
            if duration > 3.0:
                duration_style = "red"
                
            table.add_row(
                Text("Duration", style="bold cyan"),
                Text(duration_text, style=f"{duration_style} bold")
            )
        
        # Add horizontal separator with distinct styling
        separator = Text("─" * (console_width - 8), style="dim")
        table.add_row("", separator)
        
        # Add result header with enhanced styling
        table.add_row(
            Text("Result", style="bold magenta underline"),
            ""
        )
        
        # Format result with syntax highlighting
        if result is not None:
            if isinstance(result, str):
                # Check if it looks like JSON
                if result.strip().startswith(("{", "[")):
                    try:
                        parsed = json.loads(result)
                        result_formatted = self._format_json(parsed)
                        table.add_row("", result_formatted)
                    except json.JSONDecodeError:
                        # Not valid JSON, display as-is with appropriate styling
                        table.add_row("", Text(result, style="green"))
                else:
                    # Plain text with styling
                    table.add_row("", Text(result, style="green"))
            else:
                # Try to format as JSON with syntax highlighting
                result_formatted = self._format_json(result)
                table.add_row("", result_formatted)
        else:
            table.add_row("", Text("No result", style="dim italic"))
        
        # Apply enhanced border styling
        title_style = "bold white on " + ("green" if success else "red")
        border_style = "green" if success and self.config.color else "red" if self.config.color else None
            
        # Create panel with full width
        return Panel(
            table,
            title=Text("MCP Tool Result", style=title_style),
            border_style=border_style,
            expand=True,  # Make panel expand to full width
            padding=(0, 1)
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
        args_str = json.dumps(arguments, indent=2, ensure_ascii=False)
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
                    result_str = json.dumps(parsed, indent=2, ensure_ascii=False)
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
                result_str = json.dumps(result, indent=2, ensure_ascii=False, default=str)
                lines.append(f"```json\n{result_str}\n```")
            except Exception:
                # Fallback to string representation
                lines.append(f"```\n{str(result)}\n```")
    else:
        lines.append("*No result*")
    
    return "\n".join(lines)
