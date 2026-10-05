"""
ui.py - Zeya's windows, in a brown vintage-cafe style.

* NotepadPopup    - ONE popup for everything. Just write: Zeya reads your words
                    and files it under To-do list, Brain dump or Reminders.
                    The three bookmark tabs light up to show where it will go;
                    click a tab to pin it there, or click "Auto" to let Zeya decide.
* DashboardWindow - sidebar of everything saved + a board of cards + the husky
                    that runs along the bottom, pops speech bubbles and gives
                    compliment stickers when clicked.

How Zeya decides (see decide()):
  1. Brain dump  - starts with idea:/dump:/note:/thought:, starts like a thought
                   ("maybe", "what if", "I think"...), is a question, spans
                   several lines, or is long.
  2. Reminders   - a date/time is found ("tomorrow 6pm", "by Friday") or you
                   say "remind me".
  3. To-do list  - work words (assignment, do, work, lab, submit, buy...) or
                   a short text.
  4. Anything else that is longer and has no task words -> Brain dump.

Threading rules from before still apply: Tkinter lives on the main thread, other
threads (tray, hotkey) must go through the *_threadsafe helpers.
"""

import math
import random
import re
import time
import tkinter as tk
from datetime import datetime

import customtkinter as ctk
from PIL import Image, ImageOps, ImageTk

import database
import task_parser
import config

ctk.set_appearance_mode(config.APPEARANCE_MODE)
ctk.set_default_color_theme(config.COLOR_THEME)

# ---------------------------------------------------------------------------
# Look & feel - brown vintage cafe
# ---------------------------------------------------------------------------

ESPRESSO = "#3B2519"       # window background (the cafe table)
LEATHER = "#5A3825"        # notepad cover
LEATHER_EDGE = "#2A1810"
THREAD = "#D2A96E"         # stitching
BRASS = "#C9A24B"          # spiral rings
PAPER = "#F4E6C8"          # aged cream paper
PAPER_CARD = "#FBF1DA"     # lighter writing area / cards
PAPER_EDGE = "#D6BE92"
INK = "#3A2A20"            # sepia ink
MUTED = "#8C7358"
CREAM = "#F4E6C8"          # light text on dark brown
TAN = "#B89B76"
ACCENT = "#9C5B34"         # caramel / rust
ACCENT_HOVER = "#834A28"
SAGE = "#5E7F4A"

TAB_ON = {"todo": "#E2B777", "note": "#D99A87", "reminder": "#A9C294"}
TAB_OFF = {"todo": "#F1DDB7", "note": "#EBCFC4", "reminder": "#DCE6CF"}
TAB_LABEL = {"todo": "To-do list", "note": "Brain dump", "reminder": "Reminders"}
WHERE = {"todo": "your to-do list", "note": "your brain dump", "reminder": "your reminders"}
LOOKS_LIKE = {"todo": "a to-do", "note": "a brain dump", "reminder": "a reminder"}

FONT_SERIF = "Georgia"
FONT_HAND = "Ink Free"      # handwriting font on Windows 10/11; falls back if missing

SCROLL_STYLE = dict(scrollbar_button_color="#7A5236", scrollbar_button_hover_color="#9C6B46",
                    scrollbar_fg_color="transparent")

SKIP_DIRS = {"venv", ".venv", "__pycache__", ".git", "data", "node_modules"}

COMPLIMENTS = [
    "You're doing great!", "Believe in yourself", "You can do it!",
    "You are so loved", "Rest too.. you're doing enough", "Keep going! You got this",
    "Smart. Kind. Capable. Enough.", "Big dreams, little steps",
    "Cool mind, kind heart, big goals", "You're amazing just the way you are",
    "Progress over perfection", "I'm proud of you!", "You got this, cutie!",
    "Sweet dreams, warrior", "Keep shining", "You are special",
]

_state = {"root": None, "popup": None, "dashboard": None}


def _font(size, weight="normal", family=FONT_SERIF, **kwargs):
    """CTkFont helper. Pass weight="italic" for italics (CTkFont wants that
    as a separate 'slant' option, so it is translated here)."""
    if weight == "italic":
        kwargs["slant"] = "italic"
        weight = "normal"
    return ctk.CTkFont(family=family, size=size, weight=weight, **kwargs)


def _scale_of(widget):
    """Real screen scaling (1.0 = 96 dpi). Plain Tk canvases don't scale
    themselves the way CustomTkinter widgets do, so we do it by hand."""
    try:
        return max(1.0, widget.winfo_fpixels("1i") / 96.0)
    except tk.TclError:
        return 1.0


def _pretty_date(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%a %d %b")
    except (TypeError, ValueError):
        return iso or ""


def _round_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kwargs)


# ---------------------------------------------------------------------------
# Root window / thread helpers
# ---------------------------------------------------------------------------

