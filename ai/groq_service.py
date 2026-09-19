"""
ai/groq_service.py - Ultra-Fast NLP Workout Parser Powered by Groq

Extracts completed exercises from natural language input with sub-second latency
and strict active-task validation.
"""

import json
import re
import logging
from typing import Dict, Any, List, Optional
from config import GROQ_API_KEY, GROQ_MODEL, MAX_SINGLE_SET_LIMITS

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

    is_suspicious = any(
        m["amount"] > MAX_SINGLE_SET_LIMITS.get(m["task_name"].lower(), 50.0)
        for m in matches
    )
    return {
        "matches": matches,
        "unrecognized": [],
        "suspicious": is_suspicious,
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
        "4. REALITY CHECKS (STRICT SINGLE-SET HUMAN LIMITS):\n"
        "   - Maximum allowed in a single set / single go:\n"
        "     * Push-ups: 50 reps max (e.g. '90 pushups' in one go is unrealistic -> suspicious: true)\n"
        "     * Pull-ups: 20 reps max (e.g. '25 pullups' -> suspicious: true)\n"
        "     * Squats: 50 reps max\n"
        "     * Sit-ups: 50 reps max\n"
        "     * Running: 10.0 km max in a single run\n"
        "   - If ANY single exercise amount exceeds these limits: IMMEDIATELY set 'suspicious': true.\n"
        "   - Set 'low_effort': true if reps are trivially tiny (e.g. <= 5 reps of calisthenics or < 0.5 km run).\n"
        "5. COMMENTARY:\n"
        "   - EXACTLY 1 short, razor-sharp sentence in Amarok's stoic wolf tone.\n"
        "   - If suspicious: 'Unrealistic single-set volume. Log sets individually.'\n"
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

        # Validate task_names against active_tasks and enforce single-set limits
        valid_names = {t["name"].lower(): t["name"] for t in active_tasks}
        validated_matches = []
        is_suspicious = bool(data.get("suspicious", False))

        for m in data.get("matches", []):
            req_name = str(m.get("task_name", "")).strip().lower()
            amt = float(m.get("amount", 0))
            if req_name in valid_names and amt > 0:
                validated_matches.append({
                    "task_name": valid_names[req_name],
                    "amount": round(amt, 2)
                })
                # Deterministic check: reject amounts exceeding single-set limits
                limit = MAX_SINGLE_SET_LIMITS.get(req_name, 50.0)
                if amt > limit:
                    is_suspicious = True

        return {
            "matches": validated_matches,
            "unrecognized": data.get("unrecognized", []),
            "suspicious": is_suspicious,
            "commentary": str(data.get("commentary", "Discipline logged.")),
        }
    except Exception as e:
        logger.warning(f"Groq API call failed: {e}. Falling back to regex parser.")
        return regex_fallback_parser(raw_text, active_tasks)


REACTIVE_STOIC_FALLBACKS = [
    "The iron does not care how you feel today.",
    "Every rep counts. Silence the excuses.",
    "Words build nothing. Log the work.",
    "The cold tests your will. Do not break.",
    "Momentum is earned daily. Defend it.",
    "Discipline is the only bridge between desire and reality.",
]


async def generate_reactive_nudge(
    user_name: str,
    command_name: str,
    progression: Dict[str, Any],
) -> Optional[str]:
    """
    Generates an ultra-fast, contextual 1-sentence stoic observation/nudge
    based on the user's live progression snapshot using Groq.
    Strictly 1 short sentence (under 20 words total). Zero AI slop.
    """
    import random
    client = get_groq_client()
    if not client:
        return random.choice(REACTIVE_STOIC_FALLBACKS)

    system_prompt = (
        "You are Amarok, the dark, cold wolf sentinel of the Winter Arc.\n"
        "You are observing a warrior from the shadows who just executed a bot command.\n"
        "Deliver a single razor-sharp stoic observation based on their live numbers.\n\n"
        "STRICT CONSTRAINTS:\n"
        "- LENGTH: EXACTLY 1 SHORT SENTENCE (STRICTLY UNDER 20 WORDS TOTAL).\n"
        "- TONE: Gritty, austere, cold, relentless. Zero cheerleading, zero fluff, no exclamation marks.\n"
        "- Never say 'keep it up', 'great job', or 'congratulations'.\n"
        "- Output ONLY the plain text sentence. Do not wrap in quotes or prefix with your name."
    )

    pts = progression.get("points", 0)
    max_pts = progression.get("max_points", 500)
    pct = progression.get("pct", 0)
    streak = progression.get("streak", 0)
    extra = progression.get("extra_info", "")
    pending = progression.get("pending_tasks", [])

    user_prompt = (
        f"Warrior: {user_name}. Command: /{command_name}.\n"
        f"Progress: {pts}/{max_pts} pts ({pct}%). Streak: {streak} days.\n"
    )
    if extra:
        user_prompt += f"Action: {extra}\n"
    if pending:
        user_prompt += f"Pending: {', '.join(pending[:3])}\n"

    try:
        chat_completion = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=GROQ_MODEL,
            temperature=0.7,
            max_tokens=60,
        )

        txt = (chat_completion.choices[0].message.content or "").strip().strip('"').strip("'")
        if ":" in txt and txt.split(":", 1)[0].lower().strip() in ["amarok", "sentinel", "edict", "observation"]:
            txt = txt.split(":", 1)[1].strip().strip('"').strip("'")

        if txt and len(txt.split()) <= 25:
            return txt
        return random.choice(REACTIVE_STOIC_FALLBACKS)
    except Exception as e:
        logger.debug(f"Groq reactive nudge failed: {e}. Using curated fallback.")
        return random.choice(REACTIVE_STOIC_FALLBACKS)


