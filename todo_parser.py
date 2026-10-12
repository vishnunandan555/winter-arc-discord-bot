"""
todo_parser.py - Smart Schedule & Reminder Parsing Engine for Todo Addon

Handles natural language and structured reminder expressions:
- One-time: '18:00', '6 PM', 'tomorrow 10:00', 'today 18:30', 'in 2 hours', 'in 30 mins'
- Intervals: 'every 30 mins', 'every hour', 'every 2 hours'
- Conditional windowed: 'every hour after 6 PM', 'every hour after 18:00'
- Smart frequencies: '3 times a day', '5 times a day' (auto-generates spaced schedule)
- Optional 'until': 'done' (indefinite until completed), 'tomorrow 20:00', or specific date/time
"""

import json
import re
import time
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, Any, List, Optional, Tuple
from zoneinfo import ZoneInfo
from config import BOT_TZ


def parse_time_component(s: str) -> Optional[Tuple[int, int]]:
    """
    Parses time strings like '18:00', '6:30pm', '6 PM', '10am', '9:15 AM'.
    Returns (hour, minute) in 24-hour format, or None.
    """
    s_clean = s.strip().lower()
    
    # 1. 12-hour with am/pm (e.g. '6:30pm', '6pm', '6:30 pm', '6 pm')
    m_12 = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", s_clean)
    if m_12:
        hour = int(m_12.group(1))
        minute = int(m_12.group(2)) if m_12.group(2) else 0
        meridiem = m_12.group(3)
        if hour == 12:
            hour = 0 if meridiem == "am" else 12
        elif meridiem == "pm":
            hour += 12
        if 0 <= hour < 24 and 0 <= minute < 60:
            return (hour, minute)

    # 2. 24-hour HH:MM (e.g. '18:00', '09:30', '8:45')
    m_24 = re.search(r"\b(\d{1,2}):(\d{2})\b", s_clean)
    if m_24:
        hour = int(m_24.group(1))
        minute = int(m_24.group(2))
        if 0 <= hour < 24 and 0 <= minute < 60:
            return (hour, minute)

    return None


def parse_until_spec(until_text: Optional[str], tz=BOT_TZ) -> Tuple[Optional[str], Optional[int]]:
    """
    Parses 'until' condition. If omitted or 'done', returns ('done', None).
    If a date/time is provided, parses into unix epoch timestamp.
    """
    if not until_text or until_text.strip().lower() in ["done", "its done", "completed", "finish"]:
        return ("done", None)

    u_clean = until_text.strip().lower()
    now = datetime.now(tz)

    # Check relative e.g. "tomorrow 8pm"
    time_part = parse_time_component(u_clean)
    h, m = time_part if time_part else (23, 59)

    target_date = now.date()
    if "tomorrow" in u_clean:
        target_date = now.date() + timedelta(days=1)
    elif "today" in u_clean:
        target_date = now.date()
    else:
        # Check ISO date YYYY-MM-DD
        m_date = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", u_clean)
        if m_date:
            try:
                target_date = datetime(int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3))).date()
            except Exception:
                pass

    target_dt = datetime(target_date.year, target_date.month, target_date.day, h, m, tzinfo=tz)
    return (until_text.strip(), int(target_dt.timestamp()))


