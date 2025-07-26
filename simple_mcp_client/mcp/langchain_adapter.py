"""LangChain MCP adapter for integrating existing MCP servers with LangChain MCP adapters."""
import logging
from typing import Dict, List, Optional, Any, Union
import asyncio

from langchain_mcp_adapters.client import MultiServerMCPClient

from ..config import ServerConfig
# Import ServerManager type hint only for type annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .manager import ServerManager


class MCPLangChainAdapter:
    """Adapter to bridge existing MCP servers with LangChain MCP adapters."""
    
    def __init__(self, server_manager: "ServerManager"):
        """Initialize the adapter.
        
        Args:
            server_manager: The existing server manager instance.
        """
        self.server_manager = server_manager
        self.langchain_client: Optional[MultiServerMCPClient] = None
        self._tools_cache: Optional[List] = None
    
    def _convert_server_config_to_langchain_format(self) -> Dict[str, Dict[str, Any]]:
        """Convert existing server configurations to LangChain MCP client format.
        
        Returns:
            Dictionary in the format expected by MultiServerMCPClient.
        """
        langchain_config = {}
        
        for server_name, server in self.server_manager.servers.items():
            if not server.is_connected:
                continue
                
            config = server.config
            
            if config.type.lower() == "sse":
                # SSE transport configuration
                langchain_config[server_name] = {
                    "url": config.url,
                    "transport": "sse",
                }
                
                # Add environment variables if present
                if config.env:
                    langchain_config[server_name]["env"] = config.env
                    
            elif config.type.lower() == "stdio":
                # STDIO transport configuration
                langchain_config[server_name] = {
                    "command": config.command,
                    "args": config.args or [],
                    "transport": "stdio",
                }
                
                # Add environment variables if present
                if config.env:
                    langchain_config[server_name]["env"] = config.env
            else:
                logging.warning(f"Unsupported server type '{config.type}' for server '{server_name}'")
                continue
        
        return langchain_config
    
    async def initialize_langchain_client(self, use_standard_content_blocks: bool = True) -> bool:
        """Initialize the LangChain MCP client with connected servers.
        
        Args:
            use_standard_content_blocks: Whether to use standard content blocks for text-based outputs.
            
        Returns:
            True if initialization was successful, False otherwise.
        """
        try:
            # Convert server configurations
            langchain_config = self._convert_server_config_to_langchain_format()
            
            if not langchain_config:
                logging.warning("No connected servers available for LangChain MCP client")
                return False
            
            # Initialize MultiServerMCPClient
            self.langchain_client = MultiServerMCPClient(
                langchain_config
                #useStandardContentBlocks=use_standard_content_blocks
            )
            
            logging.info(f"Initialized LangChain MCP client with {len(langchain_config)} servers")
            return True
            
        except Exception as e:
            logging.error(f"Failed to initialize LangChain MCP client: {e}")
            return False
    
    async def get_tools(self) -> List:
        """Get all available tools from the LangChain MCP client.
        
        Returns:
            List of tools available from connected MCP servers.
        """
        if not self.langchain_client:
            raise RuntimeError("LangChain MCP client not initialized. Call initialize_langchain_client() first.")
        
        try:
            # Cache tools to avoid repeated calls
            if self._tools_cache is None:
                self._tools_cache = await self.langchain_client.get_tools()
                logging.info(f"Retrieved {len(self._tools_cache)} tools from LangChain MCP client")
            
            return self._tools_cache
            
        except Exception as e:
            logging.error(f"Failed to get tools from LangChain MCP client: {e}")
            raise
    
    async def refresh_tools(self) -> List:
        """Refresh the tools cache and return updated tools.
        
        Returns:
            List of refreshed tools.
        """
        self._tools_cache = None
        return await self.get_tools()
    
    def get_connected_server_names(self) -> List[str]:
        """Get names of connected servers.
        
        Returns:
            List of connected server names.
        """
        return [server.name for server in self.server_manager.get_connected_servers()]
    
    def get_server_count(self) -> int:
        """Get the number of connected servers.
        
        Returns:
            Number of connected servers.
        """
        return len(self.server_manager.get_connected_servers())
    
    async def close(self) -> None:
        """Close the LangChain MCP client and clean up resources."""
        if self.langchain_client:
            try:
                # The MultiServerMCPClient should handle cleanup automatically
                # but we'll set it to None to indicate it's no longer available
                self.langchain_client = None
                self._tools_cache = None
                logging.info("LangChain MCP client closed")
            except Exception as e:
                logging.error(f"Error closing LangChain MCP client: {e}")
    
    def is_initialized(self) -> bool:
        """Check if the LangChain MCP client is initialized.
        
        Returns:
            True if initialized, False otherwise.
        """
        return self.langchain_client is not None
