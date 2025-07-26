"""MCP server handling and management."""
import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

try:
    from mcp.client.session import ClientSession
    from mcp.types import Implementation
except ImportError:
    logging.error("""
    Error importing MCP modules. This often happens when running in VSCode debug mode.
    
    Possible solutions:
    1. Run the application directly with 'python -m simple_mcp_client.main' instead of using VSCode debug
    2. Make sure the mcp package is installed in the Python environment VSCode is using
    3. Install the package in development mode with 'pip install -e .' in the project directory
    """)
    # Define placeholder classes to allow the module to load
    class ClientSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def initialize(self): return type('obj', (object,), {'serverInfo': None})
    
    class Implementation: pass

from ..config import ServerConfig
from .models import Tool, Resource, ResourceTemplate, Prompt, PromptFormat
from .connection import ConnectionManager
from .exceptions import (
    MCPServerError, ConnectionError, DisconnectedError,
    ToolExecutionError, ResourceAccessError, PromptError
)


class MCPServer:
    """Manages connection to an MCP server and tool execution."""

    def __init__(
        self, 
        name: str, 
        config: ServerConfig,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        backoff_factor: float = 1.5,
        health_check_interval: float = 60.0
    ) -> None:
        """Initialize an MCPServer instance.
        
        Args:
            name: The name of the server.
            config: The server configuration.
            max_retries: Maximum number of connection retries.
            retry_delay: Initial delay between retries in seconds.
            backoff_factor: Factor to increase delay between retries.
            health_check_interval: Interval between health checks in seconds.
        """
        self.name: str = name
        self.config: ServerConfig = config
        
        # Create connection manager
        self.connection_manager = ConnectionManager(
            server_name=name,
            server_type=config.type,
            url=config.url,
            command=config.command,
            args=config.args,
            env=config.env,
            max_retries=max_retries,
            retry_delay=retry_delay,
            backoff_factor=backoff_factor,
            health_check_interval=health_check_interval
        )
        
        self._tools: List[Tool] = []
        self._resources: List[Resource] = []
        self._resource_templates: List[ResourceTemplate] = []
        self._prompts: List[Prompt] = []
        self._prompt_formats: List[PromptFormat] = []
        self._server_info: Optional[Implementation] = None

    @property
    def is_connected(self) -> bool:
        """Check if the server is connected.
        
        Returns:
            True if the server is connected, False otherwise.
        """
        return self.connection_manager.is_connected

    @property
    def session(self) -> Optional[ClientSession]:
        """Get the client session.
        
        Returns:
            The client session if connected, None otherwise.
        """
        return self.connection_manager.session

    @property
    def server_info(self) -> Optional[Implementation]:
        """Get the server info.
        
        Returns:
            The server info if available, None otherwise.
        """
        return self._server_info
    
    @property
    def tools(self) -> List[Tool]:
        """Get the list of available tools.
        
        Returns:
            The list of available tools.
        """
        return self._tools
    
    @property
    def resources(self) -> List[Resource]:
        """Get the list of available resources.
        
        Returns:
            The list of available resources.
        """
        return self._resources
    
    @property
    def resource_templates(self) -> List[ResourceTemplate]:
        """Get the list of available resource templates.
        
        Returns:
            The list of available resource templates.
        """
        return self._resource_templates
    
    @property
    def prompts(self) -> List[Prompt]:
        """Get the list of available prompts.
        
        Returns:
            The list of available prompts.
        """
        return self._prompts
    
    @property
    def prompt_formats(self) -> List[PromptFormat]:
        """Get the list of available prompt formats.
        
        Returns:
            The list of available prompt formats.
        """
        return self._prompt_formats

    async def connect(self) -> bool:
        """Connect to the MCP server.
        
        Returns:
            True if the connection was successful, False otherwise.
        """
        if self.is_connected:
            logging.warning(f"Server {self.name} is already connected")
            return True
        
        try:
            success, server_info = await self.connection_manager.connect()
            if success:
                self._server_info = server_info
                # Load the server capabilities
                await self._load_capabilities()
                return True
            return False
        except Exception as e:
            logging.error(f"Error connecting to MCP server {self.name}: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        await self.connection_manager.disconnect()
        self._tools = []
        self._resources = []
        self._resource_templates = []
        self._prompts = []
        self._prompt_formats = []
        self._server_info = None

    async def _load_capabilities(self) -> None:
        """Load server capabilities (tools, resources, etc.)."""
        if not self.is_connected or not self.session:
            raise DisconnectedError(f"Server {self.name} not connected")
        
        # Define a helper function for loading capabilities with retry
        async def load_with_retry(operation, error_message, result_processor):
            try:
                result = await self.connection_manager.execute_with_retry(
                    operation,
                    operation_name=f"load_{error_message}"
                )
                return result_processor(result)
            except Exception as e:
                logging.warning(f"Error loading {error_message} from {self.name}: {e}")
                return []
        
        # Load tools
        self._tools = await load_with_retry(
            lambda: self.session.list_tools(),
            "tools",
            lambda result: [
                Tool(tool.name, tool.description, tool.inputSchema)
                for tool in getattr(result, "tools", [])
            ]
        )
        
        # Load resources
        self._resources = await load_with_retry(
            lambda: self.session.list_resources(),
            "resources",
            lambda result: [
                Resource(
                    getattr(resource, "uri", ""), 
                    getattr(resource, "name", "Unknown"),
                    getattr(resource, "mimeType", None),
                    getattr(resource, "description", None)
                )
                for resource in getattr(result, "resources", [])
            ]
        )
        
        # Load resource templates
        self._resource_templates = await load_with_retry(
            lambda: self.session.list_resource_templates(),
            "resource templates",
            lambda result: [
                ResourceTemplate(
                    getattr(template, "uriTemplate", ""), 
                    getattr(template, "name", "Unknown"),
                    getattr(template, "mimeType", None),
                    getattr(template, "description", None)
                )
                for template in getattr(result, "resourceTemplates", [])
            ]
        )
        
        # Load prompts if supported
        if hasattr(self.session, "list_prompts"):
            self._prompts = await load_with_retry(
                lambda: self.session.list_prompts(),
                "prompts",
                lambda result: [
                    Prompt(
                        prompt.name,
                        prompt.description,
                        getattr(prompt, "inputSchema", {})
                    )
                    for prompt in getattr(result, "prompts", [])
                    if hasattr(prompt, "name") and hasattr(prompt, "description")
                ]
            )
        else:
            self._prompts = []
            
        # Load prompt formats if supported
        if hasattr(self.session, "list_prompt_formats"):
            self._prompt_formats = await load_with_retry(
                lambda: self.session.list_prompt_formats(),
                "prompt formats",
                lambda result: [
                    PromptFormat(
                        format.name,
                        getattr(format, "description", None),
                        getattr(format, "schema", None)
                    )
                    for format in getattr(result, "promptFormats", [])
                    if hasattr(format, "name")
                ]
            )
        else:
            self._prompt_formats = []

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        retries: int = 2,
        delay: float = 1.0,
    ) -> Any:
        """Execute a tool.
        
        Args:
            tool_name: The name of the tool to execute.
            arguments: The arguments to pass to the tool.
            retries: The number of retries.
            delay: The delay between retries.
            
        Returns:
            The result of the tool execution.
            
        Raises:
            DisconnectedError: If the server is not connected.
            ToolExecutionError: If the tool execution fails.
        """
        if not self.is_connected or not self.session:
            raise DisconnectedError(f"Server {self.name} not connected")
        
        try:
            return await self.connection_manager.execute_with_retry(
                lambda: self.session.call_tool(tool_name, arguments),
                retries=retries,
                operation_name=f"execute_tool_{tool_name}"
            )
        except Exception as e:
            raise ToolExecutionError(f"Error executing tool {tool_name} on {self.name}: {str(e)}")

    async def read_resource(self, uri: str) -> Any:
        """Read a resource from the server.
        
        Args:
            uri: The URI of the resource to read.
            
        Returns:
            The content of the resource.
            
        Raises:
            DisconnectedError: If the server is not connected.
            ResourceAccessError: If the resource read fails.
        """
        if not self.is_connected or not self.session:
            raise DisconnectedError(f"Server {self.name} not connected")
        
        # Ensure uri is a string
        uri_str = str(uri) if uri is not None else ""
        if not uri_str:
            raise ValueError("Resource URI cannot be empty")
            
        try:
            return await self.connection_manager.execute_with_retry(
                lambda: self.session.read_resource(uri_str),
                operation_name=f"read_resource_{uri_str}"
            )
        except Exception as e:
            raise ResourceAccessError(f"Error reading resource {uri_str} from {self.name}: {str(e)}")

    async def has_tool(self, tool_name: str) -> bool:
        """Check if the server has a tool with the given name.
        
        Args:
            tool_name: The name of the tool to check.
            
        Returns:
            True if the server has the tool, False otherwise.
        """
        return any(tool.name == tool_name for tool in self._tools)

    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """Get a tool by name.
        
        Args:
            tool_name: The name of the tool to get.
            
        Returns:
            The tool if found, None otherwise.
        """
        for tool in self._tools:
            if tool.name == tool_name:
                return tool
        return None
        
    async def has_prompt(self, prompt_name: str) -> bool:
        """Check if the server has a prompt with the given name.
        
        Args:
            prompt_name: The name of the prompt to check.
            
        Returns:
            True if the server has the prompt, False otherwise.
        """
        return any(prompt.name == prompt_name for prompt in self._prompts)
    
    def get_prompt(self, prompt_name: str) -> Optional[Prompt]:
        """Get a prompt by name.
        
        Args:
            prompt_name: The name of the prompt to get.
            
        Returns:
            The prompt if found, None otherwise.
        """
        for prompt in self._prompts:
            if prompt.name == prompt_name:
                return prompt
        return None
    
    async def get_prompt_content(
        self,
        prompt_name: str,
        arguments: Dict[str, Any],
        format_name: Optional[str] = None,
        retries: int = 2,
        delay: float = 1.0,
    ) -> Any:
        """Get prompt content from the server.
        
        Args:
            prompt_name: The name of the prompt to get.
            arguments: The arguments to pass to the prompt.
            format_name: Optional name of the format to use.
            retries: The number of retries.
            delay: The delay between retries.
            
        Returns:
            The prompt content.
            
        Raises:
            DisconnectedError: If the server is not connected.
            PromptError: If the prompt retrieval fails.
        """
        if not self.is_connected or not self.session:
            raise DisconnectedError(f"Server {self.name} not connected")
        
        if not await self.has_prompt(prompt_name):
            raise PromptError(f"Prompt {prompt_name} not found on server {self.name}")
        
        # Check if session has get_prompt method
        if not hasattr(self.session, "get_prompt"):
            raise PromptError(f"Server {self.name} does not support getting prompts")
        
        try:
            # Define the operation based on whether format_name is provided
            async def get_prompt_operation():
                if format_name:
                    return await self.session.get_prompt(prompt_name, arguments, format_name)
                else:
                    return await self.session.get_prompt(prompt_name, arguments)
            
            return await self.connection_manager.execute_with_retry(
                get_prompt_operation,
                retries=retries,
                operation_name=f"get_prompt_{prompt_name}"
            )
        except Exception as e:
            raise PromptError(f"Error getting prompt {prompt_name} from {self.name}: {str(e)}")
