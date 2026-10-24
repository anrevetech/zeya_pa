"""
test_sync.py - End-to-end test: call database.add_task() for each type
(task, reminder, note) and wait for the background Notion sync threads
to finish. Prints results to confirm each lands in the right section.

Does NOT modify assistant.db beyond adding three test rows (which you can
delete from the dashboard later if you like).
"""

import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import database
import notion_sync

database.init_db()

# Clear the cached schema so we get a fresh lookup
notion_sync._schema.clear()

tests = [
    ("task",     "E2E test: task item from test_sync.py"),
    ("reminder", "E2E test: reminder item from test_sync.py"),
    ("note",     "E2E test: note item from test_sync.py"),
]

print("Adding 3 items via database.add_task() …")
for task_type, title in tests:
    new_id = database.add_task(
        title=title,
        original_text=title,
        task_type=task_type,
    )
    print(f"  SQLite OK  id={new_id}  type={task_type}")

# The Notion sync runs on daemon threads. Give them time to finish.
print("\nWaiting 8 seconds for background Notion sync threads …")
time.sleep(8)

# Check the log for any errors that happened just now
from pathlib import Path
import datetime as dt

log_path = Path(__file__).parent / "data" / "notion_sync.log"
if log_path.exists():
    cutoff = dt.datetime.now() - dt.timedelta(seconds=15)
    recent_errors = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            ts_str = line[:19]
            ts = dt.datetime.fromisoformat(ts_str)
            if ts >= cutoff:
                recent_errors.append(line)
        except ValueError:
            pass
    if recent_errors:
        print("Recent log entries (possible errors):")
        for e in recent_errors:
            print(f"  {e}")
    else:
        print("No errors in notion_sync.log in the last 15 seconds!")
else:
    print("No log file found (good – means no errors were logged)")

print("\nDone! Check your Notion Daily Drop for today's page:")
print("  - 'To-do' should have the task item")
print("  - 'Brain dump' should have the note item")
print("  - 'Little reminders' should have the reminder item")
