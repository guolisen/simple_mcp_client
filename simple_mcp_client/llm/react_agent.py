"""ReAct agent implementation using LangGraph for enhanced tool reasoning."""
import logging
from typing import Dict, List, Optional, Any, Union
import asyncio
import json

from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import BaseMessage, ToolMessage, HumanMessage, SystemMessage, AIMessage

from ..config import Configuration
from ..mcp.langchain_adapter import MCPLangChainAdapter


class ReactAgentProvider:
    """ReAct agent provider using LangGraph for intelligent tool selection and reasoning."""
    
    def __init__(self, config: Configuration, mcp_adapter: MCPLangChainAdapter):
        """Initialize the ReAct agent provider.
        
        Args:
            config: The client configuration.
            mcp_adapter: The MCP LangChain adapter instance.
        """
        self.config = config
        self.mcp_adapter = mcp_adapter
        self.model = None
        self.graph = None
        self.tools = []
        self.system_message = ""
        self.timeout = config.config.llm.other_params.get("request_timeout", 60.0)
        self.loop_counter = 0
        self.max_loop_iterations = config.config.llm.other_params.get("max_loop_iterations", 15)
    
    async def initialize(self) -> bool:
        """Initialize the ReAct agent with LLM and MCP tools.
        
        Returns:
            True if initialization was successful, False otherwise.
        """
        try:
            # Initialize the language model
            llm_config = self.config.config.llm
            self.model = init_chat_model(
                llm_config.model,
                api_key=llm_config.api_key,
                base_url=llm_config.api_url,
                model_provider=llm_config.provider,
                temperature=llm_config.other_params.get("temperature", 0.7),
                max_tokens=llm_config.other_params.get("max_tokens", 4096),
            )
            
            # Get tools from MCP adapter
            if not self.mcp_adapter.is_initialized():
                await self.mcp_adapter.initialize_langchain_client()
            
            self.tools = await self.mcp_adapter.get_tools()
            
            # Create the ReAct agent graph
            await self._create_react_graph()
            
            logging.info(f"ReAct agent initialized with {len(self.tools)} tools")
            return True
            
        except Exception as e:
            logging.error(f"Failed to initialize ReAct agent: {e}")
            return False
    
    async def _create_react_graph(self) -> None:
        """Create the LangGraph StateGraph for ReAct agent."""
        def call_model(state: MessagesState):
            """Call the language model with bound tools."""
            # Add system message if not present
            messages = state["messages"]
            if not messages:
                if self.system_message:
                    # If no system message found, add our own
                    messages.insert(0, SystemMessage(content=self.system_message))
            else:
                found = False
                for _, msg in enumerate(messages):
                    if isinstance(msg, SystemMessage):
                        found = True
                        break
                if not found and self.system_message:
                    # If no system message found, add our own
                    messages.insert(0, SystemMessage(content=self.system_message))
            
            # Bind tools to the model and invoke
            response = self.model.bind_tools(self.tools).invoke(messages)
            return {"messages": messages + [response]}
        
        def should_end(state: MessagesState) -> str:
            """Determine if the conversation should end or continue with tools."""
            # Increment the loop counter
            self.loop_counter += 1
            
            # Check if max iterations reached
            if self.loop_counter >= self.max_loop_iterations:
                logging.warning(f"ReAct agent reached maximum loop iterations ({self.max_loop_iterations}), forcing end")
                return "end"
            
            last_message = state["messages"][-1]
            
            # Check if last message is from the AI and doesn't contain a tool call
            if (isinstance(last_message, AIMessage) and 
                not getattr(last_message, "tool_calls", None)):
                return "end"
            
            # If the message is a tool message or has tool calls, continue with tools
            return "tools"
        
        # Build the StateGraph
        builder = StateGraph(MessagesState)
        builder.add_node("call_model", call_model)
        builder.add_node("tools", ToolNode(self.tools))
        
        # Add edges
        builder.add_edge(START, "call_model")
        builder.add_conditional_edges(
            "call_model",
            should_end,
            {
                "tools": "tools",
                "end": END,
                "__end__": END
            }
        )
        builder.add_edge("tools", "call_model")
        
        # Compile the graph
        self.graph = builder.compile()
    
    def set_system_message(self, message: str) -> None:
        """Set the system message for the agent.
        
        Args:
            message: The system message to set.
        """
        self.system_message = message
    
    async def get_response(self, messages: List[Dict[str, str]]) -> str:
        """Get a response from the ReAct agent.
        
        Args:
            messages: List of conversation messages.
            
        Returns:
            The agent's response.
        """
        if not self.graph:
            raise RuntimeError("ReAct agent not initialized. Call initialize() first.")
        
        # Reset loop counter for new conversation
        self.loop_counter = 0
        
        try:
            # Convert messages to the format expected by LangGraph
            formatted_messages = []
            for msg in messages:
                if msg["role"] == "system" and not formatted_messages:
                    # Skip system message if we're adding our own
                    continue
                formatted_messages.append(msg)
            
            # Create the input for the graph
            graph_input = {"messages": formatted_messages}
            
            # Configure timeout
            config = RunnableConfig(
                configurable={"timeout": self.timeout}
            )
            
            # Run the graph
            response = await self.graph.ainvoke(graph_input, config=config)
            
            # Extract the final message
            final_message = response["messages"][-1]
            
            # Handle different types of message objects safely
            if isinstance(final_message, dict):
                # Dictionary access
                if "content" in final_message:
                    return final_message["content"]
                else:
                    return str(final_message)
            else:
                # Object attribute access - using hasattr for safety
                if hasattr(final_message, "content"):
                    return final_message.content
                else:
                    return str(final_message)
                
        except asyncio.TimeoutError:
            raise RuntimeError(f"ReAct agent response timed out after {self.timeout} seconds")
        except Exception as e:
            logging.error(f"Error getting ReAct agent response: {e}")
            raise
    
    async def stream_response(self, messages: List[Dict[str, str]]):
        """Stream a response from the ReAct agent.
        
        Args:
            messages: List of conversation messages.
            
        Yields:
            Chunks of the agent's response and tool executions.
        """
        if not self.graph:
            raise RuntimeError("ReAct agent not initialized. Call initialize() first.")
        
        # Reset loop counter for new conversation
        self.loop_counter = 0
        
        try:
            # Convert messages to the format expected by LangGraph
            formatted_messages = []
            for msg in messages:
                if msg["role"] == "system" and not formatted_messages:
                    # Skip system message if we're adding our own
                    continue
                formatted_messages.append(msg)
            
            # Create the input for the graph
            graph_input = {"messages": formatted_messages}
            
            # Configure timeout
            config = RunnableConfig(
                configurable={"timeout": self.timeout}
            )
            
            # Stream the graph execution with proper chunk handling
            async for chunk in self.graph.astream(graph_input, config=config):
                # Add debug logging for chunk structure
                if "call_model" in chunk:
                    # Log the structure of call_model chunks
                    messages = chunk["call_model"].get("messages", [])
                    if messages and len(messages) > 0:
                        last_message = messages[-1]
                        if hasattr(last_message, "additional_kwargs") and hasattr(last_message.additional_kwargs, "get"):
                            tool_calls = last_message.additional_kwargs.get("tool_calls", [])
                            if tool_calls:
                                logging.debug(f"Found tool calls in chunk: {tool_calls}")
                
                # Process the chunk to safely handle different types of objects
                if isinstance(chunk, dict):
                    yield chunk
                else:
                    # Convert non-dict objects to a safe format
                    yield {"data": str(chunk)}
                
        except asyncio.TimeoutError:
            raise RuntimeError(f"ReAct agent response timed out after {self.timeout} seconds")
        except Exception as e:
            logging.error(f"Error streaming ReAct agent response: {e}")
            raise
    
    async def refresh_tools(self) -> None:
        """Refresh the tools from MCP servers and recreate the graph."""
        try:
            self.tools = await self.mcp_adapter.refresh_tools()
            await self._create_react_graph()
            logging.info(f"ReAct agent tools refreshed: {len(self.tools)} tools available")
        except Exception as e:
            logging.error(f"Error refreshing ReAct agent tools: {e}")
            raise
    
    def get_tool_count(self) -> int:
        """Get the number of available tools.
        
        Returns:
            Number of available tools.
        """
        return len(self.tools)
    
    def get_model_info(self) -> Dict[str, str]:
        """Get information about the underlying model.
        
        Returns:
            Dictionary with model information.
        """
        llm_config = self.config.config.llm
        return {
            "provider": llm_config.provider,
            "model": llm_config.model,
            "api_url": llm_config.api_url,
        }
    
    async def close(self) -> None:
        """Close the ReAct agent and clean up resources."""
        try:
            self.graph = None
            self.model = None
            self.tools = []
            logging.info("ReAct agent closed")
        except Exception as e:
            logging.error(f"Error closing ReAct agent: {e}")
    
    def is_initialized(self) -> bool:
        """Check if the ReAct agent is initialized.
        
        Returns:
            True if initialized, False otherwise.
        """
        return self.graph is not None and self.model is not None
