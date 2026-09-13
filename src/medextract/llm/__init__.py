"""LLM adapter layer. Swapping models must not touch pipeline code."""

from .base import LLMClient, LLMError, LLMTimeout, get_client

__all__ = ["LLMClient", "LLMError", "LLMTimeout", "get_client"]
