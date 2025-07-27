"""Interactive console interface for MCP client."""
import asyncio
import json
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional, Callable, Awaitable, Tuple, Union

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from ..config import Configuration
from ..llm import LLMProvider, LLMProviderFactory
from ..mcp import ServerManager, Tool
from ..prompt.system import generate_system_prompt, generate_tool_format


class CommandCompleter(Completer):
    """Command completer for prompt-toolkit."""

    def __init__(self, commands: Dict[str, Dict[str, Any]]) -> None:
        """Initialize the command completer.
        
        Args:
            commands: Dictionary of commands and their metadata.
        """
        self.commands = commands
        self.command_completer = WordCompleter(
            list(commands.keys()),
            ignore_case=True,
            match_middle=False
        )
    
    def get_completions(self, document, complete_event):
        """Get completions for the current document."""
        text = document.text
        if " " not in text:
            # No space yet, complete commands
            yield from self.command_completer.get_completions(document, complete_event)
            return
        
        # Command with space, try to complete subcommands or parameters
        cmd, args = text.split(" ", 1)
        cmd = cmd.lower()
        
        if cmd not in self.commands:
            return
        
        cmd_info = self.commands[cmd]
        
        # Command with subcommands
        if "subcommands" in cmd_info:
            subcommands = cmd_info["subcommands"]
            word_completer = WordCompleter(
                subcommands,
                ignore_case=True,
                match_middle=False
            )
            
            # Create a new document with just the args part for completion
            from prompt_toolkit.document import Document
            sub_document = Document(args, len(args))
            yield from word_completer.get_completions(sub_document, complete_event)
        
        # Command with argument completion function
        if "arg_completer" in cmd_info and callable(cmd_info["arg_completer"]):
            arg_completer = cmd_info["arg_completer"]
            from prompt_toolkit.document import Document
            sub_document = Document(args, len(args))
            yield from arg_completer(sub_document, complete_event)


