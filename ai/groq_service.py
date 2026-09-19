"""
ai/groq_service.py - Ultra-Fast NLP Workout Parser Powered by Groq

Extracts completed exercises from natural language input with sub-second latency
and strict active-task validation.
"""

import json
import re
import time
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
        logger.info(f"Calling Groq API ({GROQ_MODEL}) for workout parsing: '{raw_text}'...")
        start_t = time.time()
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
        latency = time.time() - start_t
        content = chat_completion.choices[0].message.content
        data = json.loads(content)
        logger.info(f"Groq parse response received in {latency:.2f}s: {len(data.get('matches', []))} match(es)")

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
    "The scoreboard doesn't lie. Finish what you started.",
    "Every rep counts. Put the work on the board.",
    "Words build nothing. Log the discipline.",
    "Consistency beats intensity. Defend the streak today.",
    "Momentum is earned daily. Keep moving.",
    "Discipline is doing what needs to be done, regardless of how you feel.",
]


async def generate_reactive_nudge(
    user_name: str,
    command_name: str,
    progression: Dict[str, Any],
) -> Optional[str]:
    """
    Generates an ultra-fast, contextual 1-sentence stoic observation/nudge
    based on the user's live progression snapshot using Groq.
    Strictly 1 short sentence (under 18 words total). Zero AI slop, zero fantasy melodrama.
    """
    import random
    client = get_groq_client()
    if not client:
        return random.choice(REACTIVE_STOIC_FALLBACKS)

    system_prompt = (
        "You are Amarok, an uncompromising, no-nonsense accountability coach for the Winter Arc challenge.\n"
        "A user just ran a bot command. Give a single, razor-sharp, realistic observation based strictly on their actual numbers.\n\n"
        "CRITICAL RULES - NO CLICHES OR ROLEPLAY SLOP:\n"
        "1. STRICTLY FORBIDDEN: NEVER use dramatic roleplay or fantasy metaphors like 'howling dark', 'blizzard', 'lone wolf', 'shadows', 'frost', 'prowling', or gothic melodrama.\n"
        "2. Ground your observation in their REAL PROGRESS: Mention their remaining points, pending exercises, streak, or current completion rate realistically.\n"
        "3. Tone: Direct, blunt, pragmatic, and grounded. No hype, no cheerleading ('great job', 'keep it up' are forbidden).\n"
        "4. Examples of good observations:\n"
        "   - '18% logged. 410 points left on the board—finish the job.'\n"
        "   - 'Push-ups are done, but pull-ups and running are still untouched.'\n"
        "   - 'A 7-day streak only counts if you log the rest before midnight.'\n"
        "   - 'Solid set, but 350 points are still pending.'\n"
        "5. LENGTH: EXACTLY 1 SHORT SENTENCE (strictly under 18 words total).\n"
        "6. Output ONLY the plain text sentence. Do not wrap in quotes and do not include any prefix or emoji."
    )

    pts = progression.get("points", 0)
    max_pts = progression.get("max_points", 500)
    pct = progression.get("pct", 0)
    streak = progression.get("streak", 0)
    remaining = max(0, max_pts - pts)
    extra = progression.get("extra_info", "")
    completed = progression.get("completed_tasks", [])
    pending = progression.get("pending_tasks", [])

    user_prompt = (
        f"Warrior: {user_name}. Command: /{command_name}.\n"
        f"Progress: {pts}/{max_pts} pts ({pct}%). Remaining: {remaining} pts.\n"
        f"Streak: {streak} days.\n"
    )
    if extra:
        user_prompt += f"Action: {extra}\n"
    if completed:
        user_prompt += f"Completed: {', '.join(completed[:3])}\n"
    if pending:
        user_prompt += f"Pending: {', '.join(pending[:3])}\n"

    try:
        logger.info(f"Calling Groq API ({GROQ_MODEL}) for reactive observation: {user_name} on /{command_name}...")
        start_t = time.time()
        chat_completion = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=GROQ_MODEL,
            temperature=0.7,
            max_tokens=50,
        )
        latency = time.time() - start_t

        txt = (chat_completion.choices[0].message.content or "").strip().strip('"').strip("'")
        if ":" in txt and txt.split(":", 1)[0].lower().strip() in ["amarok", "sentinel", "edict", "observation", "coach"]:
            txt = txt.split(":", 1)[1].strip().strip('"').strip("'")
        txt = txt.strip("*").strip("_").strip('"').strip("'")
        logger.info(f"Groq reactive observation generated in {latency:.2f}s: '{txt}'")

        if txt and len(txt.split()) <= 25:
            return txt
        return random.choice(REACTIVE_STOIC_FALLBACKS)
    except Exception as e:
        logger.warning(f"Groq reactive nudge generation failed: {e}. Using curated fallback.", exc_info=True)
        return random.choice(REACTIVE_STOIC_FALLBACKS)


_last_nudge_timestamps: Dict[int, float] = {}
NUDGE_COOLDOWN_SECONDS: float = 3600.0  # 1 hour per user


def should_trigger_nudge(user_id: int, force: bool = False, roll_chance: float = 0.35) -> bool:
    """Evaluates whether a reactive nudge should trigger based on cooldown and random probability."""
    if force:
        logger.info(f"Nudge check for user {user_id}: triggered (force=True).")
        return True
    import time
    import random
    now = time.time()
    last_time = _last_nudge_timestamps.get(user_id, 0.0)
    elapsed = now - last_time
    if elapsed < NUDGE_COOLDOWN_SECONDS:
        rem_min = int((NUDGE_COOLDOWN_SECONDS - elapsed) // 60)
        logger.info(f"Nudge check for user {user_id}: skipped (on cooldown for {rem_min}m).")
        return False
    roll = random.random()
    if roll <= roll_chance:
        logger.info(f"Nudge check for user {user_id}: triggered (roll {roll:.2f} <= {roll_chance:.2f}).")
        return True
    logger.info(f"Nudge check for user {user_id}: skipped (roll {roll:.2f} > {roll_chance:.2f}).")
    return False


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
            channel = getattr(interaction, "channel", None)
            if not channel and hasattr(interaction, "client") and hasattr(interaction, "channel_id"):
                channel = interaction.client.get_channel(interaction.channel_id)

            sent = False
            if channel and hasattr(channel, "send"):
                try:
                    await channel.send(content)
                    sent = True
                    logger.info(f"Dispatched Amarok reactive observation to #{getattr(channel, 'name', 'chat')} for {user_name}: '{nudge}'")
                except Exception as send_err:
                    logger.warning(f"Could not send nudge via channel.send: {send_err}")

            if not sent:
                try:
                    await interaction.followup.send(content)
                    sent = True
                    logger.info(f"Dispatched Amarok reactive observation via followup for {user_name}: '{nudge}'")
                except Exception as followup_err:
                    logger.warning(f"Could not send nudge via interaction.followup: {followup_err}")
    except Exception as e:
        logger.warning(f"Could not dispatch interaction nudge for {user_name}: {e}")


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
