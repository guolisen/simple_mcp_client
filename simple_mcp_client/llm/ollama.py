"""Ollama LLM provider implementation."""
import logging
from typing import Dict, List, Optional

import httpx

from .base import LLMProvider


class OllamaProvider(LLMProvider):
    """Ollama LLM provider."""

    def __init__(self, model: str, api_url: Optional[str] = None, api_key: Optional[str] = None, **kwargs):
        """Initialize the Ollama provider.
        
        Args:
            model: The model to use.
            api_url: The API URL to use (default: http://localhost:11434/api).
            api_key: The API key to use (not used for Ollama).
            **kwargs: Additional keyword arguments.
        """
        super().__init__(model, api_url, api_key)
        self.api_url = api_url or "http://localhost:11434/api"
        self.temperature = kwargs.get("temperature", 0.7)
        self.max_tokens = kwargs.get("max_tokens", 4096)

    async def get_response(self, messages: List[Dict[str, str]]) -> str:
        """Get a response from Ollama.
        
        Args:
            messages: A list of message dictionaries.
            
        Returns:
            The LLM's response as a string.
            
        Raises:
            httpx.RequestError: If the request to Ollama fails.
        """
        logging.debug("Getting response from Ollama")
        
        formatted_messages = []
        for message in messages:
            formatted_messages.append({
                "role": message["role"],
                "content": message["content"]
            })
        
        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False
        }
        
        url = f"{self.api_url}/chat"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=60.0)
                response.raise_for_status()
                data = response.json()
                return data["message"]["content"]
        except httpx.RequestError as e:
            error_message = f"Error getting response from Ollama: {str(e)}"
            logging.error(error_message)
            
            if isinstance(e, httpx.HTTPStatusError):
                status_code = e.response.status_code
                logging.error(f"Status code: {status_code}")
                logging.error(f"Response details: {e.response.text}")
            
            return f"I encountered an error: {error_message}. Please try again or check the Ollama server."