class ConsoleInterface:
    """Interactive console interface for MCP client."""
    
    def _serialize_complex_object(self, obj: Any) -> str:
        """Safely serialize a potentially complex object to a string.
        
        Args:
            obj: The object to serialize.
            
        Returns:
            A string representation of the object.
        """
        # Custom JSON encoder to handle datetime objects
        class DateTimeEncoder(json.JSONEncoder):
            def default(self, obj):
                # Handle datetime objects by converting to ISO format string
                import datetime
                if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
                    return obj.isoformat()
                # Handle sets by converting to lists
                if isinstance(obj, set):
                    return list(obj)
                # Let the base class handle anything else
                return super().default(obj)
        
        try:
            # Try direct JSON serialization with our custom encoder
            return json.dumps(obj, indent=2, cls=DateTimeEncoder)
        except TypeError:
            # Handle objects with __dict__
            if hasattr(obj, "__dict__"):
                try:
                    obj_dict = {k: v for k, v in obj.__dict__.items() 
                               if not k.startswith('_') and not callable(v)}
                    return json.dumps(obj_dict, indent=2, cls=DateTimeEncoder)
                except Exception as e:
                    logging.debug(f"Failed to serialize object dict: {e}")
            
            # Handle objects with special content structure (like CallToolResult)
            if hasattr(obj, "content") and isinstance(obj.content, list):
                content_text = ""
                for item in obj.content:
                    if hasattr(item, "text") and item.text:
                        content_text += item.text + "\n"
                    elif hasattr(item, "__dict__"):
                        try:
                            content_text += json.dumps(item.__dict__, indent=2, cls=DateTimeEncoder) + "\n"
                        except Exception:
                            content_text += f"[Object of type {type(item).__name__}]\n"
                    else:
                        content_text += str(item) + "\n"
                return content_text
            
            # If we still have issues, convert to string and mention the type
            return f"[{type(obj).__name__}]: {str(obj)}"

    def __init__(self, config: Configuration, server_manager: ServerManager) -> None:
        """Initialize the console interface.
        
        Args:
            config: The client configuration.
            server_manager: The server manager.
        """
        self.config = config
        self.server_manager = server_manager
        self.llm_provider: Optional[LLMProvider] = None
        self.console = Console()
        
        # Command registry
        self.commands: Dict[str, Dict[str, Any]] = {
            "help": {
                "description": "Show help message",
                "handler": self._cmd_help,
            },
            "connect": {
                "description": "Connect to an MCP server",
                "handler": self._cmd_connect,
                "arg_completer": self._complete_server_names,
            },
            "disconnect": {
                "description": "Disconnect from an MCP server",
                "handler": self._cmd_disconnect,
                "arg_completer": self._complete_connected_server_names,
            },
            "servers": {
                "description": "List available MCP servers",
                "handler": self._cmd_servers,
            },
            "tools": {
                "description": "List available tools",
                "handler": self._cmd_tools,
                "arg_completer": self._complete_connected_server_names,
            },
            "resources": {
                "description": "List available resources",
                "handler": self._cmd_resources,
                "arg_completer": self._complete_connected_server_names,
            },
            "prompts": {
                "description": "List available prompts",
                "handler": self._cmd_prompts,
                "arg_completer": self._complete_connected_server_names,
            },
            "formats": {
                "description": "List available prompt formats",
                "handler": self._cmd_formats,
                "arg_completer": self._complete_connected_server_names,
            },
            "execute": {
                "description": "Execute a tool or get help for a tool",
                "handler": self._cmd_execute,
                "subcommands": ["help"],
            },
            "get-resource": {
                "description": "Get a resource from an MCP server",
                "handler": self._cmd_get_resource,
            },
            "get-prompt": {
                "description": "Get a prompt from an MCP server",
                "handler": self._cmd_get_prompt,
            },
            "chat": {
                "description": "Start a chat session with LLM and MCP tools",
                "handler": self._cmd_chat,
            },
            "config": {
                "description": "Show or modify configuration",
                "handler": self._cmd_config,
                "subcommands": ["show", "llm"],
            },
            "reload": {
                "description": "Reload configuration from file",
                "handler": self._cmd_reload,
            },
            "exit": {
                "description": "Exit the program",
                "handler": self._cmd_exit,
            },
        }
        
        # Set up prompt session
        self.history = FileHistory(os.path.expanduser("~/.mcp_client_history"))
        self.completer = CommandCompleter(self.commands)
        
        self.style = Style.from_dict({
            "prompt": "ansicyan bold",
            "command": "ansigreen",
            "error": "ansired bold",
        })
        
        self.session = PromptSession(
            history=self.history,
            completer=self.completer,
            style=self.style,
            complete_while_typing=True,
        )
        
        # Initialize LLM provider based on config
        self._initialize_llm_provider()
    
    def _initialize_llm_provider(self) -> None:
        """Initialize the LLM provider based on the current configuration."""
        llm_config = self.config.config.llm
        try:
            self.llm_provider = LLMProviderFactory.create(
                llm_config.provider,
                llm_config.model,
                llm_config.api_url,
                llm_config.api_key,
                **llm_config.other_params
            )
            logging.info(f"Initialized LLM provider: {self.llm_provider.name}")
        except Exception as e:
            logging.error(f"Error initializing LLM provider: {e}")
            self.llm_provider = None
    
    def _complete_server_names(self, document, complete_event):
        """Complete server names for prompt-toolkit."""
        word = document.get_word_before_cursor()
        for name in self.server_manager.servers.keys():
            if name.startswith(word):
                yield Completion(name, -len(word))
    
    def _complete_connected_server_names(self, document, complete_event):
        """Complete names of connected servers for prompt-toolkit."""
        word = document.get_word_before_cursor()
        for server in self.server_manager.get_connected_servers():
            if server.name.startswith(word):
                yield Completion(server.name, -len(word))
    
    async def _cmd_help(self, args: str) -> None:
        """Handle the help command.
        
        Args:
            args: Command parameters.
        """
        table = Table(title="Available Commands")
        table.add_column("Command", style="cyan")
        table.add_column("Description", style="green")
        
        for name, cmd in sorted(self.commands.items()):
            table.add_row(name, cmd["description"])
        
        self.console.print(table)
    
    async def _cmd_connect(self, args: str) -> None:
        """Handle the connect command.
        
        Args:
            args: Command parameters.
        """
        args = args.strip()
        if not args:
            self.console.print("[red]Error: Missing server name[/red]")
            return
        
        server_name = args
        if server_name not in self.server_manager.servers:
            self.console.print(f"[red]Error: Server '{server_name}' not found[/red]")
            return
        
        # Import the display_server_connection_message function from main module
        from ..main import display_server_connection_message
        
        # Use the enhanced connection message display
        await display_server_connection_message(self.console, self.server_manager, server_name)
    
    async def _cmd_disconnect(self, args: str) -> None:
        """Handle the disconnect command.
        
        Args:
            args: Command parameters.
        """
        args = args.strip()
        if not args:
            self.console.print("[red]Error: Missing server name[/red]")
            return
        
        server_name = args
        if server_name not in self.server_manager.servers:
            self.console.print(f"[red]Error: Server '{server_name}' not found[/red]")
            return
        
        server = self.server_manager.get_server(server_name)
        if not server or not server.is_connected:
            self.console.print(f"[yellow]Server '{server_name}' is not connected[/yellow]")
            return
        
        with self.console.status(f"[bold yellow]Disconnecting from {server_name}...[/bold yellow]"):
            await self.server_manager.disconnect_server(server_name)
        
        self.console.print(f"[green]Disconnected from {server_name}[/green]")
    
    async def _cmd_servers(self, args: str) -> None:
        """Handle the servers command.
        
        Args:
            args: Command parameters.
        """
        table = Table(title="MCP Servers")
        table.add_column("Name", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Type", style="blue")
        table.add_column("URL/Command", style="magenta")
        
        for name, server in sorted(self.server_manager.servers.items()):
            status = "[green]Connected" if server.is_connected else "[red]Disconnected"
            config = server.config
            
            if config.type.lower() == "sse":
                url_cmd = config.url or "[italic]Not set[/italic]"
            else:
                url_cmd = config.command or "[italic]Not set[/italic]"
            
            table.add_row(name, status, config.type, url_cmd)
        
        self.console.print(table)
    
    async def _cmd_tools(self, args: str) -> None:
        """Handle the tools command.
        
        Args:
            args: Command parameters.
        """
        args = args.strip()
        
        if args:
            # List tools for a specific server
            server_name = args
            server = self.server_manager.get_server(server_name)
            
            if not server:
                self.console.print(f"[red]Error: Server '{server_name}' not found[/red]")
                return
            
            if not server.is_connected:
                self.console.print(f"[red]Error: Server '{server_name}' is not connected[/red]")
                return
            
            tools = server.tools
            title = f"Tools from {server_name}"
            
            if not tools:
                self.console.print("[yellow]No tools available[/yellow]")
                return
            
            # For single server, don't show server column
            table = Table(title=title)
            table.add_column("Name", style="cyan")
            table.add_column("Description", style="green")
            
            for tool in sorted(tools, key=lambda t: t.name):
                table.add_row(tool.name, tool.description)
        else:
            # List all tools from all servers with server tracking
            tools_with_server = []
            for server in self.server_manager.get_connected_servers():
                for tool in server.tools:
                    tools_with_server.append((tool, server.name))
            
            title = "All Available Tools"
            
            if not tools_with_server:
                self.console.print("[yellow]No tools available[/yellow]")
                return
            
            # For all servers, include server column
            table = Table(title=title)
            table.add_column("Name", style="cyan")
            table.add_column("Description", style="green")
            table.add_column("Server", style="blue")
            
            for tool, server_name in sorted(tools_with_server, key=lambda t: t[0].name):
                table.add_row(tool.name, tool.description, server_name)
        
        self.console.print(table)
    
    async def _cmd_resources(self, args: str) -> None:
        """Handle the resources command.
        
        Args:
            args: Command parameters.
        """
        args = args.strip()
        
        if args:
            # List resources for a specific server
            server_name = args
            server = self.server_manager.get_server(server_name)
            
            if not server:
                self.console.print(f"[red]Error: Server '{server_name}' not found[/red]")
                return
            
            if not server.is_connected:
                self.console.print(f"[red]Error: Server '{server_name}' is not connected[/red]")
                return
            
            resources = server.resources
            templates = server.resource_templates
            title = f"Resources from {server_name}"
            show_server_column = False
        else:
            # List all resources from all servers with server tracking
            resources_with_server = []
            templates_with_server = []
            for server in self.server_manager.get_connected_servers():
                for resource in server.resources:
                    resources_with_server.append((resource, server.name))
                for template in server.resource_templates:
                    templates_with_server.append((template, server.name))
            
            # Check if there are any resources or templates available
            if not resources_with_server and not templates_with_server:
                self.console.print("[yellow]No resources available[/yellow]")
                return
            
            title = "All Available Resources"
            show_server_column = True
        
        if args and not resources and not templates:
            self.console.print("[yellow]No resources available[/yellow]")
            return
        
        if args and resources:
            # Single server resources
            table = Table(title=f"{title} - Direct Resources")
            table.add_column("URI", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("MIME Type", style="blue")
            
            try:
                # Sort resources safely, with a fallback for any sorting errors
                try:
                    sorted_resources = sorted(resources, key=lambda r: r.uri)
                except Exception:
                    self.console.print("[yellow]Warning: Unable to sort resources. Displaying in original order.[/yellow]")
                    sorted_resources = resources
                
                for resource in sorted_resources:
                    try:
                        table.add_row(
                            resource.uri,
                            resource.name,
                            resource.mime_type or "[italic]Not specified[/italic]"
                        )
                    except Exception as row_err:
                        self.console.print(f"[yellow]Warning: Unable to display resource: {row_err}[/yellow]")
            except Exception as table_err:
                self.console.print(f"[red]Error displaying resources table: {table_err}[/red]")
            
            self.console.print(table)
        elif not args and resources_with_server:
            # All servers resources
            table = Table(title=f"{title} - Direct Resources")
            table.add_column("URI", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("MIME Type", style="blue")
            table.add_column("Server", style="yellow")
            
            try:
                # Sort resources safely, with a fallback for any sorting errors
                try:
                    sorted_resources = sorted(resources_with_server, key=lambda r: r[0].uri)
                except Exception:
                    self.console.print("[yellow]Warning: Unable to sort resources. Displaying in original order.[/yellow]")
                    sorted_resources = resources_with_server
                
                for resource, server_name in sorted_resources:
                    try:
                        table.add_row(
                            resource.uri,
                            resource.name,
                            resource.mime_type or "[italic]Not specified[/italic]",
                            server_name
                        )
                    except Exception as row_err:
                        self.console.print(f"[yellow]Warning: Unable to display resource: {row_err}[/yellow]")
            except Exception as table_err:
                self.console.print(f"[red]Error displaying resources table: {table_err}[/red]")
            
            self.console.print(table)
        
        if args and templates:
            # Single server templates
            table = Table(title=f"{title} - Resource Templates")
            table.add_column("URI Template", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("MIME Type", style="blue")
            
            try:
                # Sort templates safely, with a fallback for any sorting errors
                try:
                    sorted_templates = sorted(templates, key=lambda t: t.uri_template)
                except Exception:
                    self.console.print("[yellow]Warning: Unable to sort templates. Displaying in original order.[/yellow]")
                    sorted_templates = templates
                
                for template in sorted_templates:
                    try:
                        table.add_row(
                            template.uri_template,
                            template.name,
                            template.mime_type or "[italic]Not specified[/italic]"
                        )
                    except Exception as row_err:
                        self.console.print(f"[yellow]Warning: Unable to display resource template: {row_err}[/yellow]")
            except Exception as table_err:
                self.console.print(f"[red]Error displaying template table: {table_err}[/red]")
            
            self.console.print(table)
        elif not args and templates_with_server:
            # All servers templates
            table = Table(title=f"{title} - Resource Templates")
            table.add_column("URI Template", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("MIME Type", style="blue")
            table.add_column("Server", style="yellow")
            
            try:
                # Sort templates safely, with a fallback for any sorting errors
                try:
                    sorted_templates = sorted(templates_with_server, key=lambda t: t[0].uri_template)
                except Exception:
                    self.console.print("[yellow]Warning: Unable to sort templates. Displaying in original order.[/yellow]")
                    sorted_templates = templates_with_server
                
                for template, server_name in sorted_templates:
                    try:
                        table.add_row(
                            template.uri_template,
                            template.name,
                            template.mime_type or "[italic]Not specified[/italic]",
                            server_name
                        )
                    except Exception as row_err:
                        self.console.print(f"[yellow]Warning: Unable to display resource template: {row_err}[/yellow]")
            except Exception as table_err:
                self.console.print(f"[red]Error displaying template table: {table_err}[/red]")
            
            self.console.print(table)
    
    async def _cmd_prompts(self, args: str) -> None:
        """Handle the prompts command.
        
        Args:
            args: Command parameters.
        """
        args = args.strip()
        
        if args:
            # List prompts for a specific server
            server_name = args
            server = self.server_manager.get_server(server_name)
            
            if not server:
                self.console.print(f"[red]Error: Server '{server_name}' not found[/red]")
                return
            
            if not server.is_connected:
                self.console.print(f"[red]Error: Server '{server_name}' is not connected[/red]")
                return
            
            prompts = server.prompts
            title = f"Prompts from {server_name}"
            
            if not prompts:
                self.console.print("[yellow]No prompts available[/yellow]")
                return
            
            # For single server, don't show server column
            table = Table(title=title)
            table.add_column("Name", style="cyan")
            table.add_column("Description", style="green")
            
            for prompt in sorted(prompts, key=lambda p: p.name):
                table.add_row(prompt.name, prompt.description)
        else:
            # List all prompts from all servers with server tracking
            prompts_with_server = []
            for server in self.server_manager.get_connected_servers():
                for prompt in server.prompts:
                    prompts_with_server.append((prompt, server.name))
            
            title = "All Available Prompts"
            
            if not prompts_with_server:
                self.console.print("[yellow]No prompts available[/yellow]")
                return
            
            # For all servers, include server column
            table = Table(title=title)
            table.add_column("Name", style="cyan")
            table.add_column("Description", style="green")
            table.add_column("Server", style="blue")
            
            for prompt, server_name in sorted(prompts_with_server, key=lambda p: p[0].name):
                table.add_row(prompt.name, prompt.description, server_name)
        
        self.console.print(table)
    
    async def _cmd_formats(self, args: str) -> None:
        """Handle the formats command.
        
        Args:
            args: Command parameters.
        """
        args = args.strip()
        
        if args:
            # List prompt formats for a specific server
            server_name = args
            server = self.server_manager.get_server(server_name)
            
            if not server:
                self.console.print(f"[red]Error: Server '{server_name}' not found[/red]")
                return
            
            if not server.is_connected:
                self.console.print(f"[red]Error: Server '{server_name}' is not connected[/red]")
                return
            
            formats = server.prompt_formats
            title = f"Prompt Formats from {server_name}"
            
            if not formats:
                self.console.print("[yellow]No prompt formats available[/yellow]")
                return
            
            # For single server, don't show server column
            table = Table(title=title)
            table.add_column("Name", style="cyan")
            table.add_column("Description", style="green")
            
            for format in sorted(formats, key=lambda f: f.name):
                table.add_row(
                    format.name,
                    format.description or "[italic]No description[/italic]"
                )
        else:
            # List all prompt formats from all servers with server tracking
            formats_with_server = []
            for server in self.server_manager.get_connected_servers():
                for format in server.prompt_formats:
                    formats_with_server.append((format, server.name))
            
            title = "All Available Prompt Formats"
            
            if not formats_with_server:
                self.console.print("[yellow]No prompt formats available[/yellow]")
                return
            
            # For all servers, include server column
            table = Table(title=title)
            table.add_column("Name", style="cyan")
            table.add_column("Description", style="green")
            table.add_column("Server", style="blue")
            
            for format, server_name in sorted(formats_with_server, key=lambda f: f[0].name):
                table.add_row(
                    format.name,
                    format.description or "[italic]No description[/italic]",
                    server_name
                )
        
        self.console.print(table)
    
    def _format_tool_help(self, tool, server_name: str) -> None:
        """Format and display help information for a tool.
        
        Args:
            tool: The Tool object to display help for.
            server_name: The name of the server the tool belongs to.
        """
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text
        from rich.box import ROUNDED
        from rich import box
        
        # Create a table for the tool info
        table = Table(
            box=ROUNDED, 
            show_header=False, 
            show_edge=False, 
            pad_edge=False,
            width=self.console.width - 4  # Account for panel borders
        )
        
        # Add columns
        table.add_column("Key", style="bold cyan", width=15, justify="right")
        table.add_column("Value", style="white", ratio=3)
        
        # Add server and tool info
        table.add_row(
            Text("Server", style="bold cyan"), 
            Text(server_name, style="bright_green bold")
        )
        table.add_row(
            Text("Tool", style="bold cyan"), 
            Text(tool.name, style="bright_yellow bold")
        )
        table.add_row(
            Text("Description", style="bold cyan"),
            Text(tool.description, style="white")
        )
        
        # Add horizontal separator
        separator = Text("─" * (self.console.width - 8), style="dim")
        table.add_row("", separator)
        
        # Add parameters header
        table.add_row(
            Text("Parameters", style="bold magenta underline"),
            ""
        )
        
        # Get the input schema properties
        properties = tool.input_schema.get("properties", {})
        required = tool.input_schema.get("required", [])
        
        if not properties:
            table.add_row("", Text("No parameters required", style="dim italic"))
        else:
            # Create a nested table for parameters
            params_table = Table(
                box=box.SIMPLE,
                show_header=True,
                show_edge=False,
                pad_edge=False
            )
            
            params_table.add_column("Parameter", style="cyan")
            params_table.add_column("Type", style="green")
            params_table.add_column("Required", style="yellow")
            params_table.add_column("Description", style="white")
            
            for param_name, param_info in properties.items():
                param_type = param_info.get("type", "any")
                is_required = param_name in required
                required_text = "Yes" if is_required else "No"
                required_style = "bright_green bold" if is_required else "dim"
                description = param_info.get("description", "No description available")
                
                params_table.add_row(
                    param_name,
                    param_type,
                    Text(required_text, style=required_style),
                    description
                )
            
            table.add_row("", params_table)
        
        # Add horizontal separator
        table.add_row("", separator)
        
        # Add example usage header
        table.add_row(
            Text("Example Usage", style="bold magenta underline"),
            ""
        )
        
        # Create example command
        example_cmd = f"execute {server_name} {tool.name}"
        
        # Add required parameters to example
        example_params = []
        for param_name in required:
            param_info = properties.get(param_name, {})
            param_type = param_info.get("type", "string")
            
            # Create an example value based on type
            example_value = self._get_example_value(param_type, param_name, param_info)
            example_params.append(f"{param_name}={example_value}")
        
        # Add a couple of optional parameters as examples if there are any
        optional_params = [p for p in properties if p not in required]
        for param_name in optional_params[:2]:  # Add up to 2 optional params
            param_info = properties.get(param_name, {})
            param_type = param_info.get("type", "string")
            
            # Create an example value based on type
            example_value = self._get_example_value(param_type, param_name, param_info)
            example_params.append(f"{param_name}={example_value}")
        
        if example_params:
            example_cmd += " " + " ".join(example_params)
            
        table.add_row("", Text(example_cmd, style="bright_blue"))
        
        # Add a note about string parameters with spaces
        table.add_row("", separator)
        table.add_row(
            Text("Note", style="bold magenta underline"),
            ""
        )
        note_text = (
            "For string parameters with spaces, enclose the value in quotes:\n"
            "  param=\"value with spaces\"\n\n"
            "Example: query=\"latest news about AI\""
        )
        table.add_row("", Text(note_text, style="yellow"))
        
        # Create panel with full width
        panel = Panel(
            table,
            title=Text("Tool Help", style="bold white on blue"),
            border_style="blue",
            expand=True,
            padding=(0, 1)
        )
        
        self.console.print(panel)
    
    def _get_example_value(self, param_type: str, param_name: str, param_info: dict) -> str:
        """Get an example value for a parameter based on its type.
        
        Args:
            param_type: The type of the parameter.
            param_name: The name of the parameter.
            param_info: The parameter information.
            
        Returns:
            An example value as a string.
        """
        if param_type == "string":
            # Check for common parameter names to provide better examples
            if "url" in param_name.lower():
                return "https://example.com"
            elif "email" in param_name.lower():
                return "user@example.com"
            elif "name" in param_name.lower():
                return "example_name"
            elif "path" in param_name.lower() or "file" in param_name.lower():
                return "/path/to/file"
            elif "date" in param_name.lower():
                return "2025-07-27"
            elif "time" in param_name.lower():
                return "12:30:00"
            elif "location" in param_name.lower() or "address" in param_name.lower():
                return '"New York"'  # Quoted because it contains a space
            elif "query" in param_name.lower() or "search" in param_name.lower() or "text" in param_name.lower():
                return '"search terms with spaces"'  # Quoted because it likely contains spaces
            elif "prompt" in param_name.lower() or "message" in param_name.lower() or "content" in param_name.lower():
                return '"Example text with multiple words"'  # Quoted because it likely contains spaces
            # Use enum values if available
            elif "enum" in param_info:
                enum_val = str(param_info["enum"][0])
                # Quote enum values if they contain spaces
                if " " in enum_val:
                    return f'"{enum_val}"'
                return enum_val
            else:
                return "example_string"
        elif param_type == "number" or param_type == "integer":
            if "minimum" in param_info and "maximum" in param_info:
                return str((param_info["minimum"] + param_info["maximum"]) // 2)
            elif "minimum" in param_info:
                return str(param_info["minimum"])
            elif "maximum" in param_info:
                return str(param_info["maximum"])
            else:
                return "42" if param_type == "integer" else "3.14"
        elif param_type == "boolean":
            return "true"
        elif param_type == "array":
            return "item1"
        elif param_type == "object":
            return "key1=value1"
        else:
            return "example_value"
    
    async def _cmd_execute(self, args: str) -> None:
        """Handle the execute command.
        
        Args:
            args: Command parameters.
            
        Format: execute <server_name> <tool_name> [arg1=val1 arg2=val2 ...]
        Format: execute <server_name> <tool_name> help
        
        For string parameters with spaces, enclose the value in quotes:
        Example: execute <server_name> <tool_name> query="search terms with spaces"
        """
        args = args.strip()
        parts = args.split()
        
        if len(parts) < 2:
            self.console.print("[red]Error: Invalid format. "
                              "Use: execute <server_name> <tool_name> [arg1=val1 ...] or "
                              "execute <server_name> <tool_name> help[/red]")
            return
        
        server_name = parts[0]
        tool_name = parts[1]
        
        # Check if this is a help request
        if len(parts) == 3 and parts[2].lower() == "help":
            server = self.server_manager.get_server(server_name)
            if not server:
                self.console.print(f"[red]Error: Server '{server_name}' not found[/red]")
                return
            
            if not server.is_connected:
                self.console.print(f"[red]Error: Server '{server_name}' is not connected[/red]")
                return
            
            tool = server.get_tool(tool_name)
            if not tool:
                self.console.print(f"[red]Error: Tool '{tool_name}' not found on server '{server_name}'[/red]")
                return
            
            # Display help information for the tool
            self._format_tool_help(tool, server_name)
            return
        
        # Parse parameters with proper handling of quoted strings
        tool_args = {}
        
        # Join the remaining parts back into a single string for proper parsing
        args_str = ' '.join(parts[2:])
        
        # Use a regex pattern to match key=value pairs, handling quoted values
        pattern = r'(\w+)=("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[^\s]+)'
        matches = re.findall(pattern, args_str)
        
        if not matches and args_str.strip():
            # If we have args but no matches, there might be a syntax error
            self.console.print("[red]Error: Could not parse arguments. "
                              "Use format: key=value or key=\"value with spaces\"[/red]")
            return
        
        for key, value in matches:
            # Remove quotes from quoted values
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            
            # Try to parse JSON-like values
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            elif value.isdigit():
                value = int(value)
            elif re.match(r"^-?\d+\.\d+$", value):
                value = float(value)
            
            tool_args[key] = value
        
        server = self.server_manager.get_server(server_name)
        if not server:
            self.console.print(f"[red]Error: Server '{server_name}' not found[/red]")
            return
        
        if not server.is_connected:
            self.console.print(f"[red]Error: Server '{server_name}' is not connected[/red]")
            return
        
        tool = server.get_tool(tool_name)
        if not tool:
            self.console.print(f"[red]Error: Tool '{tool_name}' not found on server '{server_name}'[/red]")
            return
        
        try:
            # Execute the tool with nice formatting
            # The formatting will be handled by the ServerManager.execute_tool method
            result = await self.server_manager.execute_tool(
                tool_name=tool_name,
                arguments=tool_args,
                server_name=server_name,
                print_formatting=True
            )
            
        except Exception as e:
            self.console.print(f"[red]Error executing tool: {str(e)}[/red]")
    
    async def _cmd_chat(self, args: str) -> None:
        """Handle the chat command with ReAct agent integration.
        
        Args:
            args: Command parameters.
        """
        from .chat_utils import (
            initialize_mcp_client, create_react_agent, display_chat_header,
            run_chat_loop, cleanup_chat_resources
        )
        
        mcp_adapter = None
        react_agent = None
        
        try:
            # Initialize MCP client adapter
            try:
                with self.console.status("[bold green]Initializing MCP client...[/bold green]"):
                    mcp_adapter = await initialize_mcp_client(self.server_manager)
            except RuntimeError as e:
                self.console.print(f"[red]Error: {str(e)}[/red]")
                return
            
            # Create and initialize ReAct agent
            try:
                with self.console.status("[bold green]Creating ReAct agent and loading MCP tools...[/bold green]"):
                    react_agent = await create_react_agent(self.config, mcp_adapter)
            except RuntimeError as e:
                self.console.print(f"[red]Error: {str(e)}[/red]")
                return
            
            # Display chat header
            display_chat_header(self.console, react_agent, mcp_adapter)
            
            # Run the chat loop
            await run_chat_loop(self.console, react_agent, mcp_adapter, self.session)
            
        except Exception as e:
            self.console.print(f"[red]Unexpected error in chat mode: {str(e)}[/red]")
            logging.error(f"Unexpected error in chat mode: {e}")
        
        finally:
            # Clean up resources
            await cleanup_chat_resources(mcp_adapter, react_agent)
    
    async def _cmd_config(self, args: str) -> None:
        """Handle the config command.
        
        Args:
            args: Command parameters.
        """
        args = args.strip()
        parts = args.split()
        
        if not args or parts[0] == "show":
            # Show current configuration
            config_dict = self.config.config.model_dump()
            formatted_config = json.dumps(config_dict, indent=2)
            self.console.print(Panel(formatted_config, title="Current Configuration", border_style="blue"))
            return
        
        if parts[0] == "llm":
            if len(parts) < 3:
                self.console.print("[red]Error: Invalid format. "
                                 "Use: config llm <provider> [model=<model>] [api_url=<url>] "
                                 "[api_key=<key>] [param=value ...][/red]")
                return
            
            provider = parts[1]
            
            # Parse parameters
            kwargs = {}
            for arg in parts[2:]:
                if "=" not in arg:
                    self.console.print(f"[red]Error: Invalid argument format: {arg}. "
                                     "Use: key=value[/red]")
                    return
                
                key, value = arg.split("=", 1)
                kwargs[key] = value
            
            # Update configuration
            llm_config = self.config.config.llm
            llm_config.provider = provider
            
            if "model" in kwargs:
                llm_config.model = kwargs.pop("model")
            
            if "api_url" in kwargs:
                llm_config.api_url = kwargs.pop("api_url")
            
            if "api_key" in kwargs:
                llm_config.api_key = kwargs.pop("api_key")
            
            # Remaining kwargs go into other_params
            for key, value in kwargs.items():
                llm_config.other_params[key] = value
            
            # Save configuration
            self.config.save_config(self.config.config)
            
            # Re-initialize LLM provider
            self._initialize_llm_provider()
            
            self.console.print(f"[green]LLM provider updated to {provider} "
                             f"with model {llm_config.model}[/green]")
            return
        
        self.console.print(f"[red]Error: Unknown config subcommand: {parts[0]}[/red]")
    
    async def _cmd_reload(self, args: str) -> None:
        """Handle the reload command.
        
        Args:
            args: Command parameters.
        """
        try:
            self.config.reload()
            self.console.print(f"[green]Configuration reloaded from {self.config.config_path}[/green]")
            
            # Re-initialize LLM provider
            self._initialize_llm_provider()
            
            # Re-load servers
            self.server_manager._load_servers()
            
        except Exception as e:
            self.console.print(f"[red]Error reloading configuration: {str(e)}[/red]")
    
    async def _cmd_get_resource(self, args: str) -> None:
        """Handle the get-resource command.
        
        Args:
            args: Command parameters.
            
        Format: get-resource [server_name] <resource_uri>
        """
        args = args.strip()
        parts = args.split()
        
        if not args:
            self.console.print("[red]Error: Missing resource URI.[/red]")
            self.console.print("Usage: get-resource [server_name] <resource_uri>")
            return
        
        server_name = None
        resource_uri = None
        
        if len(parts) == 1:
            # Only URI provided, try to find a server that has the resource
            resource_uri = parts[0]
        elif len(parts) >= 2:
            # Server name and URI provided
            server_name = parts[0]
            resource_uri = parts[1]
        
        try:
            # Use a status indicator
            status_context = self.console.status(f"[bold green]Getting resource {resource_uri}...[/bold green]")
            status_context.__enter__()
            
            try:
                result = await self.server_manager.get_resource(resource_uri, server_name)
                status_context.__exit__(None, None, None)
                
                # Determine how to display the resource
                if hasattr(result, "contents") and isinstance(result.contents, list):
                    # Handle ReadResourceResponse with multiple contents
                    for content in result.contents:
                        mime_type = getattr(content, "mimeType", None)
                        text = getattr(content, "text", None)
                        
                        if text:
                            # Try to format as JSON if it looks like JSON
                            if text.strip().startswith(("{", "[")):
                                try:
                                    parsed = json.loads(text)
                                    formatted = json.dumps(parsed, indent=2)
                                    self.console.print(Panel(formatted, 
                                        title=f"Resource: {resource_uri} ({mime_type})", 
                                        border_style="green"))
                                except json.JSONDecodeError:
                                    # Not valid JSON, display as-is
                                    self.console.print(Panel(text, 
                                        title=f"Resource: {resource_uri} ({mime_type})", 
                                        border_style="green"))
                            else:
                                # Plain text
                                self.console.print(Panel(text, 
                                    title=f"Resource: {resource_uri} ({mime_type})", 
                                    border_style="green"))
                        else:
                            # No text content, show object summary
                            formatted = self._serialize_complex_object(content)
                            self.console.print(Panel(formatted, 
                                title=f"Resource: {resource_uri}", 
                                border_style="green"))
                else:
                    # Handle string or other result types
                    formatted_result = self._serialize_complex_object(result)
                    self.console.print(Panel(formatted_result, 
                        title=f"Resource: {resource_uri}", 
                        border_style="green"))
                    
            except Exception as e:
                # Make sure status is cleared even on error
                status_context.__exit__(None, None, None)
                self.console.print(f"[red]Error getting resource: {str(e)}[/red]")
        except Exception as outer_e:
            # Handle any issues with the status context itself
            self.console.print(f"[red]Error setting up command environment: {str(outer_e)}[/red]")
    
    async def _cmd_get_prompt(self, args: str) -> None:
        """Handle the get-prompt command.
        
        Args:
            args: Command parameters.
            
        Format: get-prompt [server_name] <prompt_name> [format=<format_name>] [arg1=val1 arg2=val2 ...]
        """
        args = args.strip()
        parts = args.split()
        
        if len(parts) < 1:
            self.console.print("[red]Error: Missing prompt name.[/red]")
            self.console.print("Usage: get-prompt [server_name] <prompt_name> [format=<format_name>] [arg1=val1 arg2=val2 ...]")
            return
        
        server_name = None
        prompt_name = None
        format_name = None
        prompt_args = {}
        
        if len(parts) == 1:
            # Only prompt name provided
            prompt_name = parts[0]
        else:
            # Check if first two args are server and prompt, or prompt and args
            if "=" in parts[1]:
                # First arg is prompt name, rest are parameters
                prompt_name = parts[0]
                arg_parts = parts[1:]
            else:
                # First arg is server name, second is prompt name
                server_name = parts[0]
                prompt_name = parts[1]
                arg_parts = parts[2:]
            
            # Parse parameters
            for arg in arg_parts:
                if "=" not in arg:
                    self.console.print(f"[red]Error: Invalid argument format: {arg}. "
                                     "Use: key=value[/red]")
                    return
                
                key, value = arg.split("=", 1)
                
                # Handle format separately
                if key.lower() == "format":
                    format_name = value
                    continue
                
                # Try to parse JSON-like values
                if value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                elif value.isdigit():
                    value = int(value)
                elif re.match(r"^-?\d+\.\d+$", value):
                    value = float(value)
                
                prompt_args[key] = value
        
        try:
            # Use a status indicator
            status_text = f"[bold green]Getting prompt {prompt_name}"
            if server_name:
                status_text += f" from {server_name}"
            status_text += "...[/bold green]"
            
            status_context = self.console.status(status_text)
            status_context.__enter__()
            
            try:
                result = await self.server_manager.get_prompt(
                    prompt_name, prompt_args, format_name, server_name
                )
                status_context.__exit__(None, None, None)
                
                # Determine how to display the prompt
                if hasattr(result, "text"):
                    # Handle text content directly
                    title = f"Prompt: {prompt_name}"
                    if format_name:
                        title += f" (Format: {format_name})"
                    
                    self.console.print(Panel(result.text, title=title, border_style="green"))
                else:
                    # Handle string or other result types
                    formatted_result = self._serialize_complex_object(result)
                    
                    title = f"Prompt: {prompt_name}"
                    if format_name:
                        title += f" (Format: {format_name})"
                    
                    self.console.print(Panel(formatted_result, title=title, border_style="green"))
                    
            except Exception as e:
                # Make sure status is cleared even on error
                status_context.__exit__(None, None, None)
                self.console.print(f"[red]Error getting prompt: {str(e)}[/red]")
        except Exception as outer_e:
            # Handle any issues with the status context itself
            self.console.print(f"[red]Error setting up command environment: {str(outer_e)}[/red]")
    
    async def _cmd_exit(self, args: str) -> None:
        """Handle the exit command.
        
        Args:
            args: Command parameters.
        """
        self.console.print("[yellow]Disconnecting from all servers...[/yellow]")
        await self.server_manager.disconnect_all()
        self.console.print("[green]Goodbye![/green]")
        sys.exit(0)
