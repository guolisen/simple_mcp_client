#!/usr/bin/env python3
"""Main entry point for MCP Client."""

import os
import sys
import logging
import argparse
from pathlib import Path

from src.console import MCPConsole
from src.client import Client
from src.config import load_config, save_config, MCPServerConfig


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="MCP Client")
    parser.add_argument(
        "--config", "-c",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--llm", "-l",
        help="LLM provider to use (openai, ollama, deepseek, openrouter)"
    )
    parser.add_argument(
        "--model", "-m",
        help="LLM model to use"
    )
    parser.add_argument(
        "--api-key", "-k",
        help="API key for LLM provider"
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--server", "-s",
        help="MCP server to connect to (from config)"
    )
    parser.add_argument(
        "--add-server",
        help="Add a new MCP server (name:url:transport)"
    )
    return parser.parse_args()


def main():
    """Run the MCP client."""
    # Parse command-line arguments
    args = parse_args()
    
    # Set up logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Load configuration
    config_path = args.config
    
    # Add a new server if requested
    if args.add_server:
        try:
            name, url, transport = args.add_server.split(":", 2)
            
            # Load existing config or create a new one
            config = load_config(config_path)
            
            # Add the new server
            config.mcp_servers[name] = MCPServerConfig(
                url=url,
                transport=transport,
                enabled=True,
                default=not bool(config.mcp_servers)  # Default if no other servers
            )
            
            # Save the updated config
            if config_path:
                save_config(config, config_path)
            else:
                # Save to default location
                default_path = os.path.expanduser("~/.config/mcp-client/config.yaml")
                os.makedirs(os.path.dirname(default_path), exist_ok=True)
                save_config(config, default_path)
                config_path = default_path
            
            print(f"Added server {name} to configuration at {config_path}")
        except ValueError:
            print("Error: --add-server requires format name:url:transport")
            print("Example: --add-server k8s:http://localhost:8000:sse")
            sys.exit(1)
    
    # Create and run the console
    console = MCPConsole(config_path)
    
    # Override LLM provider and model if provided
    if args.llm:
        model = args.model or console.client.config.llm.model
        api_key = args.api_key or console.client.config.llm.api_key
        
        try:
            console.client.set_llm(args.llm, model, api_key=api_key)
            print(f"Using LLM provider: {args.llm}, model: {model}")
        except Exception as e:
            print(f"Error setting LLM: {e}")
    
    # Connect to server if provided
    if args.server:
        if console.client.connect_server(args.server):
            print(f"Connected to server: {args.server}")
        else:
            print(f"Failed to connect to server: {args.server}")
    
    # Run the console
    try:
        console.cmdloop()
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        console.client.close()


if __name__ == "__main__":
    main()
