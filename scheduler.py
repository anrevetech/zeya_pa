"""
scheduler.py - Background polling loop that checks for due tasks and
triggers notifications.

Design:
- APScheduler's BackgroundScheduler runs check_due_tasks() every
  CHECK_INTERVAL_SECONDS on a background thread, so it never blocks the
  UI popup or the system tray.
- This file only decides WHEN a reminder should fire. Actually showing the
  Windows toast (and wiring up Done/Snooze) lives in notifications.py.
- database.get_due_tasks() already accounts for snoozed_until, so snoozed
  tasks are picked back up automatically once their new time arrives.
"""

from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

import database
import config

# Imported at module level (not inside the function) so static analysis
# tools like Pylance can see notifications.show_reminder properly. Falls
# back gracefully if notifications.py is missing or fails to import - e.g.
# on a non-Windows machine, where win11toast can't be installed.
try:
    import notifications
    _HAS_NOTIFICATIONS = True
except ImportError:
    _HAS_NOTIFICATIONS = False

CHECK_INTERVAL_SECONDS = config.CHECK_INTERVAL_SECONDS


def check_due_tasks():
    """Find pending tasks whose due time has arrived and notify for each."""
    now_iso = datetime.now().isoformat(timespec="seconds")
    due_tasks = database.get_due_tasks(now_iso)

    for task in due_tasks:
        # Always mark reminder_sent, even if the notification itself fails -
        # otherwise a crash mid-notification leaves the task stuck, and it
        # piles up with the next task and fires twice/thrice at once.
        try:
            _trigger_notification(task)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Intentionally broad: a notification failure (e.g. win11toast
            # erroring) must never leave a task permanently stuck as
            # unsent - see the finally block below.
            print(f"[scheduler] notification failed for task {task['id']}: {e}")
        finally:
            database.mark_reminder_sent(task["id"])


def _trigger_notification(task):
    """Show the real notification if available, otherwise print a
    stand-in line (used on machines/platforms without win11toast)."""
    if _HAS_NOTIFICATIONS:
        notifications.show_reminder(task)
    else:
        print(f"[scheduler] Would notify: {task['title']} (due {task.get('due_at')})")


def start_scheduler():
    """Create, start, and return a BackgroundScheduler already polling for due tasks."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        check_due_tasks,
        "interval",
        seconds=CHECK_INTERVAL_SECONDS,
        id="check_due_tasks",
    )
    scheduler.start()
    return scheduler


if __name__ == "__main__":
    # Quick manual check: adds one task due right now, runs a check
    # immediately (not waiting for the first interval to elapse), and
    # gives you real time to click a toast button.
    database.init_db()
    now = datetime.now().replace(microsecond=0)
    task_id = database.add_task(
        title="Scheduler test task",
        original_text="Scheduler test task",
        task_type="task",
        due_date=now.date().isoformat(),
        due_time=now.strftime("%H:%M"),
        due_at=now.isoformat(),
    )
    print(f"Added test task id={task_id}, due now.")
    print("A toast should appear now - click Done or a Snooze button quickly.")
    print("(This call blocks until you click or it times out, ~20-25s.)")

    check_due_tasks()

    tasks = database.get_all_tasks()
    print("Task state:", [t for t in tasks if t["id"] == task_id])