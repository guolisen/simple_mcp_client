"""System prompt templates for Simple_mcp_client.

This module provides enhanced system prompt templates with modular components
for different aspects of the system, including tool usage, MCP integration,
React loop guidance, and more.
"""

from typing import Dict, List, Optional, Any

from ..config import Configuration
from ..mcp.server import Tool


def get_introduction(config: Optional[Configuration] = None) -> str:
    """Get the introduction section of the system prompt.
    
    Args:
        config: Optional configuration object containing custom introduction text.
        
    Returns:
        The introduction section of the system prompt.
    """
    default_intro = """You are MCP client, an AI assistant specialized in Kubernetes cluster management and cloud infrastructure operations. You have deep knowledge of container orchestration, deployment strategies, networking, and cloud environments.

===="""
    
    if config and hasattr(config.config, "prompts") and config.config.prompts.base_introduction:
        # Use the configured introduction text
        intro_text = config.config.prompts.base_introduction
        # Ensure the introduction ends with the separator
        if not intro_text.endswith("===="):
            intro_text += "\n\n===="
        return intro_text
    
    # Fall back to default introduction
    return default_intro


def get_react_loop_guidance() -> str:
    """Get the ReAct loop guidance section of the system prompt."""
    return """
REASONING AND ACTING (ReAct) PROCESS

When working on tasks, follow this reasoning and acting process:

1. REASONING: Analyze the user's request and current context
   - Understand what information you have and what you need
   - Break down complex tasks into smaller steps
   - Consider potential approaches and their tradeoffs

2. ACTING: Take appropriate actions using tools
   - Choose the right tool for the current step
   - Provide clear parameters based on your reasoning
   - Execute one action at a time

3. OBSERVING: Analyze the results
   - Interpret the information received
   - Identify any issues or unexpected results
   - Update your understanding based on new information

4. PLANNING: Determine the next steps
   - Decide if you have enough information to respond
   - Plan additional actions if needed
   - Prepare a clear response based on all information gathered

5. ENDING: Properly conclude the ReAct loop
   - Recognize when a task is fully complete and no more tool calls are needed
   - Provide a final comprehensive response that directly answers the user's request
   - Summarize key findings and actions taken when appropriate
   - Do not make additional tool calls once you have all needed information
   - End with actionable insights or next steps if relevant

This iterative process ensures thorough analysis and effective problem-solving for Kubernetes management tasks.
"""


def get_mcp_integration_guidance() -> str:
    """Get the MCP integration guidance section of the system prompt."""
    return """
MCP SERVER INTEGRATION

Model Context Protocol (MCP) servers provide specialized tools and resources for different clusters and operations. Each MCP server may offer different capabilities:

1. CLUSTER-SPECIFIC SERVERS
   - Connected to specific Kubernetes clusters
   - Provide tools for interacting with cluster resources
   - May offer specialized operations for the cluster's environment

2. LOCAL SERVERS
   - Run locally on the user's machine
   - Provide general-purpose functionality
   - May interact with local resources or configurations

3. REMOTE SERVERS
   - Connect to remote APIs or services
   - Provide integration with external platforms
   - May require specific authentication or parameters

When multiple MCP servers are available, consider which one is most appropriate for the current task based on the cluster context and required functionality.
"""


def get_response_guidelines() -> str:
    """Get guidelines for response formatting."""
    return """
RESPONSE GUIDELINES

When responding to users:

1. Be concise and focused on the Kubernetes management task at hand
2. Provide clear, actionable information that directly addresses the user's question
3. Include relevant YAML examples when suggesting configurations
4. Explain the reasoning behind your recommendations
5. Highlight potential issues or considerations for production environments
6. If there are multiple approaches, briefly explain the tradeoffs

<< MUST IMPORTANT NOTICE >>:
When calling MCP tools, you MUST strictly follow these rules:
    - Return ONLY a valid JSON object formatted as a tool call request
    - Absolutely NO explanations, comments, or extra text
    - Do NOT include any reasoning or thought process

Format longer YAML examples or command outputs in code blocks for readability.
"""

