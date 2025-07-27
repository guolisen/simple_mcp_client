"""Utility functions for the enhanced chat command with ReAct agent."""
import logging
from typing import Dict, List, Optional, Any
import json
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from ..config import Configuration
from ..mcp.manager import ServerManager
from ..mcp.langchain_adapter import MCPLangChainAdapter
from ..llm.react_agent import ReactAgentProvider
from ..prompt.system import generate_system_prompt, generate_tool_format
from .tool_formatter import format_tool_call_markdown, format_tool_result_markdown
from langchain_core.messages import BaseMessage, ToolMessage, HumanMessage, SystemMessage, AIMessage


async def initialize_mcp_client(server_manager: ServerManager) -> MCPLangChainAdapter:
    """Initialize the MCP LangChain adapter with connected servers.
    
    Args:
        server_manager: The server manager instance.
        
    Returns:
        Initialized MCP LangChain adapter.
        
    Raises:
        RuntimeError: If no servers are connected or initialization fails.
    """
    connected_servers = server_manager.get_connected_servers()
    if not connected_servers:
        raise RuntimeError("No MCP servers connected. Please connect to at least one server before starting chat.")
    
    # Create and initialize the adapter
    mcp_adapter = MCPLangChainAdapter(server_manager)
    success = await mcp_adapter.initialize_langchain_client(use_standard_content_blocks=True)
    
    if not success:
        raise RuntimeError("Failed to initialize MCP LangChain client")
    
    logging.info(f"MCP client initialized with {mcp_adapter.get_server_count()} servers")
    return mcp_adapter


async def create_react_agent(config: Configuration, mcp_adapter: MCPLangChainAdapter) -> ReactAgentProvider:
    """Create and initialize the ReAct agent.
    
    Args:
        config: The client configuration.
        mcp_adapter: The MCP LangChain adapter instance.
        
    Returns:
        Initialized ReAct agent provider.
        
    Raises:
        RuntimeError: If agent initialization fails.
    """
    # Create the ReAct agent
    react_agent = ReactAgentProvider(config, mcp_adapter)
    
    # Initialize the agent
    success = await react_agent.initialize()
    if not success:
        raise RuntimeError("Failed to initialize ReAct agent")
    
    # Generate and set system prompt
    try:
        # Get tools for system prompt generation
        tools = await mcp_adapter.get_tools()
        
        # Format tools description (simplified for system prompt)
        tools_description = ""
        if tools:
            tools_description = f"You have access to {len(tools)} tools from connected MCP servers. "
            tools_description += "Use these tools to help answer user questions and complete tasks. "
            tools_description += "The tools will be automatically bound to your responses when needed."
        
        # Generate enhanced system prompt
        system_prompt = generate_system_prompt(
            available_tools=tools_description,
            include_mcp_guidance=True,
            include_react_guidance=True,
            config=config
        )
        
        react_agent.set_system_message(system_prompt)
        
    except Exception as e:
        logging.warning(f"Failed to generate enhanced system prompt, using basic prompt: {e}")
        # Fallback to basic system prompt
        basic_prompt = (
            "You are a helpful assistant with access to tools through the Model Context Protocol (MCP). "
            "Use the available tools to help answer user questions and complete tasks. "
            "Think step by step and use tools when they can provide useful information or perform actions."
        )
        react_agent.set_system_message(basic_prompt)
    
    logging.info(f"ReAct agent created with {react_agent.get_tool_count()} tools")
    return react_agent


def format_tool_execution_display(tool_name: str, arguments: Dict[str, Any], result: Any, 
                                server_name: str = "unknown") -> str:
    """Format tool execution for display in the console.
    
    Args:
        tool_name: Name of the executed tool.
        arguments: Arguments passed to the tool.
        result: Result returned by the tool.
        server_name: Name of the server that executed the tool.
        
    Returns:
        Formatted string for display.
    """
    # Get current time for timestamps
    start_time = datetime.now()
    
    # Format tool call
    call_markdown = format_tool_call_markdown(server_name, tool_name, arguments, start_time)
    
    # Format tool result
    result_markdown = format_tool_result_markdown(server_name, tool_name, result, start_time, 
                                               datetime.now(), success=True)
    
    return f"{call_markdown}\n\n{result_markdown}"


