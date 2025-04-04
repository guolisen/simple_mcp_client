"""MCP server interface for MCP Client."""

import logging
import subprocess
import asyncio
import threading
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


# Helper function to run async code synchronously without explicit event loops
def run_async(coro):
    """Run an async coroutine in a synchronous context."""
    try:
        return asyncio.run(coro)
    except RuntimeError as e:
        # Handle case where there's already a running event loop
        if "No running event loop" in str(e) or "There is no current event loop" in str(e):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
        else:
            raise


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
        self._cleanup_lock = threading.Lock()
        self._read_stream = None
        self._write_stream = None
        self._client_context = None
    
    def connect(self) -> bool:
        """Connect to the MCP server.
        
        Returns:
            True if connected successfully, False otherwise.
        """
        if self.is_connected():
            return True
        
        try:
            # Define async setup function
            async def setup_client():
                if self.config.transport == "sse":
                    # Connect to SSE server using sse_client context manager
                    client_context = sse_client(self.config.url)
                    read_stream, write_stream = await client_context.__aenter__()
                    client = ClientSession(read_stream, write_stream)
                    
                    # Initialize the client
                    await client.initialize()
                    return client, client_context, read_stream, write_stream
                    
                elif self.config.transport == "stdio":
                    # Start stdio server process
                    if not self.config.stdio_command:
                        logging.error(f"No stdio command provided for server {self.name}")
                        return None, None, None, None
                    
                    # Create StdioServerParameters
                    server_params = StdioServerParameters(
                        command=self.config.stdio_command.split()[0],
                        args=self.config.stdio_command.split()[1:] if len(self.config.stdio_command.split()) > 1 else []
                    )
                    
                    # Connect to stdio server using stdio_client context manager
                    client_context = stdio_client(server_params)
                    read_stream, write_stream = await client_context.__aenter__()
                    client = ClientSession(read_stream, write_stream)
                    
                    # Initialize the client
                    await client.initialize()
                    return client, client_context, read_stream, write_stream
                else:
                    logging.error(f"Unsupported transport type: {self.config.transport}")
                    return None, None, None, None
            
            # Run the async setup function synchronously
            result = run_async(setup_client())
            
            if result[0] is None:
                return False
                
            self.client, self._client_context, self._read_stream, self._write_stream = result
            return True
            
        except Exception as e:
            logging.error(f"Error connecting to MCP server {self.name}: {e}")
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if self.client:
            try:
                with self._cleanup_lock:
                    if self._client_context:
                        # Define async cleanup function
                        async def cleanup():
                            await self._client_context.__aexit__(None, None, None)
                        
                        # Run the async cleanup function synchronously
                        run_async(cleanup())
                        self._client_context = None
                        self._read_stream = None
                        self._write_stream = None
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
            
            # Define async function to list tools
            async def do_list_tools():
                return await self.client.list_tools()
            
            # Run the async function synchronously
            response = run_async(do_list_tools())
            
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
            # Define async function to call tool
            async def do_call_tool():
                return await self.client.call_tool(tool_name, arguments or {})
            
            # Run the async function synchronously
            response = run_async(do_call_tool())
            
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
            # Define async function to list resources
            async def do_list_resources():
                return await self.client.list_resources()
            
            # Run the async function synchronously
            response = run_async(do_list_resources())
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
            # Define async function to list resource templates
            async def do_list_resource_templates():
                return await self.client.list_resource_templates()
            
            # Run the async function synchronously
            response = run_async(do_list_resource_templates())
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
            # Define async function to read resource
            async def do_read_resource():
                return await self.client.read_resource(uri)
            
            # Run the async function synchronously
            response = run_async(do_read_resource())
            
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
            # Define async function to get prompt
            async def do_get_prompt():
                return await self.client.get_prompt(prompt_name, arguments or {})
            
            # Run the async function synchronously
            response = run_async(do_get_prompt())
            return response.get("messages", [])
        except Exception as e:
            logging.error(f"Error getting prompt {prompt_name} from server {self.name}: {e}")
            return []