def _set_dpi_awareness():
    """On Windows, tell the OS this app handles its own display scaling so
    window coordinates are right on 125%/150% displays."""
    try:
        import ctypes  # pylint: disable=import-outside-toplevel
    except ImportError:
        return
    if not hasattr(ctypes, "windll"):
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _ensure_root():
    """Create the single hidden root window that owns the Tk event loop."""
    if _state["root"] is None:
        _set_dpi_awareness()
        root = ctk.CTk()
        root.withdraw()
        _state["root"] = root
    return _state["root"]


def get_root():
    """Shared hidden root - other modules (companion.py) attach to this."""
    return _ensure_root()


def run_on_ui_thread(func):
    """Schedule func on the Tk thread. Safe to call from any thread."""
    _ensure_root().after(0, func)


def open_popup():
    """Show the notepad, reusing it if it's already open."""
    root = _ensure_root()
    popup = _state["popup"]
    if popup is not None and popup.winfo_exists() and not popup.closing:
        popup.deiconify()
        popup.lift()
        popup.focus_force()
        return
    _state["popup"] = NotepadPopup(root)


def open_dashboard():
    """Show the dashboard, reusing it if it's already open."""
    root = _ensure_root()
    dash = _state["dashboard"]
    if dash is not None and dash.winfo_exists():
        dash.deiconify()
        dash.lift()
        dash.focus_force()
        dash.refresh()
        return
    _state["dashboard"] = DashboardWindow(root)


def open_task_list():
    """Old name, kept so nothing that still calls it breaks."""
    open_dashboard()


def open_popup_threadsafe():
    _ensure_root().after(0, open_popup)


def open_dashboard_threadsafe():
    _ensure_root().after(0, open_dashboard)


def quit_threadsafe():
    _ensure_root().after(0, _ensure_root().quit)


def run():
    """Start the Tk event loop. Call exactly once, from app.py."""
    _ensure_root().mainloop()


def _notify_dashboard(dest):
    dash = _state["dashboard"]
    if dash is not None and dash.winfo_exists():
        dash.on_item_added(dest)


# ---------------------------------------------------------------------------
# Deciding where a piece of text belongs
# ---------------------------------------------------------------------------

_WORD = re.compile(r"[a-z']+")

# Words that make something a to-do. Add your own here any time.
TASK_WORDS = {
    "assignment", "assignments", "homework", "hw", "lab", "record", "observation",
    "project", "report", "submit", "submission", "finish", "complete", "do", "work",
    "study", "revise", "revision", "practice", "prepare", "prep", "write", "read",
    "solve", "upload", "send", "email", "mail", "call", "buy", "get", "pick", "bring",
    "pay", "book", "order", "clean", "wash", "fix", "install", "update", "review",
    "attend", "meet", "meeting", "class", "exam", "quiz", "task", "todo", "cook",
    "pack", "charge", "print", "download", "register", "apply", "plan", "schedule",
    "organise", "organize", "return", "collect", "make", "build", "code", "push",
    "commit", "debug", "deploy", "learn", "finish", "revise", "visit", "ask", "check",
}

NOTE_PREFIXES = ("idea:", "dump:", "note:", "thought:")
THOUGHT_STARTS = (
    "idea", "thought", "note to self", "what if", "maybe", "i think", "i feel", "i wonder",
    "random", "remember that", "dream", "quote", "i wish", "why ", "how ", "what ",
    "should i", "i want to learn", "i'm ", "i am ", "feeling",
)
LONG_TEXT_WORDS = 25
SHORT_TEXT_WORDS = 3


def _safe_parse(text):
    try:
        return task_parser.parse_input(text)
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def decide(text):
    """Work out where text belongs. Returns (dest, text_to_save, parsed)
    where dest is 'todo', 'note' or 'reminder'."""
    cleaned = text.strip()
    low = cleaned.lower()
    words = _WORD.findall(low)

    # 1. Brain dump: explicit prefix, thought-like start, question, multi-line, long
    if (low.startswith(NOTE_PREFIXES) or low.startswith(THOUGHT_STARTS)
            or cleaned.endswith("?") or "\n" in cleaned or len(words) > LONG_TEXT_WORDS):
        if low.startswith("dump:"):
            cleaned = cleaned[5:].strip() or cleaned
        return "note", cleaned, None

    # 2. Reminder: a date/time was found, or "remind me" style wording
    parsed = _safe_parse(cleaned)
    if parsed and (parsed.get("date_detected")
                   or parsed.get("task_type") in ("reminder", "deadline")):
        return "reminder", cleaned, parsed
    if "remind" in words or "reminder" in words:
        return "reminder", cleaned, parsed

    # 3. To-do: work words, or something short
    if any(w in TASK_WORDS for w in words) or len(words) <= SHORT_TEXT_WORDS:
        return "todo", cleaned, parsed

    # 4. Longer text with no task words is more of a thought
    return "note", cleaned, None


