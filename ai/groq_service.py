"""
ai/groq_service.py - Ultra-Fast NLP Workout Parser Powered by Groq

Extracts completed exercises from natural language input with sub-second latency
and strict active-task validation.
"""

import json
import re
import logging
from typing import Dict, Any, List, Optional
from config import GROQ_API_KEY, GROQ_MODEL

logger = logging.getLogger("winter_arc.ai.groq")


_groq_client = None


def get_groq_client():
    """Returns an AsyncGroq client singleton if GROQ_API_KEY is configured."""
    global _groq_client
    if not GROQ_API_KEY:
        return None
    if _groq_client is None:
        try:
            from groq import AsyncGroq
            _groq_client = AsyncGroq(api_key=GROQ_API_KEY)
        except Exception as e:
            logger.error(f"Failed to initialize Groq client: {e}")
            return None
    return _groq_client


def regex_fallback_parser(raw_text: str, active_tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Lightweight regex parser used as a safety fallback when Groq is unavailable."""
    matches = []
    text = raw_text.lower()

    for t in active_tasks:
        name = t["name"].lower()
        patterns = []
        if "push" in name:
            patterns = [r'(\d+)\s*(?:push[\s-]?ups?|pushies)']
        elif "pull" in name:
            patterns = [r'(\d+)\s*(?:pull[\s-]?ups?|pullies|chins?)']
        elif "squat" in name:
            patterns = [r'(\d+)\s*squats?']
        elif "sit" in name:
            patterns = [r'(\d+)\s*(?:sit[\s-]?ups?|crunches)']
        elif "run" in name:
            patterns = [
                r'(\d+(?:\.\d+)?)\s*(?:km|k|kilometers?)',
                r'ran\s*(\d+(?:\.\d+)?)',
                r'(\d+(?:\.\d+)?)\s*miles?',
            ]

        for pat in patterns:
            found = re.search(pat, text)
            if found:
                val = float(found.group(1))
                if "miles" in pat:
                    val = round(val * 1.60934, 1)
                matches.append({"task_name": t["name"], "amount": val})
                break

    return {
        "matches": matches,
        "unrecognized": [],
        "suspicious": any(m["amount"] > 1000 for m in matches),
        "commentary": "Exercises parsed via local parser." if matches else "Could not recognize any active disciplines.",
    }


async def parse_quicklog(raw_text: str, active_tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Parses natural language workout text using Groq with llama-3.3-70b-versatile.
    Extracts strictly active challenge disciplines and applies reality checks.
    """
    client = get_groq_client()
    if not client:
        logger.info("GROQ_API_KEY not configured. Using regex fallback parser.")
        return regex_fallback_parser(raw_text, active_tasks)

    task_descriptions = [f"- {t['name']} (target: {t['target']} {t['unit']})" for t in active_tasks]
    tasks_block = "\n".join(task_descriptions)

    system_prompt = (
        "You are an ultra-fast, precision fitness parser for the Winter Arc bot.\n"
        "Your job is to extract completed workout counts from natural language text and map them STRICTLY to active challenge tasks.\n\n"
        f"ACTIVE CHALLENGE TASKS:\n{tasks_block}\n\n"
        "STRICT EXTRACTION RULES:\n"
        "1. ONLY extract exercises matching the active challenge tasks above. Ignore or put foreign exercises (e.g. bicep curls, bench press, yoga) in 'unrecognized'.\n"
        "2. Map slang and abbreviations to exact active task names (e.g. 'pushies' -> 'Push-ups', 'ran 5k' -> 'Running' amount 5.0, 'century squats' -> 'Squats' amount 100).\n"
        "3. Convert running distances to kilometers (e.g. '3000 meters' -> 3.0, '3 miles' -> 4.8).\n"
        "4. REALITY CHECKS:\n"
        "   - Set 'suspicious': true if an amount is blatantly absurd for a single session (e.g. >500 pushups, >200 pullups, >50 km running).\n"
        "   - Set 'low_effort': true if reps are trivially tiny (e.g. <= 5 reps of calisthenics or < 0.5 km run).\n"
        "5. COMMENTARY:\n"
        "   - EXACTLY 1 short, razor-sharp sentence in Amarok's stoic wolf tone.\n"
        "   - If suspicious: 'Cut the cap. Log your actual numbers.'\n"
        "   - If low_effort: 'X reps? The ground barely felt you. Finish the rest.'\n"
        "   - If solid: 'Discipline logged. Keep moving.'\n\n"
        "Return pure JSON format:\n"
        "{\n"
        "  \"matches\": [{\"task_name\": \"<Exact Task Name>\", \"amount\": <number>}],\n"
        "  \"unrecognized\": [\"<foreign exercise names>\"],\n"
        "  \"suspicious\": <true/false>,\n"
        "  \"commentary\": \"<1 sentence>\"\n"
        "}"
    )

    try:
        chat_completion = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text},
            ],
            model=GROQ_MODEL,
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=300,
        )

        content = chat_completion.choices[0].message.content
        data = json.loads(content)

        # Validate task_names against active_tasks
        valid_names = {t["name"].lower(): t["name"] for t in active_tasks}
        validated_matches = []
        for m in data.get("matches", []):
            req_name = str(m.get("task_name", "")).strip().lower()
            amt = float(m.get("amount", 0))
            if req_name in valid_names and amt > 0:
                validated_matches.append({
                    "task_name": valid_names[req_name],
                    "amount": round(amt, 2)
                })

        return {
            "matches": validated_matches,
            "unrecognized": data.get("unrecognized", []),
            "suspicious": bool(data.get("suspicious", False)),
            "commentary": str(data.get("commentary", "Discipline logged.")),
        }
    except Exception as e:
        logger.warning(f"Groq API call failed: {e}. Falling back to regex parser.")
        return regex_fallback_parser(raw_text, active_tasks)
