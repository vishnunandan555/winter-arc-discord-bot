"""
ai/gemini_service.py - Google Gemini Reasoning Engine for Winter Arc

Powers:
1. /grind daily academic & mental friction evaluation (with strict anti-slop rules).
2. Daily Midnight Toast & Roast digest.
3. Sunday Weekly "State of the Pack" broadcast.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger("winter_arc.ai.gemini")


class GrindEvaluation(BaseModel):
    verdict: str = Field(description="'ACCEPTED', 'REJECTED', or 'ROASTED'")
    points: int = Field(description="Points between 0 and 60. 0 if rejected or roasted.")
    key_learning: str = Field(description="Short tag of verified learning (e.g. 'Virtual Memory', 'DP Knapsack') or 'None'")
    commentary: str = Field(description="Exactly 2 to 3 sentences in Amarok's stoic, razor-sharp voice.")


def get_gemini_client():
    """Returns an authenticated GenAI Client if GEMINI_API_KEY is configured."""
    if not GEMINI_API_KEY:
        return None
    try:
        from google import genai
        return genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize Google GenAI client: {e}")
        return None


async def evaluate_grind(raw_text: str) -> Dict[str, Any]:
    """
    Evaluates a user's daily academic/engineering friction using Gemini.
    Strictly filters out vibe-coding, passive consumption, diet logs, and fluff.
    """
    client = get_gemini_client()
    if not client:
        logger.warning("GEMINI_API_KEY not configured. Falling back to default evaluation.")
        return {
            "verdict": "ACCEPTED",
            "points": 30,
            "key_learning": "Deep Focus",
            "commentary": "Solid effort noted. Gemini API key not configured, default baseline points awarded. Keep pushing.",
        }

    system_prompt = (
        "You are Amarok, the stoic, unyielding wolf mascot and supreme discipline judge of the Winter Arc.\n"
        "Your task is to evaluate a user's daily academic, engineering, and mental friction submission.\n"
        "Physical fitness is tracked separately. Here, we ONLY honor intellectual grit, deep focus, and rigorous mastery "
        "in computer science, engineering, mathematics, low-level systems, algorithms, and dense study.\n\n"
        "STRICT EVALUATION RULES:\n"
        "1. WHAT COUNTS AS REAL FRICTION (10 to 60 points max):\n"
        "   - 3+ hours of uninterrupted deep study or technical focus.\n"
        "   - Solving difficult algorithmic problems (LeetCode Medium/Hard) with actual comprehension.\n"
        "   - Deep dives into low-level systems: operating systems, kernel internals, memory management, compilers, distributed architectures, networks.\n"
        "   - Advanced mathematics, proofs, or reading dense engineering literature (e.g. DDIA, SICP, CLRS).\n"
        "   - Point scale: 10-25 (solid effort), 26-45 (serious friction), 46-60 (exceptional, rare grit).\n\n"
        "2. WHAT GETS REJECTED OR BRUTALLY ROASTED (0 points):\n"
        "   - 'Vibe-coding' or generated copy-paste projects ('I built a full-stack SaaS with Cursor in 1 hour'). Roast them for prompting instead of thinking.\n"
        "   - Passive media consumption ('I watched 3 YouTube tutorials on Rust', 'I listened to a podcast').\n"
        "   - Normal comfort or life activities ('I woke up early', 'I walked my dog', 'I tidied my desk').\n"
        "   - Diet or food diaries ('I drank water and ate chicken'). Remind them this isn't a food blog.\n"
        "   - Low-effort or nonsense entries ('I coded a bit', 'I read 2 pages').\n\n"
        "3. TONE & CONSTRAINTS:\n"
        "   - NO AI SLOP: No corporate cheerleading, no 'Great job!', no generic motivational quotes.\n"
        "   - Commentary must be EXACTLY 2 TO 3 SHORT, RAZOR-SHARP SENTENCES in Amarok's dark, stoic tone.\n"
        "   - Return pure JSON conforming strictly to the requested schema."
    )

    try:
        from google.genai import types
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"User Reflection:\n\"{raw_text}\"",
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=GrindEvaluation,
                temperature=0.2,
            ),
        )

        data = json.loads(response.text)
        points = int(data.get("points", 0))
        points = max(0, min(points, 60))
        verdict = str(data.get("verdict", "REJECTED")).upper()
        if verdict not in ["ACCEPTED", "REJECTED", "ROASTED"]:
            verdict = "ACCEPTED" if points > 0 else "REJECTED"

        return {
            "verdict": verdict,
            "points": points,
            "key_learning": str(data.get("key_learning", "None"))[:50],
            "commentary": str(data.get("commentary", "Friction logged.")),
        }
    except Exception as e:
        logger.error(f"Error calling Gemini for /grind evaluation: {e}")
        return {
            "verdict": "ACCEPTED",
            "points": 25,
            "key_learning": "Deep Focus",
            "commentary": "Your reflection is recorded. AI evaluation encountered a gateway blip, baseline points granted.",
        }


async def generate_daily_toast_and_roast(
    podium_data: List[Dict[str, Any]],
    grind_highlights: List[Dict[str, Any]],
    slacker_count: int,
    total_enrolled: int
) -> str:
    """Generates a concise (under 120 words) Daily Toast & Roast for 00:00 midnight."""
    client = get_gemini_client()
    if not client:
        return ""

    top_names = [f"#{i+1} {p['username']} ({p['points']} pts)" for i, p in enumerate(podium_data[:3])]
    grind_notes = [f"{g['username']}: {g.get('key_learning', 'grind')}" for g in grind_highlights[:3]]

    prompt = (
        f"Generate a compact midnight Winter Arc recap in Amarok's stoic, gritty voice.\n"
        f"Data:\n"
        f"- Top 3 Podium: {', '.join(top_names) if top_names else 'None'}\n"
        f"- Legit Academic/Grind Highlights: {', '.join(grind_notes) if grind_notes else 'None'}\n"
        f"- Slackers with 0 logs today: {slacker_count} out of {total_enrolled} enrolled warriors.\n\n"
        "Requirements:\n"
        "1. Honor the top 3 and legitimate deep work.\n"
        "2. Witty, biting 1-sentence roast aimed at the slackers.\n"
        "3. EXACTLY 3 TO 4 SHORT SENTENCES TOTAL (under 120 words). No AI slop."
    )

    try:
        from google.genai import types
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=200,
            ),
        )
        return response.text.strip()
    except Exception as e:
        logger.warning(f"Could not generate AI daily toast & roast: {e}")
        return ""


async def generate_weekly_state_of_the_pack(
    weekly_stats: Dict[str, Any],
    top_warriors: List[Dict[str, Any]],
    weekly_grinds: List[Dict[str, Any]],
    ghosts_count: int
) -> str:
    """Generates the Sunday 20:00 IST 'State of the Pack' community broadcast (under 160 words)."""
    client = get_gemini_client()
    if not client:
        return ""

    apex = top_warriors[0] if top_warriors else {"username": "Nobody", "points": 0}
    grind_summaries = [f"{g['username']} ({g.get('key_learning', 'study')})" for g in weekly_grinds[:4]]

    prompt = (
        f"Generate the Sunday 'State of the Pack' address for Winter Arc in Amarok's stoic wolf leader persona.\n"
        f"Weekly Data:\n"
        f"- Apex of the Week: {apex['username']} with {apex['points']} points.\n"
        f"- Total Pack Volume: {weekly_stats.get('total_pushups', 0)} push-ups, {weekly_stats.get('total_km', 0)} km run.\n"
        f"- Deep Work / Technical Breakthroughs: {', '.join(grind_summaries) if grind_summaries else 'Minimal'}\n"
        f"- Ghost Warriors (0 activity all week): {ghosts_count}\n\n"
        "Structure:\n"
        "1. The Apex Toast: Brief respect to the top grinder.\n"
        "2. The Pack Stats: Terse acknowledgement of community volume.\n"
        "3. The Roast: 1 sharp sentence on ghosts who let the frost take them.\n"
        "4. The Monday Charge: 1 commanding sentence for 05:00 AM tomorrow.\n"
        "Total length: UNDER 150 WORDS. Zero fluff."
    )

    try:
        from google.genai import types
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=250,
            ),
        )
        return response.text.strip()
    except Exception as e:
        logger.warning(f"Could not generate weekly state of the pack: {e}")
        return ""
