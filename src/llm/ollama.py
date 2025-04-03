"""Ollama LLM provider for MCP Client."""

import json
from typing import Dict, List, Optional, Generator
import logging
import httpx

from .base import LLMBase, Conversation


class OllamaLLM(LLMBase):
    """Ollama LLM provider."""
    
    def __init__(self, model: str = "llama3", host: str = "http://localhost:11434", **kwargs):
        """Initialize the Ollama LLM provider.
        
        Args:
            model: Model to use.
            host: Ollama API host URL.
            **kwargs: Additional provider-specific arguments.
        """
        super().__init__(model, **kwargs)
        self.host = host
        self.client = httpx.Client(base_url=host, timeout=60.0)
    
    def chat(self, conversation: Conversation, **kwargs) -> str:
        """Send a chat conversation to Ollama and get a response.
        
        Args:
            conversation: Chat conversation.
            **kwargs: Additional arguments to pass to the Ollama API.
        
        Returns:
            Ollama response.
        """
        # Convert conversation to Ollama format
        messages = self._convert_messages(conversation)
        
        # Set default parameters
        params = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 2000,
            }
        }
        
        # Update with any provided kwargs
        if "options" in kwargs:
            params["options"].update(kwargs.pop("options"))
        params.update(kwargs)
        
        try:
            # Call Ollama API
            response = self.client.post("/api/chat", json=params)
            response.raise_for_status()
            
            # Extract response text
            result = response.json()
            response_text = result.get("message", {}).get("content", "")
            
            return response_text
        except Exception as e:
            logging.error(f"Error calling Ollama API: {e}")
            raise
    
    def chat_stream(self, conversation: Conversation, **kwargs) -> Generator[str, None, None]:
        """Send a chat conversation to Ollama and get a streaming response.
        
        Args:
            conversation: Chat conversation.
            **kwargs: Additional arguments to pass to the Ollama API.
        
        Returns:
            Generator yielding response chunks.
        """
        # Convert conversation to Ollama format
        messages = self._convert_messages(conversation)
        
        # Set default parameters
        params = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 2000,
            }
        }
        
        # Update with any provided kwargs
        if "options" in kwargs:
            params["options"].update(kwargs.pop("options"))
        params.update(kwargs)
        
        try:
            # Call Ollama API with streaming
            with self.client.stream("POST", "/api/chat", json=params, timeout=120.0) as response:
                response.raise_for_status()
                
                # Process streaming response
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    
                    try:
                        chunk = json.loads(line)
                        if "message" in chunk and "content" in chunk["message"]:
                            yield chunk["message"]["content"]
                    except json.JSONDecodeError:
                        logging.warning(f"Failed to parse Ollama response: {line}")
        except Exception as e:
            logging.error(f"Error calling Ollama API: {e}")
            raise
    
    def get_available_models(self) -> List[str]:
        """Get a list of available Ollama models.
        
        Returns:
            List of model names.
        """
        try:
            # Call Ollama API to list models
            response = self.client.get("/api/tags")
            response.raise_for_status()
            
            # Extract model names
            result = response.json()
            models = [model["name"] for model in result.get("models", [])]
            
            return models
        except Exception as e:
            logging.error(f"Error listing Ollama models: {e}")
            return []
    
    def validate_api_key(self) -> bool:
        """Validate the Ollama connection.
        
        Returns:
            True if the connection is valid, False otherwise.
        """
        try:
            # Try to list models as a simple API call to validate the connection
            response = self.client.get("/api/tags")
            response.raise_for_status()
            return True
        except Exception as e:
            logging.error(f"Error connecting to Ollama: {e}")
            return False
    
    def _convert_messages(self, conversation: Conversation) -> List[Dict[str, str]]:
        """Convert conversation messages to Ollama format.
        
        Args:
            conversation: Chat conversation.
        
        Returns:
            List of messages in Ollama format.
        """
        # Ollama uses the same format as OpenAI
        return conversation.get_messages_as_dicts()
