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
                "description": "Execute a tool",
                "handler": self._cmd_execute,
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
        
        with self.console.status(f"[bold green]Connecting to {server_name}...[/bold green]"):
            success = await self.server_manager.connect_server(server_name)
        
        if success:
            server = self.server_manager.get_server(server_name)
            if not server:
                self.console.print("[red]Error: Failed to get server reference[/red]")
                return
            
            info = server.server_info
            if info:
                self.console.print(
                    f"[green]Connected to {server_name} "
                    f"({info.name} v{info.version})[/green]"
                )
            else:
                self.console.print(f"[green]Connected to {server_name}[/green]")
            
            # Show available tools
            if server.tools:
                self.console.print(f"Available tools: {len(server.tools)}")
        else:
            self.console.print(f"[red]Failed to connect to {server_name}[/red]")
    
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
    
    async def _cmd_execute(self, args: str) -> None:
        """Handle the execute command.
        
        Args:
            args: Command parameters.
            
        Format: execute <server_name> <tool_name> [arg1=val1 arg2=val2 ...]
        """
        args = args.strip()
        parts = args.split()
        
        if len(parts) < 2:
            self.console.print("[red]Error: Invalid format. "
                              "Use: execute <server_name> <tool_name> [arg1=val1 ...][/red]")
            return
        
        server_name = parts[0]
        tool_name = parts[1]
        
        # Parse parameters
        tool_args = {}
        for arg in parts[2:]:
            if "=" not in arg:
                self.console.print(f"[red]Error: Invalid argument format: {arg}. "
                                  "Use: key=value[/red]")
                return
            
            key, value = arg.split("=", 1)
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
            # Use a new context for the status indicator to ensure it's properly managed
            status_context = self.console.status(f"[bold green]Executing {tool_name} on {server_name}...[/bold green]")
            status_context.__enter__()
            
            try:
                result = await server.execute_tool(tool_name, tool_args)
                # Exit the status context before printing results
                status_context.__exit__(None, None, None)
                
                # Pretty print the result
                if isinstance(result, str):
                    self.console.print(Panel(result, title=f"Result: {tool_name}", border_style="green"))
                else:
                    formatted_result = self._serialize_complex_object(result)
                    self.console.print(Panel(formatted_result, title=f"Result: {tool_name}", border_style="green"))
            except Exception as e:
                # Make sure status is cleared even on error
                status_context.__exit__(None, None, None)
                self.console.print(f"[red]Error executing tool: {str(e)}[/red]")
        except Exception as outer_e:
            # Handle any issues with the status context itself
            self.console.print(f"[red]Error setting up execution environment: {str(outer_e)}[/red]")
    
    async def _cmd_chat(self, args: str) -> None:
        """Handle the chat command.
        
        Args:
            args: Command parameters.
        """
        if not self.llm_provider:
            self.console.print("[red]Error: No LLM provider configured[/red]")
            return
        
        connected_servers = self.server_manager.get_connected_servers()
        if not connected_servers:
            self.console.print("[yellow]Warning: No MCP servers connected. "
                              "Tools will not be available.[/yellow]")
        
        # Create system message with available tools
        all_tools = self.server_manager.get_all_tools()
        
        # Format tools for the system prompt
        # Either use the enhanced formatter or fall back to the basic one
        try:
            tools_description = generate_tool_format(all_tools)
        except Exception as e:
            self.console.print(f"Warning using enhanced tool formatting, falling back to basic: {str(e)}")
            # Fall back to basic formatting
            tools_description = ""
            for server_name, tools in all_tools.items():
                tools_description += f"Server: {server_name}\n\n"
                for tool in tools:
                    tools_description += tool.format_for_llm() + "\n"

        # Generate the enhanced modular system prompt
        system_prompt = generate_system_prompt(
            available_tools=tools_description,
            include_mcp_guidance=True,
            include_react_guidance=True
        )

        self.llm_provider.set_system_message(system_prompt)
        
        # count tools
        tool_count = 0
        for server_name, tools in all_tools.items():
            for tool in tools:
                tool_count += 1

        self.console.print(Panel.fit(
            f"[bold green]Chat mode started with {self.llm_provider.name} ({self.llm_provider.model})[/bold green]\n"
            f"Connected servers: {', '.join(s.name for s in connected_servers)}\n"
            f"Available tools: {tool_count}\n"
            f"Type [bold]exit[/bold] to return to command mode",
            title="MCP Chat"
        ))
        
        messages = [{"role": "system", "content": system_prompt}]
        
        # Chat loop
        while True:
            # Get user input
            try:
                user_input = await self.session.prompt_async(
                    HTML("<ansicyan><b>You:</b></ansicyan> "),
                    style=self.style
                )
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[yellow]Exiting chat mode...[/yellow]")
                break
            
            user_input = user_input.strip()
            if user_input.lower() == "exit":
                self.console.print("[yellow]Exiting chat mode...[/yellow]")
                break
            
            if not user_input:
                continue
            
            messages.append({"role": "user", "content": user_input})
            
            # Get LLM response - use explicit context management to avoid conflicts
            try:
                status = self.console.status("[bold green]Thinking...[/bold green]")
                status.__enter__()
                llm_response = await self.llm_provider.get_response(messages)
                status.__exit__(None, None, None)
            except Exception as e:
                # Ensure status is cleared even on error
                try:
                    status.__exit__(None, None, None)
                except:
                    pass
                self.console.print(f"[red]Error getting LLM response: {str(e)}[/red]")
                continue
            
            pattern = r'```json([\s\S]*?)```'
            match = re.search(pattern, llm_response)

            if match:
                llm_response = match.group(1).strip()
                print(llm_response)

            # Translate tool format if needed
            def translate_tool_format(text):
                """
                Translate from simple format to nested JSON if the first line is a tool name.

                FROM:
                filesystem_list_directory
                {"path": "/home"}

                TO:
                {
                "tool": "filesystem_list_directory",
                "parameters": {
                    "path": "/home"
                }
                }
                """
                lines = text.strip().split('\n', 1)
                if len(lines) < 2:
                    return text

                potential_tool_name = lines[0].strip()
                potential_params = lines[1].strip()

                # Check if first line looks like a tool name (no spaces, no JSON characters)
                if ' ' in potential_tool_name or '{' in potential_tool_name or '}' in potential_tool_name:
                    return text

                # Try to parse the second part as JSON
                try:
                    params = json.loads(potential_params)
                    # Create the new format
                    transformed = {
                        "tool": potential_tool_name,
                        "parameters": params
                    }
                    return json.dumps(transformed)
                except json.JSONDecodeError:
                    return text

            # Apply translation if needed
            llm_response = translate_tool_format(llm_response)

            # Check if response is a tool call
            try:
                is_tool_call = False
                try:
                    tool_call = json.loads(llm_response)
                    is_tool_call = True
                except json.JSONDecodeError:
                    is_tool_call = False
                
                if is_tool_call:
                    if 'parameters' not in tool_call:
                        tool_call['parameters'] = {}

                    self.console.print(Panel(
                        f"[bold]Executing tool:[/bold] {tool_call['tool']}\n"
                        + (f"[bold]With parameters:[/bold] {json.dumps(tool_call['parameters'], indent=2)}" if 'parameters' in tool_call else ""),
                        title="Assistant",
                        border_style="yellow"
                    ))
                    
                    try:
                        # Execute the tool
                        self.console.print(f"[bold green]Executing {tool_call['tool']}...[/bold green]")
                        result = await self.server_manager.execute_tool(
                            tool_call["tool"],
                            tool_call["parameters"]
                        )
                        
                        # Add assistant message to history
                        messages.append({"role": "assistant", "content": llm_response})
                        
                        # Prepare the tool result
                        if isinstance(result, str):
                            formatted_result = result
                        else:
                            formatted_result = self._serialize_complex_object(result)
                        
                        # Create a new system prompt that combines the user query with the tool result
                        new_system_prompt = (
                            "You are a helpful assistant with access to tools. "
                            "A tool has been called based on the user's question, and the result is provided below. "
                            "Create a natural, conversational response that incorporates this tool result. "
                            "If you need to call additional tools to fully answer the question, respond ONLY with a "
                            "JSON object in the format: {\"tool\": \"tool-name\", \"parameters\": {\"key\": \"value\"}}. "
                            "Otherwise, provide a complete and helpful response that addresses the user's original question "
                            "using the tool result.\n\n"
                            f"User's original question: {user_input}\n\n"
                            f"Tool called: {tool_call['tool']}\n"
                            f"Tool result: {formatted_result}"
                        )
                        
                        # Replace the original system message temporarily for this response
                        #original_system_message = messages[0]["content"]
                        #messages[0]["content"] = new_system_prompt
                        
                        messages.append({"role": "user", "content": formatted_result})

                        # Get final response from LLM
                        self.console.print("[bold green]Processing result...[/bold green]")
                        final_response = await self.llm_provider.get_response(messages)
                        
                        # Check if the final response is another tool call
                        try:
                            is_another_call = False
                            try:
                                another_tool_call = json.loads(final_response)
                                is_another_call = True
                            except json.JSONDecodeError:
                                is_another_call = False

                            if is_another_call:
                                # It's another tool call, so we'll display it as such
                                self.console.print(Panel(
                                    f"[bold]Assistant needs to call another tool:[/bold] {another_tool_call['tool']}\n"
                                    f"[bold]With parameters:[/bold] {json.dumps(another_tool_call['parameters'], indent=2)}",
                                    title="Assistant",
                                    border_style="yellow"
                                ))
                                
                                # Execute the second tool
                                self.console.print(f"[bold green]Executing {another_tool_call['tool']}...[/bold green]")
                                second_result = await self.server_manager.execute_tool(
                                    another_tool_call["tool"],
                                    another_tool_call["parameters"]
                                )
                                
                                # Format the result
                                if isinstance(second_result, str):
                                    second_formatted_result = second_result
                                else:
                                    second_formatted_result = self._serialize_complex_object(second_result)
                                
                                # Update the system prompt to include both tool results
                                combined_system_prompt = (
                                    "You are a helpful assistant with access to tools. "
                                    "Two tools have been called based on the user's question, and the results are provided below. "
                                    "Create a natural, conversational response that incorporates these tool results. "
                                    "Focus on providing a complete and helpful response that addresses the user's original question.\n\n"
                                    f"User's original question: {user_input}\n\n"
                                    f"First tool called: {tool_call['tool']}\n"
                                    f"First tool result: {formatted_result}\n\n"
                                    f"Second tool called: {another_tool_call['tool']}\n"
                                    f"Second tool result: {second_formatted_result}"
                                )
                                
                                # Update the system message
                                #messages[0]["content"] = combined_system_prompt
                                
                                messages.append({"role": "user", "content": second_formatted_result})

                                # Get the combined final response
                                self.console.print("[bold green]Processing combined results...[/bold green]")
                                combined_final_response = await self.llm_provider.get_response(messages)
                                
                                self.console.print(Panel(
                                    Markdown(combined_final_response),
                                    title="Assistant",
                                    border_style="green"
                                ))
                                
                                # Add final response to messages
                                messages.append({"role": "assistant", "content": combined_final_response})
                                
                                # Restore original system message
                                #messages[0]["content"] = original_system_message
                                
                            else:
                                # Not a tool call, display the response
                                self.console.print(Panel(
                                    Markdown(final_response),
                                    title="Assistant",
                                    border_style="green"
                                ))
                                
                                # Add final response to messages
                                messages.append({"role": "assistant", "content": final_response})
                                
                                # Restore original system message
                                #messages[0]["content"] = original_system_message
                                
                        except json.JSONDecodeError:
                            # Not a tool call (not valid JSON), display response directly
                            self.console.print(Panel(
                                Markdown(final_response),
                                title="Assistant",
                                border_style="green"
                            ))
                            
                            # Add final response to messages
                            messages.append({"role": "assistant", "content": final_response})
                            
                            # Restore original system message
                            #messages[0]["content"] = original_system_message
                        
                    except Exception as e:
                        error_msg = f"Error executing tool: {str(e)}"
                        self.console.print(f"[red]{error_msg}[/red]")
                        
                        # Add error as system message
                        messages.append({"role": "system", "content": error_msg})
                        
                else:
                    # Not a tool call, display response directly
                    self.console.print(Panel(
                        Markdown(llm_response),
                        title="Assistant",
                        border_style="green"
                    ))
                    
                    # Add response to messages
                    messages.append({"role": "assistant", "content": llm_response})
            
            except Exception as e:
                # Handle any error in the tool execution flow
                self.console.print(f"[red]Error processing response: {str(e)}[/red]")
                
                # Display the original response if possible
                if 'llm_response' in locals():
                    self.console.print(Panel(
                        Markdown(llm_response),
                        title="Assistant (Error Processing)",
                        border_style="red"
                    ))
                    
                    # Add response to messages
                    messages.append({"role": "assistant", "content": llm_response})
    
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
