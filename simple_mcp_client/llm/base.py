"""Base classes for LLM providers."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, model: str, api_url: Optional[str] = None, api_key: Optional[str] = None):
        """Initialize the LLM provider.
        
        Args:
            model: The model to use.
            api_url: The API URL to use.
            api_key: The API key to use.
        """
        self.model = model
        self.api_url = api_url
        self.api_key = api_key
        self.system_message: Optional[str] = None

    @property
    def name(self) -> str:
        """Get the provider name."""
        return self.__class__.__name__.replace("Provider", "")

    def set_system_message(self, message: str) -> None:
        """Set the system message for the LLM.
        
        Args:
            message: The system message to set.
        """
        self.system_message = message

    @abstractmethod
    async def get_response(self, messages: List[Dict[str, str]]) -> str:
        """Get a response from the LLM.
        
        Args:
            messages: A list of message dictionaries.
            
        Returns:
            The LLM's response as a string.
        """
        pass


class LLMProviderFactory:
    """Factory for creating LLM providers."""

    @staticmethod
    def create(provider: str, model: str, api_url: Optional[str] = None, 
               api_key: Optional[str] = None, **kwargs: Any) -> LLMProvider:
        """Create an LLM provider.
        
        Args:
            provider: The provider name.
            model: The model to use.
            api_url: The API URL to use.
            api_key: The API key to use.
            **kwargs: Additional keyword arguments to pass to the provider.
            
        Returns:
            An LLM provider instance.
            
        Raises:
            ValueError: If the provider is not supported.
        """
        if provider.lower() == "ollama":
            from .ollama import OllamaProvider
            return OllamaProvider(model, api_url, api_key, **kwargs)
        elif provider.lower() == "openai":
            from .openai import OpenAIProvider
            return OpenAIProvider(model, api_url, api_key, **kwargs)
        elif provider.lower() == "deepseek":
            from .deepseek import DeepseekProvider
            return DeepseekProvider(model, api_url, api_key, **kwargs)
        elif provider.lower() == "openrouter":
            from .openrouter import OpenRouterProvider
            return OpenRouterProvider(model, api_url, api_key, **kwargs)
        elif provider.lower() == "litellm":
            from .litellm import LiteLLMProvider
            return LiteLLMProvider(model, api_url, api_key, **kwargs)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
