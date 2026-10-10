"""
notion_sync.py - One-way sync from zeya_pa to a Notion "Daily Drop" database.
Each day gets one page with three sections: To-do, Brain dump, Little reminders.

The title and date columns are looked up from the database itself, so renaming
them in Notion (e.g. "Name" -> "Title") doesn't break the sync. Errors written
to data/notion_sync.log include Notion's own explanation.
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

_schema = {}


def _check(response):
    """Like raise_for_status, but keeps Notion's explanation of what's wrong."""
    if response.ok:
        return
    try:
        message = response.json().get("message", response.text)
    except ValueError:
        message = response.text
    raise RuntimeError(f"{response.status_code} {message}")


def _text(t):
    return [{"type": "text", "text": {"content": t}}]


def _columns():
    """Find the database's title column and date column (cached)."""
    if not _schema:
        r = requests.get(f"{API}/databases/{DB}", headers=HEADERS, timeout=10)
        _check(r)
        props = r.json()["properties"]
        _schema["title"] = next(n for n, p in props.items() if p["type"] == "title")
        dates = [n for n, p in props.items() if p["type"] == "date"]
        _schema["date"] = "Date" if "Date" in dates else (dates[0] if dates else None)
    return _schema


def _today_page_id():
    today = dt.date.today()
    page_name = today.strftime("%a, %d %b %Y")
    cols = _columns()

    if cols["date"]:
        flt = {"property": cols["date"], "date": {"equals": today.isoformat()}}
    else:   # no date column: fall back to matching the page title
        flt = {"property": cols["title"], "title": {"equals": page_name}}
    q = requests.post(f"{API}/databases/{DB}/query", headers=HEADERS, timeout=10,
                      json={"filter": flt})
    _check(q)
    if q.json()["results"]:
        return q.json()["results"][0]["id"]

    properties = {cols["title"]: {"title": _text(page_name)}}
    if cols["date"]:
        properties[cols["date"]] = {"date": {"start": today.isoformat()}}
    body = {
        "parent": {"database_id": DB},
        "icon": {"type": "emoji", "emoji": "\u2726"},
        "properties": properties,
        "children": [
            {"type": "heading_2", "heading_2": {"rich_text": _text(s)}}
            for s in SECTIONS
        ],
    }
    r = requests.post(f"{API}/pages", headers=HEADERS, json=body, timeout=10)
    _check(r)
    return r.json()["id"]


def _heading_ids(page_id):
    r = requests.get(f"{API}/blocks/{page_id}/children", headers=HEADERS, timeout=10)
    _check(r)
    ids = {}
    for b in r.json()["results"]:
        if b["type"] == "heading_2" and b["heading_2"]["rich_text"]:
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
        _check(r)
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
    _check(r)


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