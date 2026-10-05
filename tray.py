"""
tray.py - System tray icon and menu, using pystray.

Design:
- The tray icon is what keeps the app "present" after you close the popup -
  closing the popup should never fully quit the app, only Exit should.
- Menu items call back into other modules (ui.py to open the popup,
  scheduler.py's pause/resume, etc.) via callback functions passed in from
  app.py, so tray.py doesn't need to import ui.py directly and create a
  circular import.
- pystray runs its own loop; on Windows, icon.run() blocks the thread it's
  called from, so app.py should run this on its own thread while the
  scheduler runs on another and the UI runs on the main thread (Tkinter
  needs the main thread).
"""

import time

import pystray
from PIL import Image, ImageDraw

import config

# pystray's Windows backend can fire the default/left-click handler several
# times for a single physical click (a known quirk, confirmed during
# testing - 13 fires from what should've been 1 click). This debounce
# window swallows repeat fires that land within it. Kept in a dict (rather
# than reassigning a plain module-level variable) so the callback below can
# update it without needing a `global` statement.
_DEBOUNCE_SECONDS = 0.6
_debounce_state = {"last_open_time": 0.0}


def _load_icon_image():
    """Load assets/tray_icon.png if present, otherwise draw a simple
    placeholder circle so the tray icon always has something to show."""
    icon_path = config.TRAY_ICON_PATH
    if icon_path.exists():
        return Image.open(icon_path)

    # Placeholder: a simple colored circle, generated in memory. Replace
    # assets/tray_icon.png whenever you have a real icon - no code change
    # needed, this branch will stop being used automatically.
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, size - 4, size - 4), fill=(90, 140, 255, 255))
    return image


def build_tray_icon(on_open=None, on_pause_toggle=None, on_exit=None, is_paused=lambda: False):
    """
    Build (but do not yet run) the tray icon.

    on_open           - called when "Open Assistant" is clicked
    on_pause_toggle    - called when "Pause Reminders" is toggled
    on_exit           - called when "Exit" is clicked, before the icon stops
    is_paused         - callable returning current pause state, so the
                        checkbox reflects reality even if paused elsewhere
    """

    def _open(_icon, _item):
        now = time.monotonic()
        if now - _debounce_state["last_open_time"] < _DEBOUNCE_SECONDS:
            return  # swallow a rapid-fire repeat of the same click
        _debounce_state["last_open_time"] = now
        if on_open:
            on_open()

    def _toggle_pause(_icon, _item):
        if on_pause_toggle:
            on_pause_toggle()

    def _exit(icon, _item):
        if on_exit:
            on_exit()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Open Assistant", _open, default=True),
        pystray.MenuItem(
            "Pause Reminders",
            _toggle_pause,
            checked=lambda item: is_paused(),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", _exit),
    )

    icon = pystray.Icon(
        config.APP_NAME,
        icon=_load_icon_image(),
        title=config.APP_DISPLAY_NAME,
        menu=menu,
    )
    return icon


def run_tray(on_open=None, on_pause_toggle=None, on_exit=None, is_paused=lambda: False):
    """Build and run the tray icon. Blocks the calling thread - run this on
    a background thread from app.py, not the main thread."""
    icon = build_tray_icon(on_open, on_pause_toggle, on_exit, is_paused)
    icon.run()


def _manual_test():
    """Quick manual check: runs the tray icon standalone with print-based
    callbacks, so you can confirm the icon appears and the menu works
    before wiring it into app.py."""
    paused = {"value": False}

    def _on_open():
        print("[tray] Open Assistant clicked")

    def _on_pause_toggle():
        paused["value"] = not paused["value"]
        print(f"[tray] Pause Reminders toggled -> {paused['value']}")

    def _on_exit():
        print("[tray] Exit clicked - shutting down")

    print("Tray icon starting - check the system tray (or its hidden-icons overflow).")
    run_tray(
        on_open=_on_open,
        on_pause_toggle=_on_pause_toggle,
        on_exit=_on_exit,
        is_paused=lambda: paused["value"],
    )


if __name__ == "__main__":
    _manual_test()