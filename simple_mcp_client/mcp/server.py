"""MCP server handling and management."""
import asyncio
import logging
import os
import shutil
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.types import Implementation

from ..config import ServerConfig


class Tool:
    """Represents a tool with its properties."""

    def __init__(
        self, name: str, description: str, input_schema: Dict[str, Any]
    ) -> None:
        """Initialize a Tool instance.
        
        Args:
            name: The name of the tool.
            description: The description of the tool.
            input_schema: The JSON schema for the tool's input.
        """
        self.name: str = name
        self.description: str = description
        self.input_schema: Dict[str, Any] = input_schema

    def format_for_llm(self) -> str:
        """Format tool information for LLM.

        Returns:
            A formatted string describing the tool.
        """
        args_desc = []
        if "properties" in self.input_schema:
            for param_name, param_info in self.input_schema["properties"].items():
                arg_desc = (
                    f"- {param_name}: {param_info.get('description', 'No description')}"
                )
                if param_name in self.input_schema.get("required", []):
                    arg_desc += " (required)"
                args_desc.append(arg_desc)

        return f"""
Tool: {self.name}
Description: {self.description}
Arguments:
{chr(10).join(args_desc)}
"""


class Resource:
    """Represents a resource with its properties."""

    def __init__(
        self, uri: str, name: str, mime_type: Optional[str] = None, description: Optional[str] = None
    ) -> None:
        """Initialize a Resource instance.
        
        Args:
            uri: The URI of the resource.
            name: The name of the resource.
            mime_type: The MIME type of the resource.
            description: The description of the resource.
        """
        # Ensure uri is a string
        self.uri: str = str(uri) if uri is not None else ""
        self.name: str = name
        self.mime_type: Optional[str] = mime_type
        self.description: Optional[str] = description


class ResourceTemplate:
    """Represents a resource template with its properties."""

    def __init__(
        self, uri_template: str, name: str, mime_type: Optional[str] = None, description: Optional[str] = None
    ) -> None:
        """Initialize a ResourceTemplate instance.
        
        Args:
            uri_template: The URI template of the resource.
            name: The name of the resource.
            mime_type: The MIME type of the resource.
            description: The description of the resource.
        """
        # Ensure uri_template is a string
        self.uri_template: str = str(uri_template) if uri_template is not None else ""
        self.name: str = name
        self.mime_type: Optional[str] = mime_type
        self.description: Optional[str] = description


class Prompt:
    """Represents a prompt with its properties."""

    def __init__(
        self, name: str, description: str, input_schema: Dict[str, Any]
    ) -> None:
        """Initialize a Prompt instance.
        
        Args:
            name: The name of the prompt.
            description: The description of the prompt.
            input_schema: The JSON schema for the prompt's input.
        """
        self.name: str = name
        self.description: str = description
        self.input_schema: Dict[str, Any] = input_schema

    def format_for_llm(self) -> str:
        """Format prompt information for LLM.

        Returns:
            A formatted string describing the prompt.
        """
        args_desc = []
        if "properties" in self.input_schema:
            for param_name, param_info in self.input_schema["properties"].items():
                arg_desc = (
                    f"- {param_name}: {param_info.get('description', 'No description')}"
                )
                if param_name in self.input_schema.get("required", []):
                    arg_desc += " (required)"
                args_desc.append(arg_desc)

        return f"""
Prompt: {self.name}
Description: {self.description}
Arguments:
{chr(10).join(args_desc)}
"""


class PromptFormat:
    """Represents a prompt format with its properties."""

    def __init__(
        self, name: str, description: Optional[str] = None, schema: Optional[Dict[str, Any]] = None
    ) -> None:
        """Initialize a PromptFormat instance.
        
        Args:
            name: The name of the format.
            description: The description of the format.
            schema: The schema describing the format.
        """
        self.name: str = name
        self.description: Optional[str] = description
        self.schema: Optional[Dict[str, Any]] = schema


