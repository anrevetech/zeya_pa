"""
app.py - Entry point. Starts everything and wires it together.

Threading model (important - read before changing this file):
- Tkinter's event loop MUST run on the main thread. ui.run() blocks here.
- pystray's tray icon runs its own blocking loop (icon.run()), so it gets
  its own background thread.
- APScheduler's BackgroundScheduler already manages its own internal
  thread once started - nothing extra needed for it here.
- The tray's callbacks fire on the tray's thread, NOT the main thread, so
  they must never touch Tkinter widgets directly. That's why on_open uses
  ui.open_popup_threadsafe() instead of ui.open_popup() - it schedules the
  real call onto the Tk thread via root.after() instead of running it
  immediately on the wrong thread.
"""

import threading

import companion
import config
import database
import hotkey
import scheduler
import tray
import ui


def main():
    """Start the database, scheduler, tray icon, and UI event loop."""
    database.init_db()

    sched = scheduler.start_scheduler()
    paused = {"value": False}

    def on_open():
        ui.open_popup_threadsafe()

    def on_pause_toggle():
        paused["value"] = not paused["value"]
        if paused["value"]:
            sched.pause()
        else:
            sched.resume()

    def on_exit():
        sched.shutdown(wait=False)
        ui.quit_threadsafe()

    tray_thread = threading.Thread(
        target=tray.run_tray,
        kwargs=dict(
            on_open=on_open,
            on_pause_toggle=on_pause_toggle,
            on_exit=on_exit,
            is_paused=lambda: paused["value"],
        ),
        daemon=True,  # dies automatically if the main process exits
    )
    tray_thread.start()

    # Whether the popup opens on launch is controlled from config.py -
    # set OPEN_POPUP_ON_STARTUP = False there for a fully silent startup.
    if config.OPEN_POPUP_ON_STARTUP:
        ui.open_popup()

    # The floating desktop character - controlled separately from the
    # popup, since you may want the character always visible even when
    # the popup itself starts closed.
    if config.COMPANION_ALWAYS_VISIBLE:
        companion.show_companion()
    # Global hotkey to show/hide the companion from anywhere - see
    # config.COMPANION_HOTKEY for the combo. The reference must be kept
    # (not just started and discarded) or Python garbage-collects the
    # listener and the hotkey silently stops working.
    hotkey_listener = hotkey.start_hotkey_listener()  # pylint: disable=unused-variable
    ui.run()  # blocks here until Exit is clicked (or the window is closed)


if __name__ == "__main__":
    main()