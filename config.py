"""
config.py - Centralized app settings: paths, theme, scheduler timing,
window sizes, and snooze options.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# App identity
# ---------------------------------------------------------------------------

APP_NAME = "zeya_pa"
APP_DISPLAY_NAME = "Zeya - Personal Assistant"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "assistant.db"
ASSETS_DIR = BASE_DIR / "assets"
TRAY_ICON_PATH = ASSETS_DIR / "tray_icon.png"

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

APPEARANCE_MODE = "dark"          # "dark" or "light" - passed to customtkinter
COLOR_THEME = "blue"              # customtkinter's built-in color themes

# ---------------------------------------------------------------------------
# Scheduler / reminders
# ---------------------------------------------------------------------------

CHECK_INTERVAL_SECONDS = 30       # how often the scheduler polls for due tasks

SNOOZE_OPTIONS = {
    "Snooze 10m": 10,
    "Snooze 30m": 30,
    "Snooze 1h": 60,
}

TOAST_DURATION = "long"           # win11toast duration: "short" or "long"

# ---------------------------------------------------------------------------
# Window sizes
# ---------------------------------------------------------------------------

POPUP_SIZE = "380x280"            # the quick-entry popup (EntryPopup)
TASK_LIST_SIZE = "360x420"        # the task list window (TaskListWindow)

# ---------------------------------------------------------------------------
# Desktop companion (the floating character that lives on the screen)
# ---------------------------------------------------------------------------
# Global keyboard shortcut to show/hide the floating companion from
# anywhere on your desktop - your "secret" way to bring it back after
# hiding it, without fully closing the app. Format follows pynput's
# GlobalHotKeys syntax: modifiers in angle brackets, joined with "+".
# Change this to whatever combo you want as your personal shortcut.
COMPANION_HOTKEY = "<ctrl>+<alt>+z"
# Put your own GIF or PNG here later - if this file doesn't exist yet, a
# simple placeholder circle is drawn instead so the companion still shows.
COMPANION_IMAGE_PATH = ASSETS_DIR / "assistant_idle.png"

# The companion is displayed at this height; its width is computed
# automatically from the image's own aspect ratio, so a full-body image
# displays as a proper standing figure instead of being squished into a
# square. Only the fallback placeholder circle (used when no image exists
# yet) is actually square, at this same size.
COMPANION_HEIGHT_PX = 400
COMPANION_MARGIN_PX = 16        # gap from the screen edge
COMPANION_POSITION = "bottom-right"  # "bottom-right" | "bottom-left" | "top-right" | "top-left"
COMPANION_ALWAYS_VISIBLE = True   # False = only the tray icon, no floating character
# ---------------------------------------------------------------------------
# Startup behavior
# ---------------------------------------------------------------------------

OPEN_POPUP_ON_STARTUP = False

# Windows "start with Windows" registration is not implemented yet - this
# flag is a placeholder for when that feature is built (likely via a
# shortcut in shell:startup, or a registry Run key).
START_WITH_WINDOWS = False
NOTION_ENABLED = True