"""Base LLM interface for MCP Client."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Generator


class Message:
    """Chat message."""
    
    def __init__(self, role: str, content: str):
        """Initialize a chat message.
        
        Args:
            role: Role of the message sender (system, user, assistant).
            content: Content of the message.
        """
        self.role = role
        self.content = content
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary representation.
        
        Returns:
            Dictionary representation of the message.
        """
        return {
            "role": self.role,
            "content": self.content
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "Message":
        """Create a message from a dictionary.
        
        Args:
            data: Dictionary representation of the message.
        
        Returns:
            Message instance.
        """
        return cls(data["role"], data["content"])
    
    def __str__(self) -> str:
        """String representation of the message.
        
        Returns:
            String representation.
        """
        return f"{self.role}: {self.content}"


class Conversation:
    """Chat conversation."""
    
    def __init__(self, system_message: Optional[str] = None):
        """Initialize a chat conversation.
        
        Args:
            system_message: Optional system message to set the context.
        """
        self.messages: List[Message] = []
        if system_message:
            self.add_system_message(system_message)
    
    def add_system_message(self, content: str) -> None:
        """Add a system message to the conversation.
        
        Args:
            content: Content of the message.
        """
        self.messages.append(Message("system", content))
    
    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation.
        
        Args:
            content: Content of the message.
        """
        self.messages.append(Message("user", content))
    
    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to the conversation.
        
        Args:
            content: Content of the message.
        """
        self.messages.append(Message("assistant", content))
    
    def get_messages(self) -> List[Message]:
        """Get all messages in the conversation.
        
        Returns:
            List of messages.
        """
        return self.messages
    
    def get_messages_as_dicts(self) -> List[Dict[str, str]]:
        """Get all messages in the conversation as dictionaries.
        
        Returns:
            List of message dictionaries.
        """
        return [message.to_dict() for message in self.messages]
    
    def clear(self) -> None:
        """Clear the conversation."""
        self.messages = []


class LLMBase(ABC):
    """Base class for LLM providers."""
    
    def __init__(self, model: str, **kwargs):
        """Initialize the LLM provider.
        
        Args:
            model: Model to use.
            **kwargs: Additional provider-specific arguments.
        """
        self.model = model
        self.kwargs = kwargs
    
    @abstractmethod
    def chat(self, conversation: Conversation, **kwargs) -> str:
        """Send a chat conversation to the LLM and get a response.
        
        Args:
            conversation: Chat conversation.
            **kwargs: Additional provider-specific arguments.
        
        Returns:
            LLM response.
        """
        pass
    
    @abstractmethod
    def chat_stream(self, conversation: Conversation, **kwargs) -> Generator[str, None, None]:
        """Send a chat conversation to the LLM and get a streaming response.
        
        Args:
            conversation: Chat conversation.
            **kwargs: Additional provider-specific arguments.
        
        Returns:
            Generator yielding response chunks.
        """
        pass
    
    @abstractmethod
    def get_available_models(self) -> List[str]:
        """Get a list of available models.
        
        Returns:
            List of model names.
        """
        pass
    
    @abstractmethod
    def validate_api_key(self) -> bool:
        """Validate the API key.
        
        Returns:
            True if the API key is valid, False otherwise.
        """
        pass
