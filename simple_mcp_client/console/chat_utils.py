"""Utility functions for the enhanced chat command with ReAct agent."""
import logging
from typing import Dict, List, Optional, Any
import json

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from ..config import Configuration
from ..mcp.manager import ServerManager
from ..mcp.langchain_adapter import MCPLangChainAdapter
from ..llm.react_agent import ReactAgentProvider
from ..prompt.system import generate_system_prompt, generate_tool_format


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
            include_react_guidance=True
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


def format_tool_execution_display(tool_name: str, arguments: Dict[str, Any], result: Any) -> str:
    """Format tool execution for display in the console.
    
    Args:
        tool_name: Name of the executed tool.
        arguments: Arguments passed to the tool.
        result: Result returned by the tool.
        
    Returns:
        Formatted string for display.
    """
    display_parts = []
    
    # Tool name and arguments
    display_parts.append(f"**Tool:** {tool_name}")
    
    if arguments:
        args_str = json.dumps(arguments, indent=2)
        display_parts.append(f"**Arguments:**\n```json\n{args_str}\n```")
    
    # Result
    if isinstance(result, str):
        display_parts.append(f"**Result:**\n{result}")
    elif isinstance(result, dict) or isinstance(result, list):
        result_str = json.dumps(result, indent=2)
        display_parts.append(f"**Result:**\n```json\n{result_str}\n```")
    else:
        display_parts.append(f"**Result:**\n{str(result)}")
    
    return "\n\n".join(display_parts)


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
                    if hasattr(last_message, "content"):
                        return {
                            "type": "model_response",
                            "content": last_message.content
                        }
            
            elif "tools" in chunk:
                # Tool execution chunk
                return {
                    "type": "tool_execution",
                    "data": chunk["tools"]
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
    
    while True:
        try:
            # Get user input
            user_input = await session.prompt_async(
                "You: ",
                style={"prompt": "ansicyan bold"}
            )
            
            user_input = user_input.strip()
            if user_input.lower() == "exit":
                console.print("[yellow]Exiting chat mode...[/yellow]")
                break
            
            if not user_input:
                continue
            
            # Add user message to conversation
            messages.append({"role": "user", "content": user_input})
            
            # Get response from ReAct agent
            try:
                with console.status("[bold green]Agent thinking and acting...[/bold green]"):
                    response = await react_agent.get_response(messages)
                
                # Display the response
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
