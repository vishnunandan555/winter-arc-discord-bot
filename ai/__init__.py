"""
ai - AI Reasoning & Workout Parsing Services for Winter Arc Bot

Modules:
- reasoning_service: Reasoning engine for /grind evaluation, announcements, digests & ceremonies.
- groq_service: Lightning-fast NLP workout parser for /quick natural language logging and failovers.
- prompts: Structured prompt engineering rubrics and anti-slop guidelines.
- fallbacks: Authentic Stoic and active recovery fallback quotes.
- models: Pydantic schemas and error models.
"""

from ai import reasoning_service
from ai import groq_service
from ai import prompts
from ai import fallbacks
from ai import models

__all__ = [
    "reasoning_service",
    "groq_service",
    "prompts",
    "fallbacks",
    "models",
]