def get_tool_usage_guidance() -> str:
    """Get test for response formatting."""
    return """
\n\n
==========

Choose the appropriate tool based on the user's question. 
    - If no tool is needed, reply directly.
    - If cannot find the parameters from current context, ask user for more information. 
IMPORTANT: When you need to use a tool, you must ONLY respond with
the exact JSON object format below, nothing else:\n

{
  "server": "server_name",
  "tool": "tool_name",      // Must be the exact tool name from the description
  "parameters": {
    "param1": "value1",
    "param2": "value2"
  }
}

*<< IMPORTANT AFTER RECEIVING A TOOL'S RESPONSE >>*:\n
When you receive a tool's response, follow these steps:\n
1. Transform the raw data into a natural, conversational response\n
2. Keep responses concise but informative\n
3. Focus on the most relevant information\n
4. Use appropriate context from the user's question\n
5. Avoid simply repeating the raw data\n
6. If no need to call tools, summerize all of message and give the final response according to user's query\n

*<<TOOL USAGE GUIDELINES>>*
*<< MUST IMPORTANT NOTICE >>*:
When calling MCP tools, you MUST strictly follow these rules:
    - Return ONLY a valid JSON object formatted as a tool call request
    - Absolutely NO explanations, comments, or extra text
    - Do NOT include any reasoning or thought process
    - Do NOT respond with any other text, just the JSON object\n\n
"""

def generate_system_prompt(
    available_tools: str,
    include_mcp_guidance: bool = True,
    include_react_guidance: bool = True,
    config: Optional[Configuration] = None,
) -> str:
    """Generate a complete system prompt with all components.
    
    Args:
        available_tools: String describing available tools.
        include_mcp_guidance: Whether to include MCP guidance.
        include_react_guidance: Whether to include ReAct guidance.
        config: Optional configuration object containing custom prompt settings.
        
    Returns:
        Complete system prompt as a string.
    """
    # Start with introduction
    prompt_parts = [get_introduction(config)]
    
    # Add optional sections
    if include_react_guidance:
        prompt_parts.append(get_react_loop_guidance())
    
    if include_mcp_guidance:
        prompt_parts.append(get_mcp_integration_guidance())

    prompt_parts.append("\n=============\n")
    # Add tool usage guidance
    prompt_parts.append("AVAILABLE TOOLS:\n" + available_tools)
    prompt_parts.append(get_tool_usage_guidance())

    # Combine all sections
    return "\n\n".join(prompt_parts)


def generate_tool_format(
    tools_by_server: Dict[str, List[Tool]],
) -> str:
    """Generate a formatted description of tools grouped by server.
    
    This function follows a simple format inspired by the Python SDK example,
    focusing on tool names, descriptions, and parameters.
    
    Args:
        tools_by_server: Dictionary mapping server names to lists of tools.
        
    Returns:
        Formatted string describing available tools.
    """
    if not tools_by_server:
        return "No tools available."
    
    sections = []
    
    for server_name, tools in tools_by_server.items():
        section_title = f"Server: {server_name}"
        tool_descriptions = []
        
        for tool in tools:
            name = tool.name
            description = tool.description
            
            # Format input schema information if available
            input_params = []
            input_schema = tool.input_schema
            properties = input_schema.get("properties", {})
            required = input_schema.get("required", [])
            
            for param_name, param_info in properties.items():
                param_desc = param_info.get("description", "No description")
                is_required = param_name in required
                req_marker = " (required)" if is_required else ""
                
                input_params.append(f"- {param_name}: {param_desc}{req_marker}")
            
            # Format tool description
            tool_desc = [f"\nTool: {name}"]
            tool_desc.append(f"Description: {description}")
            
            if input_params:
                tool_desc.append("Arguments:")
                tool_desc.extend(input_params)
            
            tool_descriptions.append("\n".join(tool_desc))
        
        # Add server section to sections
        if tool_descriptions:
            sections.append(f"{section_title}\n\n" + "\n\n".join(tool_descriptions))
    
    return "\n\n".join(sections)
