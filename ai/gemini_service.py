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


_gemini_client = None


def get_gemini_client():
    """Returns an authenticated GenAI Client singleton if GEMINI_API_KEY is configured."""
    global _gemini_client
    if not GEMINI_API_KEY:
        return None
    if _gemini_client is None:
        try:
            from google import genai
            _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        except Exception as e:
            logger.error(f"Failed to initialize Google GenAI client: {e}")
            return None
    return _gemini_client


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


CURATED_STOIC_FALLBACKS = [
    "The iron does not negotiate with your mood. Move.",
    "Comfort is a slow poison. Step into the cold.",
    "A wolf does not seek warmth from the fire it has not yet built.",
    "Discipline is choosing between what you want now and what you want most.",
    "The snow buries the weak and hardens the disciplined.",
    "Words build nothing. Numbers on the board are the only truth.",
    "The winter does not care about your excuses. Only completed reps speak.",
    "Control your mind, or the cold will control it for you.",
]


async def generate_reminder_motivation(
    reminder_type: str = "morning",
    user_context: Optional[Dict[str, Any]] = None,
    recent_history: Optional[List[Dict[str, Any]]] = None,
    force_judgment: bool = False,
) -> str:
    """
    Generates a dynamic, razor-sharp stoic motivational quote or personal progress judgment using Gemini.
    Strictly 1 to 2 short sentences (under 25-30 words total). Zero AI slop.
    """
    import random
    client = get_gemini_client()
    if not client:
        return random.choice(CURATED_STOIC_FALLBACKS)

    include_history_judgment = False
    context_notes = []
    if user_context:
        u_name = user_context.get("username", "Warrior")
        u_streak = user_context.get("streak", 0)
        context_notes.append(f"Warrior: {u_name}")
        context_notes.append(f"Active streak: {u_streak} days")
        if recent_history:
            past_pts = [f"{d['date'][-5:]}: {d.get('points', 0)} pts" for d in recent_history[:3]]
            context_notes.append(f"Recent daily scores: {', '.join(past_pts)}")
        recent_logs = user_context.get("recent_logs")
        if recent_logs:
            phys_summary = [f"{l['amount']} {l['unit']} {l['task_name']}" for l in recent_logs[:3]]
            context_notes.append(f"Recent physical logs: {', '.join(phys_summary)}")
        recent_grinds = user_context.get("recent_grinds")
        if recent_grinds:
            grind_summary = [f"{g.get('key_learning') or 'deep work'}" for g in recent_grinds[:2]]
            context_notes.append(f"Recent study/grind: {', '.join(grind_summary)}")

        # Rarely/contextually judge their recent momentum (~35% of the time, or if slacking/testing)
        has_slacked = recent_history and recent_history[0].get("points", 0) == 0
        include_history_judgment = force_judgment or (random.random() < 0.35) or has_slacked

    prompt = (
        f"You are Amarok, the dark, stoic wolf sentinel of the Winter Arc.\n"
        f"Generate a single razor-sharp stoic reminder or discipline quote for a {reminder_type.upper()} announcement.\n\n"
        "STRICT CONSTRAINTS:\n"
        "- LENGTH: EXACTLY 1 TO 2 SHORT SENTENCES (STRICTLY UNDER 25 WORDS TOTAL).\n"
        "- TONE: Gritty, austere, cold, relentless. Zero cheerleading, zero fluff, zero generic motivational quotes.\n"
    )

    if include_history_judgment and context_notes:
        prompt += (
            f"- CONTEXT ON WARRIOR'S PREVIOUS WORK:\n"
            f"  {'; '.join(context_notes)}\n"
            f"- INSTRUCTION: Bluntly or subtly weave their past work or momentum into a cold stoic edict. "
            f"If they are slacking/idle, call it out bluntly. If consistent, remind them yesterday's sweat buys nothing today.\n"
        )
    else:
        prompt += "- Deliver an original, unpredictable stoic discipline edict tailored for the Winter Arc.\n"

    prompt += "\nOutput ONLY the plain quote text. Do not wrap in quotes, do not prefix with Amarok, do not use markdown."

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        txt = (response.text or "").strip().strip('"').strip("'")
        if ":" in txt and txt.split(":", 1)[0].lower().strip() in ["amarok", "quote", "sentinel", "edict"]:
            txt = txt.split(":", 1)[1].strip().strip('"').strip("'")

        if txt and len(txt.split()) <= 35:
            return txt
        return random.choice(CURATED_STOIC_FALLBACKS)
    except Exception as e:
        logger.debug(f"Could not generate Gemini reminder quote: {e}. Using curated fallback.")
        return random.choice(CURATED_STOIC_FALLBACKS)