def display_chat_header(console: Console, react_agent: ReactAgentProvider, mcp_adapter: MCPLangChainAdapter) -> None:
    """Display the chat session header with agent and server information.
    
    Args:
        console: Rich console instance.
        react_agent: The ReAct agent provider.
        mcp_adapter: The MCP LangChain adapter.
    """
    model_info = react_agent.get_model_info()
    server_names = mcp_adapter.get_connected_server_names()
    tool_count = react_agent.get_tool_count()
    
    header_content = (
        f"**ReAct Agent:** {model_info['provider']}/{model_info['model']}\n"
        f"**Connected Servers:** {', '.join(server_names)}\n"
        f"**Available Tools:** {tool_count}\n"
        f"**Timeout:** {react_agent.timeout}s\n\n"
        "The agent will use ReAct (Reasoning and Acting) to intelligently select and use tools.\n"
        "Type **exit** to return to command mode."
    )
    
    console.print(Panel.fit(
        header_content,
        title="Enhanced MCP Chat with ReAct Agent",
        border_style="green"
    ))


def parse_streaming_chunk(chunk: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse a streaming chunk from the ReAct agent.
    
    Args:
        chunk: Raw chunk from the agent stream.
        
    Returns:
        Parsed chunk information or None if not relevant.
    """
    try:
        # Extract relevant information from the chunk
        if isinstance(chunk, dict):
            # Look for different types of chunks
            if "call_model" in chunk:
                # Model call chunk
                messages = chunk["call_model"].get("messages", [])
                if messages:
                    last_message = messages[-1]
                    
                    # Check for tool calls in AIMessage
                    tool_calls = None
                    if isinstance(last_message, dict):
                        # Check for tool_calls in additional_kwargs
                        additional_kwargs = last_message.get("additional_kwargs", {})
                        tool_calls = additional_kwargs.get("tool_calls", [])
                        
                        # Also check for tool_calls directly in the message
                        if not tool_calls and "tool_calls" in last_message:
                            tool_calls = last_message["tool_calls"]
                            
                    elif hasattr(last_message, "additional_kwargs") and hasattr(last_message.additional_kwargs, "get"):
                        # Object with additional_kwargs attribute
                        tool_calls = last_message.additional_kwargs.get("tool_calls", [])
                    
                    # If we found tool calls, process them
                    if tool_calls:
                        # Extract the first tool call (usually there's just one)
                        tool_call = tool_calls[0]
                        
                        # Log the tool call for debugging
                        logging.debug(f"Found tool call in AIMessage: {tool_call}")
                        
                        # Extract function info
                        function_info = tool_call.get("function", {})
                        if isinstance(function_info, dict):
                            tool_name = function_info.get("name", "unknown_tool")
                            args_str = function_info.get("arguments", "{}")
                            
                            # Parse arguments string to dict
                            try:
                                args = json.loads(args_str, strict=False)
                            except json.JSONDecodeError:
                                args = {"raw_args": args_str}
                                logging.warning(f"Failed to parse tool arguments as JSON: {args_str}")
                                
                            # Create tool call data
                            logging.info(f"Extracted tool call: {tool_name} with args: {args}")
                            return {
                                "type": "tool_call",
                                "data": {
                                    "name": tool_name,
                                    "args": args,
                                    "id": tool_call.get("id", "")
                                },
                                "server_name": "unknown"  # Server name will be determined later
                            }
                    
                    # If no tool calls, process as regular model response
                    if isinstance(last_message, dict) and "content" in last_message:
                        return {
                            "type": "model_response",
                            "content": last_message["content"]
                        }
                    elif hasattr(last_message, "content"):
                        return {
                            "type": "model_response",
                            "content": last_message.content
                        }
            
            elif "tools" in chunk:
                # Tool execution chunk
                tool_data = chunk["tools"]
                
                # Extract server name if available
                server_name = "unknown"
                if isinstance(tool_data, dict) and "server_name" in tool_data:
                    server_name = tool_data["server_name"]
                
                return {
                    "type": "tool_execution",
                    "data": tool_data,
                    "server_name": server_name
                }
            
            # Handle data field for non-standard chunks
            elif "data" in chunk:
                return {
                    "type": "other",
                    "data": chunk["data"]
                }
        
        return None
        
    except Exception as e:
        logging.debug(f"Error parsing streaming chunk: {e}")
        return None


async def run_chat_loop(console: Console, react_agent: ReactAgentProvider, 
                       mcp_adapter: MCPLangChainAdapter, session) -> None:
    """Run the main chat loop with the ReAct agent.
    
    Args:
        console: Rich console instance.
        react_agent: The ReAct agent provider.
        mcp_adapter: The MCP LangChain adapter.
        session: Prompt session for user input.
    """
    messages = []
    
    # Import formatter here to avoid circular imports
    from .tool_formatter import default_formatter
    
    while True:
        try:
            # Get user input
            user_input = await session.prompt_async(
                "You: "
            )
            
            user_input = user_input.strip()
            if user_input.lower() == "exit":
                console.print("[yellow]Exiting chat mode...[/yellow]")
                break
            
            if not user_input:
                continue
            
            # Add user message to conversation
            messages.append({"role": "user", "content": user_input})
            
            # Get response from ReAct agent using streaming API
            try:
                with console.status("[bold green]Agent thinking and acting...[/bold green]") as status:
                    # Use streaming API to intercept tool calls
                    final_response_parts = []
                    current_tool_call = None
                    tool_call_start_time = None
                    
                    async for chunk in react_agent.stream_response(messages):
                        # Parse the chunk
                        parsed_chunk = parse_streaming_chunk(chunk)
                        
                        if parsed_chunk:
                            if parsed_chunk["type"] == "model_response":
                                # Accumulate model response parts
                                content = parsed_chunk["content"]
                                if content:
                                    final_response_parts.append(content)
                            
                            elif parsed_chunk["type"] == "tool_call":
                                # Extract tool data for tool call
                                tool_data = parsed_chunk["data"]
                                server_name = parsed_chunk.get("server_name", "unknown")
                                
                                # Extract tool information
                                tool_name = tool_data["name"]
                                tool_args = tool_data["args"]
                                tool_call_start_time = datetime.now()
                                
                                # Log the tool call
                                logging.info(f"Processing tool call: {tool_name} with args: {tool_args}")
                                
                                # Temporarily clear the status to show tool call
                                status.stop()
                                
                                # Format and display tool call
                                default_formatter.print_tool_call(
                                    server_name, tool_name, tool_args, tool_call_start_time
                                )
                                
                                # Store current tool call info
                                current_tool_call = {
                                    "server_name": server_name,
                                    "tool_name": tool_name,
                                    "start_time": tool_call_start_time,
                                    "id": tool_data.get("id", "")
                                }
                                
                                # Resume the status
                                status.start()
                                
                            elif parsed_chunk["type"] == "tool_execution":
                                # Extract tool data
                                tool_data = parsed_chunk["data"]
                                server_name = parsed_chunk.get("server_name", "unknown")
                                
                                # Extract ToolMessage from messages array
                                if "messages" in tool_data and len(tool_data["messages"]) > 0:
                                    # Get the first ToolMessage
                                    tool_message = tool_data["messages"][0]
                                    
                                    # Check if it's a ToolMessage object with content and name
                                    if hasattr(tool_message, 'content') and hasattr(tool_message, 'name'):
                                        # Extract tool name
                                        tool_name = tool_message.name
                                        
                                        # Parse the content which is a JSON string
                                        try:
                                            tool_result = json.loads(tool_message.content)
                                        except (json.JSONDecodeError, TypeError):
                                            # If parsing fails, use the content as is
                                            tool_result = tool_message.content
                                        
                                        # Log the tool result
                                        logging.info(f"Processing ToolMessage result for {tool_name}: {tool_result}")
                                        
                                        # Display the tool result if we have a current tool call
                                        if current_tool_call:
                                            # Temporarily clear the status to show tool result
                                            status.stop()
                                            
                                            # Format and display tool result
                                            default_formatter.print_tool_result(
                                                current_tool_call["server_name"],
                                                current_tool_call["tool_name"],
                                                tool_result,
                                                current_tool_call["start_time"],
                                                datetime.now(),
                                                success=True
                                            )
                                            
                                            # Reset current tool call
                                            current_tool_call = None
                                            
                                            # Resume the status
                                            status.start()
                                
                                # Handle original format for tool calls
                                elif "name" in tool_data and "args" in tool_data:
                                    # Tool call
                                    tool_name = tool_data["name"]
                                    tool_args = tool_data["args"]
                                    tool_call_start_time = datetime.now()
                                    
                                    # Temporarily clear the status to show tool call
                                    status.stop()
                                    
                                    # Format and display tool call
                                    default_formatter.print_tool_call(
                                        server_name, tool_name, tool_args, tool_call_start_time
                                    )
                                    
                                    # Store current tool call info
                                    current_tool_call = {
                                        "server_name": server_name,
                                        "tool_name": tool_name,
                                        "start_time": tool_call_start_time
                                    }
                                    
                                    # Resume the status
                                    status.start()
                                
                                # Handle original format for tool results
                                elif "output" in tool_data and current_tool_call:
                                    # Tool result
                                    tool_result = tool_data["output"]
                                    tool_end_time = datetime.now()
                                    
                                    # Log the tool result
                                    logging.info(f"Processing tool result for {current_tool_call['tool_name']}: {tool_result}")
                                    
                                    # Temporarily clear the status to show tool result
                                    status.stop()
                                    
                                    # Format and display tool result
                                    default_formatter.print_tool_result(
                                        current_tool_call["server_name"],
                                        current_tool_call["tool_name"],
                                        tool_result,
                                        current_tool_call["start_time"],
                                        tool_end_time,
                                        success=True
                                    )
                                    
                                    # Reset current tool call
                                    current_tool_call = None
                                    
                                    # Resume the status
                                    status.start()
                    
                    # Combine all response parts into the final response
                    response = "".join(final_response_parts)
                
                # Display the final response
                console.print(Panel(
                    Markdown(response),
                    title="Assistant",
                    border_style="green"
                ))
                
                # Add assistant response to conversation
                messages.append({"role": "assistant", "content": response})
                
            except Exception as e:
                error_msg = f"Error getting agent response: {str(e)}"
                console.print(f"[red]{error_msg}[/red]")
                logging.error(error_msg)
                
                # Add error to conversation context
                messages.append({"role": "system", "content": f"Error occurred: {str(e)}"})
        
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Exiting chat mode...[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Unexpected error in chat loop: {str(e)}[/red]")
            logging.error(f"Unexpected error in chat loop: {e}")


async def cleanup_chat_resources(mcp_adapter: MCPLangChainAdapter, react_agent: ReactAgentProvider) -> None:
    """Clean up chat resources.
    
    Args:
        mcp_adapter: The MCP LangChain adapter to clean up.
        react_agent: The ReAct agent to clean up.
    """
    try:
        if react_agent:
            await react_agent.close()
        if mcp_adapter:
            await mcp_adapter.close()
        logging.info("Chat resources cleaned up successfully")
    except Exception as e:
        logging.error(f"Error cleaning up chat resources: {e}")
