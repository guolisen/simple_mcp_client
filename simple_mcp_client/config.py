"""Configuration module for MCP client."""
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import importlib.resources

from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator


class LLMConfig(BaseModel):
    """Configuration for a specific LLM provider."""
    provider: str
    model: str
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    other_params: Dict[str, Any] = Field(default_factory=dict)


class ServerConfig(BaseModel):
    """Configuration for a specific MCP server."""
    type: str = "sse"  # 'sse' or 'stdio'
    url: Optional[str] = None  # Required for SSE servers
    command: Optional[str] = None  # Required for stdio servers
    args: List[str] = Field(default_factory=list)  # Used for stdio servers
    env: Dict[str, str] = Field(default_factory=dict)  # Environment variables
    enable: bool = True  # Whether to connect to this server at startup


class ToolFormattingConfig(BaseModel):
    """Configuration for MCP tool call formatting."""
    enabled: bool = True  # Whether to enable tool call formatting
    color: bool = True  # Whether to use colors in formatting
    compact: bool = False  # Whether to use compact formatting
    max_depth: int = 3  # Maximum depth for nested objects
    truncate_length: Union[int, str] = 100  # Maximum length for string values or "all" for no truncation
    syntax_highlighting: bool = True  # Whether to use syntax highlighting for JSON
    align_columns: bool = True  # Whether to align columns in tables
    show_icons: bool = True  # Whether to show icons for status
    color_scheme: str = "default"  # Color scheme to use (default, dark, light, monochrome)
    
    @validator('truncate_length')
    def validate_truncate_length(cls, v):
        """Validate that truncate_length is either an integer or the string 'all'."""
        if isinstance(v, str) and v.lower() != 'all':
            raise ValueError('truncate_length must be either an integer or the string "all"')
        return v


class PromptConfig(BaseModel):
    """Configuration for system prompts."""
    base_introduction: Optional[str] = None  # Base introduction system prompt


class LoggingConfig(BaseModel):
    """Configuration for logging."""
    log_path: Optional[str] = None  # Path to the log file/directory


class ConsoleConfig(BaseModel):
    """Configuration for console interface."""
    tool_formatting: ToolFormattingConfig = Field(default_factory=ToolFormattingConfig)


class ClientConfig(BaseModel):
    """Main configuration for the MCP client."""
    llm: LLMConfig
    mcpServers: Dict[str, ServerConfig]
    console: ConsoleConfig = Field(default_factory=ConsoleConfig)
    prompts: PromptConfig = Field(default_factory=PromptConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


class Configuration:
    """Manages configuration and environment variables for the MCP client."""

    def __init__(self, config_path: Optional[str] = None) -> None:
        """Initialize configuration with environment variables and config file.
        
        Args:
            config_path: Optional explicit path to config file. If provided, 
                         this overrides the default user config location.
        """
        self.load_env()
        self._config_path = config_path or self._get_default_config_path()
        self._config = self._load_or_create_config()

    def _get_default_config_path(self) -> str:
        """Get the platform-specific default configuration file path."""
        if sys.platform == "win32" or sys.platform == "WIN32" or sys.platform != "linux" or sys.platform == "win64":
            config_dir = Path(os.getenv("APPDATA")) / "simple_mcp_client"
        else:
            config_dir = Path.home() / ".config" / "simple_mcp_client"
        
        # Ensure directory exists
        config_dir.mkdir(parents=True, exist_ok=True)
        return str(config_dir / "config.json")

    @property
    def config_path(self) -> str:
        """Get the configuration file path."""
        return self._config_path

    @property
    def config(self) -> ClientConfig:
        """Get the client configuration."""
        return self._config

    @staticmethod
    def load_env() -> None:
        """Load environment variables from .env file."""
        load_dotenv()

    def _load_default_config(self) -> Dict[str, Any]:
        """Load the default configuration from the package."""
        try:
            # Try to use importlib.resources first (more reliable for packaged apps)
            try:
                with importlib.resources.open_text("simple_mcp_client.config", "default_config.json") as f:
                    return json.load(f)
            except (ImportError, FileNotFoundError):
                # Fall back to direct file access (works during development)
                module_dir = os.path.dirname(os.path.abspath(__file__))
                default_config_path = os.path.join(module_dir, "config", "default_config.json")
                with open(default_config_path, "r") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load default config: {e}")
            # Return a minimal default config if we can't load the file
            return {
                "llm": {
                    "provider": "ollama",
                    "model": "llama3",
                    "api_url": "http://localhost:11434/api"
                },
                "mcpServers": {}
            }

    def _load_or_create_config(self) -> ClientConfig:
        """Load configuration from file or create default if it doesn't exist."""
        path = Path(self._config_path)
        
        if path.exists():
            # Load existing user config
            with open(path, "r") as f:
                config_data = json.load(f)
                return ClientConfig.model_validate(config_data)
        else:
            # Copy default config to user directory
            default_config_data = self._load_default_config()
            
            # Create the config file
            with open(path, "w") as f:
                json.dump(default_config_data, f, indent=2)
            
            return ClientConfig.model_validate(default_config_data)

    def save_config(self, config: Union[ClientConfig, Dict[str, Any]]) -> None:
        """Save configuration to file.
        
        Args:
            config: Configuration to save, either as a ClientConfig object
                   or a dictionary.
        """
        if isinstance(config, ClientConfig):
            config_dict = config.model_dump()
        else:
            config_dict = config
            # Update the internal config if a dict was provided
            self._config = ClientConfig.model_validate(config_dict)
        
        path = Path(self._config_path)
        with open(path, "w") as f:
            json.dump(config_dict, f, indent=2)

    def reload(self) -> None:
        """Reload configuration from file."""
        path = Path(self._config_path)
        if path.exists():
            with open(path, "r") as f:
                config_data = json.load(f)
                self._config = ClientConfig.model_validate(config_data)
        else:
            raise FileNotFoundError(f"Configuration file not found: {self._config_path}")
