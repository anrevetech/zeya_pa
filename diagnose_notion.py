"""
diagnose_notion.py - Standalone diagnostic for the Notion Daily Drop sync.

Checks each step of the sync pipeline and prints what works and what fails,
WITHOUT ever printing the token itself.  Safe to run, safe to share the output.

Usage:
    python diagnose_notion.py
"""

import os
import sys
import datetime as dt
from pathlib import Path

# Fix encoding for Windows terminals that default to cp1252
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Step 0: load .env ───────────────────────────────────────────────
print("=" * 60)
print("STEP 0 – Loading .env")
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    loaded = load_dotenv(env_path)
    print(f"  .env file exists : {env_path.exists()}")
    print(f"  dotenv loaded ok : {loaded}")
except ImportError:
    sys.exit("  FAIL: python-dotenv is not installed (pip install python-dotenv)")

TOKEN = os.getenv("NOTION_TOKEN")
DB_ID = os.getenv("NOTION_DAILY_DB_ID")

print(f"  NOTION_TOKEN      : {'set (' + str(len(TOKEN)) + ' chars)' if TOKEN else 'MISSING'}")
print(f"  NOTION_DAILY_DB_ID: {'set (' + str(len(DB_ID)) + ' chars)' if DB_ID else 'MISSING'}")

if not TOKEN or not DB_ID:
    sys.exit("\n  FAIL: one or both env vars are missing – check .env")

import requests

API = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


def _text(t):
    return [{"type": "text", "text": {"content": t}}]


# ── Step 1: GET database ────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"STEP 1 – GET /v1/databases/{DB_ID[:8]}…")
r = requests.get(f"{API}/databases/{DB_ID}", headers=HEADERS, timeout=15)
print(f"  HTTP {r.status_code}")
if not r.ok:
    try:
        msg = r.json().get("message", r.text)
    except ValueError:
        msg = r.text
    print(f"  ERROR: {msg}")
    if r.status_code == 404:
        print("\n  → The integration probably isn't connected to this database.")
        print("    In Notion: open the database page → click '…' → Connections")
        print("    → add the integration that owns your NOTION_TOKEN.")
    sys.exit(1)

db_json = r.json()
props = db_json["properties"]
print(f"  Database title: {db_json.get('title', [{}])[0].get('plain_text', '(unknown)')}")
print(f"  Properties ({len(props)}):")
title_col = None
date_col = None
for name, prop in props.items():
    ptype = prop["type"]
    print(f"    - {name!r:30s} type={ptype}")
    if ptype == "title":
        title_col = name
    if ptype == "date":
        date_col = name

print(f"\n  Title column : {title_col!r}")
print(f"  Date column  : {date_col!r}")

# ── Step 2: find or create today's page ──────────────────────────────
print("\n" + "=" * 60)
today = dt.date.today()
page_name = today.strftime("%a, %d %b %Y")
print(f"STEP 2 – Find or create today's page: {page_name!r}")

# Query for existing page
if date_col:
    flt = {"property": date_col, "date": {"equals": today.isoformat()}}
else:
    flt = {"property": title_col, "title": {"equals": page_name}}

q = requests.post(f"{API}/databases/{DB_ID}/query", headers=HEADERS, timeout=15,
                   json={"filter": flt})
print(f"  Query HTTP {q.status_code}")
if not q.ok:
    try:
        msg = q.json().get("message", q.text)
    except ValueError:
        msg = q.text
    print(f"  ERROR: {msg}")
    sys.exit(1)

results = q.json().get("results", [])
if results:
    page_id = results[0]["id"]
    print(f"  Found existing page: {page_id}")
else:
    print("  No page for today – creating one…")
    properties = {title_col: {"title": _text(page_name)}}
    if date_col:
        properties[date_col] = {"date": {"start": today.isoformat()}}
    body = {
        "parent": {"database_id": DB_ID},
        "icon": {"type": "emoji", "emoji": "✨"},   # real emoji, not ✦
        "properties": properties,
        "children": [
            {"type": "heading_2", "heading_2": {"rich_text": _text(s)}}
            for s in ["To-do", "Brain dump", "Little reminders"]
        ],
    }
    cr = requests.post(f"{API}/pages", headers=HEADERS, json=body, timeout=15)
    print(f"  Create HTTP {cr.status_code}")
    if not cr.ok:
        try:
            msg = cr.json().get("message", cr.text)
        except ValueError:
            msg = cr.text
        print(f"  ERROR: {msg}")
        sys.exit(1)
    page_id = cr.json()["id"]
    print(f"  Created page: {page_id}")

# ── Step 3: read headings ───────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 3 – Read heading blocks")
r = requests.get(f"{API}/blocks/{page_id}/children", headers=HEADERS, timeout=15)
print(f"  HTTP {r.status_code}")
if not r.ok:
    try:
        msg = r.json().get("message", r.text)
    except ValueError:
        msg = r.text
    print(f"  ERROR: {msg}")
    sys.exit(1)

headings = {}
for b in r.json()["results"]:
    if b["type"] == "heading_2" and b["heading_2"]["rich_text"]:
        name = b["heading_2"]["rich_text"][0]["plain_text"]
        headings[name] = b["id"]
        print(f"    heading: {name!r} → {b['id']}")

for expected in ["To-do", "Brain dump", "Little reminders"]:
    if expected not in headings:
        print(f"  WARNING: heading {expected!r} not found on page")

# ── Step 4: try adding a test item ──────────────────────────────────
print("\n" + "=" * 60)
print("STEP 4 – Append a test to-do block after 'To-do' heading")
if "To-do" not in headings:
    print("  SKIP: 'To-do' heading not found")
else:
    after_id = headings["To-do"]
    block = {"type": "to_do", "to_do": {"rich_text": _text("[diagnose_notion.py test item]"), "checked": False}}
    r = requests.patch(
        f"{API}/blocks/{page_id}/children", headers=HEADERS, timeout=15,
        json={"children": [block], "after": after_id},
    )
    print(f"  HTTP {r.status_code}")
    if not r.ok:
        try:
            msg = r.json().get("message", r.text)
        except ValueError:
            msg = r.text
        print(f"  ERROR: {msg}")
    else:
        print("  SUCCESS – check today's Notion page for the test item!")

print("\n" + "=" * 60)
print("Diagnostic complete.")
