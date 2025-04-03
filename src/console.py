"""Console interface for MCP Client."""

import cmd
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Generator
import yaml

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from .client import Client
from .config import MCPServerConfig
from .llm.base import Conversation


class MCPConsole(cmd.Cmd):
    """Console interface for MCP Client."""
    
    intro = """
MCP Client Console
Type 'help' or '?' to list commands.
Type 'exit' or 'quit' to exit.
"""
    
    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        """Initialize the console.
        
        Args:
            config_path: Path to configuration file. If None, loads from default locations.
        """
        super().__init__()
        
        # Initialize client
        self.client = Client(config_path)
        
        # Set prompt from configuration
        self.prompt = self.client.config.console.prompt
        
        # Initialize rich console
        self.console = Console()
        
        # Initialize prompt toolkit session
        history_path = os.path.expanduser(self.client.config.console.history_file)
        self.session = PromptSession(
            history=FileHistory(history_path),
            auto_suggest=AutoSuggestFromHistory(),
            enable_history_search=True
        )
        
        # Initialize command completers
        self._update_completers()
    
    def _update_completers(self) -> None:
        """Update command completers."""
        # Get available commands
        commands = [
            "help", "exit", "quit",
            "chat", "servers", "connect", "disconnect",
            "tools", "call", "resources", "read",
            "llm", "providers", "models", "config",
            "save", "clear"
        ]
        
        # Get available servers
        servers = list(self.client.servers.keys())
        
        # Get available LLM providers
        providers = self.client.get_available_llm_providers()
        
        # Create completers
        self.command_completer = WordCompleter(commands)
        self.server_completer = WordCompleter(servers)
        self.provider_completer = WordCompleter(providers)
    
    def cmdloop(self, intro=None) -> None:
        """Override cmdloop to use prompt_toolkit."""
        if intro is not None:
            self.intro = intro
        if self.intro:
            self.console.print(self.intro)
        
        while True:
            try:
                line = self.session.prompt(self.prompt, completer=self.command_completer)
                line = line.strip()
                if not line:
                    continue
                
                if line == "EOF":
                    self.console.print("Exiting...")
                    break
                
                if line in ["exit", "quit"]:
                    self.console.print("Exiting...")
                    break
                
                self.onecmd(line)
            except KeyboardInterrupt:
                self.console.print("^C")
            except EOFError:
                self.console.print("Exiting...")
                break
            except Exception as e:
                self.console.print(f"Error: {e}", style="bold red")
    
    def emptyline(self) -> bool:
        """Handle empty line."""
        return False
    
    def default(self, line: str) -> None:
        """Handle unknown command."""
        self.console.print(f"Unknown command: {line}", style="bold red")
        self.console.print("Type 'help' or '?' to list commands.", style="italic")
    
    def do_help(self, arg: str) -> None:
        """Show help."""
        if not arg:
            self.console.print("Available commands:", style="bold")
            commands = [
                ("help", "Show help"),
                ("exit, quit", "Exit the console"),
                ("chat", "Start a chat with the configured LLM"),
                ("servers", "List configured MCP servers"),
                ("connect", "Connect to an MCP server"),
                ("disconnect", "Disconnect from an MCP server"),
                ("tools", "List available tools from connected servers"),
                ("call", "Call a tool on a connected server"),
                ("resources", "List available resources from connected servers"),
                ("read", "Read a resource from a connected server"),
                ("llm", "Show current LLM provider and model"),
                ("providers", "List available LLM providers"),
                ("models", "List available LLM models for a provider"),
                ("config", "Show or modify configuration"),
                ("save", "Save configuration to file"),
                ("clear", "Clear the screen")
            ]
            
            table = Table(show_header=True, header_style="bold")
            table.add_column("Command")
            table.add_column("Description")
            
            for command, description in commands:
                table.add_row(command, description)
            
            self.console.print(table)
        else:
            # Get help for specific command
            method = getattr(self, f"help_{arg}", None)
            if method:
                method()
            else:
                self.console.print(f"No help for {arg}", style="bold red")
    
    def help_chat(self) -> None:
        """Show help for chat command."""
        self.console.print("chat [message]", style="bold")
        self.console.print("Start a chat with the configured LLM.")
        self.console.print("If no message is provided, enters interactive chat mode.")
        self.console.print("In interactive chat mode, type 'exit' to return to the console.")
    
    def help_servers(self) -> None:
        """Show help for servers command."""
        self.console.print("servers", style="bold")
        self.console.print("List configured MCP servers.")
    
    def help_connect(self) -> None:
        """Show help for connect command."""
        self.console.print("connect [server_name]", style="bold")
        self.console.print("Connect to an MCP server.")
        self.console.print("If no server name is provided, connects to the default server.")
    
    def help_disconnect(self) -> None:
        """Show help for disconnect command."""
        self.console.print("disconnect [server_name]", style="bold")
        self.console.print("Disconnect from an MCP server.")
        self.console.print("If no server name is provided, disconnects from the default server.")
        self.console.print("Use 'disconnect all' to disconnect from all servers.")
    
    def help_tools(self) -> None:
        """Show help for tools command."""
        self.console.print("tools [server_name]", style="bold")
        self.console.print("List available tools from connected servers.")
        self.console.print("If no server name is provided, lists tools from the default server.")
    
    def help_call(self) -> None:
        """Show help for call command."""
        self.console.print("call <tool_name> [arguments] [server_name]", style="bold")
        self.console.print("Call a tool on a connected server.")
        self.console.print("Arguments should be provided as a JSON object.")
        self.console.print("If no server name is provided, calls the tool on the default server.")
        self.console.print("Example: call get_cluster_status {} k8s_server")
    
    def help_resources(self) -> None:
        """Show help for resources command."""
        self.console.print("resources [server_name]", style="bold")
        self.console.print("List available resources from connected servers.")
        self.console.print("If no server name is provided, lists resources from the default server.")
    
    def help_read(self) -> None:
        """Show help for read command."""
        self.console.print("read <uri> [server_name]", style="bold")
        self.console.print("Read a resource from a connected server.")
        self.console.print("If no server name is provided, reads the resource from the default server.")
    
    def help_llm(self) -> None:
        """Show help for llm command."""
        self.console.print("llm [provider] [model]", style="bold")
        self.console.print("Show or set the current LLM provider and model.")
        self.console.print("If no provider is provided, shows the current provider and model.")
        self.console.print("If a provider is provided, sets the provider and optionally the model.")
    
    def help_providers(self) -> None:
        """Show help for providers command."""
        self.console.print("providers", style="bold")
        self.console.print("List available LLM providers.")
    
    def help_models(self) -> None:
        """Show help for models command."""
        self.console.print("models [provider]", style="bold")
        self.console.print("List available LLM models for a provider.")
        self.console.print("If no provider is provided, lists models for the current provider.")
    
    def help_config(self) -> None:
        """Show help for config command."""
        self.console.print("config [section] [key] [value]", style="bold")
        self.console.print("Show or modify configuration.")
        self.console.print("If no arguments are provided, shows the entire configuration.")
        self.console.print("If only a section is provided, shows that section of the configuration.")
        self.console.print("If a section and key are provided, shows that key in the configuration.")
        self.console.print("If a section, key, and value are provided, sets that key in the configuration.")
    
    def help_save(self) -> None:
        """Show help for save command."""
        self.console.print("save [path]", style="bold")
        self.console.print("Save configuration to file.")
        self.console.print("If no path is provided, saves to the default configuration file.")
    
    def help_clear(self) -> None:
        """Show help for clear command."""
        self.console.print("clear", style="bold")
        self.console.print("Clear the screen.")
    
    def do_chat(self, arg: str) -> None:
        """Start a chat with the configured LLM."""
        if not arg:
            # Interactive chat mode
            self.console.print("Starting chat with LLM. Type 'exit' to return to the console.", style="bold")
            self.console.print(f"Using provider: {self.client.config.llm.provider}, model: {self.client.config.llm.model}", style="italic")
            
            while True:
                try:
                    user_input = self.session.prompt("You: ")
                    if user_input.lower() in ["exit", "quit"]:
                        break
                    
                    self.console.print("AI: ", end="")
                    
                    # Stream response
                    full_response = ""
                    for chunk in self.client.chat(user_input, stream=True):
                        self.console.print(chunk, end="")
                        full_response += chunk
                    
                    self.console.print()  # New line after response
                except KeyboardInterrupt:
                    self.console.print("^C")
                    break
                except EOFError:
                    break
                except Exception as e:
                    self.console.print(f"Error: {e}", style="bold red")
                    break
        else:
            # Single message
            try:
                self.console.print("AI: ", end="")
                
                # Stream response
                for chunk in self.client.chat(arg, stream=True):
                    self.console.print(chunk, end="")
                
                self.console.print()  # New line after response
            except Exception as e:
                self.console.print(f"Error: {e}", style="bold red")
    
    def do_servers(self, arg: str) -> None:
        """List configured MCP servers."""
        if not self.client.servers:
            self.console.print("No servers configured.", style="italic")
            return
        
        table = Table(show_header=True, header_style="bold")
        table.add_column("Name")
        table.add_column("URL")
        table.add_column("Transport")
        table.add_column("Connected")
        table.add_column("Default")
        
        default_server = self.client.get_server()
        
        for name, server in self.client.servers.items():
            is_default = default_server and default_server.name == name
            table.add_row(
                name,
                server.config.url,
                server.config.transport,
                "Yes" if server.is_connected() else "No",
                "Yes" if is_default else "No"
            )
        
        self.console.print(table)
    
    def do_connect(self, arg: str) -> None:
        """Connect to an MCP server."""
        server_name = arg if arg else None
        
        if self.client.connect_server(server_name):
            server = self.client.get_server(server_name)
            self.console.print(f"Connected to server: {server.name}", style="bold green")
        else:
            self.console.print(f"Failed to connect to server: {server_name or 'default'}", style="bold red")
    
    def do_disconnect(self, arg: str) -> None:
        """Disconnect from an MCP server."""
        if arg == "all":
            self.client.disconnect_all_servers()
            self.console.print("Disconnected from all servers.", style="bold green")
        else:
            server_name = arg if arg else None
            self.client.disconnect_server(server_name)
            self.console.print(f"Disconnected from server: {server_name or 'default'}", style="bold green")
    
    def do_tools(self, arg: str) -> None:
        """List available tools from connected servers."""
        server_name = arg if arg else None
        server = self.client.get_server(server_name)
        
        if not server:
            self.console.print(f"Server not found: {server_name or 'default'}", style="bold red")
            return
        
        if not server.is_connected():
            if not self.client.connect_server(server_name):
                self.console.print(f"Failed to connect to server: {server_name or 'default'}", style="bold red")
                return
        
        tools = self.client.list_tools(server_name)
        
        if not tools:
            self.console.print(f"No tools available from server: {server.name}", style="italic")
            return
        
        table = Table(show_header=True, header_style="bold")
        table.add_column("Name")
        table.add_column("Description")
        
        for tool in tools:
            table.add_row(
                tool.get("name", ""),
                tool.get("description", "")
            )
        
        self.console.print(f"Tools available from server: {server.name}", style="bold")
        self.console.print(table)
    
    def do_call(self, arg: str) -> None:
        """Call a tool on a connected server."""
        args = arg.split(maxsplit=2)
        
        if not args:
            self.console.print("Tool name required.", style="bold red")
            self.help_call()
            return
        
        tool_name = args[0]
        arguments = {}
        server_name = None
        
        if len(args) > 1:
            try:
                arguments = json.loads(args[1])
            except json.JSONDecodeError:
                # If the second argument is not valid JSON, assume it's the server name
                server_name = args[1]
        
        if len(args) > 2:
            server_name = args[2]
        
        try:
            result = self.client.call_tool(tool_name, arguments, server_name)
            
            # Pretty print the result
            if isinstance(result, str):
                try:
                    # Try to parse as JSON
                    json_result = json.loads(result)
                    self.console.print(json.dumps(json_result, indent=2), soft_wrap=True)
                except json.JSONDecodeError:
                    # Just print as string
                    self.console.print(result)
            elif isinstance(result, dict) or isinstance(result, list):
                self.console.print(json.dumps(result, indent=2), soft_wrap=True)
            else:
                self.console.print(result)
        except Exception as e:
            self.console.print(f"Error calling tool: {e}", style="bold red")
    
    def do_resources(self, arg: str) -> None:
        """List available resources from connected servers."""
        server_name = arg if arg else None
        server = self.client.get_server(server_name)
        
        if not server:
            self.console.print(f"Server not found: {server_name or 'default'}", style="bold red")
            return
        
        if not server.is_connected():
            if not self.client.connect_server(server_name):
                self.console.print(f"Failed to connect to server: {server_name or 'default'}", style="bold red")
                return
        
        resources = self.client.list_resources(server_name)
        
        if not resources:
            self.console.print(f"No resources available from server: {server.name}", style="italic")
            return
        
        table = Table(show_header=True, header_style="bold")
        table.add_column("URI")
        table.add_column("Name")
        table.add_column("MIME Type")
        
        for resource in resources:
            table.add_row(
                resource.get("uri", ""),
                resource.get("name", ""),
                resource.get("mimeType", "")
            )
        
        self.console.print(f"Resources available from server: {server.name}", style="bold")
        self.console.print(table)
    
    def do_read(self, arg: str) -> None:
        """Read a resource from a connected server."""
        args = arg.split(maxsplit=1)
        
        if not args:
            self.console.print("Resource URI required.", style="bold red")
            self.help_read()
            return
        
        uri = args[0]
        server_name = args[1] if len(args) > 1 else None
        
        try:
            content = self.client.read_resource(uri, server_name)
            
            if content is None:
                self.console.print(f"Resource not found: {uri}", style="bold red")
                return
            
            # Pretty print the content
            if isinstance(content, str):
                try:
                    # Try to parse as JSON
                    json_content = json.loads(content)
                    self.console.print(json.dumps(json_content, indent=2), soft_wrap=True)
                except json.JSONDecodeError:
                    # Just print as string
                    self.console.print(content)
            elif isinstance(content, dict) or isinstance(content, list):
                self.console.print(json.dumps(content, indent=2), soft_wrap=True)
            else:
                self.console.print(content)
        except Exception as e:
            self.console.print(f"Error reading resource: {e}", style="bold red")
    
    def do_llm(self, arg: str) -> None:
        """Show or set the current LLM provider and model."""
        args = arg.split(maxsplit=1)
        
        if not args or not args[0]:
            # Show current provider and model
            self.console.print(f"Current LLM provider: {self.client.config.llm.provider}", style="bold")
            self.console.print(f"Current LLM model: {self.client.config.llm.model}")
            return
        
        provider = args[0]
        model = args[1] if len(args) > 1 else None
        
        if provider not in self.client.get_available_llm_providers():
            self.console.print(f"Unknown LLM provider: {provider}", style="bold red")
            self.console.print(f"Available providers: {', '.join(self.client.get_available_llm_providers())}")
            return
        
        if model is None:
            # Use the default model for the provider
            models = self.client.get_available_llm_models(provider)
            if models:
                model = models[0]
            else:
                self.console.print(f"No models available for provider: {provider}", style="bold red")
                return
        
        try:
            self.client.set_llm(provider, model)
            self.console.print(f"Set LLM provider to {provider} and model to {model}", style="bold green")
        except Exception as e:
            self.console.print(f"Error setting LLM: {e}", style="bold red")
    
    def do_providers(self, arg: str) -> None:
        """List available LLM providers."""
        providers = self.client.get_available_llm_providers()
        
        table = Table(show_header=True, header_style="bold")
        table.add_column("Provider")
        table.add_column("Current")
        
        current_provider = self.client.config.llm.provider
        
        for provider in providers:
            table.add_row(
                provider,
                "Yes" if provider == current_provider else "No"
            )
        
        self.console.print(table)
    
    def do_models(self, arg: str) -> None:
        """List available LLM models for a provider."""
        provider = arg if arg else None
        
        if provider and provider not in self.client.get_available_llm_providers():
            self.console.print(f"Unknown LLM provider: {provider}", style="bold red")
            self.console.print(f"Available providers: {', '.join(self.client.get_available_llm_providers())}")
            return
        
        models = self.client.get_available_llm_models(provider)
        
        if not models:
            self.console.print(f"No models available for provider: {provider or self.client.config.llm.provider}", style="italic")
            return
        
        table = Table(show_header=True, header_style="bold")
        table.add_column("Model")
        table.add_column("Current")
        
        current_model = self.client.config.llm.model
        
        for model in models:
            table.add_row(
                model,
                "Yes" if model == current_model else "No"
            )
        
        self.console.print(f"Models available for provider: {provider or self.client.config.llm.provider}", style="bold")
        self.console.print(table)
    
    def do_config(self, arg: str) -> None:
        """Show or modify configuration."""
        args = arg.split(maxsplit=2)
        
        if not args or not args[0]:
            # Show entire configuration
            config_dict = self.client.config.model_dump()
            self.console.print(yaml.dump(config_dict, default_flow_style=False))
            return
        
        section = args[0]
        
        if section not in ["llm", "mcp_servers", "console"]:
            self.console.print(f"Unknown configuration section: {section}", style="bold red")
            self.console.print("Available sections: llm, mcp_servers, console")
            return
        
        if len(args) == 1:
            # Show section
            section_dict = getattr(self.client.config, section).model_dump()
            self.console.print(yaml.dump(section_dict, default_flow_style=False))
            return
        
        key = args[1]
        
        if len(args) == 2:
            # Show key
            section_obj = getattr(self.client.config, section)
            if hasattr(section_obj, key):
                value = getattr(section_obj, key)
                if isinstance(value, dict):
                    self.console.print(yaml.dump(value, default_flow_style=False))
                else:
                    self.console.print(value)
            else:
                self.console.print(f"Unknown key: {key} in section: {section}", style="bold red")
            return
        
        value = args[2]
        
        # Set key
        section_obj = getattr(self.client.config, section)
        if hasattr(section_obj, key):
            # Try to convert value to the appropriate type
            old_value = getattr(section_obj, key)
            if isinstance(old_value, bool):
                value = value.lower() in ["true", "yes", "1"]
            elif isinstance(old_value, int):
                value = int(value)
            elif isinstance(old_value, float):
                value = float(value)
            
            setattr(section_obj, key, value)
            self.console.print(f"Set {section}.{key} to {value}", style="bold green")
            
            # Update client if necessary
            if section == "llm" and key in ["provider", "model", "api_key", "api_base"]:
                self.client.set_llm(
                    self.client.config.llm.provider,
                    self.client.config.llm.model,
                    api_key=self.client.config.llm.api_key,
                    api_base=self.client.config.llm.api_base
                )
            
            # Update completers
            self._update_completers()
        else:
            self.console.print(f"Unknown key: {key} in section: {section}", style="bold red")
    
    def do_save(self, arg: str) -> None:
        """Save configuration to file."""
        path = arg if arg else os.path.expanduser("~/.config/mcp-client/config.yaml")
        
        try:
            self.client.save_config(path)
            self.console.print(f"Configuration saved to {path}", style="bold green")
        except Exception as e:
            self.console.print(f"Error saving configuration: {e}", style="bold red")
    
    def do_clear(self, arg: str) -> None:
        """Clear the screen."""
        os.system("cls" if os.name == "nt" else "clear")
    
    def do_exit(self, arg: str) -> bool:
        """Exit the console."""
        self.client.close()
        return True
    
    def do_quit(self, arg: str) -> bool:
        """Exit the console."""
        return self.do_exit(arg)
    
    def do_EOF(self, arg: str) -> bool:
        """Exit the console."""
        return self.do_exit(arg)