def save_entry(text, force=None):
    """Save text. `force` ('todo'/'note'/'reminder') overrides Zeya's guess.
    Returns (dest, detail_text)."""
    dest, body, parsed = decide(text)
    if force and force != dest:
        dest = force
        if dest == "note":
            body, parsed = text.strip(), None
        elif parsed is None:
            body, parsed = text.strip(), _safe_parse(text.strip())
    parsed = parsed or {}

    if dest == "note":
        database.add_task(title=body, original_text=text.strip(), task_type="note")
        return "note", ""

    database.add_task(
        title=parsed.get("title") or body,
        original_text=parsed.get("original_text") or text.strip(),
        task_type="reminder" if dest == "reminder" else "task",
        due_date=parsed.get("due_date"),
        due_time=parsed.get("due_time"),
        due_at=parsed.get("due_at"),
    )
    detail = ""
    if dest == "reminder" and parsed.get("due_date"):
        detail = _pretty_date(parsed["due_date"])
        if parsed.get("due_time"):
            detail += f" \u00b7 {parsed['due_time']}"
    return dest, detail


def dest_of(task):
    """Which board column a stored task belongs to."""
    kind = task["task_type"]
    if kind == "note":
        return "note"
    if kind in ("reminder", "deadline"):   # old 'deadline' rows count as reminders
        return "reminder"
    return "todo"


# ---------------------------------------------------------------------------
# The notepad
# ---------------------------------------------------------------------------

DEFAULT_HINT = "Just write - I'll file it under To-do, Brain dump or Reminders."


