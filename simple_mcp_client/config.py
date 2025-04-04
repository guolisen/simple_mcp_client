"""Configuration module for MCP client."""
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv
from pydantic import BaseModel, Field


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


class ClientConfig(BaseModel):
    """Main configuration for the MCP client."""
    llm: LLMConfig
    mcpServers: Dict[str, ServerConfig]
    default_server: Optional[str] = None


class Configuration:
    """Manages configuration and environment variables for the MCP client."""

    def __init__(self, config_path: Optional[str] = None) -> None:
        """Initialize configuration with environment variables and config file.
        
        Args:
            config_path: Path to the configuration file. If not provided,
                         will look for config.json in the current directory.
        """
        self.load_env()
        self._config_path = config_path or "config.json"
        self._config = self._load_or_create_config()

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

    def _load_or_create_config(self) -> ClientConfig:
        """Load configuration from file or create default if it doesn't exist."""
        path = Path(self._config_path)
        if path.exists():
            with open(path, "r") as f:
                config_data = json.load(f)
                return ClientConfig.model_validate(config_data)
        else:
            # Create default configuration
            config = ClientConfig(
                llm=LLMConfig(
                    provider="ollama",
                    model="llama3",
                    api_url="http://localhost:11434/api",
                ),
                mcpServers={
                    "k8s": ServerConfig(
                        type="sse",
                        url="http://192.168.182.128:8000/sse",
                    )
                },
                default_server="k8s",
            )
            self.save_config(config)
            return config

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
