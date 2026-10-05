"""
task_parser.py - Converts natural-language input into a structured task.

Locked rules (do not change without re-checking with the rest of the app):
1. Detect date/time using dateparser.
2. Detect explicit reminder language -> type = "reminder".
3. Detect explicit deadline language -> type = "deadline".
4. Otherwise -> type = "task" (the default/fallback).
5. Having a date NEVER by itself implies "deadline" or "reminder".
6. A missing time is NEVER invented (no silent 11:59 PM, no silent 9:00 AM).
7. This module only extracts and structures - it never saves anything.
   ui.py is responsible for showing the confirmation screen before save.
"""

import re

from dateparser.search import search_dates


# ---------------------------------------------------------------------------
# Keyword rules
# ---------------------------------------------------------------------------

REMINDER_PATTERNS = [
    r"\bremind me to\b",
    r"\bremind me about\b",
    r"\bremind me\b",
    r"\bdon't let me forget to\b",
    r"\bdont let me forget to\b",
    r"\bdon't let me forget\b",
]

DEADLINE_PATTERNS = [
    r"\bsubmit by\b",
    r"\bfinish by\b",
    r"\bcomplete by\b",
    r"\bdue by\b",
    r"\bdue\b",
    r"\bdeadline\b",
    r"\blast date\b",
    r"\bbefore\b",
    r"\bby\b",
]

TIME_SIGNAL_PATTERN = re.compile(
    r"(\d{1,2}(:\d{2})?\s*(am|pm))|"
    r"\b\d{1,2}:\d{2}\b|"
    r"\bnoon\b|\bmidnight\b|\bmorning\b|\bafternoon\b|\bevening\b|"
    r"\btonight\b|\bnight\b|\bo'clock\b",
    re.IGNORECASE,
)

DATEPARSER_SETTINGS = {
    "PREFER_DATES_FROM": "future",
    "RETURN_AS_TIMEZONE_AWARE": False,
}


# ---------------------------------------------------------------------------
# Step 1: detect task_type
# ---------------------------------------------------------------------------

def _detect_type(text: str) -> str:
    lowered = text.lower()

    for pattern in REMINDER_PATTERNS:
        if re.search(pattern, lowered):
            return "reminder"

    for pattern in DEADLINE_PATTERNS:
        if re.search(pattern, lowered):
            return "deadline"

    return "task"


# ---------------------------------------------------------------------------
# Step 2: detect date/time
# ---------------------------------------------------------------------------

def _detect_date(text: str):
    """
    Returns (matched_substring, datetime_obj, time_was_specified) or
    (None, None, False) if no date/time phrase was found.
    """
    # Restricting to English avoids dateparser occasionally misreading a
    # short common word (e.g. "me") as a date/month abbreviation in another
    # language - a real bug this produced during testing.
    matches = search_dates(text, languages=["en"], settings=DATEPARSER_SETTINGS)
    if not matches:
        return None, None, False

    # Use the first match - V1 assumes one date phrase per entry.
    matched_substring, dt = matches[0]
    time_specified = bool(TIME_SIGNAL_PATTERN.search(matched_substring))
    return matched_substring, dt, time_specified


# ---------------------------------------------------------------------------
# Step 3: clean the title
# ---------------------------------------------------------------------------

_CONNECTOR_WORDS = [
    "by", "before", "due", "on", "at", "tomorrow", "today", "tonight",
]


def _clean_title(text: str, matched_substring: str, task_type: str) -> str:
    cleaned = text

    # Strip the reminder prefix if this was a reminder (e.g. "remind me to").
    if task_type == "reminder":
        for pattern in REMINDER_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # Remove the matched date phrase itself.
    if matched_substring:
        cleaned = cleaned.replace(matched_substring, "")

    # Trim leftover connector words at the very end of the sentence, e.g.
    # "Submit Java report by" -> "Submit Java report".
    words = cleaned.strip().split()
    while words and words[-1].lower().strip(".,") in _CONNECTOR_WORDS:
        words.pop()
    cleaned = " ".join(words)

    # Collapse extra whitespace and tidy punctuation left over from removal.
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.-")

    if not cleaned:
        cleaned = text.strip()  # fallback: never return an empty title

    # Capitalize first letter only - don't touch the rest (names, acronyms).
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]

    return cleaned


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_input(text: str) -> dict:
    """
    Parse a raw natural-language string into a structured task dict.

    due_at is intentionally left None when no time was specified, so the
    scheduler never fires a notification at a time the user never gave.
    due_date is still populated so the task list can display "Friday".
    """
    original_text = text.strip()
    task_type = _detect_type(original_text)
    matched_substring, dt, time_specified = _detect_date(original_text)
    title = _clean_title(original_text, matched_substring, task_type)

    due_date = None
    due_time = None
    due_at = None

    if dt is not None:
        due_date = dt.date().isoformat()
        if time_specified:
            due_time = dt.strftime("%H:%M")
            due_at = dt.replace(second=0, microsecond=0).isoformat()

    return {
        "title": title,
        "original_text": original_text,
        "task_type": task_type,
        "due_date": due_date,
        "due_time": due_time,
        "due_at": due_at,
        "date_detected": dt is not None,
        "time_specified": time_specified,
    }


if __name__ == "__main__":
    # Quick manual check: run `python task_parser.py` to see how sample
    # inputs get parsed, without touching the database or UI.
    samples = [
        "Buy milk",
        "Buy milk tomorrow",
        "Remind me to buy milk tomorrow",
        "Buy milk by tomorrow",
        "Study at 7 PM",
        "Remind me to study at 7 PM",
        "Finish report by 7 PM",
        "Submit assignment by Friday",
        "Finish Java report tomorrow at 6 PM",
        "Call mom tomorrow evening",
        "Submit assignment on September 18 at 10:30 AM",
        "Don't let me forget to carry my ID tomorrow",
    ]
    for s in samples:
        result = parse_input(s)
        print(f"\nInput: {s}")
        for k, v in result.items():
            print(f"  {k}: {v}")