import logging
from app.ai.base import BaseLLMProvider, BaseEmbeddingProvider
from app.ai.mock_provider import MockProvider
from app.ai.gemini_provider import GeminiProvider
from app.core.config import settings

logger = logging.getLogger("synapse.ai.factory")

_mock_instance = MockProvider()


def get_llm_provider() -> BaseLLMProvider:
    """Return configured LLM provider instance."""
    provider_type = (settings.AI_PROVIDER or "mock").lower()
    if provider_type == "gemini":
        return GeminiProvider(api_key=settings.GEMINI_API_KEY)
    elif provider_type == "mock":
        return _mock_instance
    else:
        logger.info(f"Provider '{provider_type}' not natively registered; defaulting to deterministic MockProvider.")
        return _mock_instance


def get_embedding_provider() -> BaseEmbeddingProvider:
    """Return configured embedding provider instance."""
    provider_type = (settings.AI_PROVIDER or "mock").lower()
    if provider_type == "gemini":
        return GeminiProvider(api_key=settings.GEMINI_API_KEY)
    elif provider_type == "mock":
        return _mock_instance
    else:
        return _mock_instance
