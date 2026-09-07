import logging
from typing import List, Optional
from app.ai.base import ExtractedProgressEventDTO
from app.ai.factory import get_llm_provider

logger = logging.getLogger("synapse.field_capture.extractor")


class FieldEventExtractor:
    """
    Extracts atomic physical progress events from unstructured field report text
    using the active AI Provider (defaults to deterministic MockProvider).
    """

    @staticmethod
    async def extract_events_from_text(
        raw_text: str, report_date: Optional[str] = None
    ) -> List[ExtractedProgressEventDTO]:
        llm_provider = get_llm_provider()
        logger.info(f"Extracting progress events using {llm_provider.__class__.__name__}...")
        events = await llm_provider.extract_events(raw_text, report_date)
        logger.info(f"Successfully extracted {len(events)} discrete progress events.")
        return events
