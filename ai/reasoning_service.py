"""
ai/reasoning_service.py - High-Reasoning & Synthesis Engine for Winter Arc

Powers:
1. /grind daily academic & mental friction evaluation (with strict anti-slop rules).
2. Daily Announcements (05:00 Morning Kickoff, 16:30 Afternoon Check-in, 21:00 Evening Warning).
3. Daily Midnight Toast & Roast digest (00:00).
4. Sunday Weekly "State of the Pack" broadcast (10:00).
5. Milestone Phase Transition Ceremonies.
6. Personalized 05:00 Morning DM Reflections.

Execution Pipeline:
- Tier 1 (Primary): OpenRouter (openrouter/free or configured model) via standard async HTTPS
- Tier 2 (Secondary Fallback): Groq Cloud (openai/gpt-oss-20b)
- Tier 3 (Tertiary Fallback): Curated authentic Stoic quotes & deterministic templates
"""

import json
import time
import asyncio
import logging
import re
import random
from typing import Dict, Any, List, Optional, Tuple
import httpx

from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_FALLBACK_MODELS,
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_FALLBACK_MODELS,
)
from ai.models import (
    GrindEvaluation,
    EveningCalloutItem,
    EveningAlertPayload,
    ReasoningServiceError,
    AIServiceError,
)
from ai.fallbacks import (
    CURATED_STOIC_FALLBACKS,
    AUTHENTIC_STOIC_QUOTES,
    AUTHENTIC_REST_QUOTES,
    ARD_AFTERNOON_FALLBACKS,
    ARD_EVENING_FALLBACKS,
    get_default_callout,
)
from ai.prompts import (
    GRIND_EVALUATION_SYSTEM_PROMPT,
    build_grind_eval_schema_instruction,
    build_daily_toast_and_roast_prompt,
    TOAST_ROAST_SYSTEM_PROMPT,
    build_weekly_state_of_the_pack_prompt,
    RECAP_SYSTEM_PROMPT,
    build_reminder_motivation_prompt,
    REMINDER_SYSTEM_INSTRUCTION,
    build_personalized_morning_briefing_prompt,
    BRIEFING_SYSTEM_PROMPT,
    build_evening_alert_system_prompt,
    build_phase_ceremony_prompt,
    CEREMONY_SYSTEM_PROMPT,
)
from ai.groq_service import safe_groq_chat_completion

logger = logging.getLogger("winter_arc.ai.reasoning")


# -------------------------------------------------------------------------
# OpenRouter Client Engine (Tier 1 Primary Reasoning)
# -------------------------------------------------------------------------

def clean_ai_thought_leakage(text: Optional[str], is_json: bool = False) -> Optional[str]:
    """
    Sanitizes LLM outputs by removing reasoning blocks, <think> tags,
    and analytical preambles (e.g. 'Here's a thinking process:', '1. Analyze User Request:').
    Returns the cleaned plain output string, or None if the output is pure leaked thought/empty.
    """
    if not text:
        return None

    # 1. Strip XML-like thinking / reasoning tags
    text = re.sub(r"(?is)<think>.*?</think>", "", text)
    if "<think>" in text:
        text = text.split("<think>")[0]
    text = re.sub(r"(?is)<(thought|reasoning|analysis|scratchpad)>.*?</\1>", "", text)
    for tag in ["<thought>", "<reasoning>", "<analysis>", "<scratchpad>"]:
        if tag in text:
            text = text.split(tag)[0]

    # If JSON is expected, extract json block or raw json
    if is_json:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        m_raw = re.search(r"(\{.*\})", text, re.DOTALL)
        if m_raw:
            return m_raw.group(1).strip()
        return text.strip() or None

    # 2. Identify thought leakage patterns and analytical preambles
    thought_leak_patterns = [
        r"(?i)\bhere'?s\s+a\s+thinking\s+process\b",
        r"(?i)\bthinking\s+process\b",
        r"(?i)\bthought\s+process\b",
        r"(?i)\banalyze\s+user\s+request\b",
        r"(?i)\banalyzing\s+the\s+(user\s+)?request\b",
        r"(?i)\blet'?s\s+analyze\b",
        r"(?i)\b\*\*persona:\*\*",
        r"(?i)\b\*\*context:\*\*",
        r"(?i)\b\*\*instruction:\*\*",
        r"(?i)\b\*\*guidelines:\*\*",
        r"(?i)\b\*\*tone:\*\*",
        r"(?i)\b\*\*target\s+audience:\*\*",
    ]

    has_leak = any(re.search(p, text) for p in thought_leak_patterns)
    if has_leak:
        parts = re.split(r"\n\s*\n", text)
        candidates = []
        for part in parts:
            p_strip = part.strip()
            if not any(re.search(p, p_strip) for p in thought_leak_patterns) and len(p_strip.split()) >= 4:
                p_clean = re.sub(r"(?i)^(output|response|final quote|quote|check-?in)\s*:\s*", "", p_strip)
                candidates.append(p_clean)
        if candidates:
            text = candidates[-1]
        else:
            logger.warning(f"Discarded AI output due to thought/reasoning leakage: {repr(text)[:120]}")
            return None

    # 3. Clean leading author/role prefixes
    text = text.strip()
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()
    if ":" in text:
        prefix = text.split(":", 1)[0].lower().strip()
        if prefix in ["amarok", "quote", "sentinel", "edict", "response", "output"]:
            text = text.split(":", 1)[1].strip()
            if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
                text = text[1:-1].strip()

    # 4. Final verification
    if any(re.search(p, text) for p in thought_leak_patterns):
        logger.warning(f"Discarded AI output with residual thought leakage: {repr(text)[:120]}")
        return None

    text = text.strip()
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()
    return text if len(text.split()) >= 3 else None


