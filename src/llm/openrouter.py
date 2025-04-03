"""OpenRouter LLM provider for MCP Client."""

import os
from typing import Dict, List, Optional, Generator
import logging

try:
    from openai import OpenAI
    from openai.types.chat import ChatCompletion, ChatCompletionChunk
except ImportError:
    logging.error("OpenAI package not installed. Install it with 'pip install openai'.")
    raise

from .base import LLMBase, Conversation


class OpenRouterLLM(LLMBase):
    """OpenRouter LLM provider."""
    
    def __init__(self, model: str = "anthropic/claude-3-opus", api_key: Optional[str] = None, **kwargs):
        """Initialize the OpenRouter LLM provider.
        
        Args:
            model: Model to use.
            api_key: OpenRouter API key. If not provided, will try to use the OPENROUTER_API_KEY environment variable.
            **kwargs: Additional provider-specific arguments.
        """
        super().__init__(model, **kwargs)
        
        # Use provided API key or try to get from environment
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            logging.warning("No OpenRouter API key provided. Set it in the configuration or OPENROUTER_API_KEY environment variable.")
        
        # Initialize OpenAI client with OpenRouter base URL
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1"
        )
    
    def chat(self, conversation: Conversation, **kwargs) -> str:
        """Send a chat conversation to OpenRouter and get a response.
        
        Args:
            conversation: Chat conversation.
            **kwargs: Additional arguments to pass to the OpenRouter API.
        
        Returns:
            OpenRouter response.
        """
        if not self.api_key:
            raise ValueError("OpenRouter API key not provided.")
        
        # Prepare messages
        messages = conversation.get_messages_as_dicts()
        
        # Set default parameters
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2000,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
            "headers": {
                "HTTP-Referer": "https://mcp-client.local",  # Required by OpenRouter
                "X-Title": "MCP Client"  # Optional, helps OpenRouter identify your app
            }
        }
        
        # Update with any provided kwargs
        if "headers" in kwargs:
            params["headers"].update(kwargs.pop("headers"))
        params.update(kwargs)
        
        try:
            # Call OpenRouter API
            response: ChatCompletion = self.client.chat.completions.create(**params)
            
            # Extract response text
            response_text = response.choices[0].message.content or ""
            
            return response_text
        except Exception as e:
            logging.error(f"Error calling OpenRouter API: {e}")
            raise
    
    def chat_stream(self, conversation: Conversation, **kwargs) -> Generator[str, None, None]:
        """Send a chat conversation to OpenRouter and get a streaming response.
        
        Args:
            conversation: Chat conversation.
            **kwargs: Additional arguments to pass to the OpenRouter API.
        
        Returns:
            Generator yielding response chunks.
        """
        if not self.api_key:
            raise ValueError("OpenRouter API key not provided.")
        
        # Prepare messages
        messages = conversation.get_messages_as_dicts()
        
        # Set default parameters
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2000,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
            "stream": True,
            "headers": {
                "HTTP-Referer": "https://mcp-client.local",  # Required by OpenRouter
                "X-Title": "MCP Client"  # Optional, helps OpenRouter identify your app
            }
        }
        
        # Update with any provided kwargs
        if "headers" in kwargs:
            params["headers"].update(kwargs.pop("headers"))
        params.update(kwargs)
        
        try:
            # Call OpenRouter API with streaming
            stream = self.client.chat.completions.create(**params)
            
            # Yield response chunks
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logging.error(f"Error calling OpenRouter API: {e}")
            raise
    
    def get_available_models(self) -> List[str]:
        """Get a list of available OpenRouter models.
        
        Returns:
            List of model names.
        """
        # OpenRouter doesn't have a direct API to list models
        # Return a predefined list of popular models
        return [
            "anthropic/claude-3-opus",
            "anthropic/claude-3-sonnet",
            "anthropic/claude-3-haiku",
            "google/gemini-pro",
            "meta-llama/llama-3-70b-instruct",
            "meta-llama/llama-3-8b-instruct",
            "mistralai/mistral-large",
            "mistralai/mistral-medium",
            "mistralai/mistral-small"
        ]
    
    def validate_api_key(self) -> bool:
        """Validate the OpenRouter API key.
        
        Returns:
            True if the API key is valid, False otherwise.
        """
        if not self.api_key:
            return False
        
        try:
            # Try a simple API call to validate the key
            # Just get the models list from OpenRouter
            response = self.client.models.list()
            return True
        except Exception as e:
            logging.error(f"Error validating OpenRouter API key: {e}")
            return False
