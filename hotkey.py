"""
hotkey.py - A global keyboard shortcut, working from anywhere on the
desktop (not just when the app has focus), that shows/hides the floating
companion. This is the "secret shortcut" way to bring it back after
hiding it, without needing the tray icon and without closing the app.

Design:
- pynput.keyboard.GlobalHotKeys runs its own background thread and does
  the actual system-level key listening.
- Its callback fires on that listener's own thread, never the Tk main
  thread - so it hands off to companion.toggle_companion() via
  ui.run_on_ui_thread(), the same safe pattern tray.py's callbacks use.
- The listener itself is returned so app.py can hold a reference (and,
  if ever needed, call .stop() on it) - letting it get garbage collected
  would silently stop the hotkey from working.
"""

from pynput import keyboard

import companion
import config
import ui


def _on_hotkey():
    ui.run_on_ui_thread(companion.toggle_companion)


def start_hotkey_listener():
    """Start listening for the configured hotkey combo in the background.
    Returns the listener - keep a reference to it for as long as the app
    runs, or the hotkey stops working once it's garbage collected."""
    listener = keyboard.GlobalHotKeys({config.COMPANION_HOTKEY: _on_hotkey})
    listener.start()
    return listener


if __name__ == "__main__":
    # Quick manual check: starts the companion and the hotkey listener
    # together. Try pressing the configured combo (default Ctrl+Alt+Z) -
    # the companion should hide, then pressing it again should bring it
    # back in the same spot.
    import database

    database.init_db()
    companion.show_companion()
    start_hotkey_listener()
    print(f"Listening for {config.COMPANION_HOTKEY} - try it now.")
    ui.run()