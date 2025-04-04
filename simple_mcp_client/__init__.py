"""Simple MCP client for testing MCP servers."""
from .config import Configuration
from .mcp import ServerManager, MCPServer, Tool
from .llm import LLMProvider, LLMProviderFactory
from .console import ConsoleInterface
from .main import main

__version__ = "0.1.0"

__all__ = [
    "Configuration", 
    "ServerManager", 
    "MCPServer", 
    "Tool", 
    "LLMProvider", 
    "LLMProviderFactory", 
    "ConsoleInterface", 
    "main"
]