_last_nudge_timestamps: Dict[int, float] = {}
NUDGE_COOLDOWN_SECONDS: float = 3600.0  # 1 hour per user


def should_trigger_nudge(user_id: int, force: bool = False, roll_chance: float = 0.35) -> bool:
    """Evaluates whether a reactive nudge should trigger based on cooldown and random probability."""
    if force:
        return True
    import time
    import random
    now = time.time()
    last_time = _last_nudge_timestamps.get(user_id, 0.0)
    if now - last_time < NUDGE_COOLDOWN_SECONDS:
        return False
    return random.random() <= roll_chance


def record_nudge_triggered(user_id: int):
    """Updates the last nudge timestamp for a user."""
    import time
    _last_nudge_timestamps[user_id] = time.time()


async def dispatch_interaction_nudge(
    interaction: Any,
    user_id: int,
    user_name: str,
    command_name: str,
    progression: Optional[Dict[str, Any]] = None,
    extra_info: str = "",
    force: bool = False,
):
    """
    Non-blocking background dispatcher that sends a separate follow-up message
    from Amarok after an interaction response.
    """
    if not should_trigger_nudge(user_id, force=force):
        return

    record_nudge_triggered(user_id)

    try:
        if progression is None:
            from datetime import datetime
            from config import BOT_TZ
            import database as db
            today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")
            prog = db.get_user_daily_progress(user_id, today_str)
            streak = db.calculate_streak(user_id, today_str)
            tasks = prog.get("tasks", [])
            completed = [t["name"] for t in tasks if t.get("completed")]
            pending = [t["name"] for t in tasks if not t.get("completed")]
            progression = {
                "points": prog.get("total_points", 0),
                "max_points": prog.get("max_possible_points", 500),
                "pct": int(round(prog.get("overall_completion_rate", 0) * 100)),
                "streak": streak,
                "completed_tasks": completed,
                "pending_tasks": pending,
                "extra_info": extra_info,
            }

        nudge = await generate_reactive_nudge(
            user_name=user_name,
            command_name=command_name,
            progression=progression,
        )
        if nudge:
            content = f"<@{user_id}> 🐺 **Amarok observes**:\n> *\"{nudge}\"*"
            if getattr(interaction, "channel", None) and hasattr(interaction.channel, "send"):
                try:
                    await interaction.channel.send(content)
                    return
                except Exception:
                    pass
            await interaction.followup.send(content)
    except Exception as e:
        logger.debug(f"Could not dispatch interaction nudge for {user_name}: {e}")


async def dispatch_channel_nudge(
    channel: Any,
    user_id: int,
    user_name: str,
    command_name: str,
    progression: Optional[Dict[str, Any]] = None,
    extra_info: str = "",
    force: bool = False,
):
    """
    Non-blocking background dispatcher that sends a separate channel message
    from Amarok in message-based logging contexts (e.g. #quick-log).
    """
    if not should_trigger_nudge(user_id, force=force):
        return

    record_nudge_triggered(user_id)

    try:
        if progression is None:
            from datetime import datetime
            from config import BOT_TZ
            import database as db
            today_str = datetime.now(BOT_TZ).strftime("%Y-%m-%d")
            prog = db.get_user_daily_progress(user_id, today_str)
            streak = db.calculate_streak(user_id, today_str)
            tasks = prog.get("tasks", [])
            completed = [t["name"] for t in tasks if t.get("completed")]
            pending = [t["name"] for t in tasks if not t.get("completed")]
            progression = {
                "points": prog.get("total_points", 0),
                "max_points": prog.get("max_possible_points", 500),
                "pct": int(round(prog.get("overall_completion_rate", 0) * 100)),
                "streak": streak,
                "completed_tasks": completed,
                "pending_tasks": pending,
                "extra_info": extra_info,
            }

        nudge = await generate_reactive_nudge(
            user_name=user_name,
            command_name=command_name,
            progression=progression,
        )
        if nudge:
            content = f"<@{user_id}> 🐺 **Amarok observes**:\n> *\"{nudge}\"*"
            await channel.send(content)
    except Exception as e:
        logger.debug(f"Could not dispatch channel nudge for {user_name}: {e}")
