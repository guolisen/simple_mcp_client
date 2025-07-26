"""Model classes for MCP server resources and tools."""
from typing import Dict, Any, List, Optional


class Tool:
    """Represents a tool with its properties."""

    def __init__(
        self, name: str, description: str, input_schema: Dict[str, Any]
    ) -> None:
        """Initialize a Tool instance.
        
        Args:
            name: The name of the tool.
            description: The description of the tool.
            input_schema: The JSON schema for the tool's input.
        """
        self.name: str = name
        self.description: str = description
        self.input_schema: Dict[str, Any] = input_schema

    def format_for_llm(self) -> str:
        """Format tool information for LLM.

        Returns:
            A formatted string describing the tool.
        """
        args_desc = []
        if "properties" in self.input_schema:
            for param_name, param_info in self.input_schema["properties"].items():
                arg_desc = (
                    f"- {param_name}: {param_info.get('description', 'No description')}"
                )
                if param_name in self.input_schema.get("required", []):
                    arg_desc += " (required)"
                args_desc.append(arg_desc)

        return f"""
Tool: {self.name}
Description: {self.description}
Arguments:
{chr(10).join(args_desc)}
"""


class Resource:
    """Represents a resource with its properties."""

    def __init__(
        self, uri: str, name: str, mime_type: Optional[str] = None, description: Optional[str] = None
    ) -> None:
        """Initialize a Resource instance.
        
        Args:
            uri: The URI of the resource.
            name: The name of the resource.
            mime_type: The MIME type of the resource.
            description: The description of the resource.
        """
        # Ensure uri is a string
        self.uri: str = str(uri) if uri is not None else ""
        self.name: str = name
        self.mime_type: Optional[str] = mime_type
        self.description: Optional[str] = description


class ResourceTemplate:
    """Represents a resource template with its properties."""

    def __init__(
        self, uri_template: str, name: str, mime_type: Optional[str] = None, description: Optional[str] = None
    ) -> None:
        """Initialize a ResourceTemplate instance.
        
        Args:
            uri_template: The URI template of the resource.
            name: The name of the resource.
            mime_type: The MIME type of the resource.
            description: The description of the resource.
        """
        # Ensure uri_template is a string
        self.uri_template: str = str(uri_template) if uri_template is not None else ""
        self.name: str = name
        self.mime_type: Optional[str] = mime_type
        self.description: Optional[str] = description


class Prompt:
    """Represents a prompt with its properties."""

    def __init__(
        self, name: str, description: str, input_schema: Dict[str, Any]
    ) -> None:
        """Initialize a Prompt instance.
        
        Args:
            name: The name of the prompt.
            description: The description of the prompt.
            input_schema: The JSON schema for the prompt's input.
        """
        self.name: str = name
        self.description: str = description
        self.input_schema: Dict[str, Any] = input_schema

    def format_for_llm(self) -> str:
        """Format prompt information for LLM.

        Returns:
            A formatted string describing the prompt.
        """
        args_desc = []
        if "properties" in self.input_schema:
            for param_name, param_info in self.input_schema["properties"].items():
                arg_desc = (
                    f"- {param_name}: {param_info.get('description', 'No description')}"
                )
                if param_name in self.input_schema.get("required", []):
                    arg_desc += " (required)"
                args_desc.append(arg_desc)

        return f"""
Prompt: {self.name}
Description: {self.description}
Arguments:
{chr(10).join(args_desc)}
"""


class PromptFormat:
    """Represents a prompt format with its properties."""

    def __init__(
        self, name: str, description: Optional[str] = None, schema: Optional[Dict[str, Any]] = None
    ) -> None:
        """Initialize a PromptFormat instance.
        
        Args:
            name: The name of the format.
            description: The description of the format.
            schema: The schema describing the format.
        """
        self.name: str = name
        self.description: Optional[str] = description
        self.schema: Optional[Dict[str, Any]] = schema
