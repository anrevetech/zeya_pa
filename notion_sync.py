"""
notion_sync.py - One-way sync from zeya_pa to a Notion "Daily Drop" database.
Each day gets one page with three sections: To-do, Brain dump, Little reminders.
"""

import os
import threading
import datetime as dt
from pathlib import Path

import requests
from dotenv import load_dotenv

# Always load .env from the same folder as this file, regardless of where
# the app is launched from.
load_dotenv(Path(__file__).parent / ".env")

API = "https://api.notion.com/v1"
DB = os.getenv("NOTION_DAILY_DB_ID")
HEADERS = {
    "Authorization": f"Bearer {os.getenv('NOTION_TOKEN')}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
SECTIONS = ["To-do", "Brain dump", "Little reminders"]


def _text(t):
    return [{"type": "text", "text": {"content": t}}]


def _today_page_id():
    today = dt.date.today()
    q = requests.post(
        f"{API}/databases/{DB}/query", headers=HEADERS, timeout=10,
        json={"filter": {"property": "Date", "date": {"equals": today.isoformat()}}},
    )
    q.raise_for_status()
    if q.json()["results"]:
        return q.json()["results"][0]["id"]

    body = {
        "parent": {"database_id": DB},
        "icon": {"type": "emoji", "emoji": "✦"},
        "properties": {
            "Name": {"title": _text(today.strftime("%a, %d %b %Y"))},
            "Date": {"date": {"start": today.isoformat()}},
        },
        "children": [
            {"type": "heading_2", "heading_2": {"rich_text": _text(s)}}
            for s in SECTIONS
        ],
    }
    r = requests.post(f"{API}/pages", headers=HEADERS, json=body, timeout=10)
    r.raise_for_status()
    return r.json()["id"]


def _heading_ids(page_id):
    r = requests.get(f"{API}/blocks/{page_id}/children", headers=HEADERS, timeout=10)
    r.raise_for_status()
    ids = {}
    for b in r.json()["results"]:
        if b["type"] == "heading_2":
            ids[b["heading_2"]["rich_text"][0]["plain_text"]] = b["id"]
    return ids


def _ensure_headings(page_id):
    """Return {section: block_id}, adding any missing section headings to the
    page first (covers pages that already existed without our layout)."""
    ids = _heading_ids(page_id)
    missing = [s for s in SECTIONS if s not in ids]
    if missing:
        r = requests.patch(
            f"{API}/blocks/{page_id}/children", headers=HEADERS, timeout=10,
            json={"children": [
                {"type": "heading_2", "heading_2": {"rich_text": _text(s)}}
                for s in missing
            ]},
        )
        r.raise_for_status()
        ids = _heading_ids(page_id)
    return ids


def push(kind, text):
    """kind: 'task' -> To-do, 'reminder' -> Little reminders, 'note' -> Brain dump"""
    section = {"task": "To-do", "reminder": "Little reminders", "note": "Brain dump"}[kind]
    page_id = _today_page_id()
    after = _ensure_headings(page_id)[section]
    if kind == "task":
        block = {"type": "to_do", "to_do": {"rich_text": _text(text), "checked": False}}
    else:
        block = {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _text(text)}}
    r = requests.patch(
        f"{API}/blocks/{page_id}/children", headers=HEADERS, timeout=10,
        json={"children": [block], "after": after},
    )
    r.raise_for_status()


def _log(message):
    """Append a timestamped line to data/notion_sync.log (works under pythonw,
    where print() output is invisible)."""
    try:
        log_dir = Path(__file__).parent / "data"
        log_dir.mkdir(exist_ok=True)
        with open(log_dir / "notion_sync.log", "a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now().isoformat(timespec='seconds')}  {message}\n")
    except OSError:
        pass


def push_async(kind, text):
    """Send to Notion in the background; never blocks or crashes the app."""
    def _run():
        try:
            push(kind, text)
        except Exception as e:  # pylint: disable=broad-exception-caught
            _log(f"Notion sync skipped: {e}")
    threading.Thread(target=_run, daemon=True).start()