"""
notifications.py - Shows a Windows toast notification for a due task, with
Done / Snooze actions wired back into the database.

win11toast is Windows-only (it wraps the WinRT toast APIs), so this module
can only be tested on Windows itself, not in a general Python sandbox.
"""

import time
from datetime import datetime, timedelta

from win11toast import toast

import config
import database

SNOOZE_OPTIONS = config.SNOOZE_OPTIONS

_TYPE_ICONS = {
    "task": "\U0001F4DD",       # memo
    "reminder": "\U0001F514",   # bell
    "deadline": "\u23F0",       # alarm clock
}


def _due_line(task):
    date = task.get("due_date")
    time_ = task.get("due_time")
    if date and time_:
        return f"Due {date} · {time_}"
    if date:
        return f"Due {date}"
    return "Due now"


def show_reminder(task):
    """Display a toast for a single due task. Called by scheduler.py."""
    task_id = task["id"]
    icon = _TYPE_ICONS.get(task.get("task_type", "task"), "\U0001F4DD")
    title = f"{icon} {task['title']}"
    body = _due_line(task)

    toast(
        title,
        body,
        buttons=["Done"] + list(SNOOZE_OPTIONS.keys()),
        on_click=lambda result: _handle_action(result, task_id),
        duration=config.TOAST_DURATION,
    )


def _handle_action(result, task_id):
    """Callback fired when the user clicks a toast button (or the toast
    body itself). result may be a plain string or a dict, depending on
    what was clicked, so both are handled."""
    action = result.get("arguments") if isinstance(result, dict) else result

    # win11toast prefixes button values with "http:" (e.g. "http:Done") -
    # confirmed by testing, not documented anywhere obvious. Strip it.
    if isinstance(action, str) and action.startswith("http:"):
        action = action[len("http:"):]

    if action == "Done":
        database.complete_task(task_id)
        return

    if action in SNOOZE_OPTIONS:
        minutes = SNOOZE_OPTIONS[action]
        new_time = (datetime.now() + timedelta(minutes=minutes)).isoformat(timespec="seconds")
        database.snooze_task(task_id, new_time)
        return

    # Toast dismissed or body clicked with no button: leave the task as is.
    # reminder_sent is already 1 by this point, so it won't re-fire on its
    # own - the user can still snooze/complete it from the task list later.


def _manual_test():
    """Quick manual check (Windows only): fires one real toast so you can
    click a button and confirm the database updates correctly."""
    database.init_db()
    now = datetime.now().replace(microsecond=0)
    test_task_id = database.add_task(
        title="Notification test task",
        original_text="Notification test task",
        task_type="reminder",
        due_date=now.date().isoformat(),
        due_time=now.strftime("%H:%M"),
        due_at=now.isoformat(),
    )
    print(f"Added test task id={test_task_id}. A toast should appear now - click a button.")
    show_reminder(database.get_all_tasks(status="pending")[-1])

    time.sleep(15)  # give yourself time to click before the script exits
    tasks = database.get_all_tasks()
    print("Task state after your click:", [t for t in tasks if t["id"] == test_task_id])


if __name__ == "__main__":
    _manual_test()