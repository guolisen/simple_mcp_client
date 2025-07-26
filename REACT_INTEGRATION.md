# ReAct Agent Integration for MCP Client

This document describes the enhanced chat functionality that integrates LangChain MCP adapters and LangGraph's ReAct agent into the MCP client.

## Overview

The `chat` command has been refactored to use a ReAct (Reasoning and Acting) agent that provides intelligent tool selection and reasoning capabilities. This enhancement leverages:

- **LangChain MCP Adapters**: For seamless integration with existing MCP servers
- **LangGraph ReAct Agent**: For intelligent reasoning and tool selection
- **Enhanced User Experience**: Clear visibility into agent reasoning and tool execution

## Key Features

### 1. Intelligent Tool Reasoning
- The ReAct agent uses reasoning to determine which tools to use and when
- Better tool chaining and multi-step problem solving
- Improved context awareness across tool executions

### 2. Enhanced Chat Experience
- Clear display of agent reasoning process
- Detailed tool execution information (tool name, arguments, results)
- Better error handling and timeout management
- Configurable timeout settings (default: 60 seconds)

### 3. Seamless MCP Integration
- Works with existing MCP server configurations
- Supports both SSE and STDIO transports
- Maintains backward compatibility with current server setups
- Automatic tool discovery and binding

## Architecture

### Core Components

1. **MCPLangChainAdapter** (`simple_mcp_client/mcp/langchain_adapter.py`)
   - Bridges existing MCP servers with LangChain's MultiServerMCPClient
   - Handles server configuration conversion
   - Manages tool caching and refresh

2. **ReactAgentProvider** (`simple_mcp_client/llm/react_agent.py`)
   - Implements LangGraph ReAct agent
   - Manages LLM initialization and tool binding
   - Provides streaming and non-streaming response modes

3. **Chat Utilities** (`simple_mcp_client/console/chat_utils.py`)
   - Modular functions for chat initialization and management
   - Enhanced display formatting for tool executions
   - Resource cleanup and error handling

### Integration Flow

```
User Input → ReAct Agent → Tool Selection → Tool Execution → Response Generation
     ↑                                                              ↓
     └─────────────── Enhanced Chat Loop ──────────────────────────┘
```

## Usage

### Starting Enhanced Chat

```bash
# Connect to MCP servers first
MCP> connect my-server

# Start the enhanced chat with ReAct agent
MCP> chat
```

### Example Interaction

```
You: What's the weather like in San Francisco and what time is it there?

[Agent thinking and acting...]
