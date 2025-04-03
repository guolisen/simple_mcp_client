"""OpenAI LLM provider for MCP Client."""

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


class OpenAILLM(LLMBase):
    """OpenAI LLM provider."""
    
    def __init__(self, model: str = "gpt-4", api_key: Optional[str] = None, api_base: Optional[str] = None, **kwargs):
        """Initialize the OpenAI LLM provider.
        
        Args:
            model: Model to use.
            api_key: OpenAI API key. If not provided, will try to use the OPENAI_API_KEY environment variable.
            api_base: OpenAI API base URL. If not provided, will use the default OpenAI API base URL.
            **kwargs: Additional provider-specific arguments.
        """
        super().__init__(model, **kwargs)
        
        # Use provided API key or try to get from environment
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            logging.warning("No OpenAI API key provided. Set it in the configuration or OPENAI_API_KEY environment variable.")
        
        # Initialize OpenAI client
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=api_base
        )
    
    def chat(self, conversation: Conversation, **kwargs) -> str:
        """Send a chat conversation to OpenAI and get a response.
        
        Args:
            conversation: Chat conversation.
            **kwargs: Additional arguments to pass to the OpenAI API.
        
        Returns:
            OpenAI response.
        """
        if not self.api_key:
            raise ValueError("OpenAI API key not provided.")
        
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
            # Call OpenAI API
            response: ChatCompletion = self.client.chat.completions.create(**params)
            
            # Extract response text
            response_text = response.choices[0].message.content or ""
            
            return response_text
        except Exception as e:
            logging.error(f"Error calling OpenAI API: {e}")
            raise
    
    def chat_stream(self, conversation: Conversation, **kwargs) -> Generator[str, None, None]:
        """Send a chat conversation to OpenAI and get a streaming response.
        
        Args:
            conversation: Chat conversation.
            **kwargs: Additional arguments to pass to the OpenAI API.
        
        Returns:
            Generator yielding response chunks.
        """
        if not self.api_key:
            raise ValueError("OpenAI API key not provided.")
        
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
            # Call OpenAI API with streaming
            stream = self.client.chat.completions.create(**params)
            
            # Yield response chunks
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logging.error(f"Error calling OpenAI API: {e}")
            raise
    
    def get_available_models(self) -> List[str]:
        """Get a list of available OpenAI models.
        
        Returns:
            List of model names.
        """
        if not self.api_key:
            logging.warning("OpenAI API key not provided. Cannot list models.")
            return []
        
        try:
            # Call OpenAI API to list models
            models = self.client.models.list()
            
            # Filter for chat models
            chat_models = [
                model.id for model in models.data
                if model.id.startswith(("gpt-3.5", "gpt-4"))
            ]
            
            return chat_models
        except Exception as e:
            logging.error(f"Error listing OpenAI models: {e}")
            return []
    
    def validate_api_key(self) -> bool:
        """Validate the OpenAI API key.
        
        Returns:
            True if the API key is valid, False otherwise.
        """
        if not self.api_key:
            return False
        
        try:
            # Try to list models as a simple API call to validate the key
            self.client.models.list()
            return True
        except Exception as e:
            logging.error(f"Error validating OpenAI API key: {e}")
            return False
