"""Tests for the configuration module."""
import os
import json
import pytest
from pathlib import Path

from simple_mcp_client.config import Configuration, ClientConfig, LLMConfig, ServerConfig


class TestConfiguration:
    """Test cases for the Configuration class."""
    
    def test_load_config(self, temp_config_file):
        """Test loading configuration from a file."""
        config = Configuration(temp_config_file)
        
        # Verify the configuration was loaded correctly
        assert config.config.llm.provider == "test_provider"
        assert config.config.llm.model == "test_model"
        assert config.config.llm.api_url == "http://test-api.com"
        assert config.config.llm.api_key == "test_key"
        assert config.config.llm.other_params["temperature"] == 0.5
        assert config.config.llm.other_params["max_tokens"] == 1000
        
        # Verify server configurations
        assert "test_server" in config.config.mcpServers
        assert config.config.mcpServers["test_server"].type == "sse"
        assert config.config.mcpServers["test_server"].url == "http://test-server.com/sse"
        assert config.config.mcpServers["test_server"].enable is True
        
        assert "stdio_server" in config.config.mcpServers
        assert config.config.mcpServers["stdio_server"].type == "stdio"
        assert config.config.mcpServers["stdio_server"].command == "test_command"
        assert config.config.mcpServers["stdio_server"].args == ["arg1", "arg2"]
        assert config.config.mcpServers["stdio_server"].env == {"TEST_ENV": "test_value"}
        
        # Verify console configuration
        assert config.config.console.tool_formatting.enabled is True
        assert config.config.console.tool_formatting.color is True
        assert config.config.console.tool_formatting.max_depth == 3
        
        # Verify prompts configuration
        assert config.config.prompts.base_introduction == "You are a helpful assistant."
    
    def test_save_config(self, tmp_path):
        """Test saving configuration to a file."""
        config_path = tmp_path / "new_config.json"
        
        # Create a new configuration
        config = Configuration(str(config_path))
        
        # Modify some values
        config.config.llm.provider = "new_provider"
        config.config.llm.model = "new_model"
        config.config.llm.api_key = "new_key"
        
        # Add a new server
        config.config.mcpServers["new_server"] = ServerConfig(
            type="sse",
            url="http://new-server.com/sse",
            enable=True
        )
        
        # Save the configuration
        config.save_config(config.config)
        
        # Verify the file was created
        assert config_path.exists()
        
        # Load the saved configuration and verify the values
        with open(config_path, "r") as f:
            saved_config = json.load(f)
        
        assert saved_config["llm"]["provider"] == "new_provider"
        assert saved_config["llm"]["model"] == "new_model"
        assert saved_config["llm"]["api_key"] == "new_key"
        assert "new_server" in saved_config["mcpServers"]
        assert saved_config["mcpServers"]["new_server"]["type"] == "sse"
        assert saved_config["mcpServers"]["new_server"]["url"] == "http://new-server.com/sse"
    
    def test_reload_config(self, temp_config_file):
        """Test reloading configuration from a file."""
        config = Configuration(temp_config_file)
        
        # Modify the config file directly
        with open(temp_config_file, "r") as f:
            config_data = json.load(f)
        
        config_data["llm"]["provider"] = "modified_provider"
        config_data["llm"]["model"] = "modified_model"
        
        with open(temp_config_file, "w") as f:
            json.dump(config_data, f)
        
        # Reload the configuration
        config.reload()
        
        # Verify the changes were loaded
        assert config.config.llm.provider == "modified_provider"
        assert config.config.llm.model == "modified_model"
    
    def test_default_config_creation(self, tmp_path, monkeypatch):
        """Test creation of default configuration when file doesn't exist."""
        config_path = tmp_path / "nonexistent_config.json"
        
        # Mock the _load_default_config method to return a predictable config
        def mock_load_default_config(self):
            return {
                "llm": {
                    "provider": "test_default_provider",
                    "model": "test_default_model",
                    "api_url": "http://test-default-api.com"
                },
                "mcpServers": {
                    "test_default_server": {
                        "type": "sse",
                        "url": "http://test-default-server.com/sse",
                        "enable": True
                    }
                },
                "console": {
                    "tool_formatting": {
                        "enabled": True,
                        "color": True,
                        "compact": False,
                        "max_depth": 3,
                        "truncate_length": 100
                    }
                }
            }
        
        monkeypatch.setattr(Configuration, "_load_default_config", mock_load_default_config)
        
        # Create a configuration with a nonexistent file path
        config = Configuration(str(config_path))
        
        # Verify the file was created with default values
        assert config_path.exists()
        
        # Verify the default values from our mock
        assert config.config.llm.provider == "test_default_provider"
        assert config.config.llm.model == "test_default_model"
        assert config.config.llm.api_url == "http://test-default-api.com"
        assert "test_default_server" in config.config.mcpServers
    
    def test_config_path_property(self, temp_config_file):
        """Test the config_path property."""
        config = Configuration(temp_config_file)
        assert config.config_path == temp_config_file
        
    def test_get_default_config_path(self, monkeypatch):
        """Test the _get_default_config_path method."""
        # Mock sys.platform to test Windows path
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr("os.getenv", lambda x: "C:/Users/Test/AppData/Roaming" if x == "APPDATA" else None)
        
        config = Configuration()
        expected_win_path = "C:/Users/Test/AppData/Roaming/simple_mcp_client/config.json"
        assert config._get_default_config_path().replace("\\", "/") == expected_win_path
        
        # Mock sys.platform to test Unix path
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setattr(Path, "home", lambda: Path("/home/test"))
        
        config = Configuration()
        expected_unix_path = "/home/test/.config/simple_mcp_client/config.json"
        assert config._get_default_config_path().replace("\\", "/") == expected_unix_path
        
    def test_load_default_config(self, monkeypatch, tmp_path):
        """Test loading the default configuration."""
        # Create a mock default config file
        mock_config = {
            "llm": {
                "provider": "mock_provider",
                "model": "mock_model"
            },
            "mcpServers": {}
        }
        
        # Create a temp file with the mock config
        config_file = tmp_path / "default_config.json"
        with open(config_file, "w") as f:
            json.dump(mock_config, f)
        
        # Mock the _load_default_config method to return our mock config
        def mock_load_default_config(self):
            with open(config_file, "r") as f:
                return json.load(f)
        
        monkeypatch.setattr(Configuration, "_load_default_config", mock_load_default_config)
        
        # Test the method directly
        config = Configuration()
        default_config = config._load_default_config()
        
        assert default_config["llm"]["provider"] == "mock_provider"
        assert default_config["llm"]["model"] == "mock_model"
    
    def test_save_config_dict(self, tmp_path):
        """Test saving configuration as a dictionary."""
        config_path = tmp_path / "dict_config.json"
        config = Configuration(str(config_path))
        
        # Create a modified config dictionary
        config_dict = {
            "llm": {
                "provider": "dict_provider",
                "model": "dict_model",
                "api_url": "http://dict-api.com",
                "api_key": "dict_key",
                "other_params": {}
            },
            "mcpServers": {
                "dict_server": {
                    "type": "sse",
                    "url": "http://dict-server.com/sse",
                    "enable": True
                }
            },
            "console": {
                "tool_formatting": {
                    "enabled": True,
                    "color": True,
                    "compact": False,
                    "max_depth": 3,
                    "truncate_length": 100,
                    "syntax_highlighting": True,
                    "align_columns": True,
                    "show_icons": True,
                    "color_scheme": "default"
                }
            },
            "prompts": {
                "base_introduction": "Dict introduction."
            }
        }
        
        # Save the dictionary
        config.save_config(config_dict)
        
        # Reload the configuration
        config.reload()
        
        # Verify the values
        assert config.config.llm.provider == "dict_provider"
        assert config.config.llm.model == "dict_model"
        assert "dict_server" in config.config.mcpServers
        assert config.config.prompts.base_introduction == "Dict introduction."
    
    def test_reload_nonexistent_file(self, tmp_path):
        """Test reloading a nonexistent file raises an error."""
        config_path = tmp_path / "temp_config.json"
        
        # Create and save a configuration
        config = Configuration(str(config_path))
        
        # Delete the file
        os.remove(config_path)
        
        # Attempt to reload should raise FileNotFoundError
        with pytest.raises(FileNotFoundError):
            config.reload()


