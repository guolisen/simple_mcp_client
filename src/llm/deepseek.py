"""Deepseek LLM provider for MCP Client."""

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


class DeepseekLLM(LLMBase):
    """Deepseek LLM provider."""
    
    def __init__(self, model: str = "deepseek-chat", api_key: Optional[str] = None, api_base: Optional[str] = None, **kwargs):
        """Initialize the Deepseek LLM provider.
        
        Args:
            model: Model to use.
            api_key: Deepseek API key. If not provided, will try to use the DEEPSEEK_API_KEY environment variable.
            api_base: Deepseek API base URL. If not provided, will use the default Deepseek API base URL.
            **kwargs: Additional provider-specific arguments.
        """
        super().__init__(model, **kwargs)
        
        # Use provided API key or try to get from environment
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        if not self.api_key:
            logging.warning("No Deepseek API key provided. Set it in the configuration or DEEPSEEK_API_KEY environment variable.")
        
        # Initialize OpenAI client with Deepseek base URL
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=api_base or "https://api.deepseek.com/v1"
        )
    
    def chat(self, conversation: Conversation, **kwargs) -> str:
        """Send a chat conversation to Deepseek and get a response.
        
        Args:
            conversation: Chat conversation.
            **kwargs: Additional arguments to pass to the Deepseek API.
        
        Returns:
            Deepseek response.
        """
        if not self.api_key:
            raise ValueError("Deepseek API key not provided.")
        
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
        }
        
        # Update with any provided kwargs
        params.update(kwargs)
        
        try:
            # Call Deepseek API
            response: ChatCompletion = self.client.chat.completions.create(**params)
            
            # Extract response text
            response_text = response.choices[0].message.content or ""
            
            return response_text
        except Exception as e:
            logging.error(f"Error calling Deepseek API: {e}")
            raise
    
    def chat_stream(self, conversation: Conversation, **kwargs) -> Generator[str, None, None]:
        """Send a chat conversation to Deepseek and get a streaming response.
        
        Args:
            conversation: Chat conversation.
            **kwargs: Additional arguments to pass to the Deepseek API.
        
        Returns:
            Generator yielding response chunks.
        """
        if not self.api_key:
            raise ValueError("Deepseek API key not provided.")
        
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
        }
        
        # Update with any provided kwargs
        params.update(kwargs)
        
        try:
            # Call Deepseek API with streaming
            stream = self.client.chat.completions.create(**params)
            
            # Yield response chunks
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logging.error(f"Error calling Deepseek API: {e}")
            raise
    
    def get_available_models(self) -> List[str]:
        """Get a list of available Deepseek models.
        
        Returns:
            List of model names.
        """
        # Deepseek doesn't have a direct API to list models
        # Return a predefined list of known models
        return [
            "deepseek-chat",
            "deepseek-coder"
        ]
    
    def validate_api_key(self) -> bool:
        """Validate the Deepseek API key.
        
        Returns:
            True if the API key is valid, False otherwise.
        """
        if not self.api_key:
            return False
        
        try:
            # Try a simple API call to validate the key
            # Just get the models list from Deepseek
            response = self.client.models.list()
            return True
        except Exception as e:
            logging.error(f"Error validating Deepseek API key: {e}")
            return False