class NotepadPopup(ctk.CTkToplevel):
    """One popup for everything. Leather cover, brass spiral, cream paper,
    handwriting. Slides up + fades in. Widgets are placed with relative
    coordinates so the layout holds at any screen scaling."""

    WIDTH, HEIGHT = 470, 500

    def __init__(self, master):
        super().__init__(master)
        self.attributes("-alpha", 0.0)          # invisible until positioned
        self.title("Zeya \u2726")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.configure(fg_color=ESPRESSO)

        self.closing = False
        self._pinned = None        # None = auto; or "todo"/"note"/"reminder"
        self._dest = "todo"
        self._live_job = None
        self._status_job = None
        self._hint_text = DEFAULT_HINT
        self._status_text = ""
        self._s = _scale_of(self)

        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self._build()
        self.bind("<Escape>", lambda _e: self.discard())
        self._animate_in()

    # ---- building ---------------------------------------------------

    def _build(self):
        self.bg = tk.Canvas(self, bg=ESPRESSO, highlightthickness=0, bd=0)
        self.bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg.bind("<Configure>", self._paint)

        self.tab_buttons = {}
        for key, relx in (("todo", 0.12), ("note", 0.335), ("reminder", 0.55)):
            btn = ctk.CTkButton(
                self, text=TAB_LABEL[key], width=96, height=30, corner_radius=8,
                bg_color=PAPER, font=_font(12, "bold"), text_color=INK,
                border_width=0, border_color=INK,
                command=lambda k=key: self._on_tab(k),
            )
            btn.place(relx=relx, rely=0.125)
            self.tab_buttons[key] = btn

        self.auto_button = ctk.CTkButton(
            self, text="\u2726 Auto", width=62, height=30, corner_radius=8, bg_color=PAPER,
            font=_font(12, "bold"), text_color=CREAM, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._on_auto,
        )
        self.auto_button.place(relx=0.775, rely=0.125)

        self.text_input = ctk.CTkTextbox(
            self, fg_color=PAPER_CARD, bg_color=PAPER, text_color=INK,
            border_width=1, border_color=PAPER_EDGE, corner_radius=8,
            font=_font(17, family=FONT_HAND), wrap="word",
        )
        self.text_input.place(relx=0.12, rely=0.31, relwidth=0.80, relheight=0.39)
        self.text_input.bind("<Return>", self._on_enter_key)
        self.text_input.bind("<KeyRelease>", self._on_key_release)

        ctk.CTkButton(
            self, text="\U0001F5D1  Discard", width=100, height=34, bg_color=PAPER,
            fg_color="#EBCFC4", hover_color="#E0B8A9", text_color="#8E3B2E",
            font=_font(12, "bold"), command=self.discard,
        ).place(relx=0.12, rely=0.79)
        ctk.CTkButton(
            self, text="Dashboard", width=92, height=34, bg_color=PAPER,
            fg_color="#EAD6AE", hover_color="#DFC793", border_width=1,
            border_color="#C9AE7E", text_color=INK, font=_font(12), command=open_dashboard,
        ).place(relx=0.35, rely=0.79)
        ctk.CTkButton(
            self, text="Save", width=96, height=34, bg_color=PAPER,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=CREAM,
            font=_font(14, "bold"), command=self.save,
        ).place(relx=0.70, rely=0.79)

        self._refresh_tabs()

    def _paint(self, event):
        """Draw the cover, stitching, paper, rings, margin line and a coffee ring."""
        c, w, h, s = self.bg, event.width, event.height, self._s
        c.delete("all")

        _round_rect(c, 3 * s, 3 * s, w - 3 * s, h - 3 * s, 26 * s,
                    fill=LEATHER, outline=LEATHER_EDGE, width=2)
        _round_rect(c, 13 * s, 13 * s, w - 13 * s, h - 13 * s, 20 * s,
                    fill="", outline=THREAD, width=1, dash=(6, 4))

        px1, py1, px2, py2 = 0.05 * w, 0.085 * h, 0.95 * w, 0.955 * h
        _round_rect(c, px1 + 2 * s, py1 + 3 * s, px2 + 2 * s, py2 + 3 * s, 10 * s,
                    fill="#44281A", outline="")
        _round_rect(c, px1, py1, px2, py2, 10 * s, fill=PAPER, outline=PAPER_EDGE, width=1)

        # coffee-cup ring, half hidden under the writing card
        cx, cy, r = 0.83 * w, 0.745 * h, 0.055 * w
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#E6CFA4", width=max(3, int(5 * s)))
        c.create_oval(cx - r + 4 * s, cy - r + 4 * s, cx + r - 4 * s, cy + r - 4 * s,
                      outline="#DDC391", width=1)

        # brass spiral rings through punched holes
        count = 7
        for i in range(count):
            x = px1 + (i + 0.5) * (px2 - px1) / count
            c.create_oval(x - 5 * s, py1 + 6 * s, x + 5 * s, py1 + 15 * s,
                          fill=LEATHER_EDGE, outline="")
            c.create_oval(x - 6 * s, py1 - 17 * s, x + 6 * s, py1 + 13 * s,
                          outline=BRASS, width=max(2, int(3 * s)))

        # red margin line (double, like old school paper)
        for x in (0.098 * w, 0.106 * w):
            c.create_line(x, 0.215 * h, x, 0.93 * h, fill="#CE8F80", width=max(1, int(1.5 * s)))

        c.create_text(0.12 * w, 0.222 * h, anchor="w", text="Today's page",
                      font=(FONT_SERIF, 15, "bold italic"), fill=INK)
        c.create_text(0.92 * w, 0.222 * h, anchor="e",
                      text=datetime.now().strftime("%a, %d %b"),
                      font=(FONT_SERIF, 11, "italic"), fill=MUTED)
        c.create_text(0.12 * w, 0.272 * h, anchor="w", text=self._hint_text, tags="hint",
                      font=(FONT_SERIF, 10, "italic"), fill=MUTED, width=0.8 * w)
        c.create_text(0.12 * w, 0.728 * h, anchor="w", text=self._status_text, tags="status",
                      font=(FONT_SERIF, 11, "bold"), fill=SAGE, width=0.8 * w)

    # ---- tabs / deciding --------------------------------------------

    def _refresh_tabs(self):
        for key, btn in self.tab_buttons.items():
            pinned = self._pinned == key
            btn.configure(
                fg_color=TAB_ON[key] if key == self._dest else TAB_OFF[key],
                hover_color=TAB_ON[key], border_width=2 if pinned else 0)
        self.auto_button.configure(
            fg_color=ACCENT if self._pinned is None else "#EAD6AE",
            text_color=CREAM if self._pinned is None else INK)

    def _set_hint(self, text):
        self._hint_text = text
        self.bg.itemconfigure("hint", text=text)

    def _set_status(self, text):
        self._status_text = text
        self.bg.itemconfigure("status", text=text)

    def _on_tab(self, key):
        """Clicking a tab pins your entry there (click again to unpin)."""
        self._pinned = None if self._pinned == key else key
        if self._pinned:
            self._dest = key
            self._set_hint(f"Pinned to {TAB_LABEL[key]}. Tap \u2726 Auto to let me decide.")
        else:
            self._live_classify()
        self._refresh_tabs()
        self.text_input.focus_set()

    def _on_auto(self):
        self._pinned = None
        self._live_classify()
        self._refresh_tabs()
        self.text_input.focus_set()

    def _on_key_release(self, _event):
        if self._pinned is not None:
            return
        if self._live_job is not None:
            self.after_cancel(self._live_job)
        self._live_job = self.after(350, self._live_classify)

    def _live_classify(self):
        """Light up the tab the text will land in, while you write."""
        self._live_job = None
        if self._pinned is not None or not self.winfo_exists():
            return
        text = self.text_input.get("1.0", "end").strip()
        if not text:
            self._dest = "todo"
            self._set_hint(DEFAULT_HINT)
        else:
            try:
                self._dest = decide(text)[0]
            except Exception:  # pylint: disable=broad-exception-caught
                self._dest = "todo"
            self._set_hint(f"Looks like {LOOKS_LIKE[self._dest]} \u2726  (tap a tab to change)")
        self._refresh_tabs()

    def _on_enter_key(self, event):
        if not (event.state & 0x0001):     # Enter saves, Shift+Enter = new line
            self.save()
            return "break"
        return None

    # ---- actions ----------------------------------------------------

    def save(self):
        text = self.text_input.get("1.0", "end").strip()
        if not text:
            return
        dest, detail = save_entry(text, force=self._pinned)
        self.text_input.delete("1.0", "end")

        message = f"\u2713 Added to {WHERE[dest]}"
        if detail:
            message += f"  \u00b7  {detail}"
        self._set_status(message)
        if self._status_job is not None:
            self.after_cancel(self._status_job)
        self._status_job = self.after(3200, self._clear_status)

        if self._pinned is None:
            self._dest = dest
            self._set_hint(DEFAULT_HINT)
        self._refresh_tabs()
        _notify_dashboard(dest)
        self.text_input.focus_set()

    def _clear_status(self):
        self._status_job = None
        if self.winfo_exists():
            self._set_status("")

    def discard(self):
        """The trash/cancel button: throw the draft away and slide down."""
        if self.closing:
            return
        self.text_input.delete("1.0", "end")
        self._animate_out()

    # ---- animation --------------------------------------------------

    def _target_xy(self):
        try:
            scale = self._get_window_scaling()
        except AttributeError:
            scale = self._s
        width, height = int(self.WIDTH * scale), int(self.HEIGHT * scale)
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2 - int(30 * scale)
        return x, y

    def _animate_in(self):
        x, y = self._target_xy()
        if not getattr(config, "NOTEPAD_ANIMATION", True):
            self.geometry(f"+{x}+{y}")
            self.attributes("-alpha", 1.0)
            self.after(60, self.text_input.focus_force)
            return
        start_y, steps = y + int(70 * self._s), 12

        def step(i):
            if not self.winfo_exists():
                return
            t = i / steps
            ease = 1 - (1 - t) ** 3
            self.geometry(f"+{x}+{int(start_y + (y - start_y) * ease)}")
            self.attributes("-alpha", ease)
            if i < steps:
                self.after(14, lambda: step(i + 1))
            else:
                self.lift()
                self.text_input.focus_force()

        step(0)

    def _animate_out(self):
        self.closing = True
        x, y = self.winfo_x(), self.winfo_y()
        end_y, steps = y + int(60 * self._s), 9

        def step(i):
            if not self.winfo_exists():
                return
            t = i / steps
            self.geometry(f"+{x}+{int(y + (end_y - y) * t)}")
            self.attributes("-alpha", 1 - t)
            if i < steps:
                self.after(14, lambda: step(i + 1))
            else:
                self.destroy()

        step(0)


