#!/usr/bin/env python
"""
Test script for the updated Configuration class.
This script demonstrates how the new configuration system works with platform-specific paths.
"""
import os
import sys
from pathlib import Path
from simple_mcp_client.config import Configuration

def main():
    """Test the Configuration class."""
    print("Testing the Configuration class...")
    
    # Create a new Configuration instance
    # This will use the platform-specific default path
    config = Configuration()
    
    # Print the config path
    print(f"Config path: {config.config_path}")
    
    # Print some values from the config
    print("\nCurrent configuration:")
    print(f"LLM Provider: {config.config.llm.provider}")
    print(f"LLM Model: {config.config.llm.model}")
    print(f"LLM API URL: {config.config.llm.api_url}")
    
    # Print the list of configured servers
    print("\nConfigured servers:")
    for server_name, server in config.config.mcpServers.items():
        status = "Enabled" if server.enable else "Disabled"
        server_type = server.type
        if server_type == "sse":
            url = server.url or "N/A"
            print(f"  - {server_name} ({status}, {server_type}): {url}")
        else:
            command = server.command or "N/A"
            print(f"  - {server_name} ({status}, {server_type}): {command}")
    
    print("\nTest complete!")
    print("The configuration file is now stored in a platform-specific location:")
    print(f"  - Windows: %APPDATA%\\simple_mcp_client\\config.json")
    print(f"  - Linux/macOS: ~/.config/simple_mcp_client/config.json")
    print("\nThe default configuration is loaded from the package's default_config.json file.")

if __name__ == "__main__":
    main()
