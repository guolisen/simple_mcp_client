"""Shared fixtures for testing the Simple MCP Client."""
import os
import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from simple_mcp_client.config import Configuration, ClientConfig, LLMConfig, ServerConfig
from simple_mcp_client.mcp.models import Tool, Resource, ResourceTemplate, Prompt, PromptFormat
from simple_mcp_client.mcp.server import MCPServer
from simple_mcp_client.mcp.manager import ServerManager
from simple_mcp_client.mcp.langchain_adapter import MCPLangChainAdapter
from simple_mcp_client.llm.react_agent import ReactAgentProvider


@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary config file for testing."""
    config_path = tmp_path / "config.json"
    test_config = {
        "llm": {
            "provider": "test_provider",
            "model": "test_model",
            "api_url": "http://test-api.com",
            "api_key": "test_key",
            "other_params": {
                "temperature": 0.5,
                "max_tokens": 1000,
                "request_timeout": 30.0,
                "max_loop_iterations": 10
            }
        },
        "mcpServers": {
            "test_server": {
                "type": "sse",
                "url": "http://test-server.com/sse",
                "enable": True
            },
            "stdio_server": {
                "type": "stdio",
                "command": "test_command",
                "args": ["arg1", "arg2"],
                "env": {"TEST_ENV": "test_value"},
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
            "base_introduction": "You are a helpful assistant."
        }
    }
    
    with open(config_path, "w") as f:
        json.dump(test_config, f)
    
    return str(config_path)


@pytest.fixture
def mock_config(temp_config_file):
    """Create a Configuration instance with the test config file."""
    return Configuration(temp_config_file)


@pytest.fixture
def mock_tool():
    """Create a mock Tool instance."""
    return Tool(
        name="test_tool",
        description="A test tool",
        input_schema={
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "First parameter"
                },
                "param2": {
                    "type": "integer",
                    "description": "Second parameter"
                }
            },
            "required": ["param1"]
        }
    )


@pytest.fixture
def mock_resource():
    """Create a mock Resource instance."""
    return Resource(
        uri="test/resource",
        name="Test Resource",
        mime_type="text/plain",
        description="A test resource"
    )


@pytest.fixture
def mock_prompt():
    """Create a mock Prompt instance."""
    return Prompt(
        name="test_prompt",
        description="A test prompt",
        input_schema={
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "First parameter"
                }
            },
            "required": ["param1"]
        }
    )


@pytest.fixture
def mock_server_info():
    """Create a mock server info object."""
    server_info = MagicMock(
        name="mock_server_info",
        spec=["name", "version", "description"]
    )
    server_info.name = "Test Server"
    server_info.version = "1.0.0"
    server_info.description = "A test server"
    return server_info


@pytest.fixture
def mock_session():
    """Create a mock ClientSession."""
    session = AsyncMock()
    session.serverInfo = MagicMock(
        name="server_info",
        spec=["name", "version", "description"]
    )
    session.serverInfo.name = "Test Server"
    session.serverInfo.version = "1.0.0"
    session.serverInfo.description = "A test server"
    
    # Mock list_tools method
    tools_result = MagicMock()
    tool1 = MagicMock(
        name="tool1",
        spec=["name", "description", "inputSchema"]
    )
    tool1.name = "test_tool1"
    tool1.description = "Test tool 1"
    tool1.inputSchema = {"type": "object"}
    
    tool2 = MagicMock(
        name="tool2",
        spec=["name", "description", "inputSchema"]
    )
    tool2.name = "test_tool2"
    tool2.description = "Test tool 2"
    tool2.inputSchema = {"type": "object"}
    
    tools_result.tools = [tool1, tool2]
    session.list_tools = AsyncMock(return_value=tools_result)
    
    # Mock list_resources method
    resources_result = MagicMock()
    resource1 = MagicMock(
        name="resource1",
        spec=["uri", "name", "mimeType", "description"]
    )
    resource1.uri = "test/resource1"
    resource1.name = "Test Resource 1"
    resource1.mimeType = "text/plain"
    resource1.description = "Test resource 1"
    
    resources_result.resources = [resource1]
    session.list_resources = AsyncMock(return_value=resources_result)
    
    # Mock list_resource_templates method
    templates_result = MagicMock()
    template1 = MagicMock(
        name="template1",
        spec=["uriTemplate", "name", "mimeType", "description"]
    )
    template1.uriTemplate = "test/template/{param}"
    template1.name = "Test Template 1"
    template1.mimeType = "text/plain"
    template1.description = "Test template 1"
    
    templates_result.resourceTemplates = [template1]
    session.list_resource_templates = AsyncMock(return_value=templates_result)
    
    # Mock list_prompts method
    prompts_result = MagicMock()
    prompt1 = MagicMock(
        name="prompt1",
        spec=["name", "description", "inputSchema"]
    )
    prompt1.name = "test_prompt1"
    prompt1.description = "Test prompt 1"
    prompt1.inputSchema = {"type": "object"}
    
    prompts_result.prompts = [prompt1]
    session.list_prompts = AsyncMock(return_value=prompts_result)
    
    # Mock list_prompt_formats method
    formats_result = MagicMock()
    format1 = MagicMock(
        name="format1",
        spec=["name", "description", "schema"]
    )
    format1.name = "test_format1"
    format1.description = "Test format 1"
    format1.schema = {"type": "object"}
    
    formats_result.promptFormats = [format1]
    session.list_prompt_formats = AsyncMock(return_value=formats_result)
    
    # Mock call_tool method
    session.call_tool = AsyncMock(return_value="Tool result")
    
    # Mock read_resource method
    session.read_resource = AsyncMock(return_value="Resource content")
    
    # Mock get_prompt method
    session.get_prompt = AsyncMock(return_value="Prompt content")
    
    # Mock initialize method
    init_result = MagicMock()
    init_result.serverInfo = MagicMock(
        name="server_info",
        spec=["name", "version", "description"]
    )
    init_result.serverInfo.name = "Test Server"
    init_result.serverInfo.version = "1.0.0"
    init_result.serverInfo.description = "A test server"
    session.initialize = AsyncMock(return_value=init_result)
    
    return session


@pytest.fixture
def mock_mcp_server(mock_config, mock_session):
    """Create a mock MCPServer instance."""
    server_config = mock_config.config.mcpServers["test_server"]
    server = MCPServer("test_server", server_config)
    
    # Mock the connection manager
    server.connection_manager = MagicMock()
    server.connection_manager.is_connected = True
    server.connection_manager.session = mock_session
    server.connection_manager.connect = AsyncMock(return_value=(True, mock_session.serverInfo))
    server.connection_manager.disconnect = AsyncMock()
    server.connection_manager.execute_with_retry = AsyncMock(side_effect=lambda op, **kwargs: op())
    
    # Set server properties
    server._tools = [
        Tool("test_tool1", "Test tool 1", {"type": "object"}),
        Tool("test_tool2", "Test tool 2", {"type": "object"})
    ]
    server._resources = [
        Resource("test/resource1", "Test Resource 1", "text/plain", "Test resource 1")
    ]
    server._resource_templates = [
        ResourceTemplate("test/template/{param}", "Test Template 1", "text/plain", "Test template 1")
    ]
    server._prompts = [
        Prompt("test_prompt1", "Test prompt 1", {"type": "object"})
    ]
    server._prompt_formats = [
        PromptFormat("test_format1", "Test format 1", {"type": "object"})
    ]
    server._server_info = mock_session.serverInfo
    
    return server


@pytest.fixture
def mock_server_manager(mock_config, mock_mcp_server):
    """Create a mock ServerManager instance."""
    manager = ServerManager(mock_config)
    
    # Replace the servers dictionary with our mock server
    manager.servers = {"test_server": mock_mcp_server}
    
    return manager


@pytest.fixture
def mock_mcp_adapter(mock_server_manager):
    """Create a mock MCPLangChainAdapter instance."""
    adapter = MCPLangChainAdapter(mock_server_manager)
    
    # Mock the LangChain client
    adapter.langchain_client = MagicMock()
    adapter._tools_cache = [
        MagicMock(name="tool1"),
        MagicMock(name="tool2")
    ]
    
    # Set initialized state
    adapter.is_initialized = lambda: True
    
    # Mock methods
    adapter.get_tools = AsyncMock(return_value=adapter._tools_cache)
    adapter.refresh_tools = AsyncMock(return_value=adapter._tools_cache)
    
    return adapter


@pytest.fixture
def mock_react_agent(mock_config, mock_mcp_adapter):
    """Create a mock ReactAgentProvider instance."""
    agent = ReactAgentProvider(mock_config, mock_mcp_adapter)
    
    # Mock the model and graph
    agent.model = MagicMock()
    agent.graph = MagicMock()
    agent.tools = [MagicMock(), MagicMock()]
    
    # Mock the model's bind_tools method
    agent.model.bind_tools = MagicMock(return_value=agent.model)
    agent.model.invoke = MagicMock(return_value=MagicMock(content="Model response"))
    
    # Mock the graph's invoke and stream methods
    agent.graph.ainvoke = AsyncMock(return_value={"messages": [MagicMock(content="Graph response")]})
    agent.graph.astream = AsyncMock(return_value=[{"call_model": {"messages": [MagicMock(content="Streaming response")]}}])
    
    # Mock methods
    agent.initialize = AsyncMock(return_value=True)
    agent.get_response = AsyncMock(return_value="Agent response")
    agent.close = AsyncMock()
    
    return agent


@pytest.fixture
def event_loop():
    """Create an event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
