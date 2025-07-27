"""Server manager for handling multiple MCP servers."""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from ..config import Configuration, ServerConfig
from .server import MCPServer
from .models import Tool, Resource, ResourceTemplate, Prompt, PromptFormat
from .exceptions import (
    MCPServerError, ConnectionError, DisconnectedError,
    ToolExecutionError, ResourceAccessError, PromptError
)


class ServerManager:
    """Manages multiple MCP servers."""

    def __init__(
        self, 
        config: Configuration,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        backoff_factor: float = 1.5,
        health_check_interval: float = 60.0
    ) -> None:
        """Initialize a ServerManager instance.
        
        Args:
            config: The client configuration.
            max_retries: Maximum number of connection retries.
            retry_delay: Initial delay between retries in seconds.
            backoff_factor: Factor to increase delay between retries.
            health_check_interval: Interval between health checks in seconds.
        """
        self.config = config
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor
        self.health_check_interval = health_check_interval
        self.servers: Dict[str, MCPServer] = {}
        self._load_servers()

    def _load_servers(self) -> None:
        """Load servers from configuration."""
        for name, server_config in self.config.config.mcpServers.items():
            self.servers[name] = MCPServer(
                name, 
                server_config,
                max_retries=self.max_retries,
                retry_delay=self.retry_delay,
                backoff_factor=self.backoff_factor,
                health_check_interval=self.health_check_interval
            )

    async def connect_server(self, name: str) -> bool:
        """Connect to a server.
        
        Args:
            name: The name of the server to connect to.
            
        Returns:
            True if the connection was successful, False otherwise.
        """
        if name not in self.servers:
            logging.error(f"Server {name} not found")
            return False
        
        return await self.servers[name].connect()

    async def disconnect_server(self, name: str) -> None:
        """Disconnect from a server.
        
        Args:
            name: The name of the server to disconnect from.
        """
        if name not in self.servers:
            logging.error(f"Server {name} not found")
            return
        
        await self.servers[name].disconnect()

    async def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        for name in list(self.servers.keys()):
            await self.disconnect_server(name)

    def get_server(self, name: str) -> Optional[MCPServer]:
        """Get a server by name.
        
        Args:
            name: The name of the server to get.
            
        Returns:
            The server if found, None otherwise.
        """
        return self.servers.get(name)

    def get_connected_servers(self) -> List[MCPServer]:
        """Get all connected servers.
        
        Returns:
            A list of connected servers.
        """
        return [server for server in self.servers.values() if server.is_connected]

    def get_server_with_tool(self, tool_name: str) -> Optional[MCPServer]:
        """Find a server that has a tool with the given name.
        
        Args:
            tool_name: The name of the tool to find.
            
        Returns:
            The server that has the tool if found, None otherwise.
        """
        for server in self.get_connected_servers():
            if any(tool.name == tool_name for tool in server.tools):
                return server
        return None

    def add_server(
        self, 
        name: str, 
        config: ServerConfig
    ) -> None:
        """Add a new server to the manager.
        
        Args:
            name: The name of the new server.
            config: The configuration for the new server.
        """
        if name in self.servers:
            logging.warning(f"Overwriting existing server configuration for {name}")
        
        self.servers[name] = MCPServer(
            name, 
            config,
            max_retries=self.max_retries,
            retry_delay=self.retry_delay,
            backoff_factor=self.backoff_factor,
            health_check_interval=self.health_check_interval
        )
        
        # Update configuration
        self.config.config.mcpServers[name] = config
        self.config.save_config(self.config.config)

    async def remove_server(self, name: str) -> bool:
        """Remove a server from the manager.
        
        Args:
            name: The name of the server to remove.
            
        Returns:
            True if the server was removed, False otherwise.
        """
        if name not in self.servers:
            return False
        
        # Disconnect if connected
        if self.servers[name].is_connected:
            await self.disconnect_server(name)
        
        # Remove from servers
        del self.servers[name]
        
        # Remove from configuration
        if name in self.config.config.mcpServers:
            del self.config.config.mcpServers[name]
            self.config.save_config(self.config.config)
        
        return True

    def get_all_tools(self) -> Dict[str, List[Tool]]:
        """Get all tools from all connected servers.
        
        Returns:
            A dictionary mapping server names to lists of tools.
        """
        tools = {}
        for server in self.get_connected_servers():
            tools[server.name] = server.tools
        return tools
    
    def get_all_prompts(self) -> List[Prompt]:
        """Get all prompts from all connected servers.
        
        Returns:
            A list of all prompts.
        """
        prompts = []
        for server in self.get_connected_servers():
            prompts.extend(server.prompts)
        return prompts
    
    def get_all_prompt_formats(self) -> List[PromptFormat]:
        """Get all prompt formats from all connected servers.
        
        Returns:
            A list of all prompt formats.
        """
        formats = []
        for server in self.get_connected_servers():
            formats.extend(server.prompt_formats)
        return formats
    
    def get_server_with_prompt(self, prompt_name: str) -> Optional[MCPServer]:
        """Find a server that has a prompt with the given name.
        
        Args:
            prompt_name: The name of the prompt to find.
            
        Returns:
            The server that has the prompt if found, None otherwise.
        """
        for server in self.get_connected_servers():
            if any(prompt.name == prompt_name for prompt in server.prompts):
                return server
        return None

    async def execute_tool(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any],
        server_name: Optional[str] = None,
        retries: int = 2,
        print_formatting: bool = True
    ) -> Any:
        """Execute a tool on a server.
        
        Args:
            tool_name: The name of the tool to execute.
            arguments: The arguments to pass to the tool.
            server_name: The name of the server to execute the tool on.
                        If not provided, will try to find a server with the tool.
            retries: Number of retries for the operation.
            print_formatting: Whether to print formatted tool call and result.
            
        Returns:
            The result of the tool execution.
            
        Raises:
            MCPServerError: If no server with the tool is found or connected.
            ToolExecutionError: If the tool execution fails.
        """
        # Find the appropriate server
        if server_name:
            server = self.get_server(server_name)
            if not server:
                raise MCPServerError(f"Server {server_name} not found")
        else:
            # Try to find a server with the tool
            server = self.get_server_with_tool(tool_name)
            if not server:
                raise MCPServerError(f"No connected server found with tool {tool_name}")
        
        # Record start time
        start_time = datetime.now()
        
        # Print formatted tool call if requested
        if print_formatting:
            # Import here to avoid circular imports
            from ..console.tool_formatter import default_formatter
            default_formatter.print_tool_call(server.name, tool_name, arguments, start_time)
        
        try:
            # The server.execute_tool method will handle reconnection if needed
            result = await server.execute_tool(tool_name, arguments, retries=retries)
            
            # Record end time
            end_time = datetime.now()
            
            # Print formatted tool result if requested
            if print_formatting:
                # Import here to avoid circular imports
                from ..console.tool_formatter import default_formatter
                default_formatter.print_tool_result(
                    server.name, tool_name, result, start_time, end_time, success=True
                )
            
            return result
            
        except Exception as e:
            # Record end time for error case
            end_time = datetime.now()
            
            # Print formatted error result if requested
            if print_formatting:
                # Import here to avoid circular imports
                from ..console.tool_formatter import default_formatter
                default_formatter.print_tool_result(
                    server.name, tool_name, str(e), start_time, end_time, success=False
                )
            
            # Re-raise the exception
            raise
    
    async def get_resource(
        self, 
        uri: str, 
        server_name: Optional[str] = None,
        retries: int = 2
    ) -> Any:
        """Get a resource from a server.
        
        Args:
            uri: The URI of the resource to get.
            server_name: The name of the server to get the resource from.
                        If not provided, will try to find a server that has the resource.
            retries: Number of retries for the operation.
            
        Returns:
            The resource content.
            
        Raises:
            MCPServerError: If no server with the resource is found or connected.
            ResourceAccessError: If the resource access fails.
        """
        if server_name:
            server = self.get_server(server_name)
            if not server:
                raise MCPServerError(f"Server {server_name} not found")
            
            # The server.read_resource method will handle reconnection if needed
            return await server.read_resource(uri)
        
        # Try to find a server with the resource in all connected servers
        errors = []
        for server in self.get_connected_servers():
            try:
                # The server.read_resource method will handle reconnection if needed
                return await server.read_resource(uri)
            except Exception as e:
                errors.append(f"{server.name}: {str(e)}")
                continue
        
        error_details = "\n".join(errors) if errors else "No connected servers available"
        raise ResourceAccessError(f"No connected server found that can provide resource {uri}. Errors: {error_details}")
    
    async def get_prompt(
        self, 
        prompt_name: str, 
        arguments: Dict[str, Any],
        format_name: Optional[str] = None,
        server_name: Optional[str] = None,
        retries: int = 2
    ) -> Any:
        """Get a prompt from a server.
        
        Args:
            prompt_name: The name of the prompt to get.
            arguments: The arguments to pass to the prompt.
            format_name: Optional name of the format to use.
            server_name: The name of the server to get the prompt from.
                        If not provided, will try to find a server with the prompt.
            retries: Number of retries for the operation.
            
        Returns:
            The prompt content.
            
        Raises:
            MCPServerError: If no server with the prompt is found or connected.
            PromptError: If the prompt retrieval fails.
        """
        if server_name:
            server = self.get_server(server_name)
            if not server:
                raise MCPServerError(f"Server {server_name} not found")
            
            # The server.get_prompt_content method will handle reconnection if needed
            return await server.get_prompt_content(
                prompt_name, arguments, format_name, retries=retries
            )
        
        # Try to find a server with the prompt
        server = self.get_server_with_prompt(prompt_name)
        if not server:
            raise MCPServerError(f"No connected server found with prompt {prompt_name}")
        
        # The server.get_prompt_content method will handle reconnection if needed
        return await server.get_prompt_content(
            prompt_name, arguments, format_name, retries=retries
        )