class MCPServer:
    """Manages connection to an MCP server and tool execution."""

    def __init__(self, name: str, config: ServerConfig) -> None:
        """Initialize an MCPServer instance.
        
        Args:
            name: The name of the server.
            config: The server configuration.
        """
        self.name: str = name
        self.config: ServerConfig = config
        self.session: Optional[ClientSession] = None
        self._exit_stack: AsyncExitStack = AsyncExitStack()
        self._cleanup_lock: asyncio.Lock = asyncio.Lock()
        self._tools: List[Tool] = []
        self._resources: List[Resource] = []
        self._resource_templates: List[ResourceTemplate] = []
        self._prompts: List[Prompt] = []
        self._prompt_formats: List[PromptFormat] = []
        self._server_info: Optional[Implementation] = None
        self._connected: bool = False

    @property
    def is_connected(self) -> bool:
        """Check if the server is connected.
        
        Returns:
            True if the server is connected, False otherwise.
        """
        return self._connected and self.session is not None

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
            if self.config.type.lower() == "sse":
                if not self.config.url:
                    logging.error(f"URL is required for SSE server {self.name}")
                    return False
                
                url = self.config.url
                if not urlparse(url).scheme:
                    logging.error(f"Invalid URL for SSE server {self.name}: {url}")
                    return False
                
                logging.info(f"Connecting to SSE server {self.name} at {url}")
                streams = await self._exit_stack.enter_async_context(sse_client(url))
                read, write = streams
            
            elif self.config.type.lower() == "stdio":
                if not self.config.command:
                    logging.error(f"Command is required for stdio server {self.name}")
                    return False
                
                command = self.config.command
                args = self.config.args
                env = {**os.environ, **self.config.env} if self.config.env else None
                
                logging.info(f"Connecting to stdio server {self.name} with command {command}")
                stdio_params = (command, args, env)
                stdio_transport = await self._exit_stack.enter_async_context(
                    stdio_client(stdio_params)
                )
                read, write = stdio_transport
            
            else:
                logging.error(f"Unsupported server type for {self.name}: {self.config.type}")
                return False
            
            # Initialize the session
            self.session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            init_result = await self.session.initialize()
            self._server_info = init_result.serverInfo
            
            logging.info(f"Connected to MCP server {self.name}")
            self._connected = True
            
            # Load the server capabilities
            await self._load_capabilities()
            
            return True
        
        except Exception as e:
            logging.error(f"Error connecting to MCP server {self.name}: {e}")
            await self.disconnect()
            return False

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        async with self._cleanup_lock:
            try:
                await self._exit_stack.aclose()
                self.session = None
                self._connected = False
                self._tools = []
                self._resources = []
                self._resource_templates = []
                self._prompts = []
                self._prompt_formats = []
                self._server_info = None
                logging.info(f"Disconnected from MCP server {self.name}")
            except Exception as e:
                logging.error(f"Error during disconnect of server {self.name}: {e}")

    async def _load_capabilities(self) -> None:
        """Load server capabilities (tools, resources, etc.)."""
        if not self.is_connected or not self.session:
            raise RuntimeError(f"Server {self.name} not connected")
        
        # Load tools
        try:
            tools_response = await self.session.list_tools()
            self._tools = []
            
            if hasattr(tools_response, "tools"):
                for tool in tools_response.tools:
                    self._tools.append(Tool(tool.name, tool.description, tool.inputSchema))
        except Exception as e:
            logging.error(f"Error loading tools from {self.name}: {e}")
        
        # Load resources
        try:
            resources_response = await self.session.list_resources()
            self._resources = []
            
            if hasattr(resources_response, "resources"):
                for resource in resources_response.resources:
                    try:
                        self._resources.append(
                            Resource(
                                getattr(resource, "uri", ""), 
                                getattr(resource, "name", "Unknown"),
                                getattr(resource, "mimeType", None),
                                getattr(resource, "description", None)
                            )
                        )
                    except Exception as res_err:
                        logging.warning(f"Error adding resource: {res_err}. Skipping.")
        except Exception as e:
            logging.error(f"Error loading resources from {self.name}: {e}")
        
        # Load resource templates
        try:
            templates_response = await self.session.list_resource_templates()
            self._resource_templates = []
            
            if hasattr(templates_response, "resourceTemplates"):
                for template in templates_response.resourceTemplates:
                    try:
                        self._resource_templates.append(
                            ResourceTemplate(
                                getattr(template, "uriTemplate", ""), 
                                getattr(template, "name", "Unknown"),
                                getattr(template, "mimeType", None),
                                getattr(template, "description", None)
                            )
                        )
                    except Exception as template_err:
                        logging.warning(f"Error adding resource template: {template_err}. Skipping.")
        except Exception as e:
            logging.error(f"Error loading resource templates from {self.name}: {e}")
            
        # Load prompts if supported
        self._prompts = []
        if hasattr(self.session, "list_prompts"):
            try:
                prompts_response = await self.session.list_prompts()
                
                if hasattr(prompts_response, "prompts"):
                    for prompt in prompts_response.prompts:
                        # Check if all required attributes exist
                        if hasattr(prompt, "name") and hasattr(prompt, "description"):
                            # Use getattr with a default empty dict for inputSchema
                            input_schema = getattr(prompt, "inputSchema", {})
                            self._prompts.append(
                                Prompt(
                                    prompt.name,
                                    prompt.description,
                                    input_schema
                                )
                            )
            except Exception as e:
                logging.error(f"Error loading prompts from {self.name}: {e}")
            
        # Load prompt formats if supported
        self._prompt_formats = []
        if hasattr(self.session, "list_prompt_formats"):
            try:
                formats_response = await self.session.list_prompt_formats()
                
                if hasattr(formats_response, "promptFormats"):
                    for format in formats_response.promptFormats:
                        # Check if the required name attribute exists
                        if hasattr(format, "name"):
                            self._prompt_formats.append(
                                PromptFormat(
                                    format.name,
                                    getattr(format, "description", None),
                                    getattr(format, "schema", None)
                                )
                            )
            except Exception as e:
                logging.error(f"Error loading prompt formats from {self.name}: {e}")

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
            RuntimeError: If the server is not connected.
            Exception: If the tool execution fails.
        """
        if not self.is_connected or not self.session:
            raise RuntimeError(f"Server {self.name} not connected")
        
        attempt = 0
        while attempt < retries:
            try:
                logging.info(f"Executing {tool_name} on {self.name}...")
                result = await self.session.call_tool(tool_name, arguments)
                return result
            
            except Exception as e:
                attempt += 1
                logging.warning(
                    f"Error executing tool: {e}. Attempt {attempt} of {retries}."
                )
                if attempt < retries:
                    logging.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logging.error("Max retries reached. Failing.")
                    raise

    async def read_resource(self, uri: str) -> Any:
        """Read a resource from the server.
        
        Args:
            uri: The URI of the resource to read.
            
        Returns:
            The content of the resource.
            
        Raises:
            RuntimeError: If the server is not connected.
            Exception: If the resource read fails.
        """
        if not self.is_connected or not self.session:
            raise RuntimeError(f"Server {self.name} not connected")
        
        # Ensure uri is a string
        uri_str = str(uri) if uri is not None else ""
        if not uri_str:
            raise ValueError("Resource URI cannot be empty")
            
        try:
            result = await self.session.read_resource(uri_str)
            return result
        except Exception as e:
            logging.error(f"Error reading resource {uri_str} from {self.name}: {e}")
            raise

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
