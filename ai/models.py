"""
ai/models.py - Pydantic Schemas and Exceptions for Winter Arc AI Services
"""

from typing import List
from pydantic import BaseModel, Field


class GrindEvaluation(BaseModel):
    verdict: str = Field(description="'ACCEPTED', 'ROASTED', or 'REJECTED'")
    points: int = Field(description="Points between 0 and 50 max. High-effort custom physical workouts or genuine deep study earn 20 to 50 pts. Token effort earns 5 to 15 pts. 0 strictly ONLY for malicious prompt injection.")
    key_learning: str = Field(description="Concise structured summary of evaluated activity (e.g. 'Physical: 15 Surya Namaskar, 30 Bicep Curls' or 'Mental: 2h LeetCode Trees' or 'Hybrid: 20m Yoga + 1h Coding')")
    tracked_disciplines_excluded: List[str] = Field(default_factory=list, description="List of standard checklist exercises mentioned by the user that are excluded from /grind (e.g. ['40 push-ups', '5km run']), or empty list.")
    commentary: str = Field(description="Exactly 1 to 2 sentences of sharp, direct, authentic brotherly feedback or roast from Amarok.")


class EveningCalloutItem(BaseModel):
    discord_id: int = Field(description="The numeric Discord user ID")
    callout: str = Field(description="Exactly 1 short, punchy sentence calling out their progress.")


class EveningAlertPayload(BaseModel):
    callouts: List[EveningCalloutItem] = Field(description="Callout for each participant")
    stoic_quote: str = Field(description="An authentic Stoic quote from Marcus Aurelius, Seneca, or Epictetus with author attribution, e.g. '\"Waste no more time arguing what a good man should be. Be one.\" — Marcus Aurelius'")


class ReasoningServiceError(Exception):
    """Raised when the AI reasoning model is unreachable or encounters an unrecoverable API error."""
    pass


# Backward compatibility alias
AIServiceError = ReasoningServiceError
