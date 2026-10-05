"""
setup_startup.py - One-time setup script: registers (or unregisters) this
app to launch automatically when Windows starts, by dropping a small .bat
launcher into your Windows user's Startup folder.

Run once to turn it on:
    python setup_startup.py

Undo it:
    python setup_startup.py --remove

This only affects your own Windows user account (not all users), and only
ever touches a single file, here:
    %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup

It does not modify the Windows registry.
"""

import os
import sys
from pathlib import Path

import config

STARTUP_DIR = (
    Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
)
LAUNCHER_NAME = f"{config.APP_NAME}.bat"


def _find_python():
    """Prefer the project's venv pythonw.exe (runs with no console window).
    Falls back to the venv's python.exe, then to whatever Python is
    currently running this script, in that order."""
    venv_scripts = config.BASE_DIR / "venv" / "Scripts"

    pythonw = venv_scripts / "pythonw.exe"
    if pythonw.exists():
        return pythonw, True

    python_exe = venv_scripts / "python.exe"
    if python_exe.exists():
        return python_exe, False

    return Path(sys.executable), False


def register():
    """Write the startup launcher. Safe to run again later - it just
    overwrites the same file with the current paths."""
    STARTUP_DIR.mkdir(parents=True, exist_ok=True)
    python_path, is_silent = _find_python()
    app_path = config.BASE_DIR / "app.py"
    launcher_path = STARTUP_DIR / LAUNCHER_NAME

    bat_content = (
        "@echo off\r\n"
        f'cd /d "{config.BASE_DIR}"\r\n'
        f'start "" "{python_path}" "{app_path}"\r\n'
    )
    launcher_path.write_text(bat_content, encoding="utf-8")

    print(f"Registered for startup: {launcher_path}")
    print(f"Using: {python_path}")
    if not is_silent:
        print(
            "Note: pythonw.exe wasn't found in your venv, so a console "
            "window will briefly flash on startup. The app still works "
            "fine either way - this just affects whether you see a black "
            "window for a moment."
        )


def unregister():
    """Remove the startup launcher, if it exists."""
    launcher_path = STARTUP_DIR / LAUNCHER_NAME
    if launcher_path.exists():
        launcher_path.unlink()
        print(f"Removed: {launcher_path}")
    else:
        print("Nothing to remove - it wasn't registered.")


if __name__ == "__main__":
    if "--remove" in sys.argv:
        unregister()
    else:
        register()