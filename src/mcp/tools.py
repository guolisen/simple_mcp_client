"""MCP tools helper functions for MCP Client."""

import logging
from typing import Dict, List, Optional, Any, Union

from .server import MCPServer


def call_tool(server: MCPServer, tool_name: str, arguments: Dict[str, Any] = None) -> Any:
    """Call a tool on an MCP server.
    
    Args:
        server: MCP server.
        tool_name: Name of the tool to call.
        arguments: Arguments to pass to the tool.
    
    Returns:
        Tool response.
    """
    return server.call_tool(tool_name, arguments)


def list_tools(server: MCPServer) -> List[Dict[str, Any]]:
    """List available tools on an MCP server.
    
    Args:
        server: MCP server.
    
    Returns:
        List of tool information.
    """
    return server.list_tools()


def list_resources(server: MCPServer) -> List[Dict[str, Any]]:
    """List available resources on an MCP server.
    
    Args:
        server: MCP server.
    
    Returns:
        List of resource information.
    """
    return server.list_resources()


def read_resource(server: MCPServer, uri: str) -> Optional[Dict[str, Any]]:
    """Read a resource from an MCP server.
    
    Args:
        server: MCP server.
        uri: Resource URI.
    
    Returns:
        Resource content or None if not found.
    """
    return server.read_resource(uri)


def get_prompt(server: MCPServer, prompt_name: str, arguments: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Get a prompt from an MCP server.
    
    Args:
        server: MCP server.
        prompt_name: Name of the prompt to get.
        arguments: Arguments to pass to the prompt.
    
    Returns:
        Prompt messages.
    """
    return server.get_prompt(prompt_name, arguments)


def find_tool(server: MCPServer, tool_name: str) -> Optional[Dict[str, Any]]:
    """Find a tool on an MCP server.
    
    Args:
        server: MCP server.
        tool_name: Name of the tool to find.
    
    Returns:
        Tool information or None if not found.
    """
    tools = server.list_tools()
    for tool in tools:
        if tool.get("name") == tool_name:
            return tool
    return None


def find_resource(server: MCPServer, uri: str) -> Optional[Dict[str, Any]]:
    """Find a resource on an MCP server.
    
    Args:
        server: MCP server.
        uri: Resource URI.
    
    Returns:
        Resource information or None if not found.
    """
    resources = server.list_resources()
    for resource in resources:
        if resource.get("uri") == uri:
            return resource
    return None


def find_resource_template(server: MCPServer, uri_template: str) -> Optional[Dict[str, Any]]:
    """Find a resource template on an MCP server.
    
    Args:
        server: MCP server.
        uri_template: Resource URI template.
    
    Returns:
        Resource template information or None if not found.
    """
    templates = server.list_resource_templates()
    for template in templates:
        if template.get("uriTemplate") == uri_template:
            return template
    return None
