"""Connection management for MCP servers."""
import asyncio
import logging
import time
from contextlib import AsyncExitStack
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, Awaitable
from urllib.parse import urlparse

try:
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client, StdioServerParameters
except ImportError:
    logging.error("""
    Error importing MCP modules. This often happens when running in VSCode debug mode.
    
    Possible solutions:
    1. Run the application directly with 'python -m simple_mcp_client.main' instead of using VSCode debug
    2. Make sure the mcp package is installed in the Python environment VSCode is using
    3. Install the package in development mode with 'pip install -e .' in the project directory
    """)
    # Define placeholder classes to allow the module to load
    class ClientSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def initialize(self): return type('obj', (object,), {'serverInfo': None})
    
    class StdioServerParameters:
        def __init__(self, command=None, args=None, env=None): pass
    
    async def sse_client(url): return (None, None)
    async def stdio_client(params): return (None, None)

from .exceptions import (
    MCPServerError, ConnectionError, NetworkError, TimeoutError, 
    AuthenticationError, ProtocolError, ServerSideError, DisconnectedError
)


class ConnectionManager:
    """Manages connection to an MCP server with reconnection capabilities."""
    
    def __init__(
        self, 
        server_name: str,
        server_type: str,
        url: Optional[str] = None,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        backoff_factor: float = 1.5,
        health_check_interval: float = 60.0
    ) -> None:
        """Initialize a ConnectionManager instance.
        
        Args:
            server_name: The name of the server.
            server_type: The type of the server (sse or stdio).
            url: The URL for SSE servers.
            command: The command for stdio servers.
            args: The command arguments for stdio servers.
            env: Environment variables for stdio servers.
            max_retries: Maximum number of connection retries.
            retry_delay: Initial delay between retries in seconds.
            backoff_factor: Factor to increase delay between retries.
            health_check_interval: Interval between health checks in seconds.
        """
        self.server_name = server_name
        self.server_type = server_type.lower()
        self.url = url
        self.command = command
        self.args = args or []
        self.env = env or {}
        
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor
        self.health_check_interval = health_check_interval
        
        self.session: Optional[ClientSession] = None
        self._exit_stack: AsyncExitStack = AsyncExitStack()
        self._connected: bool = False
        self._last_activity: float = 0
        self._health_check_task: Optional[asyncio.Task] = None
        self._cleanup_lock: asyncio.Lock = asyncio.Lock()
    
    @property
    def is_connected(self) -> bool:
        """Check if the connection is active.
        
        Returns:
            True if connected, False otherwise.
        """
        return self._connected and self.session is not None
    
    def _update_activity_timestamp(self) -> None:
        """Update the last activity timestamp."""
        self._last_activity = time.time()
    
    async def connect(self) -> Tuple[bool, Any]:
        """Connect to the MCP server.
        
        Returns:
            Tuple of (success, server_info).
            
        Raises:
            Various connection errors based on the failure mode.
        """
        if self.is_connected:
            logging.warning(f"Server {self.server_name} is already connected")
            return True, self.session.serverInfo if hasattr(self.session, "serverInfo") else None
        
        attempt = 0
        last_error = None
        
        while attempt < self.max_retries:
            try:
                if attempt > 0:
                    delay = self.retry_delay * (self.backoff_factor ** (attempt - 1))
                    logging.info(f"Retrying connection to {self.server_name} in {delay:.2f} seconds (attempt {attempt + 1}/{self.max_retries})")
                    await asyncio.sleep(delay)
                
                logging.info(f"Connecting to {self.server_type} server {self.server_name}")
                
                if self.server_type == "sse":
                    if not self.url:
                        raise ConnectionError(f"URL is required for SSE server {self.server_name}")
                    
                    url = self.url
                    if not urlparse(url).scheme:
                        raise ConnectionError(f"Invalid URL for SSE server {self.server_name}: {url}")
                    
                    try:
                        streams = await self._exit_stack.enter_async_context(sse_client(url))
                        read, write = streams
                    except ConnectionRefusedError as e:
                        raise NetworkError(f"Connection refused to {self.server_name} at {url}: {str(e)}")
                    except asyncio.TimeoutError as e:
                        raise TimeoutError(f"Connection timeout to {self.server_name} at {url}: {str(e)}")
                    except Exception as e:
                        raise ConnectionError(f"Failed to connect to {self.server_name} at {url}: {str(e)}")
                
                elif self.server_type == "stdio":
                    if not self.command:
                        raise ConnectionError(f"Command is required for stdio server {self.server_name}")
                    
                    import shutil
                    import os
                    
                    # Handle special case for npx and validate command
                    command = self.command
                    if command == "npx":
                        command = shutil.which("npx")
                    
                    if command is None:
                        raise ConnectionError(f"Invalid command for stdio server {self.server_name}: command not found")
                    
                    env = {**os.environ, **self.env} if self.env else None
                    
                    try:
                        # Use StdioServerParameters for better structure
                        server_params = StdioServerParameters(
                            command=command,
                            args=self.args,
                            env=env
                        )
                        
                        stdio_transport = await self._exit_stack.enter_async_context(
                            stdio_client(server_params)
                        )
                        read, write = stdio_transport
                    except FileNotFoundError as e:
                        raise NetworkError(f"Command not found for {self.server_name}: {str(e)}")
                    except PermissionError as e:
                        raise AuthenticationError(f"Permission denied for {self.server_name}: {str(e)}")
                    except Exception as e:
                        raise ConnectionError(f"Failed to connect to stdio server {self.server_name}: {str(e)}")
                
                else:
                    raise ConnectionError(f"Unsupported server type for {self.server_name}: {self.server_type}")
                
                # Initialize the session
                self.session = await self._exit_stack.enter_async_context(
                    ClientSession(read, write)
                )
                
                try:
                    init_result = await self.session.initialize()
                    server_info = init_result.serverInfo
                except Exception as e:
                    raise ProtocolError(f"Failed to initialize session with {self.server_name}: {str(e)}")
                
                logging.info(f"Connected to MCP server {self.server_name}")
                self._connected = True
                self._update_activity_timestamp()
                
                # Start health check task if interval is positive
                if self.health_check_interval > 0:
                    self._start_health_check()
                
                return True, server_info
                
            except (NetworkError, TimeoutError, AuthenticationError, ProtocolError) as e:
                logging.warning(f"Connection error to {self.server_name}: {str(e)}")
                last_error = e
                attempt += 1
                # Clean up any partial connection
                await self._cleanup_connection()
            
            except Exception as e:
                logging.error(f"Unexpected error connecting to {self.server_name}: {str(e)}")
                last_error = ConnectionError(f"Unexpected error: {str(e)}")
                attempt += 1
                # Clean up any partial connection
                await self._cleanup_connection()
        
        # All retries failed
        if last_error:
            raise last_error
        else:
            raise ConnectionError(f"Failed to connect to {self.server_name} after {self.max_retries} attempts")
    
    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        await self._cleanup_connection()
    
    async def _cleanup_connection(self) -> None:
        """Clean up the connection resources."""
        async with self._cleanup_lock:
            # Cancel health check task if running
            if self._health_check_task:
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
                self._health_check_task = None
            
            # Close exit stack to clean up connections
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                logging.error(f"Error closing connections for {self.server_name}: {e}")
            
            # Reset connection state
            self.session = None
            self._connected = False
            self._exit_stack = AsyncExitStack()
            logging.info(f"Disconnected from MCP server {self.server_name}")
    
    def _start_health_check(self) -> None:
        """Start the health check task."""
        if self._health_check_task is not None:
            self._health_check_task.cancel()
        
        self._health_check_task = asyncio.create_task(
            self._health_check_loop()
        )
    
    async def _health_check_loop(self) -> None:
        """Run periodic health checks."""
        try:
            while True:
                await asyncio.sleep(self.health_check_interval)
                await self._perform_health_check()
        except asyncio.CancelledError:
            # Task was cancelled, exit gracefully
            pass
        except Exception as e:
            logging.error(f"Error in health check loop for {self.server_name}: {e}")
    
    async def _perform_health_check(self) -> None:
        """Perform a health check on the connection."""
        if not self.is_connected:
            logging.warning(f"Health check skipped: {self.server_name} is not connected")
            return
        
        try:
            # Simple ping to check if the connection is still alive
            # This will vary based on the MCP implementation
            if hasattr(self.session, "ping"):
                await self.session.ping()
            else:
                # Fallback: check if list_tools works
                await self.session.list_tools()
            
            # Update activity timestamp on successful check
            self._update_activity_timestamp()
            logging.debug(f"Health check passed for {self.server_name}")
            
        except Exception as e:
            logging.warning(f"Health check failed for {self.server_name}: {e}")
            logging.info(f"Attempting to reconnect to {self.server_name}")
            
            # Disconnect and reconnect
            await self._cleanup_connection()
            try:
                await self.connect()
            except Exception as reconnect_error:
                logging.error(f"Failed to reconnect to {self.server_name}: {reconnect_error}")
    
    async def ensure_connected(self) -> bool:
        """Ensure the server is connected, reconnecting if necessary.
        
        Returns:
            True if connected (or reconnected), False otherwise.
        """
        if self.is_connected:
            return True
        
        try:
            success, _ = await self.connect()
            return success
        except Exception as e:
            logging.error(f"Failed to reconnect to {self.server_name}: {e}")
            return False
    
    async def execute_with_retry(
        self, 
        operation: Callable[[], Awaitable[Any]], 
        retries: int = 2,
        operation_name: str = "operation"
    ) -> Any:
        """Execute an operation with automatic reconnection on failure.
        
        Args:
            operation: Async callable operation to execute.
            retries: Number of retries for the operation.
            operation_name: Name of the operation for logging.
            
        Returns:
            Result of the operation.
            
        Raises:
            DisconnectedError: If reconnection fails.
            Exception: If the operation fails after all retries.
        """
        if not self.is_connected:
            # Try to reconnect first
            if not await self.ensure_connected():
                raise DisconnectedError(f"Server {self.server_name} is disconnected and reconnection failed")
        
        attempt = 0
        last_error = None
        
        while attempt <= retries:
            try:
                # Update activity timestamp
                self._update_activity_timestamp()
                
                # Execute the operation
                result = await operation()
                return result
                
            except Exception as e:
                attempt += 1
                last_error = e
                
                # Check if this looks like a disconnection
                if "not connected" in str(e).lower() or "connection" in str(e).lower():
                    logging.warning(f"{operation_name} failed due to connection issue: {e}")
                    
                    # Try to reconnect
                    await self._cleanup_connection()
                    try:
                        success, _ = await self.connect()
                        if not success:
                            raise DisconnectedError(f"Failed to reconnect to {self.server_name}")
                    except Exception as reconnect_error:
                        if attempt >= retries:
                            raise DisconnectedError(f"Failed to reconnect to {self.server_name}: {reconnect_error}")
                        logging.warning(f"Reconnection attempt {attempt} failed: {reconnect_error}")
                        # Continue to next retry
                        continue
                else:
                    # Not a connection issue, just retry the operation
                    logging.warning(f"{operation_name} failed (attempt {attempt}/{retries}): {e}")
                    
                # If we have retries left, wait before retrying
                if attempt <= retries:
                    delay = self.retry_delay * (self.backoff_factor ** (attempt - 1))
                    logging.info(f"Retrying {operation_name} in {delay:.2f} seconds")
                    await asyncio.sleep(delay)
        
        # All retries failed
        if last_error:
            raise last_error
        else:
            raise MCPServerError(f"{operation_name} failed after {retries} retries")