def parse_remind_spec(
    remind_text: Optional[str],
    until_text: Optional[str] = None,
    tz=BOT_TZ,
    current_dt: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Parses user remind input into structured scheduling parameters:
    - remind_type: 'once', 'interval', 'daily_fixed', 'smart_frequency'
    - remind_interval_mins: int
    - remind_fixed_times: list of "HH:MM"
    - remind_window_start: "HH:MM" (e.g. for "after 6pm")
    - next_reminder_at: unix epoch
    - confirmation_msg: user-facing confirmation
    """
    if not remind_text or not remind_text.strip():
        u_spec, u_ts = parse_until_spec(until_text, tz=tz) if (until_text and until_text.strip()) else (None, None)
        return {
            "remind_spec": None,
            "remind_type": None,
            "remind_interval_mins": None,
            "remind_fixed_times": None,
            "remind_window_start": None,
            "until_spec": u_spec,
            "until_timestamp": u_ts,
            "next_reminder_at": None,
            "confirmation_msg": "Task added to your list.",
        }

    raw = remind_text.strip()
    low = raw.lower()
    now = current_dt if current_dt is not None else datetime.now(tz)
    until_spec, until_ts = parse_until_spec(until_text, tz=tz)

    until_desc = f" until {until_spec}" if until_spec and until_spec != "done" else " until marked done"

    # =====================================================================
    # 1a. Spaced within Waking Window ('7 times between 7am and 10pm')
    # =====================================================================
    m_between = re.search(r"(\d+)\s*(?:times?|x)?\s*(?:every\s*day|daily)?\s*between\s+(.+?)\s+and\s+(.+)", low)
    if m_between:
        count = int(m_between.group(1))
        count = max(1, min(count, 12))
        start_str = m_between.group(2).strip()
        end_str = m_between.group(3).strip()

        start_time = parse_time_component(start_str) or (7, 0)
        end_time = parse_time_component(end_str) or (22, 0)

        start_mins = start_time[0] * 60 + start_time[1]
        end_mins = end_time[0] * 60 + end_time[1]
        if end_mins <= start_mins:
            end_mins = start_mins + (14 * 60)  # default 14-hour span

        if count == 1:
            times = [f"{start_time[0]:02d}:{start_time[1]:02d}"]
        else:
            step = (end_mins - start_mins) / (count - 1)
            times = []
            for i in range(count):
                tot_m = int(round(start_mins + i * step))
                th = (tot_m // 60) % 24
                tm = tot_m % 60
                times.append(f"{th:02d}:{tm:02d}")

        # Find first next reminder timestamp
        next_ts = None
        for t_str in times:
            h, m = [int(p) for p in t_str.split(":", 1)]
            cand_dt = datetime(now.year, now.month, now.day, h, m, tzinfo=tz)
            if cand_dt > now:
                next_ts = int(cand_dt.timestamp())
                break

        if not next_ts:
            tom = now.date() + timedelta(days=1)
            h, m = [int(p) for p in times[0].split(":", 1)]
            cand_dt = datetime(tom.year, tom.month, tom.day, h, m, tzinfo=tz)
            next_ts = int(cand_dt.timestamp())

        readable_schedule = ", ".join(f"**{t}**" for t in times)
        conf = f"🔔 Reminders scheduled **{count} times a day** between {times[0]} and {times[-1]} ({readable_schedule}){until_desc}."
        return {
            "remind_spec": raw,
            "remind_type": "smart_frequency",
            "remind_interval_mins": None,
            "remind_fixed_times": times,
            "remind_window_start": times[0],
            "until_spec": until_spec,
            "until_timestamp": until_ts,
            "next_reminder_at": next_ts,
            "confirmation_msg": conf,
            "frequency_count": count,
        }

    # =====================================================================
    # 1b. Smart Frequencies ('3 times a day', '5 times a day')
    # =====================================================================
    m_freq = re.search(r"(\d+)\s*(?:times?|x)\s*(?:a|per)?\s*day", low)
    if m_freq:
        count = int(m_freq.group(1))
        count = max(1, min(count, 8)) # clamp between 1 and 8
        if count == 1:
            times = ["10:00"]
        elif count == 2:
            times = ["10:00", "18:00"]
        elif count == 3:
            times = ["10:00", "15:00", "20:00"]
        elif count == 4:
            times = ["09:00", "13:00", "17:00", "21:00"]
        elif count == 5:
            times = ["09:00", "12:00", "15:00", "18:00", "21:00"]
        else:
            # Distribute between 08:00 and 22:00
            start_h = 8
            end_h = 22
            step = (end_h - start_h) / (count - 1)
            times = [f"{int(round(start_h + i * step)):02d}:00" for i in range(count)]

        # Find first next reminder timestamp
        next_ts = None
        for t_str in times:
            h, m = [int(p) for p in t_str.split(":", 1)]
            cand_dt = datetime(now.year, now.month, now.day, h, m, tzinfo=tz)
            if cand_dt > now:
                next_ts = int(cand_dt.timestamp())
                break
        
        # If all passed today, pick first time tomorrow
        if not next_ts:
            tom = now.date() + timedelta(days=1)
            h, m = [int(p) for p in times[0].split(":", 1)]
            cand_dt = datetime(tom.year, tom.month, tom.day, h, m, tzinfo=tz)
            next_ts = int(cand_dt.timestamp())

        readable_schedule = ", ".join(f"**{t}**" for t in times)
        conf = f"🔔 Reminders scheduled **{count} times a day** ({readable_schedule}){until_desc}."
        return {
            "remind_spec": raw,
            "remind_type": "smart_frequency",
            "remind_interval_mins": None,
            "remind_fixed_times": times,
            "remind_window_start": None,
            "until_spec": until_spec,
            "until_timestamp": until_ts,
            "next_reminder_at": next_ts,
            "confirmation_msg": conf,
            "frequency_count": count,
        }

    # =====================================================================
    # 1c. Multi-Day Intervals ('every 4 days at 10am', 'every 2 days at 2pm')
    # =====================================================================
    m_multi_days = re.search(r"every\s+(\d+)\s+days?(?:\s+at\s+(.+))?", low)
    if m_multi_days:
        days_qty = int(m_multi_days.group(1))
        time_part_raw = m_multi_days.group(2)
        if not time_part_raw or not time_part_raw.strip():
            raise ValueError(f"Please specify an alert time for multi-day reminders (e.g. 'every {days_qty} days at 10am').")
        parsed_t = parse_time_component(time_part_raw.strip())
        if not parsed_t:
            raise ValueError(f"Could not parse alert time '{time_part_raw}'. Please use format like '10am' or '14:00'.")
        dh, dm = parsed_t
        time_str = f"{dh:02d}:{dm:02d}"
        today_dt = datetime(now.year, now.month, now.day, dh, dm, tzinfo=tz)
        if today_dt > now:
            next_ts = int(today_dt.timestamp())
        else:
            next_ts = int((today_dt + timedelta(days=days_qty)).timestamp())
        conf = f"🔔 Recurring reminder scheduled **every {days_qty} days at {time_str}**{until_desc}."
        return {
            "remind_spec": raw,
            "remind_type": "custom_days",
            "remind_interval_mins": None,
            "remind_interval_days": days_qty,
            "remind_fixed_times": [time_str],
            "remind_window_start": None,
            "until_spec": until_spec,
            "until_timestamp": until_ts,
            "next_reminder_at": next_ts,
            "confirmation_msg": conf,
            "frequency_count": 1,
        }

    # =====================================================================
    # 1d. Specific Weekdays ('sun, wed, thu, sat at 6am')
    # =====================================================================
    m_weekdays = re.search(r"(?:every\s+)?([a-z,\s]+?)\s+at\s+(.+)", low)
    if m_weekdays:
        days_candidate = m_weekdays.group(1).strip()
        time_candidate = m_weekdays.group(2).strip()
        w_map = {
            "mon": 0, "monday": 0,
            "tue": 1, "tues": 1, "tuesday": 1,
            "wed": 2, "web": 2, "wednesday": 2,
            "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
            "fri": 4, "friday": 4,
            "sat": 5, "saturday": 5,
            "sun": 6, "sunday": 6,
        }
        tokens = [re.sub(r'[^a-z]', '', tok) for tok in re.split(r'[, ]+', days_candidate)]
        matched_w_days = [w_map[tok] for tok in tokens if tok in w_map]
        parsed_t = parse_time_component(time_candidate)
        if matched_w_days and parsed_t:
            matched_w_days = sorted(list(set(matched_w_days)))
            dh, dm = parsed_t
            time_str = f"{dh:02d}:{dm:02d}"
            # Find next upcoming occurrence
            next_ts = None
            today_weekday = now.weekday()
            today_dt = datetime(now.year, now.month, now.day, dh, dm, tzinfo=tz)
            if today_weekday in matched_w_days and today_dt > now:
                next_ts = int(today_dt.timestamp())
            else:
                for offset in range(1, 8):
                    cand_date = now.date() + timedelta(days=offset)
                    if cand_date.weekday() in matched_w_days:
                        cand_dt = datetime(cand_date.year, cand_date.month, cand_date.day, dh, dm, tzinfo=tz)
                        next_ts = int(cand_dt.timestamp())
                        break

            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            schedule_str = ", ".join(day_names[d] for d in matched_w_days)
            conf = f"🔔 Recurring reminder scheduled on **{schedule_str} at {time_str}**{until_desc}."
            return {
                "remind_spec": raw,
                "remind_type": "weekdays",
                "remind_interval_mins": None,
                "remind_fixed_times": [time_str],
                "remind_window_start": None,
                "until_spec": until_spec,
                "until_timestamp": until_ts,
                "next_reminder_at": next_ts,
                "confirmation_msg": conf,
                "weekdays_list": matched_w_days,
                "frequency_count": len(matched_w_days),
            }

    # =====================================================================
    # 2. Windowed Interval ('every hour after 6 PM', 'every 30 mins after 18:00')
    # =====================================================================
    m_window = re.search(r"every\s+(\d+)?\s*(hours?|hrs?|mins?|minutes?)\s+after\s+(.+)", low)
    if m_window:
        val_str = m_window.group(1)
        unit = m_window.group(2)
        after_str = m_window.group(3).strip()

        interval_mins = 60
        if "min" in unit:
            interval_mins = int(val_str) if val_str else 30
        else:
            interval_mins = (int(val_str) if val_str else 1) * 60

        window_time = parse_time_component(after_str)
        w_h, w_m = window_time if window_time else (18, 0)
        window_start_str = f"{w_h:02d}:{w_m:02d}"

        # Calculate next_reminder_at
        # Window starts at w_h:w_m today
        today_window_dt = datetime(now.year, now.month, now.day, w_h, w_m, tzinfo=tz)
        if now < today_window_dt:
            # Not yet at window start today
            next_ts = int(today_window_dt.timestamp())
        else:
            # We are after window start today; add interval from now
            next_ts = int((now + timedelta(minutes=interval_mins)).timestamp())

        conf = f"🔔 Recurring reminder scheduled **every {interval_mins} mins after {window_start_str}**{until_desc}."
        return {
            "remind_spec": raw,
            "remind_type": "interval",
            "remind_interval_mins": interval_mins,
            "remind_fixed_times": None,
            "remind_window_start": window_start_str,
            "until_spec": until_spec,
            "until_timestamp": until_ts,
            "next_reminder_at": next_ts,
            "confirmation_msg": conf,
        }

    # =====================================================================
    # 3. Simple Interval ('every hour', 'every 2 hours', 'every 30 mins')
    # =====================================================================
    m_interval = re.search(r"every\s+(\d+)?\s*(hours?|hrs?|mins?|minutes?)", low)
    if m_interval:
        val_str = m_interval.group(1)
        unit = m_interval.group(2)
        if "min" in unit:
            interval_mins = int(val_str) if val_str else 30
        else:
            interval_mins = (int(val_str) if val_str else 1) * 60

        next_ts = int((now + timedelta(minutes=interval_mins)).timestamp())
        interval_label = f"{interval_mins // 60} hour(s)" if interval_mins >= 60 and interval_mins % 60 == 0 else f"{interval_mins} mins"
        conf = f"🔔 Recurring reminder scheduled **every {interval_label}**{until_desc}."
        return {
            "remind_spec": raw,
            "remind_type": "interval",
            "remind_interval_mins": interval_mins,
            "remind_fixed_times": None,
            "remind_window_start": None,
            "until_spec": until_spec,
            "until_timestamp": until_ts,
            "next_reminder_at": next_ts,
            "confirmation_msg": conf,
        }

    # =====================================================================
    # 4. Relative Offsets ('in 2 hours', 'in 30 mins', 'in 45 minutes')
    # =====================================================================
    m_in = re.search(r"\bin\s+(\d+)\s*(hours?|hrs?|mins?|minutes?)\b", low)
    if m_in:
        qty = int(m_in.group(1))
        unit = m_in.group(2)
        delta = timedelta(hours=qty) if "h" in unit else timedelta(minutes=qty)
        target_dt = now + delta
        next_ts = int(target_dt.timestamp())
        time_display = target_dt.strftime("%A, %I:%M %p")
        conf = f"⏰ One-time reminder scheduled for **{time_display}** (in {qty} {unit})."
        return {
            "remind_spec": raw,
            "remind_type": "once",
            "remind_interval_mins": None,
            "remind_fixed_times": None,
            "remind_window_start": None,
            "until_spec": until_spec,
            "until_timestamp": until_ts,
            "next_reminder_at": next_ts,
            "confirmation_msg": conf,
        }

    # =====================================================================
    # 4b. Daily Recurring Times ('every day at 10:00', 'every day 10:00', 'daily at 18:00')
    # =====================================================================
    m_daily = re.search(r"(?:every\s*day|daily)(?:\s+at)?\s+(.+)", low)
    if m_daily:
        time_part = m_daily.group(1).strip()
        parsed_daily_time = parse_time_component(time_part)
        if parsed_daily_time:
            dh, dm = parsed_daily_time
            time_str = f"{dh:02d}:{dm:02d}"
            times = [time_str]
            today_dt = datetime(now.year, now.month, now.day, dh, dm, tzinfo=tz)
            if today_dt > now:
                next_ts = int(today_dt.timestamp())
            else:
                next_ts = int((today_dt + timedelta(days=1)).timestamp())
            conf = f"🔔 Recurring reminder scheduled **every day at {time_str}**{until_desc}."
            return {
                "remind_spec": raw,
                "remind_type": "daily_fixed",
                "remind_interval_mins": None,
                "remind_fixed_times": times,
                "remind_window_start": None,
                "until_spec": until_spec,
                "until_timestamp": until_ts,
                "next_reminder_at": next_ts,
                "confirmation_msg": conf,
            }

    # =====================================================================
    # 5. One-Time Fixed Dates / Times ('tomorrow 10:00', 'today 18:30', '18:00', '6 PM')
    # =====================================================================
    parsed_time = parse_time_component(low)
    if parsed_time:
        hour, minute = parsed_time
        target_date = now.date()

        if "tomorrow" in low:
            target_date = now.date() + timedelta(days=1)
        elif "today" in low:
            target_date = now.date()
        else:
            # Check ISO date or month names
            m_date = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", low)
            if m_date:
                try:
                    target_date = datetime(int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3))).date()
                except Exception:
                    pass
            else:
                # If time was given without date, and time already passed today, assume tomorrow
                cand_dt = datetime(now.year, now.month, now.day, hour, minute, tzinfo=tz)
                if cand_dt <= now:
                    target_date = now.date() + timedelta(days=1)

        target_dt = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=tz)
        next_ts = int(target_dt.timestamp())
        time_display = target_dt.strftime("%A, %b %d at %I:%M %p")
        conf = f"⏰ One-time reminder scheduled for **{time_display}**."
        return {
            "remind_spec": raw,
            "remind_type": "once",
            "remind_interval_mins": None,
            "remind_fixed_times": None,
            "remind_window_start": None,
            "until_spec": until_spec,
            "until_timestamp": until_ts,
            "next_reminder_at": next_ts,
            "confirmation_msg": conf,
        }

    # If unrecognized, provide fallback 1 hour alert
    next_ts = int((now + timedelta(hours=1)).timestamp())
    return {
        "remind_spec": raw,
        "remind_type": "once",
        "remind_interval_mins": None,
        "remind_fixed_times": None,
        "remind_window_start": None,
        "until_spec": until_spec,
        "until_timestamp": until_ts,
        "next_reminder_at": next_ts,
        "confirmation_msg": f"⏰ Reminder set for **in 1 hour** ({raw}).",
    }


def compute_next_reminder(
    task: Dict[str, Any],
    tz=BOT_TZ,
    from_dt: Optional[datetime] = None,
) -> Optional[int]:
    """
    Calculates the NEXT timestamp for a recurring task after a reminder has fired.
    Returns None if:
    - Task is a one-time reminder ('once')
    - 'until_timestamp' has been reached or passed
    """
    remind_type = task.get("remind_type")
    if not remind_type or remind_type == "once":
        return None

    now = from_dt if from_dt is not None else datetime.now(tz)
    until_ts = task.get("until_timestamp")

    # 1. Interval
    if remind_type == "interval":
        interval_mins = task.get("remind_interval_mins") or 60
        next_dt = now + timedelta(minutes=interval_mins)

        # Check window condition (e.g. "after 18:00")
        w_start = task.get("remind_window_start")
        if w_start:
            try:
                wh, wm = [int(p) for p in w_start.split(":", 1)]
                # If next_dt rolled over into the early morning (e.g. past midnight),
                # postpone next reminder to today's window start (18:00)
                if next_dt.hour < wh:
                    next_dt = datetime(next_dt.year, next_dt.month, next_dt.day, wh, wm, tzinfo=tz)
            except Exception:
                pass

        next_ts = int(next_dt.timestamp())
        if until_ts and next_ts > until_ts:
            return None
        return next_ts

    # 2. Smart frequency or daily fixed times
    if remind_type in ["smart_frequency", "daily_fixed", "fixed_daily"]:
        fixed_times = task.get("fixed_times_list")
        if not fixed_times and task.get("remind_fixed_times"):
            rft = task["remind_fixed_times"]
            if isinstance(rft, list):
                fixed_times = rft
            elif isinstance(rft, str):
                try:
                    fixed_times = json.loads(rft)
                except Exception:
                    fixed_times = []
        if not fixed_times:
            return None

        # Look for next time today
        for t_str in fixed_times:
            h, m = [int(p) for p in t_str.split(":", 1)]
            cand_dt = datetime(now.year, now.month, now.day, h, m, tzinfo=tz)
            if cand_dt > now + timedelta(minutes=1): # allow 1 min buffer
                next_ts = int(cand_dt.timestamp())
                if until_ts and next_ts > until_ts:
                    return None
                return next_ts

        # All times passed today, pick first time tomorrow
        tom = now.date() + timedelta(days=1)
        h, m = [int(p) for p in fixed_times[0].split(":", 1)]
        cand_dt = datetime(tom.year, tom.month, tom.day, h, m, tzinfo=tz)
        next_ts = int(cand_dt.timestamp())
        if until_ts and next_ts > until_ts:
            return None
        return next_ts

    # 3. Multi-day custom intervals ('custom_days')
    if remind_type == "custom_days":
        interval_days = task.get("remind_interval_days") or 1
        fixed_times = task.get("fixed_times_list")
        if not fixed_times and task.get("remind_fixed_times"):
            try:
                fixed_times = json.loads(task["remind_fixed_times"]) if isinstance(task["remind_fixed_times"], str) else task["remind_fixed_times"]
            except Exception:
                fixed_times = []
        t_str = fixed_times[0] if fixed_times else "10:00"
        h, m = [int(p) for p in t_str.split(":", 1)]
        next_date = now.date() + timedelta(days=interval_days)
        cand_dt = datetime(next_date.year, next_date.month, next_date.day, h, m, tzinfo=tz)
        next_ts = int(cand_dt.timestamp())
        if until_ts and next_ts > until_ts:
            return None
        return next_ts

    # 4. Specific weekdays ('weekdays')
    if remind_type == "weekdays":
        fixed_times = task.get("fixed_times_list")
        if not fixed_times and task.get("remind_fixed_times"):
            try:
                fixed_times = json.loads(task["remind_fixed_times"]) if isinstance(task["remind_fixed_times"], str) else task["remind_fixed_times"]
            except Exception:
                fixed_times = []
        t_str = fixed_times[0] if fixed_times else "10:00"
        h, m = [int(p) for p in t_str.split(":", 1)]
        w_days = task.get("weekdays_list") or [0, 1, 2, 3, 4, 5, 6]
        for offset in range(1, 8):
            cand_date = now.date() + timedelta(days=offset)
            if cand_date.weekday() in w_days:
                cand_dt = datetime(cand_date.year, cand_date.month, cand_date.day, h, m, tzinfo=tz)
                next_ts = int(cand_dt.timestamp())
                if until_ts and next_ts > until_ts:
                    return None
                return next_ts

    return None


def infer_task_counter_and_reset(
    remind_result: Dict[str, Any],
    raw_count: Optional[int] = None,
    raw_reset: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Determines target_count, reset_period, and reset_interval_days using
    intelligent defaults and reminder inheritance.
    Returns a dict with 'target_count', 'reset_period', and 'reset_interval_days'.
    """
    reset_period = "none"
    reset_days = 0

    if raw_reset:
        norm_reset = raw_reset.strip().lower()
        if "day" in norm_reset or "daily" in norm_reset:
            m_days = re.search(r"(\d+)\s*days?", norm_reset)
            if m_days and int(m_days.group(1)) > 1:
                reset_period = "custom_days"
                reset_days = int(m_days.group(1))
            else:
                reset_period = "daily"
                reset_days = 1
        elif "week" in norm_reset:
            reset_period = "weekly"
            reset_days = 7
        elif norm_reset in ["none", "never"]:
            reset_period = "none"
            reset_days = 0
        else:
            reset_period = "daily"
            reset_days = 1
    else:
        # Inherit from reminder engine if raw_reset was omitted
        r_type = remind_result.get("remind_type")
        if r_type in ["smart_frequency", "daily_fixed"]:
            reset_period = "daily"
            reset_days = 1
        elif r_type == "custom_days":
            reset_period = "custom_days"
            reset_days = remind_result.get("remind_interval_days", 1)
        elif r_type == "weekdays":
            reset_period = "weekly"
            reset_days = 7
        elif r_type == "interval":
            reset_period = "daily"
            reset_days = 1
        else:
            reset_period = "none"
            reset_days = 0

    if raw_count is not None and int(raw_count) > 0:
        target_count = int(raw_count)
    else:
        freq_count = remind_result.get("frequency_count")
        if freq_count and freq_count > 1:
            target_count = freq_count
        else:
            target_count = 0

    return {
        "target_count": target_count,
        "reset_period": reset_period,
        "reset_interval_days": reset_days,
    }

