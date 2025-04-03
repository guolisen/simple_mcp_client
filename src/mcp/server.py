"""MCP server interface for MCP Client."""

import logging
import subprocess
from typing import Dict, List, Optional, Any, Union
import json

try:
    from mcp import stdio_client, StdioServerParameters
    from mcp.client.sse import sse_client
    from mcp.client.session import ClientSession
    from mcp.types import Resource, ResourceTemplate
except ImportError:
    logging.error("MCP package not installed. Install it with 'pip install mcp'.")
    raise

from ..config import MCPServerConfig


class MCPServer:
    """MCP server interface."""
    
    def __init__(self, name: str, config: MCPServerConfig):
        """Initialize the MCP server interface.
        
        Args:
            name: Server name.
            config: Server configuration.
        """
        self.name = name
        self.config = config
        self.client: Optional[ClientSession] = None
        self.stdio_process: Optional[subprocess.Popen] = None
        self._client_task = None
    
    def connect(self) -> bool:
        """Connect to the MCP server.
        
        Returns:
            True if connected successfully, False otherwise.
        """
        if self.is_connected():
            return True
        
        try:
            import asyncio
            
            # Create a new event loop for async operations
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            if self.config.transport == "sse":
                # Connect to SSE server using sse_client context manager
                client_context = sse_client(self.config.url)
                read_stream, write_stream = loop.run_until_complete(client_context.__aenter__())
                self.client = ClientSession(read_stream, write_stream)
                self._client_task = (client_context, loop)
                
                # Initialize the client
                loop.run_until_complete(self.client.initialize())
                return True
                
            elif self.config.transport == "stdio":
                # Start stdio server process
                if not self.config.stdio_command:
                    logging.error(f"No stdio command provided for server {self.name}")
                    return False
                
                # Create StdioServerParameters
                server_params = StdioServerParameters(
                    command=self.config.stdio_command.split()[0],
                    args=self.config.stdio_command.split()[1:] if len(self.config.stdio_command.split()) > 1 else []
                )
                
                # Connect to stdio server using stdio_client context manager
                client_context = stdio_client(server_params)
                read_stream, write_stream = loop.run_until_complete(client_context.__aenter__())
                self.client = ClientSession(read_stream, write_stream)
                self._client_task = (client_context, loop)
                
                # Initialize the client
                loop.run_until_complete(self.client.initialize())
                return True
            else:
                logging.error(f"Unsupported transport type: {self.config.transport}")
                return False
        except Exception as e:
            logging.error(f"Error connecting to MCP server {self.name}: {e}")
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if self.client:
            try:
                if self._client_task:
                    client_context, loop = self._client_task
                    # Close the client context
                    loop.run_until_complete(client_context.__aexit__(None, None, None))
                    self._client_task = None
            except Exception as e:
                logging.error(f"Error closing MCP client for server {self.name}: {e}")
            finally:
                self.client = None
    
    def is_connected(self) -> bool:
        """Check if connected to the MCP server.
        
        Returns:
            True if connected, False otherwise.
        """
        return self.client is not None
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools.
        
        Returns:
            List of tool information.
        """
        if not self.is_connected():
            logging.info(f"Not connected to server {self.name}, attempting to connect")
            if not self.connect():
                logging.error(f"Failed to connect to server {self.name}")
                return []
        
        try:
            logging.info(f"Listing tools for server {self.name}")
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(self.client.list_tools())
            logging.info(f"Got response from server {self.name}: {response}")
            return response.get("tools", [])
        except Exception as e:
            logging.error(f"Error listing tools for server {self.name}: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return []
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any] = None) -> Any:
        """Call a tool.
        
        Args:
            tool_name: Name of the tool to call.
            arguments: Arguments to pass to the tool.
        
        Returns:
            Tool response.
        """
        if not self.is_connected():
            if not self.connect():
                raise ConnectionError(f"Failed to connect to MCP server {self.name}")
        
        try:
            response = self.client.call_tool(tool_name, arguments or {})
            
            # Try to parse the response as JSON if it's a string
            if isinstance(response, str):
                try:
                    return json.loads(response)
                except json.JSONDecodeError:
                    return response
            
            return response
        except Exception as e:
            logging.error(f"Error calling tool {tool_name} on server {self.name}: {e}")
            raise
    
    def list_resources(self) -> List[Resource]:
        """List available resources.
        
        Returns:
            List of resources.
        """
        if not self.is_connected():
            if not self.connect():
                return []
        
        try:
            response = self.client.list_resources()
            return response.get("resources", [])
        except Exception as e:
            logging.error(f"Error listing resources for server {self.name}: {e}")
            return []
    
    def list_resource_templates(self) -> List[ResourceTemplate]:
        """List available resource templates.
        
        Returns:
            List of resource templates.
        """
        if not self.is_connected():
            if not self.connect():
                return []
        
        try:
            response = self.client.list_resource_templates()
            return response.get("resourceTemplates", [])
        except Exception as e:
            logging.error(f"Error listing resource templates for server {self.name}: {e}")
            return []
    
    def read_resource(self, uri: str) -> Optional[Dict[str, Any]]:
        """Read a resource.
        
        Args:
            uri: Resource URI.
        
        Returns:
            Resource content or None if not found.
        """
        if not self.is_connected():
            if not self.connect():
                return None
        
        try:
            response = self.client.read_resource(uri)
            
            if "contents" in response and response["contents"]:
                content = response["contents"][0]
                
                # Try to parse the content as JSON if it's text
                if content.get("mimeType") == "application/json" and "text" in content:
                    try:
                        return json.loads(content["text"])
                    except json.JSONDecodeError:
                        return content["text"]
                
                return content.get("text", "")
            
            return None
        except Exception as e:
            logging.error(f"Error reading resource {uri} from server {self.name}: {e}")
            return None
    
    def get_prompt(self, prompt_name: str, arguments: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Get a prompt.
        
        Args:
            prompt_name: Name of the prompt to get.
            arguments: Arguments to pass to the prompt.
        
        Returns:
            Prompt messages.
        """
        if not self.is_connected():
            if not self.connect():
                return []
        
        try:
            response = self.client.get_prompt(prompt_name, arguments or {})
            return response.get("messages", [])
        except Exception as e:
            logging.error(f"Error getting prompt {prompt_name} from server {self.name}: {e}")
            return []
