"""OpenAI LLM provider implementation."""
import logging
import os
from typing import Dict, List, Optional

import httpx

from .base import LLMProvider


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider."""

    def __init__(self, model: str, api_url: Optional[str] = None, api_key: Optional[str] = None, **kwargs):
        """Initialize the OpenAI provider.
        
        Args:
            model: The model to use.
            api_url: The API URL to use (default: https://api.openai.com/v1).
            api_key: The API key to use. If not provided, will look for OPENAI_API_KEY env var.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(model, api_url, api_key)
        self.api_url = api_url or "https://api.openai.com/v1"
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logging.warning("No OpenAI API key provided. Set OPENAI_API_KEY environment variable.")
        
        self.temperature = kwargs.get("temperature", 0.7)
        self.max_tokens = kwargs.get("max_tokens", 4096)
        self.top_p = kwargs.get("top_p", 1.0)

    async def get_response(self, messages: List[Dict[str, str]]) -> str:
        """Get a response from OpenAI.
        
        Args:
            messages: A list of message dictionaries.
            
        Returns:
            The LLM's response as a string.
            
        Raises:
            httpx.RequestError: If the request to OpenAI fails.
        """
        logging.debug("Getting response from OpenAI")
        
        if not self.api_key:
            return "Error: OpenAI API key not provided. Please set OPENAI_API_KEY environment variable."
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "stream": False
        }
        
        url = f"{self.api_url}/chat/completions"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payload, timeout=60.0)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except httpx.RequestError as e:
            error_message = f"Error getting response from OpenAI: {str(e)}"
            logging.error(error_message)
            
            if isinstance(e, httpx.HTTPStatusError):
                status_code = e.response.status_code
                logging.error(f"Status code: {status_code}")
                logging.error(f"Response details: {e.response.text}")
            
            return f"I encountered an error: {error_message}. Please try again or check your API key."
