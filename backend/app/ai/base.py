from abc import ABC, abstractmethod
from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field


class ExtractedProgressEventDTO(BaseModel):
    """
    Normalized physical event extracted from unstructured field text.
    Strictly typed schema matching ARCHITECTURE.md specifications.
    """
    work_description: str = Field(
        ..., description="Normalized summary of physical work executed"
    )
    discipline: str = Field(
        ..., description="Civil, Piping, Mechanical, Electrical, Instrumentation, or General"
    )
    location_chainage: Optional[str] = Field(
        None, description="Chainage, well-pad, or site location (e.g. 'Ch 14+000 to 15+200')"
    )
    quantity_reported: Optional[float] = Field(
        None, description="Numerical quantity executed"
    )
    uom: Optional[str] = Field(
        None, description="Unit of measurement (e.g. M, KM, SQM, MT, JOINTS)"
    )
    status_claim: str = Field(
        "IN_PROGRESS", description="STARTED, IN_PROGRESS, MILESTONE_COMPLETED, or SUSPENDED"
    )
    event_date: Optional[date] = Field(
        None, description="Date work was performed"
    )
    raw_text_snippet: str = Field(
        ..., description="Exact verbatim excerpt from DPR providing provenance"
    )


class CandidateArbitrationDTO(BaseModel):
    """Structured response from close-candidate LLM arbitration."""
    preferred_activity_id: str = Field(..., description="ID of the preferred candidate activity")
    preferred_activity_code: str = Field(..., description="Code of the preferred activity")
    reasoning: str = Field(..., description="Explainable justification for why this candidate is preferred")
    confidence_adjustment: float = Field(default=0.0, description="Optional slight confidence bonus/penalty [-0.05, 0.05]")


class BaseLLMProvider(ABC):
    """Abstract interface for LLM operations (event extraction, candidate reasoning)."""

    @abstractmethod
    async def extract_events(
        self, raw_text: str, report_date: Optional[str] = None
    ) -> List[ExtractedProgressEventDTO]:
        """Extract atomic progress events from raw DPR / field log text."""
        pass

    @abstractmethod
    async def arbitrate_candidates(
        self,
        event_dict: dict,
        candidate_1: dict,
        candidate_2: dict,
    ) -> CandidateArbitrationDTO:
        """Arbitrate between two close candidates and provide contextual reasoning."""
        pass


class BaseEmbeddingProvider(ABC):
    """Abstract interface for generating dense semantic vector embeddings."""

    @abstractmethod
    async def get_embedding(self, text: str) -> List[float]:
        """Generate a 768-dimensional normalized dense embedding vector."""
        pass
