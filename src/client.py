"""Main client class for MCP Client."""

import logging
import os
from typing import Dict, List, Optional, Any, Union, Type
from pathlib import Path

from .config import Config, MCPServerConfig, load_config, get_default_server
from .llm.base import LLMBase, Conversation
from .llm.openai import OpenAILLM
from .llm.ollama import OllamaLLM
from .llm.deepseek import DeepseekLLM
from .llm.openrouter import OpenRouterLLM
from .mcp.server import MCPServer


class Client:
    """Main client class."""
    
    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        """Initialize the client.
        
        Args:
            config_path: Path to configuration file. If None, loads from default locations.
        """
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        
        # Load configuration
        self.config = load_config(config_path)
        
        # Set log level from configuration
        log_level = getattr(logging, self.config.console.log_level.upper(), logging.INFO)
        logging.getLogger().setLevel(log_level)
        
        # Initialize LLM
        self.llm = self._create_llm()
        
        # Initialize MCP servers
        self.servers: Dict[str, MCPServer] = {}
        self._initialize_servers()
        
        # Initialize conversation
        self.conversation = Conversation(
            system_message="You are a helpful assistant with access to Kubernetes information through MCP."
        )
    
    def _create_llm(self) -> LLMBase:
        """Create an LLM instance based on configuration.
        
        Returns:
            LLM instance.
        """
        llm_config = self.config.llm
        provider = llm_config.provider.lower()
        
        if provider == "openai":
            return OpenAILLM(
                model=llm_config.model,
                api_key=llm_config.api_key,
                api_base=llm_config.api_base
            )
        elif provider == "ollama":
            return OllamaLLM(
                model=llm_config.model,
                host=llm_config.ollama.host
            )
        elif provider == "deepseek":
            return DeepseekLLM(
                model=llm_config.model,
                api_key=llm_config.api_key,
                api_base=llm_config.api_base
            )
        elif provider == "openrouter":
            return OpenRouterLLM(
                model=llm_config.model,
                api_key=llm_config.api_key
            )
        else:
            logging.warning(f"Unknown LLM provider: {provider}, falling back to OpenAI")
            return OpenAILLM(
                model=llm_config.model,
                api_key=llm_config.api_key,
                api_base=llm_config.api_base
            )
    
    def _initialize_servers(self) -> None:
        """Initialize MCP servers from configuration."""
        for server_name, server_config in self.config.mcp_servers.items():
            if server_config.enabled:
                self.servers[server_name] = MCPServer(server_name, server_config)
    
    def get_server(self, server_name: Optional[str] = None) -> Optional[MCPServer]:
        """Get an MCP server.
        
        Args:
            server_name: Name of the server to get. If None, returns the default server.
        
        Returns:
            MCP server or None if not found.
        """
        if server_name:
            return self.servers.get(server_name)
        
        # Get default server
        default_server = get_default_server(self.config)
        if default_server:
            return self.servers.get(default_server[0])
        
        # If no default server, return the first server
        if self.servers:
            return next(iter(self.servers.values()))
        
        return None
    
    def connect_server(self, server_name: Optional[str] = None) -> bool:
        """Connect to an MCP server.
        
        Args:
            server_name: Name of the server to connect to. If None, connects to the default server.
        
        Returns:
            True if connected successfully, False otherwise.
        """
        server = self.get_server(server_name)
        if not server:
            logging.error(f"Server not found: {server_name or 'default'}")
            return False
        
        return server.connect()
    
    def disconnect_server(self, server_name: Optional[str] = None) -> None:
        """Disconnect from an MCP server.
        
        Args:
            server_name: Name of the server to disconnect from. If None, disconnects from the default server.
        """
        server = self.get_server(server_name)
        if server:
            server.disconnect()
    
    def disconnect_all_servers(self) -> None:
        """Disconnect from all MCP servers."""
        for server in self.servers.values():
            server.disconnect()
    
    def add_server(self, name: str, config: MCPServerConfig) -> None:
        """Add an MCP server.
        
        Args:
            name: Server name.
            config: Server configuration.
        """
        self.servers[name] = MCPServer(name, config)
        self.config.mcp_servers[name] = config
    
    def remove_server(self, name: str) -> bool:
        """Remove an MCP server.
        
        Args:
            name: Server name.
        
        Returns:
            True if removed successfully, False otherwise.
        """
        if name in self.servers:
            server = self.servers[name]
            server.disconnect()
            del self.servers[name]
            del self.config.mcp_servers[name]
            return True
        return False
    
    def set_llm(self, provider: str, model: str, **kwargs) -> None:
        """Set the LLM provider and model.
        
        Args:
            provider: LLM provider name.
            model: Model name.
            **kwargs: Additional provider-specific arguments.
        """
        provider = provider.lower()
        
        # Update configuration
        self.config.llm.provider = provider
        self.config.llm.model = model
        
        # Update API key and base URL if provided
        if "api_key" in kwargs:
            self.config.llm.api_key = kwargs["api_key"]
        
        if "api_base" in kwargs:
            self.config.llm.api_base = kwargs["api_base"]
        
        # Create new LLM instance
        self.llm = self._create_llm()
    
    def chat(self, message: str, stream: bool = False) -> Union[str, List[str]]:
        """Send a message to the LLM and get a response.
        
        Args:
            message: User message.
            stream: Whether to stream the response.
        
        Returns:
            LLM response or list of response chunks if streaming.
        """
        # Add user message to conversation
        self.conversation.add_user_message(message)
        
        try:
            if stream:
                # Stream response
                chunks = []
                for chunk in self.llm.chat_stream(self.conversation):
                    chunks.append(chunk)
                    yield chunk
                
                # Add assistant message to conversation
                self.conversation.add_assistant_message("".join(chunks))
            else:
                # Get response
                response = self.llm.chat(self.conversation)
                
                # Add assistant message to conversation
                self.conversation.add_assistant_message(response)
                
                return response
        except Exception as e:
            logging.error(f"Error in chat: {e}")
            error_message = f"Error: {str(e)}"
            
            # Add error message to conversation
            self.conversation.add_assistant_message(error_message)
            
            if stream:
                yield error_message
            else:
                return error_message
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any] = None, server_name: Optional[str] = None) -> Any:
        """Call a tool on an MCP server.
        
        Args:
            tool_name: Name of the tool to call.
            arguments: Arguments to pass to the tool.
            server_name: Name of the server to call the tool on. If None, uses the default server.
        
        Returns:
            Tool response.
        """
        server = self.get_server(server_name)
        if not server:
            raise ValueError(f"Server not found: {server_name or 'default'}")
        
        return server.call_tool(tool_name, arguments or {})
    
    def list_tools(self, server_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """List available tools on an MCP server.
        
        Args:
            server_name: Name of the server to list tools for. If None, uses the default server.
        
        Returns:
            List of tool information.
        """
        server = self.get_server(server_name)
        if not server:
            return []
        
        return server.list_tools()
    
    def list_resources(self, server_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """List available resources on an MCP server.
        
        Args:
            server_name: Name of the server to list resources for. If None, uses the default server.
        
        Returns:
            List of resource information.
        """
        server = self.get_server(server_name)
        if not server:
            return []
        
        return server.list_resources()
    
    def read_resource(self, uri: str, server_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Read a resource from an MCP server.
        
        Args:
            uri: Resource URI.
            server_name: Name of the server to read the resource from. If None, uses the default server.
        
        Returns:
            Resource content or None if not found.
        """
        server = self.get_server(server_name)
        if not server:
            return None
        
        return server.read_resource(uri)
    
    def get_available_llm_providers(self) -> List[str]:
        """Get a list of available LLM providers.
        
        Returns:
            List of provider names.
        """
        return ["openai", "ollama", "deepseek", "openrouter"]
    
    def get_available_llm_models(self, provider: Optional[str] = None) -> List[str]:
        """Get a list of available LLM models.
        
        Args:
            provider: Provider name. If None, uses the current provider.
        
        Returns:
            List of model names.
        """
        provider = provider or self.config.llm.provider
        provider = provider.lower()
        
        if provider == "openai":
            if isinstance(self.llm, OpenAILLM):
                return self.llm.get_available_models()
            return self.config.llm.openai.models
        elif provider == "ollama":
            if isinstance(self.llm, OllamaLLM):
                return self.llm.get_available_models()
            return self.config.llm.ollama.models
        elif provider == "deepseek":
            if isinstance(self.llm, DeepseekLLM):
                return self.llm.get_available_models()
            return self.config.llm.deepseek.models
        elif provider == "openrouter":
            if isinstance(self.llm, OpenRouterLLM):
                return self.llm.get_available_models()
            return self.config.llm.openrouter.models
        else:
            return []
    
    def save_config(self, config_path: Union[str, Path]) -> None:
        """Save configuration to file.
        
        Args:
            config_path: Path to save configuration to.
        """
        from .config import save_config
        save_config(self.config, config_path)
    
    def close(self) -> None:
        """Close the client."""
        self.disconnect_all_servers()
