"""
database.py - All SQLite access for zeya_pa. Creates the tasks table and
provides simple functions to add, query, and update tasks. No other module
should open sqlite3 connections directly - everything goes through here.
"""

import sqlite3
from datetime import datetime

import config

DB_DIR = config.DATA_DIR
DB_PATH = config.DB_PATH


def get_connection():
    """Open a connection to the SQLite database, creating the data folder
    if needed. Callers are responsible for closing the connection."""
    DB_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the tasks table if it doesn't already exist. Safe to call
    every startup."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            original_text TEXT,
            task_type TEXT NOT NULL DEFAULT 'task',
            due_date TEXT,
            due_time TEXT,
            due_at TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            completed_at TEXT,
            snoozed_until TEXT,
            reminder_sent INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def _sync_to_notion(task_type, title):
    """Push a newly saved task to today's Notion Daily Drop page.

    Fully optional: does nothing if NOTION_ENABLED is off, and any failure
    (missing package, no internet, bad token) is swallowed so saving a task
    to SQLite never breaks. The import is lazy so the app still runs offline
    even if requests/python-dotenv aren't installed.
    """
    if not getattr(config, "NOTION_ENABLED", False):
        return
    try:
        import notion_sync  # pylint: disable=import-outside-toplevel
        # note -> Brain dump, reminder/deadline -> Little reminders, else To-do
        kind = {"note": "note", "reminder": "reminder", "deadline": "reminder"}.get(
            task_type, "task")
        notion_sync.push_async(kind, title[:1900])   # Notion caps text blocks at 2000 chars
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print("Notion sync skipped:", exc)


def add_task(title, original_text, task_type="task", due_date=None, due_time=None, due_at=None):
    """Insert a new task and return its new id.

    task_type is one of: 'task' (to-do), 'reminder', 'note' (brain dump).
    'deadline' is no longer a separate type - it is stored as a reminder."""
    if task_type == "deadline":
        task_type = "reminder"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks (title, original_text, task_type, due_date, due_time, due_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (title, original_text, task_type, due_date, due_time, due_at, datetime.now().isoformat()),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    # Runs only after the SQLite insert has succeeded.
    _sync_to_notion(task_type, title)

    return new_id


def get_all_tasks(status=None):
    """Return all tasks, optionally filtered by status ('pending' or 'completed')."""
    conn = get_connection()
    cursor = conn.cursor()
    if status:
        cursor.execute(
            "SELECT * FROM tasks WHERE status = ? ORDER BY due_at IS NULL, due_at ASC",
            (status,),
        )
    else:
        cursor.execute("SELECT * FROM tasks ORDER BY due_at IS NULL, due_at ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_due_tasks(now_iso):
    """Return pending tasks whose due_at has passed and haven't had a reminder sent yet."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM tasks
        WHERE status = 'pending'
          AND reminder_sent = 0
          AND due_at IS NOT NULL
          AND (
              (snoozed_until IS NOT NULL AND snoozed_until <= ?)
              OR (snoozed_until IS NULL AND due_at <= ?)
          )
    """, (now_iso, now_iso))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_reminder_sent(task_id):
    """Flag a task's reminder as sent so it isn't notified again."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET reminder_sent = 1 WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()


def snooze_task(task_id, snoozed_until_iso):
    """Reset reminder_sent and set a new snooze time so the scheduler picks it up again."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tasks SET snoozed_until = ?, reminder_sent = 0 WHERE id = ?
    """, (snoozed_until_iso, task_id))
    conn.commit()
    conn.close()


def complete_task(task_id):
    """Mark a task completed and stamp the completion time."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tasks SET status = 'completed', completed_at = ? WHERE id = ?
    """, (datetime.now().isoformat(), task_id))
    conn.commit()
    conn.close()


def delete_task(task_id):
    """Permanently remove a task."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized at:", DB_PATH)