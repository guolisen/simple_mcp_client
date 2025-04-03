"""Configuration module for MCP Client."""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Union, Any
from pydantic import BaseModel, Field


class LLMProviderConfig(BaseModel):
    """Configuration for an LLM provider."""
    
    host: Optional[str] = None
    models: List[str] = Field(default_factory=list)


class LLMConfig(BaseModel):
    """LLM configuration."""
    
    provider: str = "openai"  # ollama, deepseek, openai, openrouter
    model: str = "gpt-4"
    api_key: str = ""
    api_base: Optional[str] = None
    
    # Provider-specific configurations
    ollama: LLMProviderConfig = Field(default_factory=LLMProviderConfig)
    deepseek: LLMProviderConfig = Field(default_factory=LLMProviderConfig)
    openai: LLMProviderConfig = Field(default_factory=LLMProviderConfig)
    openrouter: LLMProviderConfig = Field(default_factory=LLMProviderConfig)


class MCPServerConfig(BaseModel):
    """MCP server configuration."""
    
    url: str = "http://localhost:8000"
    transport: str = "sse"  # sse or stdio
    enabled: bool = True
    default: bool = False
    stdio_command: Optional[str] = None


class ConsoleConfig(BaseModel):
    """Console configuration."""
    
    history_file: str = "~/.mcp_client_history"
    log_level: str = "info"
    max_history: int = 1000
    prompt: str = "mcp> "


class Config(BaseModel):
    """Main configuration."""
    
    llm: LLMConfig = Field(default_factory=LLMConfig)
    mcp_servers: Dict[str, MCPServerConfig] = Field(default_factory=dict)
    console: ConsoleConfig = Field(default_factory=ConsoleConfig)


def find_config_file() -> Optional[Path]:
    """Find the configuration file."""
    # Check environment variable
    env_config = os.environ.get("MCP_CLIENT_CONFIG")
    if env_config:
        config_path = Path(env_config)
        if config_path.exists():
            return config_path
    
    # Check common locations
    common_locations = [
        Path("./config.yaml"),
        Path("./config/config.yaml"),
        Path("./config/default_config.yaml"),
        Path("/etc/mcp-client/config.yaml"),
        Path.home() / ".config" / "mcp-client" / "config.yaml",
    ]
    
    for location in common_locations:
        if location.exists():
            return location
    
    return None


def load_config(config_path: Optional[Union[str, Path]] = None) -> Config:
    """Load configuration from file and environment variables."""
    config = Config()
    
    # Load from file if provided
    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
    else:
        path = find_config_file()
    
    # Load from file if found
    if path:
        with open(path, "r") as f:
            file_config = yaml.safe_load(f)
            if file_config:
                # Update config with file values
                if "llm" in file_config:
                    update_llm_config(config.llm, file_config["llm"])
                
                if "mcp_servers" in file_config:
                    for server_name, server_config in file_config["mcp_servers"].items():
                        config.mcp_servers[server_name] = MCPServerConfig(**server_config)
                
                if "console" in file_config:
                    config.console = ConsoleConfig(**file_config["console"])
    
    # Load from environment variables
    load_env_variables(config)
    
    return config


def update_llm_config(llm_config: LLMConfig, file_config: Dict[str, Any]) -> None:
    """Update LLM configuration from file values."""
    for key, value in file_config.items():
        if key in ["provider", "model", "api_key", "api_base"]:
            setattr(llm_config, key, value)
        elif key in ["ollama", "deepseek", "openai", "openrouter"]:
            if isinstance(value, dict):
                provider_config = getattr(llm_config, key)
                for provider_key, provider_value in value.items():
                    setattr(provider_config, provider_key, provider_value)


def load_env_variables(config: Config) -> None:
    """Load configuration from environment variables."""
    # LLM configuration
    if "MCP_CLIENT_LLM_PROVIDER" in os.environ:
        config.llm.provider = os.environ["MCP_CLIENT_LLM_PROVIDER"]
    
    if "MCP_CLIENT_LLM_MODEL" in os.environ:
        config.llm.model = os.environ["MCP_CLIENT_LLM_MODEL"]
    
    if "MCP_CLIENT_LLM_API_KEY" in os.environ:
        config.llm.api_key = os.environ["MCP_CLIENT_LLM_API_KEY"]
    
    if "MCP_CLIENT_LLM_API_BASE" in os.environ:
        config.llm.api_base = os.environ["MCP_CLIENT_LLM_API_BASE"]
    
    # Provider-specific configurations
    if "MCP_CLIENT_OLLAMA_HOST" in os.environ:
        config.llm.ollama.host = os.environ["MCP_CLIENT_OLLAMA_HOST"]
    
    # Console configuration
    if "MCP_CLIENT_CONSOLE_LOG_LEVEL" in os.environ:
        config.console.log_level = os.environ["MCP_CLIENT_CONSOLE_LOG_LEVEL"]


def get_default_server(config: Config) -> Optional[tuple[str, MCPServerConfig]]:
    """Get the default MCP server configuration."""
    for server_name, server_config in config.mcp_servers.items():
        if server_config.default and server_config.enabled:
            return (server_name, server_config)
    
    # If no default is set, use the first enabled server
    for server_name, server_config in config.mcp_servers.items():
        if server_config.enabled:
            return (server_name, server_config)
    
    return None


def save_config(config: Config, config_path: Union[str, Path]) -> None:
    """Save configuration to file."""
    path = Path(config_path)
    
    # Create parent directories if they don't exist
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert config to dict
    config_dict = config.model_dump()
    
    # Save to file
    with open(path, "w") as f:
        yaml.dump(config_dict, f, default_flow_style=False)
