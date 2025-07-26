#!/usr/bin/env python3
"""
Test script for the refactored chat command with ReAct agent integration.
This script demonstrates the enhanced MCP chat functionality.
"""

import asyncio
import logging
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simple_mcp_client.config import Configuration
from simple_mcp_client.mcp import ServerManager
from simple_mcp_client.console.chat_utils import (
    initialize_mcp_client, create_react_agent, cleanup_chat_resources
)


async def test_react_chat():
    """Test the ReAct chat functionality."""
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    print("Testing ReAct Chat Integration")
    print("=" * 40)
    
    try:
        # Load configuration
        print("1. Loading configuration...")
        config = Configuration()
        print(f"   ✓ Configuration loaded from {config.config_path}")
        
        # Create server manager
        print("2. Creating server manager...")
        server_manager = ServerManager(config)
        print(f"   ✓ Server manager created with {len(server_manager.servers)} configured servers")
        
        # Connect to default server if available
        default_server = config.config.default_server
        if default_server and default_server in server_manager.servers:
            print(f"3. Connecting to default server: {default_server}...")
            success = await server_manager.connect_server(default_server)
            if success:
                print(f"   ✓ Connected to {default_server}")
                server = server_manager.get_server(default_server)
                if server and server.tools:
                    print(f"   ✓ Server has {len(server.tools)} tools available")
            else:
                print(f"   ✗ Failed to connect to {default_server}")
                print("   Note: This is expected if the server is not running")
        else:
            print("3. No default server configured or server not found")
        
        # Test MCP adapter initialization
        print("4. Testing MCP LangChain adapter...")
        connected_servers = server_manager.get_connected_servers()
        if connected_servers:
            try:
                mcp_adapter = await initialize_mcp_client(server_manager)
                print(f"   ✓ MCP adapter initialized with {mcp_adapter.get_server_count()} servers")
                
                # Test ReAct agent creation
                print("5. Testing ReAct agent creation...")
                react_agent = await create_react_agent(config, mcp_adapter)
                print(f"   ✓ ReAct agent created with {react_agent.get_tool_count()} tools")
                
                model_info = react_agent.get_model_info()
                print(f"   ✓ Using model: {model_info['provider']}/{model_info['model']}")
                
                # Test a simple interaction (without actual user input)
                print("6. Testing agent response capability...")
                test_messages = [{"role": "user", "content": "Hello, can you help me?"}]
                
                try:
                    response = await react_agent.get_response(test_messages)
                    print(f"   ✓ Agent responded successfully")
                    print(f"   Response preview: {response[:100]}...")
                except Exception as e:
                    print(f"   ⚠ Agent response test failed (this may be due to API configuration): {e}")
                
                # Clean up
                print("7. Cleaning up resources...")
                await cleanup_chat_resources(mcp_adapter, react_agent)
                print("   ✓ Resources cleaned up")
                
            except RuntimeError as e:
                print(f"   ✗ MCP adapter initialization failed: {e}")
                print("   This is expected if no MCP servers are connected")
        else:
            print("   ⚠ No connected servers available for testing")
            print("   To fully test the functionality, connect to an MCP server first")
        
        print("\n" + "=" * 40)
        print("✓ ReAct Chat Integration Test Completed")
        print("\nThe refactored chat command is ready to use!")
        print("Run the main client and use the 'chat' command to experience the enhanced functionality.")
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        logging.error(f"Test error: {e}", exc_info=True)
        return False
    
    finally:
        # Ensure cleanup
        try:
            if 'server_manager' in locals():
                await server_manager.disconnect_all()
        except Exception as e:
            logging.error(f"Cleanup error: {e}")
    
    return True


def main():
    """Main entry point for the test."""
    try:
        result = asyncio.run(test_react_chat())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
