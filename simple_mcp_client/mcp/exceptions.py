"""Custom exceptions for MCP server operations."""


class MCPServerError(Exception):
    """Base class for MCP server exceptions."""
    pass


class ConnectionError(MCPServerError):
    """Error connecting to MCP server."""
    pass


class NetworkError(ConnectionError):
    """Network-related connection error."""
    pass


class TimeoutError(ConnectionError):
    """Connection or operation timed out."""
    pass


class AuthenticationError(ConnectionError):
    """Authentication failed."""
    pass


class ProtocolError(MCPServerError):
    """Error in MCP protocol."""
    pass


class ServerSideError(MCPServerError):
    """Error reported by the server."""
    pass


class DisconnectedError(MCPServerError):
    """Operation attempted on a disconnected server."""
    pass


class ToolExecutionError(MCPServerError):
    """Error executing a tool."""
    pass


class ResourceAccessError(MCPServerError):
    """Error accessing a resource."""
    pass


class PromptError(MCPServerError):
    """Error retrieving or processing a prompt."""
    pass
