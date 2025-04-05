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
        
        # Command with space, try to complete subcommands or arguments
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
        try:
            # Try direct JSON serialization
            return json.dumps(obj, indent=2)
        except TypeError:
            # Handle objects with __dict__
            if hasattr(obj, "__dict__"):
                try:
                    obj_dict = {k: v for k, v in obj.__dict__.items() 
                               if not k.startswith('_') and not callable(v)}
                    return json.dumps(obj_dict, indent=2)
                except:
                    pass
            
            # Handle objects with special content structure (like CallToolResult)
            if hasattr(obj, "content") and isinstance(obj.content, list):
                content_text = ""
                for item in obj.content:
                    if hasattr(item, "text") and item.text:
                        content_text += item.text + "\n"
                    elif hasattr(item, "__dict__"):
                        try:
                            content_text += json.dumps(item.__dict__, indent=2) + "\n"
                        except:
                            content_text += f"[Object of type {type(item).__name__}]\n"
                    else:
                        content_text += str(item) + "\n"
                return content_text
            
            # Last resort - string representation
            return str(obj)

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
            "execute": {
                "description": "Execute a tool",
                "handler": self._cmd_execute,
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
            args: Command arguments.
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
            args: Command arguments.
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
            args: Command arguments.
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
            args: Command arguments.
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
            args: Command arguments.
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
        else:
            # List all tools from all servers
            tools = self.server_manager.get_all_tools()
            title = "All Available Tools"
        
        if not tools:
            self.console.print("[yellow]No tools available[/yellow]")
            return
        
        table = Table(title=title)
        table.add_column("Name", style="cyan")
        table.add_column("Description", style="green")
        
        for tool in sorted(tools, key=lambda t: t.name):
            table.add_row(tool.name, tool.description)
        
        self.console.print(table)
    
    async def _cmd_resources(self, args: str) -> None:
        """Handle the resources command.
        
        Args:
            args: Command arguments.
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
        else:
            # List all resources from all servers
            resources = []
            templates = []
            for server in self.server_manager.get_connected_servers():
                resources.extend(server.resources)
                templates.extend(server.resource_templates)
            title = "All Available Resources"
        
        if not resources and not templates:
            self.console.print("[yellow]No resources available[/yellow]")
            return
        
        if resources:
            table = Table(title=f"{title} - Direct Resources")
            table.add_column("URI", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("MIME Type", style="blue")
            
            for resource in sorted(resources, key=lambda r: r.uri):
                table.add_row(
                    resource.uri,
                    resource.name,
                    resource.mime_type or "[italic]Not specified[/italic]"
                )
            
            self.console.print(table)
        
        if templates:
            table = Table(title=f"{title} - Resource Templates")
            table.add_column("URI Template", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("MIME Type", style="blue")
            
            for template in sorted(templates, key=lambda t: t.uri_template):
                table.add_row(
                    template.uri_template,
                    template.name,
                    template.mime_type or "[italic]Not specified[/italic]"
                )
            
            self.console.print(table)
    
    async def _cmd_execute(self, args: str) -> None:
        """Handle the execute command.
        
        Args:
            args: Command arguments.
            
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
        
        # Parse arguments
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
            args: Command arguments.
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
        tools_description = "\n".join([tool.format_for_llm() for tool in all_tools])
        
        system_message = (
            "You are a helpful assistant with access to these tools:\n\n"
            f"{tools_description}\n"
            "Choose the appropriate tool based on the user's question. "
            "If no tool is needed, reply directly.\n\n"
            "IMPORTANT: When you need to use a tool, you must ONLY respond with "
            "the exact JSON object format below, nothing else:\n"
            "{\n"
            '    "tool": "tool-name",\n'
            '    "arguments": {\n'
            '        "argument-name": "value"\n'
            "    }\n"
            "}\n\n"
            "After receiving a tool's response:\n"
            "1. Transform the raw data into a natural, conversational response\n"
            "2. Keep responses concise but informative\n"
            "3. Focus on the most relevant information\n"
            "4. Use appropriate context from the user's question\n"
            "5. Avoid simply repeating the raw data\n\n"
            "Please use only the tools that are explicitly defined above."
        )
        
        self.llm_provider.set_system_message(system_message)
        
        self.console.print(Panel.fit(
            f"[bold green]Chat mode started with {self.llm_provider.name} ({self.llm_provider.model})[/bold green]\n"
            f"Connected servers: {', '.join(s.name for s in connected_servers)}\n"
            f"Available tools: {len(all_tools)}\n"
            f"Type [bold]exit[/bold] to return to command mode",
            title="MCP Chat"
        ))
        
        messages = [{"role": "system", "content": system_message}]
        
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
            
            # Check if response is a tool call
            try:
                tool_call = json.loads(llm_response)
                if isinstance(tool_call, dict) and "tool" in tool_call and "arguments" in tool_call:
                    self.console.print(Panel(
                        f"[bold]Executing tool:[/bold] {tool_call['tool']}\n"
                        f"[bold]With arguments:[/bold] {json.dumps(tool_call['arguments'], indent=2)}",
                        title="Assistant",
                        border_style="yellow"
                    ))
                    
                    try:
                        # Execute the tool without a status indicator
                        # (avoid nested live displays)
                        self.console.print(f"[bold green]Executing {tool_call['tool']}...[/bold green]")
                        result = await self.server_manager.execute_tool(
                            tool_call["tool"],
                            tool_call["arguments"]
                        )
                        
                        # Add assistant message to history
                        messages.append({"role": "assistant", "content": llm_response})
                        
                        # Add system message with tool result
                        if isinstance(result, str):
                            result_str = f"Tool execution result: {result}"
                        else:
                            formatted_result = self._serialize_complex_object(result)
                            result_str = f"Tool execution result: {formatted_result}"
                        messages.append({"role": "system", "content": result_str})
                        
                        # Get final response from LLM
                        self.console.print("[bold green]Processing result...[/bold green]")
                        self.console.print(messages)
                        final_response = await self.llm_provider.get_response(messages)
                        
                        self.console.print(Panel(
                            Markdown(final_response),
                            title="Assistant",
                            border_style="green"
                        ))
                        
                        # Add final response to messages
                        messages.append({"role": "assistant", "content": final_response})
                        
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
            
            except json.JSONDecodeError:
                # Not a tool call (not valid JSON), display response directly
                self.console.print(Panel(
                    Markdown(llm_response),
                    title="Assistant",
                    border_style="green"
                ))
                
                # Add response to messages
                messages.append({"role": "assistant", "content": llm_response})
    
    async def _cmd_config(self, args: str) -> None:
        """Handle the config command.
        
        Args:
            args: Command arguments.
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
            
            # Parse arguments
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
            args: Command arguments.
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
    
    async def _cmd_exit(self, args: str) -> None:
        """Handle the exit command.
        
        Args:
            args: Command arguments.
        """
        self.console.print("[yellow]Disconnecting from all servers...[/yellow]")
        await self.server_manager.disconnect_all()
        self.console.print("[green]Goodbye![/green]")
        sys.exit(0)
