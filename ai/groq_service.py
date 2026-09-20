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


def extract_disciplines_fallback(raw_text: str, active_tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Robust pure-Python text and number extractor used as a fallback.
    Extracts numbers and exercises whether formatted as '25 pushups' or 'pushups 25',
    supporting commas, lists, and common exercise aliases.
    """
    text = raw_text.lower().strip()
    matches_dict: Dict[str, float] = {}

    discipline_map = {
        "Push-ups": [r"push[\s-]?ups?", r"pushies", r"\bpush\b"],
        "Pull-ups": [r"pull[\s-]?ups?", r"pullies", r"chin[\s-]?ups?", r"\bchins?\b", r"\bpull\b"],
        "Squats": [r"squats?", r"\bsquat\b"],
        "Sit-ups": [r"sit[\s-]?ups?", r"crunches", r"\bcrunch\b", r"\babs\b"],
        "Running": [r"running", r"\bruns?\b", r"\bran\b", r"jog(?:ged)?", r"kilometers?", r"\bkm\b", r"\bk\b", r"miles?"],
    }

    # Identify which active tasks correspond to standard disciplines
    for t in active_tasks:
        t_name = t["name"]
        keywords = []
        for d_key, kw_list in discipline_map.items():
            if d_key.lower() in t_name.lower():
                keywords = kw_list
                break
        if not keywords:
            keywords = [re.escape(t_name.lower())]

        kw_pattern = "(?:" + "|".join(keywords) + ")"

        # Pattern 1: Number before keyword (e.g. '25 pushups', '5km run', '25 reps of pushups')
        pat1 = rf"(?:^|[\s,;+&])(\d+(?:\.\d+)?)\s*(?:reps?\s*(?:of\s*)?|km\s*|k\s*)?{kw_pattern}(?:[\s,;+&]|$)"
        # Pattern 2: Keyword before number (e.g. 'pushups: 25', 'pushups 25', 'squats = 50', 'run 5km')
        pat2 = rf"(?:^|[\s,;+&]){kw_pattern}\s*[:=–-]?\s*(\d+(?:\.\d+)?)(?:\s*(?:reps?|km|k|miles?))?(?:[\s,;+&]|$)"

        m1 = re.search(pat1, text)
        m2 = re.search(pat2, text)

        val = None
        matched_str = ""
        if m1:
            val = float(m1.group(1))
            matched_str = m1.group(0)
        elif m2:
            val = float(m2.group(1))
            matched_str = m2.group(0)
        elif "run" in t_name.lower():
            # Special standalone running distance patterns (e.g. '5km', '5.2 km', '3 miles')
            m_dist = re.search(r"(?:^|[\s,;+&])(\d+(?:\.\d+)?)\s*(km|k|miles?|kilometers?)(?:[\s,;+&]|$)", text)
            if m_dist:
                val = float(m_dist.group(1))
                matched_str = m_dist.group(0)

        if val is not None and val > 0:
            if "mile" in matched_str:
                val = round(val * 1.60934, 1)
            matches_dict[t_name] = round(val, 2)

    matches = [{"task_name": k, "amount": v} for k, v in matches_dict.items()]
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


def regex_fallback_parser(raw_text: str, active_tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compatibility wrapper redirecting to extract_disciplines_fallback."""
    return extract_disciplines_fallback(raw_text, active_tasks)


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
        "   - EXACTLY 1 short, razor-sharp sentence of direct, disciplined coaching.\n"
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

        if not validated_matches:
            logger.info(f"Groq returned 0 matches for '{raw_text}'. Attempting pure-Python extractor fallback...")
            fallback_res = extract_disciplines_fallback(raw_text, active_tasks)
            if fallback_res.get("matches"):
                logger.info(f"Pure-Python fallback rescued {len(fallback_res['matches'])} match(es)")
                return fallback_res

        return {
            "matches": validated_matches,
            "unrecognized": data.get("unrecognized", []),
            "suspicious": is_suspicious,
            "commentary": str(data.get("commentary", "Discipline logged.")),
        }
    except Exception as e:
        logger.warning(f"Groq API call failed: {e}. Falling back to pure-Python extractor.")
        return extract_disciplines_fallback(raw_text, active_tasks)


REACTIVE_STOIC_FALLBACKS = [
    "Zero points on the board won't defend your streak. Drop and get moving.",
    "You could be good today, but instead you choose tomorrow. Drop and begin.",
    "Decent set, but the rest of the board is still waiting for you.",
    "We suffer more often in imagination than in reality. Finish the reps.",
    "Stop checking your numbers and go put more work on the board.",
    "The day is slipping away. Finish your remaining disciplines before midnight.",
    "Think of how long you have put this off. Put the work on the board.",
    "Good pace so far, but don't get comfortable until you hit clean day.",
    "No man is more unhappy than he who never faces adversity. Keep pushing.",
]


async def generate_reactive_nudge(
    user_name: str,
    command_name: str,
    progression: Dict[str, Any],
) -> Optional[str]:
    """
    Generates an ultra-fast, contextual 1-2 sentence high-energy reaction
    based on the user's live progression snapshot using Groq.
    Direct, motivating or roasting, grounded in actual numbers, with occasional
    familiar stoic discipline wisdom woven in. Zero AI slop, zero fantasy melodrama.
    """
    import random
    client = get_groq_client()
    if not client:
        return random.choice(REACTIVE_STOIC_FALLBACKS)

    system_prompt = (
        "You are Amarok, an uncompromising, high-energy accountability coach for the Winter Arc challenge.\n"
        "A user just ran a bot command. Speak directly to them in 1 to 2 punchy, realistic sentences with real personality and bite.\n\n"
        "RULES FOR DYNAMIC ENERGY AND TONE:\n"
        "1. NO ROBOTIC DATABASE READOUTS: NEVER output dry, lifeless statistics like 'Zero points logged with all three exercises still pending' or '40 points logged'.\n"
        "2. ROAST OR MOTIVATE BASED ON REAL NUMBERS:\n"
        "   - IF USER HAS 0 POINTS OR IS SLACKING: Roast them ruthlessly but realistically for opening Discord to stare at a flat zero, making excuses, or wasting daylight.\n"
        "     * Examples: 'You opened Discord just to stare at a flat zero? Drop and start with push-ups.'\n"
        "     * 'Zero points on the board and you're checking your stats like you accomplished something. Go earn it.'\n"
        "     * 'Day is slipping away and you haven't touched a single rep. Stop scrolling and move.'\n"
        "   - IF USER JUST LOGGED OR HAS SOLID MOMENTUM: Push them with relentless intensity to close out the remaining volume.\n"
        "     * Examples: 'Decent set, but don't start celebrating yet—pull-ups and squats are still waiting.'\n"
        "     * '400 points down. You are too close to a clean day to leave those last 100 points on the table.'\n"
        "     * '12-day streak on the line. Do not let today be the day you get soft and break it.'\n"
        "3. OCCASIONAL FAMILIAR STOIC WISDOM: Roughly 20% of the time, or when a warrior is hesitating, weave in or adapt a famous, sharp stoic quote (e.g. Marcus Aurelius, Seneca, Epictetus, Musashi) to cut through excuses.\n"
        "   - Examples: 'You could be good today, but instead you choose tomorrow. Drop and begin.'\n"
        "   - 'We suffer more in imagination than reality. Knock out the remaining set.'\n"
        "   - 'Think of how long you have put this off. Put the reps on the board.'\n"
        "4. NO FANTASY ROLEPLAY: Do NOT use dramatic medieval wolf roleplay ('the moon calls', 'the pack prowls', 'shadows'). Speak like a real, relentless training coach.\n"
        "5. LENGTH: 1 TO 2 PUNCHY SENTENCES (under 25 words total).\n"
        "6. Output ONLY the plain text sentence speaking directly to the user. Do not wrap in quotes, do not include any prefix, and do not use emojis."
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
            temperature=0.8,
            max_tokens=60,
        )
        latency = time.time() - start_t

        txt = (chat_completion.choices[0].message.content or "").strip().strip('"').strip("'")
        if ":" in txt and txt.split(":", 1)[0].lower().strip() in ["amarok", "sentinel", "edict", "observation", "coach"]:
            txt = txt.split(":", 1)[1].strip().strip('"').strip("'")
        txt = txt.strip("*").strip("_").strip('"').strip("'")
        logger.info(f"Groq reactive observation generated in {latency:.2f}s: '{txt}'")

        if txt and len(txt.split()) <= 30:
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
        logger.info(f"Nudge check for user {user_id}: triggered (roll {roll:.2f} <= {roll_chance}).")
        return True
    logger.info(f"Nudge check for user {user_id}: skipped (roll {roll:.2f} > {roll_chance}).")
    return False


def record_nudge_triggered(user_id: int) -> None:
    """Records the timestamp when a nudge is dispatched for cooldown tracking."""
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
    Non-blocking background dispatcher that sends a separate direct reaction
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
            content = f"<@{user_id}> {nudge}"
            channel = getattr(interaction, "channel", None)
            if not channel and hasattr(interaction, "client") and hasattr(interaction, "channel_id"):
                channel = interaction.client.get_channel(interaction.channel_id)

            sent = False
            if channel and hasattr(channel, "send"):
                try:
                    await channel.send(content)
                    sent = True
                    logger.info(f"Dispatched direct reaction to #{getattr(channel, 'name', 'chat')} for {user_name}: '{nudge}'")
                except Exception as send_err:
                    logger.warning(f"Could not send reaction via channel.send: {send_err}")

            if not sent:
                try:
                    await interaction.followup.send(content)
                    sent = True
                    logger.info(f"Dispatched direct reaction via followup for {user_name}: '{nudge}'")
                except Exception as followup_err:
                    logger.warning(f"Could not send reaction via interaction.followup: {followup_err}")
    except Exception as e:
        logger.warning(f"Could not dispatch interaction reaction for {user_name}: {e}")


async def dispatch_channel_nudge(
    channel: Any,
    user_id: int,
    user_name: str,
    command_name: str,
    progression: Optional[Dict[str, Any]] = None,
    extra_info: str = "",
    force: bool = False,
    message: Optional[Any] = None,
):
    """
    Non-blocking background dispatcher that sends a direct reaction message
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
            if message and hasattr(message, "reply"):
                try:
                    await message.reply(nudge, mention_author=True)
                    logger.info(f"Replied directly to message in #{getattr(channel, 'name', 'chat')} for {user_name}: '{nudge}'")
                    return
                except Exception as reply_err:
                    logger.warning(f"Could not reply directly to message: {reply_err}")

            content = f"<@{user_id}> {nudge}"
            await channel.send(content)
            logger.info(f"Dispatched direct reaction to #{getattr(channel, 'name', 'chat')} for {user_name}: '{nudge}'")
    except Exception as e:
        logger.debug(f"Could not dispatch channel reaction for {user_name}: {e}")