def get_openrouter_candidate_models(requested_model: Optional[str] = None) -> List[str]:
    """Builds an ordered, deduplicated list of fallback models for OpenRouter."""
    primary = requested_model or OPENROUTER_MODEL
    ordered = [primary] + OPENROUTER_FALLBACK_MODELS
    seen = set()
    res = []
    for m in ordered:
        if m and m not in seen:
            seen.add(m)
            res.append(m)
    return res


async def safe_openrouter_chat_completion(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    response_format: Optional[Dict[str, Any]] = None,
    temperature: float = 0.7,
    max_tokens: int = 300,
    timeout: float = 12.0,
) -> Optional[str]:
    """
    Executes a chat completion via OpenRouter with candidate fallback models.
    Returns the string text content of the completion or None if all models fail.
    """
    if not OPENROUTER_API_KEY:
        return None

    candidates = get_openrouter_candidate_models(model)
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/vishnunandan555/winter-arc-discord-bot",
        "X-Title": "Winter Arc Bot",
    }

    for idx, cand_model in enumerate(candidates):
        payload: Dict[str, Any] = {
            "model": cand_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        try:
            async with httpx.AsyncClient(timeout=timeout) as http_client:
                resp = await http_client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", "")
                        if content:
                            cleaned = clean_ai_thought_leakage(content, is_json=bool(response_format))
                            if cleaned:
                                if idx > 0:
                                    logger.info(f"✅ OpenRouter fallback SUCCESS: Recovered with model '{cand_model}'.")
                                return cleaned
                            else:
                                logger.warning(f"⚠️ OpenRouter model '{cand_model}' returned thought leakage or empty response. Attempting next model...")
                elif resp.status_code == 429:
                    logger.warning(f"⚠️ OpenRouter model '{cand_model}' rate-limited (429). Attempting next model...")
                else:
                    logger.warning(f"⚠️ OpenRouter model '{cand_model}' returned {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            logger.warning(f"⚠️ OpenRouter model '{cand_model}' failed ({e}). Attempting next model...")

    return None


# -------------------------------------------------------------------------
# Health Check Banner
# -------------------------------------------------------------------------

async def check_ai_health() -> Dict[str, str]:
    """
    Performs startup health checks on configured AI services (OpenRouter & Groq)
    and logs their operational status.
    """
    results = {}
    logger.info("Verifying AI engines connectivity and availability...")

    # 1. OpenRouter (Primary Reasoning)
    openrouter_status = "NOT CONFIGURED (OPENROUTER_API_KEY missing)"
    if OPENROUTER_API_KEY:
        try:
            ping_res = await asyncio.wait_for(
                safe_openrouter_chat_completion(
                    messages=[{"role": "user", "content": "ping"}],
                    model=OPENROUTER_MODEL,
                    max_tokens=5,
                    timeout=8.0,
                ),
                timeout=10.0
            )
            if ping_res:
                openrouter_status = f"ONLINE ({OPENROUTER_MODEL})"
            else:
                openrouter_status = "UNAVAILABLE (All candidate models failed)"
        except Exception as e:
            openrouter_status = f"ERROR ({str(e)[:80]})"
    results["openrouter"] = openrouter_status

    # 2. Groq Cloud (Ultra-Fast Fallback & NLP)
    groq_status = "NOT CONFIGURED (GROQ_API_KEY missing)"
    if GROQ_API_KEY:
        try:
            from ai.groq_service import get_groq_client
            groq_client = get_groq_client()
            if groq_client:
                res = await asyncio.wait_for(
                    safe_groq_chat_completion(
                        groq_client,
                        messages=[{"role": "user", "content": "ping"}],
                        model=GROQ_MODEL,
                        max_tokens=5,
                    ),
                    timeout=8.0
                )
                groq_status = f"ONLINE ({GROQ_MODEL})"
            else:
                groq_status = "INITIALIZATION FAILED"
        except Exception as e:
            groq_status = f"ERROR ({str(e)[:80]})"
    results["groq"] = groq_status

    logger.info("=" * 60)
    logger.info("🧠 AI ENGINE STARTUP HEALTH STATUS:")
    logger.info(f"  • OpenRouter:  {results['openrouter']}")
    logger.info(f"  • Groq Cloud:  {results['groq']}")
    logger.info("=" * 60)
    return results


# -------------------------------------------------------------------------
# /grind Evaluation Pipeline
# -------------------------------------------------------------------------

def _postprocess_grind_evaluation(data: Dict[str, Any], raw_text: str, provider: str = "OpenRouter") -> Dict[str, Any]:
    """Validates and clamps grind evaluation fields conforming to standard schema."""
    points = int(data.get("points", 0))
    verdict = str(data.get("verdict", "REJECTED")).upper()
    if verdict not in ["ACCEPTED", "REJECTED", "ROASTED"]:
        verdict = "ACCEPTED" if points > 0 else "REJECTED"

    is_injection = any(h in raw_text.lower() for h in [
        "ignore previous", "ignore all", "system prompt", "give me 50", "give me 60", "developer mode", "jailbreak"
    ])
    if is_injection:
        verdict = "REJECTED"
        points = 0
    elif verdict == "ROASTED" and points <= 0:
        points = 10

    points = max(0, min(points, 50))

    excluded = data.get("tracked_disciplines_excluded", [])
    if not isinstance(excluded, list):
        excluded = [str(excluded)] if excluded else []
    excluded_clean = [str(x).strip() for x in excluded if str(x).strip()]

    learning_candidate = str(data.get("key_learning") or "").strip()
    if not learning_candidate or learning_candidate.lower() == "none":
        learning_candidate = "Effort" if verdict == "ROASTED" else "Custom Grind"
    learning_candidate = learning_candidate[:100]

    commentary_str = str(data.get("commentary") or "Grind logged.").strip()
    if not commentary_str:
        commentary_str = "Grind logged."

    logger.info(f"{provider} /grind evaluation completed: {verdict} ({points} pts, summary: {learning_candidate}, excluded: {excluded_clean})")
    return {
        "verdict": verdict,
        "points": points,
        "key_learning": learning_candidate,
        "tracked_disciplines_excluded": excluded_clean,
        "commentary": commentary_str,
    }


async def _evaluate_grind_with_openrouter(raw_text: str, system_prompt: str) -> Optional[Dict[str, Any]]:
    """Evaluates /grind submission via OpenRouter."""
    if not OPENROUTER_API_KEY:
        return None

    openrouter_system = build_grind_eval_schema_instruction()
    messages = [
        {"role": "system", "content": openrouter_system},
        {"role": "user", "content": f'User Reflection:\n"{raw_text}"'}
    ]

    try:
        logger.info(f"Calling OpenRouter API ({OPENROUTER_MODEL}) for /grind evaluation...")
        start_t = time.time()
        content = await safe_openrouter_chat_completion(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=450,
            timeout=12.0
        )
        if not content:
            return None
        latency = time.time() - start_t
        clean_content = clean_ai_thought_leakage(content, is_json=True) or content.strip()
        clean_content = re.sub(r"^```(?:json)?\s*", "", clean_content, flags=re.IGNORECASE)
        clean_content = re.sub(r"\s*```$", "", clean_content).strip()
        if "{" in clean_content and "}" in clean_content:
            clean_content = clean_content[clean_content.find("{"):clean_content.rfind("}") + 1]
        data = json.loads(clean_content)
        return _postprocess_grind_evaluation(data, raw_text, provider=f"OpenRouter ({OPENROUTER_MODEL}) in {latency:.2f}s")
    except Exception as e:
        logger.warning(f"OpenRouter /grind evaluation failed ({e}). Falling back to Groq...")
        return None


async def _evaluate_grind_with_groq(raw_text: str, system_prompt: str) -> Dict[str, Any]:
    """Fallback evaluation engine powered by Groq."""
    from ai.groq_service import get_groq_client
    groq_client = get_groq_client()
    if not groq_client:
        logger.warning("Groq AI client is not configured or GROQ_API_KEY missing.")
        raise ReasoningServiceError("Neither OpenRouter nor Groq AI evaluation service is available.")

    groq_system = build_grind_eval_schema_instruction()
    try:
        logger.info(f"Calling Groq API ({GROQ_MODEL}) for fallback /grind evaluation...")
        start_t = time.time()
        chat_completion = await asyncio.wait_for(
            safe_groq_chat_completion(
                groq_client,
                messages=[
                    {"role": "system", "content": groq_system},
                    {"role": "user", "content": f'User Reflection:\n"{raw_text}"'},
                ],
                model=GROQ_MODEL,
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=400,
            ),
            timeout=8.0
        )
        latency = time.time() - start_t
        used_model = getattr(chat_completion, "model", GROQ_MODEL)
        content = chat_completion.choices[0].message.content or "{}"
        clean_content = clean_ai_thought_leakage(content, is_json=True) or content.strip()
        clean_content = re.sub(r"^```(?:json)?\s*", "", clean_content, flags=re.IGNORECASE)
        clean_content = re.sub(r"\s*```$", "", clean_content).strip()
        if "{" in clean_content and "}" in clean_content:
            clean_content = clean_content[clean_content.find("{"):clean_content.rfind("}") + 1]
        data = json.loads(clean_content)
        return _postprocess_grind_evaluation(data, raw_text, provider=f"Groq ({used_model}) in {latency:.2f}s")
    except Exception as e:
        logger.error(f"Error calling Groq for fallback /grind evaluation: {e}")
        raise ReasoningServiceError(f"Both OpenRouter and Groq AI evaluation services failed ({e}).")


async def evaluate_grind(raw_text: str) -> Dict[str, Any]:
    """
    Evaluates a user's daily physical custom workout or intellectual deep work friction.
    Primary: OpenRouter.
    Fallback: Groq Cloud.
    """
    system_prompt = GRIND_EVALUATION_SYSTEM_PROMPT

    # 1. Primary: OpenRouter
    openrouter_res = await _evaluate_grind_with_openrouter(raw_text, system_prompt)
    if openrouter_res:
        return openrouter_res

    # 2. Secondary: Groq Fallback
    try:
        return await _evaluate_grind_with_groq(raw_text, system_prompt)
    except Exception as groq_err:
        logger.warning(f"Groq /grind fallback also failed ({groq_err}).")
        raise ReasoningServiceError(f"All AI evaluation services (OpenRouter, Groq) failed: {groq_err}")


# -------------------------------------------------------------------------
# Daily Midnight Toast & Roast (00:00)
# -------------------------------------------------------------------------

async def generate_daily_toast_and_roast(
    podium_data: List[Dict[str, Any]],
    grind_highlights: List[Dict[str, Any]],
    slacker_count: int,
    total_enrolled: int
) -> str:
    """Generates a concise (under 80 words) Daily Toast & Roast for 00:00 midnight."""
    prompt = build_daily_toast_and_roast_prompt(podium_data, grind_highlights, slacker_count, total_enrolled)
    toast_sys_prompt = TOAST_ROAST_SYSTEM_PROMPT

    # 1. Primary: OpenRouter
    if OPENROUTER_API_KEY:
        try:
            logger.info(f"Calling OpenRouter API ({OPENROUTER_MODEL}) for midnight toast & roast...")
            res = await safe_openrouter_chat_completion(
                messages=[
                    {"role": "system", "content": toast_sys_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=200,
                timeout=10.0,
            )
            res = clean_ai_thought_leakage(res)
            if res and len(res.split()) >= 5:
                return res
        except Exception as e:
            logger.warning(f"OpenRouter toast & roast failed ({e}). Falling back to Groq...")

    # 2. Secondary: Groq Fallback
    try:
        from ai.groq_service import get_groq_client
        groq_client = get_groq_client()
        if groq_client:
            completion = await asyncio.wait_for(
                safe_groq_chat_completion(
                    groq_client,
                    messages=[
                        {"role": "system", "content": toast_sys_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    model=GROQ_MODEL,
                    temperature=0.7,
                    max_tokens=200,
                ),
                timeout=6.0
            )
            raw = completion.choices[0].message.content or ""
            txt = clean_ai_thought_leakage(raw)
            if txt and len(txt.split()) >= 5:
                logger.info("Groq fallback daily toast & roast generated successfully.")
                return txt
    except Exception as groq_err:
        logger.warning(f"Groq daily toast & roast fallback failed ({groq_err}). Using deterministic summary.")

    # 3. Tertiary: Static Fallback
    if podium_data:
        top_name = podium_data[0]["username"]
        top_pts = podium_data[0]["points"]
        return f"Midnight gavel falls. Respect to {top_name} for securing #{1} with {top_pts} points today. Reset the board and bring higher standards tomorrow."
    return "Midnight gavel falls. Zero excuses roll over. Tomorrow begins now."


# -------------------------------------------------------------------------
# Sunday State of the Pack (10:00 AM)
# -------------------------------------------------------------------------

async def generate_weekly_state_of_the_pack(
    weekly_stats: Dict[str, Any],
    top_warriors: List[Dict[str, Any]],
    weekly_grinds: List[Dict[str, Any]],
    ghosts_count: int
) -> str:
    """Generates the Sunday 10:00 IST community broadcast reflection (under 80 words)."""
    prompt = build_weekly_state_of_the_pack_prompt(weekly_stats, top_warriors, weekly_grinds, ghosts_count)
    recap_sys_prompt = RECAP_SYSTEM_PROMPT

    # 1. Primary: OpenRouter
    if OPENROUTER_API_KEY:
        try:
            logger.info(f"Calling OpenRouter API ({OPENROUTER_MODEL}) for weekly state of the pack...")
            res = await safe_openrouter_chat_completion(
                messages=[
                    {"role": "system", "content": recap_sys_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=200,
                timeout=10.0,
            )
            res = clean_ai_thought_leakage(res)
            if res and len(res.split()) >= 5:
                return res
        except Exception as e:
            logger.warning(f"OpenRouter weekly state of the pack failed ({e}). Falling back to Groq...")

    # 2. Secondary: Groq Fallback
    try:
        from ai.groq_service import get_groq_client
        groq_client = get_groq_client()
        if groq_client:
            completion = await asyncio.wait_for(
                safe_groq_chat_completion(
                    groq_client,
                    messages=[
                        {"role": "system", "content": recap_sys_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    model=GROQ_MODEL,
                    temperature=0.7,
                    max_tokens=200,
                ),
                timeout=6.0
            )
            raw = completion.choices[0].message.content or ""
            txt = clean_ai_thought_leakage(raw)
            if txt and len(txt.split()) >= 5:
                logger.info("Groq fallback weekly state of the pack generated successfully.")
                return txt
    except Exception as groq_err:
        logger.warning(f"Groq weekly state of the pack fallback failed ({groq_err}). Using deterministic summary.")

    # 3. Tertiary: Static Fallback
    if top_warriors:
        p1 = top_warriors[0].get("points", top_warriors[0].get("total_points", 0))
        contenders = [top_warriors[0]["username"]]
        for w in top_warriors[1:3]:
            pw = w.get("points", w.get("total_points", 0))
            if p1 > 0 and pw >= p1 * 0.7:
                contenders.append(w["username"])
        if len(contenders) > 1:
            leaders_str = ", ".join(contenders[:-1]) + f" and {contenders[-1]}"
            return f"Week concluded. High-level battle at the top between {leaders_str} setting the standard. If you stayed at zero, new week starts tomorrow—step up."
        else:
            return f"Week concluded. Salute to {top_warriors[0]['username']} for dominating the pack this week. To everyone trailing behind: close the gap starting tomorrow."
    return "Week concluded. Execution continues tomorrow at 00:00 IST. Step up."


# -------------------------------------------------------------------------
# Dynamic Reminder Motivation & Stoic Quotes
# -------------------------------------------------------------------------

async def generate_reminder_motivation(
    reminder_type: str = "morning",
    user_context: Optional[Dict[str, Any]] = None,
    recent_history: Optional[List[Dict[str, Any]]] = None,
    force_judgment: bool = False,
) -> str:
    """
    Generates a dynamic stoic motivational quote or personal progress judgment.
    """
    prompt = build_reminder_motivation_prompt(reminder_type, user_context, recent_history, force_judgment)

    tokens_to_use = 250 if reminder_type in ["afternoon_recovery", "evening_recovery"] else 150
    word_limit = 65 if reminder_type in ["afternoon_recovery", "evening_recovery"] else 35
    sys_instruction = REMINDER_SYSTEM_INSTRUCTION

    # 1. Primary: OpenRouter
    if OPENROUTER_API_KEY:
        try:
            logger.info(f"Calling OpenRouter API ({OPENROUTER_MODEL}) for {reminder_type} reminder quote...")
            txt = await safe_openrouter_chat_completion(
                messages=[
                    {"role": "system", "content": sys_instruction},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=tokens_to_use,
                timeout=8.0,
            )
            txt = clean_ai_thought_leakage(txt)
            if not txt or len(txt.split()) < 3:
                raise ValueError("OpenRouter quote rejected due to thought leakage or invalid length.")

            if len(txt.split()) > word_limit:
                sentences = re.split(r"(?<=[.!?])\s+", txt)
                accum = []
                for s in sentences:
                    if len((" ".join(accum + [s])).split()) <= word_limit:
                        accum.append(s)
                    else:
                        break
                txt = " ".join(accum) if accum else (" ".join(txt.split()[:word_limit - 5]) + ".")

            logger.info(f"OpenRouter {reminder_type} quote generated: '{txt}'")
            return txt
        except Exception as e:
            logger.warning(f"OpenRouter {reminder_type} reminder quote failed ({e}). Falling back to Groq...")

    # 2. Secondary: Groq Fallback
    try:
        from ai.groq_service import get_groq_client
        groq_client = get_groq_client()
        if groq_client:
            logger.info(f"Calling Groq API ({GROQ_MODEL}) for fallback {reminder_type} reminder quote...")
            completion = await asyncio.wait_for(
                safe_groq_chat_completion(
                    groq_client,
                    messages=[
                        {"role": "system", "content": sys_instruction},
                        {"role": "user", "content": prompt},
                    ],
                    model=GROQ_MODEL,
                    temperature=0.7,
                    max_tokens=tokens_to_use,
                ),
                timeout=6.0
            )
            g_raw = completion.choices[0].message.content or ""
            g_txt = clean_ai_thought_leakage(g_raw)
            if not g_txt or len(g_txt.split()) < 3:
                raise ValueError("Groq quote rejected due to thought leakage or invalid length.")

            if len(g_txt.split()) > word_limit:
                sentences = re.split(r"(?<=[.!?])\s+", g_txt)
                accum = []
                for s in sentences:
                    if len((" ".join(accum + [s])).split()) <= word_limit:
                        accum.append(s)
                    else:
                        break
                g_txt = " ".join(accum) if accum else (" ".join(g_txt.split()[:word_limit - 5]) + ".")

            logger.info(f"Groq fallback {reminder_type} quote generated: '{g_txt}'")
            return g_txt
    except Exception as groq_err:
        logger.warning(f"Groq {reminder_type} quote fallback failed: {groq_err}")

    # 3. Tertiary: Static Fallback
    logger.warning(f"Could not generate AI {reminder_type} quote. Using curated fallback.")
    if reminder_type == "morning_recovery":
        return random.choice(AUTHENTIC_REST_QUOTES)
    if reminder_type == "afternoon_recovery":
        return random.choice(ARD_AFTERNOON_FALLBACKS)
    if reminder_type == "evening_recovery":
        return random.choice(ARD_EVENING_FALLBACKS)
    return random.choice(AUTHENTIC_STOIC_QUOTES)


# -------------------------------------------------------------------------
# Personalized Morning Briefing (05:00 AM DMs)
# -------------------------------------------------------------------------

async def generate_personalized_morning_briefing(
    briefing_context: Dict[str, Any],
    is_recovery: bool = False,
) -> str:
    """Generates a personalized 2-sentence morning reflection for opted-in member DMs."""
    u_name = briefing_context.get("username", "Warrior")
    prompt = build_personalized_morning_briefing_prompt(briefing_context, is_recovery)
    briefing_sys_prompt = BRIEFING_SYSTEM_PROMPT

    # 1. Primary: OpenRouter
    if OPENROUTER_API_KEY:
        try:
            logger.info(f"Calling OpenRouter API ({OPENROUTER_MODEL}) for personalized morning briefing for {u_name}...")
            txt = await safe_openrouter_chat_completion(
                messages=[
                    {"role": "system", "content": briefing_sys_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=220,
                timeout=10.0,
            )
            txt = clean_ai_thought_leakage(txt)
            if not txt or len(txt.split()) < 3:
                raise ValueError("OpenRouter morning briefing rejected due to thought leakage or invalid length.")

            if len(txt.split()) <= 70:
                logger.info(f"OpenRouter morning briefing generated for {u_name}: '{txt}'")
                return txt
        except Exception as e:
            logger.warning(f"OpenRouter morning briefing failed for {u_name} ({e}). Falling back to Groq...")

    # 2. Secondary: Groq Fallback
    try:
        from ai.groq_service import get_groq_client
        groq_client = get_groq_client()
        if groq_client:
            logger.info(f"Calling Groq API ({GROQ_MODEL}) for fallback morning briefing for {u_name}...")
            completion = await asyncio.wait_for(
                safe_groq_chat_completion(
                    groq_client,
                    messages=[
                        {"role": "system", "content": briefing_sys_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    model=GROQ_MODEL,
                    temperature=0.7,
                    max_tokens=220,
                ),
                timeout=6.0
            )
            g_raw = completion.choices[0].message.content or ""
            g_txt = clean_ai_thought_leakage(g_raw)
            if not g_txt or len(g_txt.split()) < 3:
                raise ValueError("Groq morning briefing rejected due to thought leakage or invalid length.")

            if len(g_txt.split()) <= 70:
                logger.info(f"Groq fallback morning briefing generated: '{g_txt}'")
                return g_txt
    except Exception as groq_err:
        logger.warning(f"Groq morning briefing fallback also failed: {groq_err}")

    # 3. Tertiary: Static Fallback
    logger.warning(f"Could not generate personalized morning briefing for {u_name}. Using curated fallback.")
    if is_recovery:
        total_7d = briefing_context.get("total_pts_7d", 0)
        streak = briefing_context.get("streak", 0)
        solid_days = briefing_context.get("solid_days", 0)
        if total_7d >= 100 or streak >= 3 or solid_days >= 2:
            return "You've put in brutal consistency over the last few days. Take pride in that work, but do not sit stagnant on the couch. Focus on deep hydration (3L+), hip & hamstring mobility, and a 20-minute gentle walk to flush out lactic acid. Rebuild the engine."
        else:
            return "You've been lagging behind on your volume over the past few days. While today protects your streak, do NOT treat it as an excuse to do zero. Get outside, hit a solid 30-minute walk, stretch, hydrate, and use today to build the momentum you've been missing for tomorrow."
    return random.choice(CURATED_STOIC_FALLBACKS)


# -------------------------------------------------------------------------
# Evening Alert Callouts & Quote (21:00 IST)
# -------------------------------------------------------------------------

async def generate_evening_alert_data(
    warriors_data: List[Dict[str, Any]],
    override_quote: Optional[str] = None
) -> Tuple[Dict[int, str], str]:
    """Generates personalized 1-sentence accountability callouts and selects stoic quote for 21:00 IST."""
    fallback_callouts: Dict[int, str] = {}
    for w in warriors_data:
        pts = w.get("points", 0)
        d_id = int(w["discord_id"])
        fallback_callouts[d_id] = get_default_callout(pts)

    fallback_quote = override_quote or random.choice(AUTHENTIC_STOIC_QUOTES)

    if not warriors_data:
        return fallback_callouts, fallback_quote

    participant_lines = []
    for w in warriors_data:
        d_id = w["discord_id"]
        u_name = w.get("username", "Warrior")
        pts = w.get("points", 0)
        streak = w.get("streak", 0)
        participant_lines.append(
            f"- User ID: {d_id} | Username: {u_name} | Points today: {pts} | Streak: {streak}d"
        )

    system_prompt = build_evening_alert_system_prompt()
    tokens_to_use = min(1500, max(450, len(warriors_data) * 60 + 200))

    # 1. Primary: OpenRouter
    if OPENROUTER_API_KEY:
        try:
            logger.info(f"Calling OpenRouter API ({OPENROUTER_MODEL}) for evening alert callouts & quote...")
            res_content = await safe_openrouter_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Participants tonight (3 hours before midnight):\n" + "\n".join(participant_lines)},
                ],
                response_format={"type": "json_object"},
                temperature=0.4,
                max_tokens=tokens_to_use,
                timeout=12.0,
            )
            if res_content:
                clean_content = clean_ai_thought_leakage(res_content, is_json=True)
                if "{" in clean_content and "}" in clean_content:
                    clean_content = clean_content[clean_content.find("{"):clean_content.rfind("}") + 1]
                data = json.loads(clean_content)
                result_callouts = dict(fallback_callouts)
                for item in data.get("callouts", []):
                    try:
                        user_id = int(item.get("discord_id"))
                        callout_text = clean_ai_thought_leakage(str(item.get("callout", ""))).strip()
                        if callout_text and not any(m in callout_text.lower() for m in ["thinking process", "analyze user", "reasoning", "thought:"]) and user_id in result_callouts:
                            result_callouts[user_id] = callout_text
                    except (ValueError, TypeError):
                        continue

                if override_quote:
                    chosen_quote = override_quote
                else:
                    chosen_quote = clean_ai_thought_leakage(str(data.get("stoic_quote", ""))).strip()
                    if not chosen_quote or "—" not in chosen_quote or any(m in chosen_quote.lower() for m in ["thinking process", "analyze user", "reasoning", "thought:"]):
                        chosen_quote = fallback_quote

                logger.info(f"OpenRouter evening alert successfully parsed {len(result_callouts)} callout(s).")
                return result_callouts, chosen_quote
        except Exception as e:
            logger.warning(f"OpenRouter evening alert failed ({e}). Falling back to Groq...")

    # 2. Secondary: Groq Fallback
    try:
        from ai.groq_service import get_groq_client
        groq_client = get_groq_client()
        if groq_client:
            completion = await asyncio.wait_for(
                safe_groq_chat_completion(
                    groq_client,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Participants tonight:\n" + "\n".join(participant_lines)},
                    ],
                    model=GROQ_MODEL,
                    response_format={"type": "json_object"},
                    temperature=0.4,
                    max_tokens=tokens_to_use,
                ),
                timeout=8.0
            )
            content = completion.choices[0].message.content or "{}"
            clean_content = clean_ai_thought_leakage(content, is_json=True)
            if "{" in clean_content and "}" in clean_content:
                clean_content = clean_content[clean_content.find("{"):clean_content.rfind("}") + 1]
            data = json.loads(clean_content)

            result_callouts = dict(fallback_callouts)
            for item in data.get("callouts", []):
                try:
                    user_id = int(item.get("discord_id"))
                    callout_text = clean_ai_thought_leakage(str(item.get("callout", ""))).strip()
                    if callout_text and not any(m in callout_text.lower() for m in ["thinking process", "analyze user", "reasoning", "thought:"]) and user_id in result_callouts:
                        result_callouts[user_id] = callout_text
                except (ValueError, TypeError):
                    continue

            if override_quote:
                chosen_quote = override_quote
            else:
                chosen_quote = clean_ai_thought_leakage(str(data.get("stoic_quote", ""))).strip()
                if not chosen_quote or "—" not in chosen_quote or any(m in chosen_quote.lower() for m in ["thinking process", "analyze user", "reasoning", "thought:"]):
                    chosen_quote = fallback_quote

            return result_callouts, chosen_quote
    except Exception as groq_err:
        logger.warning(f"Groq evening alert fallback also failed ({groq_err}). Using deterministic callouts.")

    return fallback_callouts, fallback_quote


# -------------------------------------------------------------------------
# Phase Ceremony Proclamation
# -------------------------------------------------------------------------

async def generate_phase_ceremony(
    phase_info: Dict[str, Any],
    top_warriors: List[Dict[str, Any]],
    bottom_warriors: List[Dict[str, Any]],
    next_phase_info: Optional[Dict[str, Any]] = None
) -> str:
    """Generates the official End-of-Phase ceremony proclamation."""
    prompt = build_phase_ceremony_prompt(phase_info, top_warriors, bottom_warriors, next_phase_info)
    ceremony_system = CEREMONY_SYSTEM_PROMPT

    # 1. Primary: OpenRouter
    if OPENROUTER_API_KEY:
        try:
            logger.info(f"Calling OpenRouter API ({OPENROUTER_MODEL}) for phase ceremony address...")
            res = await safe_openrouter_chat_completion(
                messages=[
                    {"role": "system", "content": ceremony_system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.75,
                max_tokens=450,
                timeout=12.0,
            )
            if res:
                clean_res = clean_ai_thought_leakage(res).strip()
                if clean_res and not any(m in clean_res.lower() for m in ["thinking process", "analyze user", "reasoning", "thought:"]):
                    return clean_res
        except Exception as e:
            logger.warning(f"OpenRouter phase ceremony failed ({e}). Falling back to Groq...")

    # 2. Secondary: Groq Fallback
    try:
        from ai.groq_service import get_groq_client
        groq_client = get_groq_client()
        if groq_client:
            completion = await asyncio.wait_for(
                safe_groq_chat_completion(
                    groq_client,
                    messages=[
                        {"role": "system", "content": ceremony_system},
                        {"role": "user", "content": prompt},
                    ],
                    model=GROQ_MODEL,
                    temperature=0.75,
                    max_tokens=450,
                ),
                timeout=8.0
            )
            txt = completion.choices[0].message.content or ""
            clean_txt = clean_ai_thought_leakage(txt).strip()
            if clean_txt and not any(m in clean_txt.lower() for m in ["thinking process", "analyze user", "reasoning", "thought:"]):
                logger.info("Groq fallback phase ceremony generated successfully.")
                return clean_txt
    except Exception as groq_err:
        logger.warning(f"Groq phase ceremony fallback failed ({groq_err}). Using deterministic proclamation.")

    # 3. Tertiary: Static Fallback
    top_names = [w['username'] for w in top_warriors[:3]]
    top_str = f"Salute to {', '.join(top_names)} and everyone who held the line daily throughout {phase_info['name']}." if top_names else f"Respect to everyone who held the line daily throughout {phase_info['name']}."
    next_str = f"Prepare for {next_phase_info['name']} tomorrow." if next_phase_info else "The Winter Arc stands conquered."
    return f"{phase_info['name']} has officially closed. {top_str} The standards only rise from here. {next_str}"
