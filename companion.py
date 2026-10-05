"""
companion.py - A small always-on-top character/GIF that sits at a fixed
position on the desktop itself (not hidden in the tray), separate from the
popup and the tray icon. Click it to open the quick-entry popup, or drag
it anywhere on screen - its position is remembered across restarts.

Design:
- A borderless window, positioned either at a remembered spot (see
  data/companion_position.json) or, the first time it ever runs, at a
  screen corner set by config.py.
- Displayed at a fixed HEIGHT (config.COMPANION_HEIGHT_PX); the width is
  computed from the image's own aspect ratio, so a full-body image shows
  as a proper standing figure instead of being squished into a square.
- Uses Windows' "-transparentcolor" window attribute so there's no visible
  background box behind the character - just the image floats on the
  desktop. This is a Windows-only Tkinter feature, which is fine since
  this app targets Windows only; on other platforms it's silently skipped
  (you'd see a solid magenta rectangle instead, but nothing breaks).
- Plain tkinter.Toplevel is used instead of CTkToplevel - CustomTkinter's
  theming layer interferes with the transparent-color trick.
- If the configured image is an animated GIF, frames are extracted with
  Pillow and cycled with root.after() - Tkinter has no built-in GIF
  animation support of its own.
- If no image file exists yet at the configured path, a simple placeholder
  circle is drawn instead (same fallback pattern used in tray.py), so the
  companion is always visible even before you've picked a real character.
- A press-and-release with no real movement counts as a click (opens the
  popup); a press-and-release with movement counts as a drag (repositions
  it and saves the new spot) - DRAG_THRESHOLD_PX is the cutoff between
  the two, so a slightly shaky click doesn't get misread as a drag.
"""

import json
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

import config
import ui

_TRANSPARENT_KEY = "#ff00ff"  # an unlikely-to-occur magenta used as the
                              # "make this color invisible" key color

DRAG_THRESHOLD_PX = 4
POSITION_FILE = config.DATA_DIR / "companion_position.json"

_companion = {"window": None}


def show_companion():
    """Create the floating companion if it doesn't already exist. Safe to
    call more than once - later calls are a no-op."""
    if _companion["window"] is not None:
        return
    root = ui.get_root()
    _companion["window"] = CompanionWindow(root)


def toggle_companion():
    """Show/hide the companion. If it doesn't exist yet (e.g.
    COMPANION_ALWAYS_VISIBLE was False at startup), this creates it
    instead - so the hotkey always does something sensible either way."""
    window = _companion["window"]
    if window is None:
        show_companion()
        return
    window.toggle_visibility()


def _load_saved_position():
    """Return a saved (x, y) from a previous drag, or None if there isn't
    one yet / it can't be read."""
    if not POSITION_FILE.exists():
        return None
    try:
        data = json.loads(POSITION_FILE.read_text(encoding="utf-8"))
        return int(data["x"]), int(data["y"])
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def _save_position(x, y):
    """Persist the companion's current position so it reopens in the same
    spot next time. Failure here is non-fatal - the companion just falls
    back to the default corner on the next launch."""
    try:
        config.DATA_DIR.mkdir(exist_ok=True)
        POSITION_FILE.write_text(json.dumps({"x": x, "y": y}), encoding="utf-8")
    except OSError:
        pass


def _load_frames():
    """Return (frames, width, height). frames is a list of
    (PhotoImage, duration_ms) tuples. A static image, a missing file, or
    an unreadable file all come back as one frame. width/height are the
    actual on-screen size to use - computed from the image's own aspect
    ratio and the configured target height, so nothing gets squished."""
    path = config.COMPANION_IMAGE_PATH
    target_h = config.COMPANION_HEIGHT_PX

    if not path.exists():
        return [(_placeholder_frame(target_h), 1000)], target_h, target_h

    try:
        img = Image.open(path)
    except OSError:
        return [(_placeholder_frame(target_h), 1000)], target_h, target_h

    orig_w, orig_h = img.size
    target_w = max(1, round(orig_w * target_h / orig_h))

    frames = []
    frame_count = getattr(img, "n_frames", 1)
    for frame_index in range(frame_count):
        img.seek(frame_index)
        frame = img.convert("RGBA").resize((target_w, target_h))
        duration = img.info.get("duration", 100)
        frames.append((ImageTk.PhotoImage(frame), duration))

    if not frames:
        return [(_placeholder_frame(target_h), 1000)], target_h, target_h

    return frames, target_w, target_h