class TestLLMConfig:
    """Test cases for the LLMConfig class."""
    
    def test_llm_config_creation(self):
        """Test creating an LLMConfig instance."""
        llm_config = LLMConfig(
            provider="test_provider",
            model="test_model",
            api_url="http://test-api.com",
            api_key="test_key",
            other_params={"temperature": 0.7}
        )
        
        assert llm_config.provider == "test_provider"
        assert llm_config.model == "test_model"
        assert llm_config.api_url == "http://test-api.com"
        assert llm_config.api_key == "test_key"
        assert llm_config.other_params["temperature"] == 0.7
    
    def test_llm_config_optional_fields(self):
        """Test LLMConfig with optional fields omitted."""
        llm_config = LLMConfig(
            provider="test_provider",
            model="test_model"
        )
        
        assert llm_config.provider == "test_provider"
        assert llm_config.model == "test_model"
        assert llm_config.api_url is None
        assert llm_config.api_key is None
        assert llm_config.other_params == {}


class TestServerConfig:
    """Test cases for the ServerConfig class."""
    
    def test_server_config_creation(self):
        """Test creating a ServerConfig instance."""
        server_config = ServerConfig(
            type="sse",
            url="http://test-server.com/sse",
            env={"TEST_ENV": "test_value"},
            enable=True
        )
        
        assert server_config.type == "sse"
        assert server_config.url == "http://test-server.com/sse"
        assert server_config.command is None
        assert server_config.args == []
        assert server_config.env == {"TEST_ENV": "test_value"}
        assert server_config.enable is True
    
    def test_stdio_server_config(self):
        """Test creating a stdio ServerConfig instance."""
        server_config = ServerConfig(
            type="stdio",
            command="test_command",
            args=["arg1", "arg2"],
            env={"TEST_ENV": "test_value"},
            enable=True
        )
        
        assert server_config.type == "stdio"
        assert server_config.url is None
        assert server_config.command == "test_command"
        assert server_config.args == ["arg1", "arg2"]
        assert server_config.env == {"TEST_ENV": "test_value"}
        assert server_config.enable is True
    
    def test_server_config_defaults(self):
        """Test ServerConfig default values."""
        server_config = ServerConfig()
        
        assert server_config.type == "sse"
        assert server_config.url is None
        assert server_config.command is None
        assert server_config.args == []
        assert server_config.env == {}
        assert server_config.enable is True
