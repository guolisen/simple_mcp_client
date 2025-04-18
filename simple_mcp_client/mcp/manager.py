"""Server manager for handling multiple MCP servers."""
import logging
from typing import Dict, List, Optional, Any

from ..config import Configuration, ServerConfig
from .server import MCPServer, Tool, Resource, ResourceTemplate, Prompt, PromptFormat


class ServerManager:
    """Manages multiple MCP servers."""

    def __init__(self, config: Configuration) -> None:
        """Initialize a ServerManager instance.
        
        Args:
            config: The client configuration.
        """
        self.config = config
        self.servers: Dict[str, MCPServer] = {}
        self._load_servers()

    def _load_servers(self) -> None:
        """Load servers from configuration."""
        for name, server_config in self.config.config.mcpServers.items():
            self.servers[name] = MCPServer(name, server_config)

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

    def add_server(self, name: str, config: ServerConfig) -> None:
        """Add a new server to the manager.
        
        Args:
            name: The name of the new server.
            config: The configuration for the new server.
        """
        if name in self.servers:
            logging.warning(f"Overwriting existing server configuration for {name}")
        
        self.servers[name] = MCPServer(name, config)
        
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
    
    def get_all_prompts(self) -> List[List[Prompt]]:
        """Get all prompts from all connected servers.
        
        Returns:
            A list of all prompts.
        """
        prompts = []
        for server in self.get_connected_servers():
            prompts.extend(server.prompts)
        return prompts
    
    def get_all_prompt_formats(self) -> List[List[PromptFormat]]:
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

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any],
                          server_name: Optional[str] = None) -> Any:
        """Execute a tool on a server.
        
        Args:
            tool_name: The name of the tool to execute.
            arguments: The arguments to pass to the tool.
            server_name: The name of the server to execute the tool on.
                        If not provided, will try to find a server with the tool.
            
        Returns:
            The result of the tool execution.
            
        Raises:
            RuntimeError: If no server with the tool is found or connected.
        """
        if server_name:
            server = self.get_server(server_name)
            if not server:
                raise RuntimeError(f"Server {server_name} not found")
            if not server.is_connected:
                raise RuntimeError(f"Server {server_name} is not connected")
            if not await server.has_tool(tool_name):
                raise RuntimeError(f"Server {server_name} does not have tool {tool_name}")
            
            return await server.execute_tool(tool_name, arguments)
        
        # Try to find a server with the tool
        server = self.get_server_with_tool(tool_name)
        if not server:
            raise RuntimeError(f"No connected server found with tool {tool_name}")
        
        return await server.execute_tool(tool_name, arguments)
    
    async def get_resource(self, uri: str, server_name: Optional[str] = None) -> Any:
        """Get a resource from a server.
        
        Args:
            uri: The URI of the resource to get.
            server_name: The name of the server to get the resource from.
                        If not provided, will try to find a server that has the resource.
            
        Returns:
            The resource content.
            
        Raises:
            RuntimeError: If no server with the resource is found or connected.
        """
        if server_name:
            server = self.get_server(server_name)
            if not server:
                raise RuntimeError(f"Server {server_name} not found")
            if not server.is_connected:
                raise RuntimeError(f"Server {server_name} is not connected")
            
            return await server.read_resource(uri)
        
        # Try to find a server with the resource in all connected servers
        for server in self.get_connected_servers():
            try:
                return await server.read_resource(uri)
            except Exception:
                continue
        
        raise RuntimeError(f"No connected server found that can provide resource {uri}")
    
    async def get_prompt(self, prompt_name: str, arguments: Dict[str, Any],
                        format_name: Optional[str] = None,
                        server_name: Optional[str] = None) -> Any:
        """Get a prompt from a server.
        
        Args:
            prompt_name: The name of the prompt to get.
            arguments: The arguments to pass to the prompt.
            format_name: Optional name of the format to use.
            server_name: The name of the server to get the prompt from.
                        If not provided, will try to find a server with the prompt.
            
        Returns:
            The prompt content.
            
        Raises:
            RuntimeError: If no server with the prompt is found or connected.
        """
        if server_name:
            server = self.get_server(server_name)
            if not server:
                raise RuntimeError(f"Server {server_name} not found")
            if not server.is_connected:
                raise RuntimeError(f"Server {server_name} is not connected")
            if not await server.has_prompt(prompt_name):
                raise RuntimeError(f"Server {server_name} does not have prompt {prompt_name}")
            
            return await server.get_prompt_content(prompt_name, arguments, format_name)
        
        # Try to find a server with the prompt
        server = self.get_server_with_prompt(prompt_name)
        if not server:
            raise RuntimeError(f"No connected server found with prompt {prompt_name}")
        
        return await server.get_prompt_content(prompt_name, arguments, format_name)