def _placeholder_frame(size):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, size - 4, size - 4), fill=(90, 140, 255, 255))
    return ImageTk.PhotoImage(image)


class CompanionWindow:
    """The floating, borderless, always-on-top, draggable character window."""

    def __init__(self, root):
        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg=_TRANSPARENT_KEY)
        try:
            self.window.attributes("-transparentcolor", _TRANSPARENT_KEY)
        except tk.TclError:
            pass  # -transparentcolor is Windows-only; harmless elsewhere
        try:
            # Windows-only: keeps this floating window out of the taskbar
            # and Alt+Tab list, since overrideredirect alone doesn't
            # guarantee that on every Windows version.
            self.window.attributes("-toolwindow", True)
        except tk.TclError:
            pass

        self._frames, self._width, self._height = _load_frames()
        self._frame_index = 0
        self._press_screen_pos = (0, 0)
        self._press_win_pos = (0, 0)
        self._dragged = False
        self._visible = True

        self.label = tk.Label(self.window, bg=_TRANSPARENT_KEY, bd=0, highlightthickness=0)
        self.label.pack()
        self.label.bind("<ButtonPress-1>", self._on_press)
        self.label.bind("<B1-Motion>", self._on_drag)
        self.label.bind("<ButtonRelease-1>", self._on_release)

        self._position_window()
        self._animate()

    def _position_window(self):
        width, height = self._width, self._height
        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()

        saved = _load_saved_position()
        if saved is not None:
            x, y = saved
            # Clamp in case the screen resolution changed since it was saved.
            x = max(0, min(x, screen_w - width))
            y = max(0, min(y, screen_h - height))
        else:
            x, y = self._default_corner_position(screen_w, screen_h, width, height)

        self.window.geometry(f"{width}x{height}+{x}+{y}")

    @staticmethod
    def _default_corner_position(screen_w, screen_h, width, height):
        margin = config.COMPANION_MARGIN_PX
        position = config.COMPANION_POSITION

        # 48px extra bottom clearance so it doesn't sit under the taskbar.
        if position == "bottom-right":
            return screen_w - width - margin, screen_h - height - margin - 48
        if position == "bottom-left":
            return margin, screen_h - height - margin - 48
        if position == "top-right":
            return screen_w - width - margin, margin
        return margin, margin  # "top-left" or any unrecognized value

    def _animate(self):
        frame, duration = self._frames[self._frame_index]
        self.label.configure(image=frame)
        self.label.image = frame  # keep a reference - Tkinter drops it otherwise
        self._frame_index = (self._frame_index + 1) % len(self._frames)
        self.window.after(duration, self._animate)

    def _on_press(self, event):
        self._press_screen_pos = (event.x_root, event.y_root)
        self._press_win_pos = (self.window.winfo_x(), self.window.winfo_y())
        self._dragged = False

    def _on_drag(self, event):
        dx = event.x_root - self._press_screen_pos[0]
        dy = event.y_root - self._press_screen_pos[1]
        if not self._dragged and abs(dx) + abs(dy) > DRAG_THRESHOLD_PX:
            self._dragged = True
        if self._dragged:
            new_x = self._press_win_pos[0] + dx
            new_y = self._press_win_pos[1] + dy
            self.window.geometry(f"+{new_x}+{new_y}")

    def _on_release(self, _event):
        if self._dragged:
            _save_position(self.window.winfo_x(), self.window.winfo_y())
        else:
            ui.open_popup()

    def toggle_visibility(self):
        """Hide the companion (withdraw, no window destruction - the app,
        tray, and scheduler all keep running) or bring it back exactly
        where it was. Called from the global hotkey."""
        if self._visible:
            self.window.withdraw()
        else:
            self.window.deiconify()
            self.window.attributes("-topmost", True)  # re-assert after deiconify
        self._visible = not self._visible


if __name__ == "__main__":
    # Quick manual check: shows just the companion, without the tray or
    # scheduler running. Click it - the popup should open. Drag it - it
    # should move smoothly and stay put on the next run.
    show_companion()
    ui.run()