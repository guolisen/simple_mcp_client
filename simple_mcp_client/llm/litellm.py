"""LiteLLM provider implementation for unified LLM API access."""
import logging
import os
from typing import Dict, List, Optional, Any

import litellm
from litellm import completion

from .base import LLMProvider


class LiteLLMProvider(LLMProvider):
    """LiteLLM provider for unified LLM API access."""

    def __init__(self, model: str, api_url: Optional[str] = None, api_key: Optional[str] = None, **kwargs):
        """Initialize the LiteLLM provider.
        
        Args:
            model: The model to use.
            api_url: The API URL to use. For LiteLLM this can be model-specific.
            api_key: The API key to use. If not provided, will look for appropriate env var.
            **kwargs: Additional keyword arguments for LiteLLM.
                      Common options include:
                      - temperature: (float) Controls randomness (0-2)
                      - max_tokens: (int) Maximum tokens to generate
                      - top_p: (float) Nucleus sampling parameter (0-1)
                      - request_timeout: (float) Request timeout in seconds
        """
        super().__init__(model, api_url, api_key)
        
        # Override model name if it includes provider prefix
        if "/" in model and not model.startswith("gpt-"):
            # LiteLLM uses format "<provider>/<model>" (e.g., "anthropic/claude-3-opus-20240229")
            self.provider_name, self.model_name = model.split("/", 1)
            self.model = model
        else:
            # Default to the model name directly
            self.provider_name = None
            self.model_name = model
        
        # Map of provider names to their environment variable names for API keys
        provider_env_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "cohere": "COHERE_API_KEY",
            "azure": "AZURE_API_KEY",
        }
        
        # Set the API key if provided, otherwise try to get from environment
        if self.api_key is None:
            if self.provider_name and self.provider_name.lower() in provider_env_map:
                env_var = provider_env_map[self.provider_name.lower()]
                self.api_key = os.getenv(env_var)
                if not self.api_key:
                    logging.warning(f"No API key provided. Set {env_var} environment variable.")
            else:
                # Try to get OpenAI API key as fallback
                self.api_key = os.getenv("OPENAI_API_KEY")
                if not self.api_key:
                    logging.warning("No API key provided and couldn't determine provider. "
                                   "Set appropriate API key environment variable.")
        
        # Set API base URL if provided
        if self.api_url:
            litellm.api_base = self.api_url
        
        # Store other parameters
        self.temperature = kwargs.get("temperature", 0.7)
        self.max_tokens = kwargs.get("max_tokens", 4096)
        self.top_p = kwargs.get("top_p", 1.0)
        self.request_timeout = kwargs.get("request_timeout", 60.0)
        
        # Store additional parameters for LiteLLM
        self.additional_params = {k: v for k, v in kwargs.items() 
                                if k not in ["temperature", "max_tokens", "top_p", "request_timeout"]}
    
    async def get_response(self, messages: List[Dict[str, str]]) -> str:
        """Get a response using LiteLLM.
        
        Args:
            messages: A list of message dictionaries with 'role' and 'content'.
            
        Returns:
            The LLM's response as a string.
            
        Raises:
            Exception: If there's an error calling the LLM.
        """
        logging.debug(f"Getting response from LiteLLM using model {self.model}")
        
        if not self.api_key and self.provider_name not in ["ollama", "local"]:
            return "Error: API key not provided. Please set appropriate API key environment variable."
        
        try:
            # Construct the parameters for LiteLLM
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "top_p": self.top_p,
                "timeout": self.request_timeout,
            }
            
            # Add API key if available
            if self.api_key:
                params["api_key"] = self.api_key
            
            # Add any additional parameters
            params.update(self.additional_params)
            
            # Make the call to LiteLLM
            response = await litellm.acompletion(**params)
            
            # Extract and return the response content
            return response.choices[0].message.content
            
        except Exception as e:
            error_message = f"Error getting response from LiteLLM: {str(e)}"
            logging.error(error_message)
            return f"I encountered an error: {error_message}. Please try again or check your configuration."