EntryPopup = NotepadPopup   # old name, in case anything still imports it


# ---------------------------------------------------------------------------
# The husky
# ---------------------------------------------------------------------------

def _find_pet_dir():
    """Locate the folder holding the husky pictures. Looks in assets/pet first,
    then a few other likely places so a slightly misplaced folder still works."""
    candidates = [config.ASSETS_DIR / "pet", config.ASSETS_DIR / "stickers", config.ASSETS_DIR,
                  config.BASE_DIR / "pet", config.BASE_DIR / "stickers"]
    for base in (config.ASSETS_DIR, config.BASE_DIR):
        try:
            for child in base.iterdir():
                if child.is_dir() and child.name.lower() not in SKIP_DIRS:
                    candidates += [child, child / "pet", child / "assets" / "pet"]
        except OSError:
            pass
    for folder in candidates:
        if (folder / "pet_run.png").exists() or any(folder.glob("sticker_*.png")):
            return folder
    return config.ASSETS_DIR / "pet"


class PetStrip(tk.Canvas):
    """A strip along the bottom of the dashboard where the husky lives.

    It runs back and forth, naps now and then, shows speech bubbles (say())
    and pops a random compliment sticker when you click it. If the pictures
    can't be found it says so on screen instead of drawing a mystery ball.
    """

    FLOOR = "#5A3825"

    def __init__(self, master, bg):
        self._s = _scale_of(master)
        s = self._s
        super().__init__(master, height=int(210 * s), bg=bg, highlightthickness=0, bd=0)
        self._ground = int(200 * s)
        self._pet_h = int(118 * s)
        self._after = None
        self._extra = []
        self._last_sticker = -1
        self._mode = "none"
        self._pet = None

        self.create_rectangle(0, self._ground, 5000, int(210 * s), fill=self.FLOOR, outline="")
        self.create_line(0, self._ground, 5000, self._ground, fill="#7A5236", width=2)

        self._dir_path = _find_pet_dir()
        self._run = self._load("pet_run.png", self._pet_h)
        self._rest = self._load("pet_rest.png", int(96 * s)) or self._run
        self._run = self._run or self._rest
        self._stickers = self._load_stickers(int(180 * s))

        if self._run is None:
            self.create_text(
                20 * s, self._ground - 60 * s, anchor="w", fill=TAN, justify="left",
                font=(FONT_SERIF, 11, "italic"), width=600 * s,
                text=("Husky pictures not found.\nCopy the 'pet' folder (from the zip) into:\n"
                      f"{config.ASSETS_DIR}"))
            return

        self._x = 160 * s
        self._dir = 1
        self._phase = 0.0
        self._mode = "run"
        self._until = time.monotonic() + random.uniform(5, 9)
        self._pet = self.create_image(self._x, self._ground, image=self._run[0], anchor="s")
        self._make_clickable(self._pet)
        self._tick()

    # ---- images -----------------------------------------------------

    def _load(self, filename, height):
        try:
            img = Image.open(self._dir_path / filename).convert("RGBA")
        except OSError:
            return None
        width = max(1, round(img.width * height / img.height))
        img = img.resize((width, height), Image.LANCZOS)
        return ImageTk.PhotoImage(img), ImageTk.PhotoImage(ImageOps.mirror(img))

    def _load_stickers(self, height):
        stickers = []
        for path in sorted(self._dir_path.glob("sticker_*.png")):
            try:
                img = Image.open(path).convert("RGBA")
            except OSError:
                continue
            width = max(1, round(img.width * height / img.height))
            stickers.append(ImageTk.PhotoImage(img.resize((width, height), Image.LANCZOS)))
        return stickers

    # ---- movement ---------------------------------------------------

    def _tick(self):
        if not self.winfo_exists():
            return
        now = time.monotonic()
        s = self._s
        if self._mode == "run":
            width = max(self.winfo_width(), 400)
            self._phase += 0.35
            self._x += self._dir * 2.6 * s
            if self._x > width - 80 * s:
                self._x, self._dir = width - 80 * s, -1
            elif self._x < 80 * s:
                self._x, self._dir = 80 * s, 1
            hop = abs(math.sin(self._phase)) * 7 * s
            self.itemconfigure(self._pet, image=self._run[0 if self._dir > 0 else 1])
            self.coords(self._pet, self._x, self._ground - hop)
            if now >= self._until:
                self._mode = "rest"
                self._until = now + random.uniform(3, 6)
                self.itemconfigure(self._pet, image=self._rest[0])
                self.coords(self._pet, self._x, self._ground)
        elif self._mode == "rest":
            if now >= self._until:
                self._resume_running()
        elif now >= self._until:       # busy: bubble / sticker finished
            self._clear_extra()
            self._resume_running()
        self._after = self.after(40, self._tick)

    def _resume_running(self):
        self._mode = "run"
        self._dir = random.choice((-1, 1))
        self._until = time.monotonic() + random.uniform(5, 10)
        self.itemconfigure(self._pet, state="normal")

    def _clear_extra(self):
        for item in self._extra:
            self.delete(item)
        self._extra = []

    def _make_clickable(self, item):
        self.tag_bind(item, "<Button-1>", lambda _e: self.pop_sticker())
        self.tag_bind(item, "<Enter>", lambda _e: self.configure(cursor="hand2"))
        self.tag_bind(item, "<Leave>", lambda _e: self.configure(cursor=""))

    # ---- speech bubble ---------------------------------------------

    def say(self, text, ms=2800):
        """Show a speech bubble above the husky for a moment."""
        if self._pet is None or not self.winfo_exists():
            return
        self._clear_extra()
        s = self._s
        self._mode, self._until = "busy", time.monotonic() + ms / 1000
        self.itemconfigure(self._pet, state="normal", image=self._run[0])
        self.coords(self._pet, self._x, self._ground)

        label = self.create_text(0, 0, text=text, fill=INK, justify="center",
                                 font=(FONT_SERIF, 11, "bold"), width=int(230 * s))
        x1, y1, x2, y2 = self.bbox(label)
        pad = 12 * s
        half, height = (x2 - x1) / 2 + pad, (y2 - y1) + 2 * pad
        cx = min(max(self._x, half + 8 * s), max(self.winfo_width(), 400) - half - 8 * s)
        bottom = self._ground - self._pet_h - 12 * s
        top = bottom - height
        box = _round_rect(self, cx - half, top, cx + half, bottom, 16 * s,
                          fill=PAPER, outline=ACCENT, width=2)
        tx = min(max(self._x, cx - half + 22 * s), cx + half - 22 * s)
        tail = self.create_polygon(tx - 8 * s, bottom - 1, tx + 8 * s, bottom - 1,
                                   tx, bottom + 11 * s, fill=PAPER, outline="")
        edge = self.create_line(tx - 7 * s, bottom, tx + 7 * s, bottom, fill=PAPER, width=3)
        self.coords(label, cx, (top + bottom) / 2)
        self.tag_raise(label)
        self._extra = [box, tail, edge, label]

    def pop_sticker(self):
        """Clicked: swap into a random compliment sticker for a few seconds."""
        if self._pet is None or not self.winfo_exists():
            return
        if not self._stickers:
            self.say(random.choice(COMPLIMENTS), 3200)
            return
        self._clear_extra()
        index = random.randrange(len(self._stickers))
        if index == self._last_sticker:
            index = (index + 1) % len(self._stickers)
        self._last_sticker = index

        self._mode, self._until = "busy", time.monotonic() + 3.8
        self.itemconfigure(self._pet, state="hidden")
        photo = self._stickers[index]
        half = photo.width() / 2
        x = min(max(self._x, half + 6), max(self.winfo_width(), 400) - half - 6)
        item = self.create_image(x, self._ground, image=photo, anchor="s")
        self._make_clickable(item)
        self._extra = [item]

    # ---- reactions --------------------------------------------------

    def react_added(self, dest):
        lines = {
            "todo": ["Added to your to-do list \u2726", "To-do noted! You've got this \u2665"],
            "note": ["Tucked into your brain dump \u2726", "Brain dump saved - lighter mind \u2665"],
            "reminder": ["Reminder set - I'll nudge you \u2726", "Got it, I'll remind you \u2665"],
        }
        self.say(random.choice(lines[dest]))

    def react_done(self):
        self.say(random.choice(["Nice! One less thing \u2665", "Done! Proud of you \u2726"]))

    def react_deleted(self):
        self.say("Poof - gone!", 1800)

    def destroy(self):
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
        super().destroy()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class DashboardWindow(ctk.CTkToplevel):
    """Sidebar of everything saved + board of cards + the husky."""

    BOARD = "#4A2F20"            # dark leather board
    COLUMNS = [                  # key, title, accent colour
        ("todo", "To-do list", "#E8BE7B"),
        ("note", "Brain dump", "#E2A58F"),
        ("reminder", "Reminders", "#B3CC9D"),
    ]

    def __init__(self, master):
        super().__init__(master)
        self.title("Zeya \u2726")
        self.geometry(getattr(config, "DASHBOARD_SIZE", "1100x720"))
        self.minsize(960, 640)
        self.configure(fg_color=ESPRESSO)
        self.attributes("-topmost", True)
        self.after(300, lambda: self.winfo_exists() and self.attributes("-topmost", False))

        self._items = []
        self._cards = {}
        self._columns = {}

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()
        self.refresh()
        self.after(800, lambda: self.winfo_exists() and self.pet.say("Hi! Let's get things done \u2665"))

    # ---- layout -----------------------------------------------------

    def _build_sidebar(self):
        side = ctk.CTkFrame(self, width=260, corner_radius=0, fg_color="#2E1C12")
        side.grid(row=0, column=0, sticky="nsew")
        side.pack_propagate(False)

        ctk.CTkLabel(side, text="Zeya \u2726", font=_font(26, "bold"), text_color=CREAM,
                     anchor="w").pack(fill="x", padx=18, pady=(18, 0))
        ctk.CTkLabel(side, text="everything you've saved", font=_font(12, "italic"),
                     text_color=TAN, anchor="w").pack(fill="x", padx=18)

        ctk.CTkButton(side, text="+  New note", height=36, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, text_color=CREAM, font=_font(13, "bold"),
                      command=open_popup).pack(fill="x", padx=16, pady=(14, 8))

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_a: self._rebuild_sidebar())
        ctk.CTkEntry(side, textvariable=self._search_var, placeholder_text="Search...",
                     fg_color="#3F2A1D", border_color="#6B4A33", text_color=CREAM,
                     placeholder_text_color=TAN, height=32,
                     ).pack(fill="x", padx=16, pady=(0, 8))

        self._count_label = ctk.CTkLabel(side, text="", font=_font(12, "bold"),
                                         text_color=TAN, anchor="w")
        self._count_label.pack(fill="x", padx=18)

        self._side_list = ctk.CTkScrollableFrame(side, fg_color="transparent", **SCROLL_STYLE)
        self._side_list.pack(fill="both", expand=True, padx=6, pady=(4, 8))

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=(12, 16), pady=(16, 8))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)

        board = ctk.CTkFrame(main, fg_color="transparent")
        board.grid(row=0, column=0, sticky="nsew")
        board.grid_rowconfigure(0, weight=1)
        board.grid_columnconfigure((0, 1, 2), weight=1, uniform="col")

        for i, (key, title, accent) in enumerate(self.COLUMNS):
            col = ctk.CTkFrame(board, fg_color=self.BOARD, corner_radius=18,
                               border_width=1, border_color="#6B4A33")
            col.grid(row=0, column=i, sticky="nsew", padx=6)
            header = ctk.CTkLabel(col, text=title, font=_font(17, "bold"),
                                  text_color=accent, anchor="w")
            header.pack(fill="x", padx=16, pady=(14, 4))
            scroll = ctk.CTkScrollableFrame(col, fg_color="transparent", **SCROLL_STYLE)
            scroll.pack(fill="both", expand=True, padx=6, pady=(0, 8))
            self._columns[key] = (header, scroll, title)

        self.pet = PetStrip(main, bg=ESPRESSO)
        self.pet.grid(row=1, column=0, sticky="ew", pady=(6, 0))

    # ---- data -> widgets --------------------------------------------

    def refresh(self):
        self._items = database.get_all_tasks()
        self._rebuild_board()
        self._rebuild_sidebar()

    @staticmethod
    def _ordered(tasks, dest):
        pending = [t for t in tasks if t["status"] == "pending"]
        done = [t for t in tasks if t["status"] != "pending"]
        if dest == "reminder":
            pending.sort(key=lambda t: (t["due_at"] or "9999", t["id"]))
        else:
            pending.sort(key=lambda t: -t["id"])
        done.sort(key=lambda t: -t["id"])
        return pending + done

    def _rebuild_board(self):
        self._cards = {}
        for key, title, accent in self.COLUMNS:
            header, scroll, _ = self._columns[key]
            for child in scroll.winfo_children():
                child.destroy()
            tasks = self._ordered([t for t in self._items if dest_of(t) == key], key)
            open_count = sum(1 for t in tasks if t["status"] == "pending")
            header.configure(text=f"{title}  \u00b7  {open_count}")
            if not tasks:
                ctk.CTkLabel(scroll, text="Nothing here yet \u2726", text_color=TAN,
                             font=_font(12, "italic")).pack(pady=18)
            for task in tasks:
                self._make_card(scroll, task, key, accent)

    def _make_card(self, parent, task, dest, accent):
        done = task["status"] != "pending"
        card = ctk.CTkFrame(parent, fg_color="#D8C6A2" if done else PAPER,
                            corner_radius=10, border_width=0, border_color="#C0572F")
        card.pack(fill="x", pady=5, padx=2)
        card.grid_columnconfigure(0, weight=1)
        self._cards[task["id"]] = card

        font = _font(13, overstrike=True) if done else _font(13)
        ctk.CTkLabel(card, text=task["title"], font=font, anchor="w", justify="left",
                     wraplength=125, text_color=MUTED if done else INK,
                     ).grid(row=0, column=0, sticky="w", padx=(12, 4), pady=(9, 2))

        if task["due_date"]:
            when = _pretty_date(task["due_date"])
            if task["due_time"]:
                when += f" \u00b7 {task['due_time']}"
            ctk.CTkLabel(card, text=f"\u23F0 {when}", font=_font(11, "italic"),
                         text_color=MUTED, anchor="w",
                         ).grid(row=1, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 9))
        else:
            card.grid_rowconfigure(1, minsize=6)

        col = 1
        if dest != "note" and not done:
            ctk.CTkButton(card, text="\u2713", width=28, height=28, corner_radius=14,
                          fg_color=accent, hover_color=accent, text_color=INK,
                          font=_font(13, "bold"),
                          command=lambda t=task: self._mark_done(t),
                          ).grid(row=0, column=col, padx=(0, 4), pady=(6, 0))
            col += 1
        ctk.CTkButton(card, text="\U0001F5D1", width=28, height=28, corner_radius=14,
                      fg_color="transparent", hover_color="#EBCFC4", text_color="#9C3B2E",
                      command=lambda t=task: self._delete(t),
                      ).grid(row=0, column=col, padx=(0, 8), pady=(6, 0))

    def _rebuild_sidebar(self):
        for child in self._side_list.winfo_children():
            child.destroy()
        needle = self._search_var.get().strip().lower()
        shown = [t for t in sorted(self._items, key=lambda t: -t["id"])
                 if not needle or needle in t["title"].lower()]
        self._count_label.configure(text=f"All saved  \u00b7  {len(shown)}")
        icons = {"todo": "\u2610", "note": "\u270E", "reminder": "\u23F0"}
        for task in shown:
            text = task["title"].replace("\n", " ")
            if len(text) > 26:
                text = text[:25] + "\u2026"
            done = task["status"] != "pending"
            ctk.CTkButton(
                self._side_list, text=f"{icons[dest_of(task)]}  {text}", anchor="w", height=30,
                fg_color="transparent", hover_color="#4A3022", font=_font(12),
                text_color=TAN if done else CREAM,
                command=lambda t=task: self._flash(t["id"]),
            ).pack(fill="x", pady=1)

    # ---- actions ----------------------------------------------------

    def _flash(self, task_id):
        card = self._cards.get(task_id)
        if card is None or not card.winfo_exists():
            return
        card.configure(border_width=3)
        self.after(1400, lambda: card.winfo_exists() and card.configure(border_width=0))

    def _mark_done(self, task):
        database.complete_task(task["id"])
        self.refresh()
        self.pet.react_done()

    def _delete(self, task):
        database.delete_task(task["id"])
        self.refresh()
        self.pet.react_deleted()

    def on_item_added(self, dest):
        """Called by the notepad after saving: refresh and let the husky react."""
        self.refresh()
        self.pet.react_added(dest)


if __name__ == "__main__":
    database.init_db()
    open_popup()
    open_dashboard()
    run()