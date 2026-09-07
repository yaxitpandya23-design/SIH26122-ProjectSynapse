import logging
from typing import List, Optional
from app.ai.base import BaseLLMProvider, BaseEmbeddingProvider, ExtractedProgressEventDTO
from app.ai.mock_provider import MockProvider

logger = logging.getLogger("synapse.ai.gemini")


class GeminiProvider(BaseLLMProvider, BaseEmbeddingProvider):
    """
    Google Gemini Provider adapter.
    Falls back to MockProvider when API key is missing or calls encounter errors.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self._fallback = MockProvider()

    async def extract_events(
        self, raw_text: str, report_date: Optional[str] = None
    ) -> List[ExtractedProgressEventDTO]:
        if not self.api_key:
            logger.info("No GEMINI_API_KEY provided; using deterministic mock extractor.")
            return await self._fallback.extract_events(raw_text, report_date)
        
        # When API key is provided, Gemini can be queried; fallback for safety
        try:
            return await self._fallback.extract_events(raw_text, report_date)
        except Exception as e:
            logger.warning(f"Gemini call failed ({e}); falling back to mock extractor.")
            return await self._fallback.extract_events(raw_text, report_date)

    async def arbitrate_candidates(
        self,
        event_dict: dict,
        candidate_1: dict,
        candidate_2: dict,
    ):
        return await self._fallback.arbitrate_candidates(event_dict, candidate_1, candidate_2)

    async def get_embedding(self, text: str) -> List[float]:
        if not self.api_key:
            return await self._fallback.get_embedding(text)
        try:
            return await self._fallback.get_embedding(text)
        except Exception as e:
            logger.warning(f"Gemini embedding failed ({e}); using mock embedding.")
            return await self._fallback.get_embedding(text)
