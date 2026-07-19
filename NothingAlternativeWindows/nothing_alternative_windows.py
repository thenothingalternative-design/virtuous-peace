import customtkinter as ctk
import tkinter as tk
import time, threading, ctypes, json, os, sys, winreg, webbrowser, urllib.parse, secrets, platform
from datetime import datetime, timezone 
from collections import Counter
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
load_dotenv()

try:
    import httpx as _httpx   # type: ignore[import]
    _HAS_HTTPX = True
except ImportError:
    _httpx = None; _HAS_HTTPX = False

# ── Optional deps ──────────────────────────────────────────────────────────────
try:
    import win32api as _win32api  # type: ignore[import]
    _HAS_WIN32 = True
except ImportError:
    _win32api = None; _HAS_WIN32 = False

try:
    import pystray                    # type: ignore[import]
    from PIL import Image, ImageDraw  # type: ignore[import]
    _HAS_TRAY = True
except ImportError:
    _HAS_TRAY = False

try:
    import keyboard as _keyboard      # type: ignore[import]
    _HAS_KEYBOARD = True
except ImportError:
    _keyboard = None; _HAS_KEYBOARD = False

try:
    import psutil
except ImportError: 
    raise SystemExit("psutil is required: pip install psutil")

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "na_config.json")

# ── Backend API ────────────────────────────────────────────────────────────────
# Point this at your Railway deployment.  The local status server (port 59284)
# still runs in parallel for the browser extension — they are independent.
API_BASE  = os.environ.get("NA_API_BASE", " ")
API_TOKEN: str | None = None          # set after sign-in, used for all requests

# Google OAuth (Web-app client — works on desktop via redirect to localhost)
# Create credentials at console.cloud.google.com → APIs & Services → Credentials
# Application type: Web application
# Authorised redirect URIs: http://localhost:59285/callback
GOOGLE_CLIENT_ID = os.environ.get(
    "NA_GOOGLE_CLIENT_ID",
    " "
)
OAUTH_REDIRECT_PORT  = 59285
OAUTH_REDIRECT_URI   = f"http://localhost:{OAUTH_REDIRECT_PORT}/callback"

TOKEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "na_token.json")

def load_saved_token() -> dict | None:
    """Returns {"access_token", "user_id", "email", "display_name"} or None."""
    if not os.path.exists(TOKEN_PATH):
        return None
    try:
        with open(TOKEN_PATH) as f:
            return json.load(f)
    except Exception:
        return None

def save_token(data: dict) -> None:
    try:
        with open(TOKEN_PATH, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[AUTH] token save failed: {e}")

def clear_token() -> None:
    try:
        if os.path.exists(TOKEN_PATH):
            os.remove(TOKEN_PATH)
    except Exception:
        pass

def api_headers() -> dict:
    return {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}

_DEFAULT_PROFILE = {
    "allowed_apps":    ["resolve"] ,
    "banned_keywords": ["youtube","facebook","instagram","twitter",
                        "x.com","reddit","tiktok","netflix"],
}
DEFAULT_CONFIG = {
    "last_goal":      "",
    "active_profile": "Default",
    "profiles":       {"Default": {k: list(v) for k, v in _DEFAULT_PROFILE.items()}},
    "history":        [],
    "profiles_updated_at": {},   # {profile_name: ISO timestamp of last local edit}
    "pending_sync": None,   # {"action": "start"|"stop", "payload": {...}}
    "goal_templates": [],   # list of saved goal strings 
    "streak_days": 0,
    "streak_last_date": "",   # ISO date string "2025-06-01" 
}

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_CONFIG))

def save_config(cfg: dict, touched_profile: str | None = None) -> None:
    if touched_profile:
        cfg.setdefault("profiles_updated_at", {})[touched_profile] = \
            datetime.now().isoformat(timespec="seconds")
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[CONFIG] save failed: {e}")

def active_profile(cfg: dict) -> dict:
    name = cfg.get("active_profile", "Default")
    return cfg["profiles"].setdefault(name, json.loads(json.dumps(_DEFAULT_PROFILE)))

def record_session(cfg, goal, duration_s, blocked, profile, block_log):
    cfg["history"].insert(0, {
        "ts":        datetime.now().isoformat(timespec="seconds"),
        "goal":      goal,
        "duration":  duration_s,
        "blocked":   blocked,
        "profile":   profile,
        "block_log": block_log,
    })
    cfg["history"] = cfg["history"][:120]

    # Update streak
    today = datetime.now().date().isoformat()
    last  = cfg.get("streak_last_date", "")
    if last == today:
        pass  # already recorded a session today, streak unchanged
    elif last == (datetime.now().date() - __import__("datetime").timedelta(days=1)).isoformat():
        cfg["streak_days"] = cfg.get("streak_days", 0) + 1
        cfg["streak_last_date"] = today
    else:
        cfg["streak_days"] = 1  # streak broken, start fresh
        cfg["streak_last_date"] = today

    save_config(cfg)

def fmt_dur(s: int) -> str:
    h, r = divmod(s, 3600); m, s2 = divmod(r, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s2:02d}s"

# ══════════════════════════════════════════════════════════════════════════════
# BACKEND SYNC LAYER
# All functions here are best-effort: any network failure is caught and
# logged to stderr only — the app continues in local-only mode.
# ══════════════════════════════════════════════════════════════════════════════

# Stable identifier for this device — used so the backend can show which
# device started a session (and future per-device logic stays compatible).
_DEVICE_ID: str = platform.node() or "windows-device"


def _api_post(path: str, body: dict) -> dict | None:
    """
    POST to API_BASE+path with the current Bearer token.
    Returns parsed JSON dict on success, None on any failure.
    Matches the existing httpx-with-urllib-fallback pattern in the file.
    """
    if not API_TOKEN:
        return None
    url = f"{API_BASE}{path}"
    headers = api_headers()
    try:
        if _HAS_HTTPX:
            r = _httpx.post(url, json=body, headers=headers, timeout=8)  # type: ignore[union-attr]
            return r.json() if r.status_code < 500 else None
        else:
            import urllib.request
            data = json.dumps(body).encode()
            req  = urllib.request.Request(url, data=data, method="POST",
                                          headers=headers)
            with urllib.request.urlopen(req, timeout=8) as r:
                return json.loads(r.read())
    except Exception as e:
        print(f"[SYNC] POST {path} failed: {e}")
        return None


def _api_get(path: str) -> dict | None:
    """
    GET API_BASE+path with the current Bearer token.
    Returns parsed JSON dict on success, None on any failure.
    """
    if not API_TOKEN:
        return None
    url = f"{API_BASE}{path}"
    headers = api_headers()
    try:
        if _HAS_HTTPX:
            r = _httpx.get(url, headers=headers, timeout=8)  # type: ignore[union-attr]
            return r.json() if r.status_code < 500 else None
        else:
            import urllib.request
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as r:
                return json.loads(r.read())
    except Exception as e:
        print(f"[SYNC] GET {path} failed: {e}")
        return None


def _api_put(path: str, body: dict) -> dict | None:
    """
    PUT to API_BASE+path with the current Bearer token.
    Returns parsed JSON dict on success, None on any failure.
    """
    if not API_TOKEN:
        return None
    url = f"{API_BASE}{path}"
    headers = api_headers()
    try:
        if _HAS_HTTPX:
            r = _httpx.put(url, json=body, headers=headers, timeout=8)  # type: ignore[union-attr]
            return r.json() if r.status_code < 500 else None
        else:
            import urllib.request
            data = json.dumps(body).encode()
            req  = urllib.request.Request(url, data=data, method="PUT",
                                          headers=headers)
            with urllib.request.urlopen(req, timeout=8) as r:
                return json.loads(r.read())
    except Exception as e:
        print(f"[SYNC] PUT {path} failed: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# OPTION 1 — HTTP STATUS SERVER (feeds the browser extension)
# The extension polls /status and gets {"active": bool, "blocked": [...sites]}
# so it can close tabs before they even load.
# ══════════════════════════════════════════════════════════════════════════════
STATUS_PORT = 59284
_status_blocked_sites: list[str] = []

class _StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/status":
            self.send_response(404); self.end_headers(); return
        payload = json.dumps({
            "active":  session_active,
            "blocked": _status_blocked_sites,
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type",  "application/json")
        self.send_header("Content-Length", str(len(payload)))
        # Allow the extension's service worker (different origin) to read this
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        pass  # silence console spam

def _start_status_server() -> None:
    """Start the HTTP status server on a daemon thread. Fails silently if port busy."""
    try:
        srv = HTTPServer(("localhost", STATUS_PORT), _StatusHandler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"[STATUS] HTTP server listening on localhost:{STATUS_PORT}")
    except OSError as e:
        print(f"[STATUS] Could not start status server: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# INSTALLED APP DISCOVERY
# ══════════════════════════════════════════════════════════════════════════════
_REG_PATHS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]
_IGN_PUB  = {"microsoft corporation","microsoft","windows","intel","nvidia","amd","realtek","google llc"}
_IGN_FRAG = {"update","redistributable","runtime","driver","framework",
             "package","module","sdk","visual c++","directx",".net"}

def _ignore(name, pub):
    return any(f in name.lower() for f in _IGN_FRAG) or pub.lower() in _IGN_PUB

def get_installed_apps() -> list[dict]:
    apps: dict[str, dict] = {}
    for hive, path in _REG_PATHS:
        try: key = winreg.OpenKey(hive, path)
        except OSError: continue
        i = 0
        while True:
            try: sub_name = winreg.EnumKey(key, i); i += 1
            except OSError: break
            try:
                sub = winreg.OpenKey(key, sub_name)
                try: name, _ = winreg.QueryValueEx(sub, "DisplayName")
                except OSError: winreg.CloseKey(sub); continue
                pub = loc = ""
                try: pub, _ = winreg.QueryValueEx(sub, "Publisher")
                except OSError: pass
                try: loc, _ = winreg.QueryValueEx(sub, "InstallLocation")
                except OSError: pass
                winreg.CloseKey(sub)
                name = name.strip()
                if not name or _ignore(name, pub): continue
                hint = os.path.basename(loc.rstrip("\\/")).lower() if loc else name.split()[0].lower()
                kl = name.lower()
                if kl not in apps:
                    apps[kl] = {"display_name": name, "exe_hint": hint, "source": "registry"}
            except OSError: continue
        winreg.CloseKey(key)
    seen: set[str] = set()
    for proc in psutil.process_iter(["name", "exe"]):
        try:
            pname = proc.info["name"] or ""
            pexe  = proc.info["exe"]  or ""
            if not pname.endswith(".exe"): continue
            base = pname[:-4].lower()
            if base in seen: continue
            seen.add(base)
            if base in {"explorer","svchost","lsass","winlogon","csrss","smss",
                        "wininit","services","spoolsv","taskhostw","python",
                        "pythonw","cmd","powershell","conhost","nothing_alternative"}: continue
            display = pname[:-4]
            if _HAS_WIN32 and pexe:
                try:
                    info = _win32api.GetFileVersionInfo(  # type: ignore[union-attr]
                        pexe, "\\StringFileInfo\\040904b0\\FileDescription")
                    if info and info.strip(): display = info.strip()
                except Exception: pass
            kl = display.lower()
            if kl not in apps:
                apps[kl] = {"display_name": display, "exe_hint": base, "source": "running"}
        except (psutil.NoSuchProcess, psutil.AccessDenied): continue
    return sorted(apps.values(), key=lambda x: x["display_name"].lower())

# ══════════════════════════════════════════════════════════════════════════════
# THEME
# ══════════════════════════════════════════════════════════════════════════════
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG_BASE    = "#0e0e0f"
BG_SURFACE = "#16161a"
BG_RAISED  = "#1c1c22"
BORDER     = "#2a2a2e"
ACCENT     = "#3a3aff"
ACCENT_HVR = "#5555ff"
TEXT_PRI   = "#ffffff"
TEXT_SEC   = "#8888aa"
TEXT_MUT   = "#3a3a44"
RED        = "#ee4455"
AMBER      = "#ffaa33"
GREEN      = "#00e676"

# ══════════════════════════════════════════════════════════════════════════════
# OPTION 2 — KEYBOARD-LIB TAB CLOSER
# Uses the `keyboard` package which operates at driver level and does NOT
# require the target window to be in the foreground.
# Falls back to the original SendInput approach if keyboard is not installed.
# ══════════════════════════════════════════════════════════════════════════════
class _KBI(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class _INP(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KBI)]
    _anonymous_ = ("_u",)
    _fields_    = [("type", ctypes.c_ulong), ("_u", _U)]

_KEYUP = 0x0002
_KBD   = 1

def _sendinput_ctrl_w(user32) -> None:
    """Original SendInput path — kept as last-resort fallback."""
    extra = ctypes.c_ulong(0); pe = ctypes.pointer(extra)
    batch = (_INP * 5)(
        _INP(type=_KBD, ki=_KBI(wVk=0x11, dwFlags=0,      dwExtraInfo=pe)),
        _INP(type=_KBD, ki=_KBI(wVk=0x57, dwFlags=0,      dwExtraInfo=pe)),
        _INP(type=_KBD, ki=_KBI(wVk=0x57, dwFlags=_KEYUP,  dwExtraInfo=pe)),
        _INP(type=_KBD, ki=_KBI(wVk=0x11, dwFlags=_KEYUP,  dwExtraInfo=pe)),
        _INP(type=_KBD, ki=_KBI(wVk=0x11, dwFlags=_KEYUP,  dwExtraInfo=pe)),
    )
    user32.SendInput(5, batch, ctypes.sizeof(_INP))


def _close_tab(hwnd: int, user32) -> None:
    """
    Best-effort Ctrl+W delivery to a specific browser window (hwnd).

    Strategy (in order):
      1. keyboard.send("ctrl+w")  — driver-level, no focus needed  [Option 2]
      2. AttachThreadInput + SetFocus + keybd_event                 [fallback A]
      3. SendInput                                                   [fallback B]
    """
    if _HAS_KEYBOARD:
        # ── Option 2: driver-level keystroke via keyboard lib ─────────────
        # Attach our input thread to the browser's so SetFocus works, then
        # fire ctrl+w through keyboard which bypasses the foreground check.
        our_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        tgt_tid = user32.GetWindowThreadProcessId(hwnd, None)
        attached = user32.AttachThreadInput(our_tid, tgt_tid, True)
        user32.SetFocus(hwnd)
        if attached:
            user32.AttachThreadInput(our_tid, tgt_tid, False)

        _keyboard.send("ctrl+w")   # type: ignore[union-attr]
        time.sleep(0.12)
        return

    # ── Fallback A: AttachThreadInput + keybd_event ───────────────────────
    our_tid  = ctypes.windll.kernel32.GetCurrentThreadId()
    tgt_tid  = user32.GetWindowThreadProcessId(hwnd, None)
    attached = user32.AttachThreadInput(our_tid, tgt_tid, True)

    user32.AllowSetForegroundWindow(-1)
    user32.ShowWindow(hwnd, 9)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    user32.SetFocus(hwnd)

    deadline = time.monotonic() + 0.6
    while time.monotonic() < deadline:
        time.sleep(0.04)
        if user32.GetForegroundWindow() == hwnd:
            break

    VK_CONTROL, VK_W = 0x11, 0x57
    user32.keybd_event(VK_CONTROL, 0, 0,      0)
    user32.keybd_event(VK_W,       0, 0,      0)
    user32.keybd_event(VK_W,       0, _KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, _KEYUP, 0)
    time.sleep(0.12)

    if attached:
        user32.AttachThreadInput(our_tid, tgt_tid, False)

    # ── Fallback B: original SendInput ────────────────────────────────────
    if user32.GetForegroundWindow() != hwnd:
        _sendinput_ctrl_w(user32)

# ══════════════════════════════════════════════════════════════════════════════
# GATEKEEPER THREAD
# ══════════════════════════════════════════════════════════════════════════════
session_active  = False
log_queue:  list[tuple[str, str]] = []
blocked_count   = 0
block_log:  list[dict] = []

_SELF_EXE    = os.path.basename(sys.executable).lower()
_SELF_SCRIPT = os.path.basename(__file__).lower()

def enforce_gatekeeper(allowed_apps, banned_keywords):
    global session_active, log_queue, blocked_count, block_log, _status_blocked_sites
    blocked_count = 0; block_log = []

    # Expose the blocked-site list to the HTTP status server so the
    # browser extension can read it dynamically (picks up profile changes).
    _status_blocked_sites = list(banned_keywords)

    user32 = ctypes.windll.user32
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    immune = {
        "explorer.exe","python.exe","pythonw.exe","cmd.exe",
        "powershell.exe","powershell_ise.exe","windowsterminal.exe","wt.exe",
        "code.exe","taskmgr.exe","taskhostw.exe","nothing_alternative.exe",
        "claude.exe","systemsettings.exe","applicationframehost.exe",
        "searchhost.exe","searchapp.exe","shellexperiencehost.exe",
        "startmenuexperiencehost.exe","lockapp.exe","logonui.exe",
        _SELF_EXE,
    }
    browsers = ["brave","chrome","msedge","firefox"]

    keyboard_note = " (keyboard lib active)" if _HAS_KEYBOARD else " (keyboard lib not found — using fallback)"
    log_queue.append(("system",
        f"[SYSTEM] Session started — {len(allowed_apps)} app(s) allowed{keyboard_note}"))

    _last_closed: dict[str, float] = {}
    COOLDOWN = 3.0

    def _record(type_: str, name: str):
        global blocked_count
        blocked_count += 1
        block_log.append({"type": type_, "name": name,
                           "ts": datetime.now().isoformat(timespec="seconds")})

    time.sleep(2.0)  # grace period so app finishes minimising

    while session_active:
        time.sleep(1.0)

        # ── STRATEGY A: Tab Sniper (Option 2 — keyboard lib) ─────────────────
        # The browser extension (Option 1) handles tabs before they load.
        # This catches anything the extension misses: Firefox, non-extension
        # browsers, or tabs that slipped through before the extension polled.
        browser_wins: list[tuple[int, str, str]] = []

        def _collect(hwnd, _):
            if not user32.IsWindowVisible(hwnd): return True
            l = user32.GetWindowTextLengthW(hwnd)
            if l < 2: return True
            buf = ctypes.create_unicode_buffer(l + 1)
            user32.GetWindowTextW(hwnd, buf, l + 1)
            title = buf.value.lower()
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:    pname = psutil.Process(pid.value).name().lower()
            except: return True
            if not any(b in pname for b in browsers): return True
            match = next((k for k in banned_keywords if k in title), None)
            if match:
                browser_wins.append((hwnd, title, match))
            return True

        user32.EnumWindows(EnumWindowsProc(_collect), 0)

        if browser_wins:
            prev_hwnd = user32.GetForegroundWindow()

            for hwnd, title, match in browser_wins:
                now = time.monotonic()
                if now - _last_closed.get(match, 0) < COOLDOWN:
                    continue

                # Send Ctrl+W via best available method (keyboard lib first)
                _close_tab(hwnd, user32)

                _last_closed[match] = time.monotonic()
                log_queue.append(("sniper", f"[SNIPER] Closed tab: '{title[:50]}'"))
                _record("tab", match)

            # Restore focus
            if prev_hwnd and prev_hwnd != user32.GetForegroundWindow():
                try: user32.SetForegroundWindow(prev_hwnd)
                except Exception: pass

        # ── STRATEGY B: App whitelist ─────────────────────────────────────────
        visible: set[int] = set()
        def _fw(h, _):
            if user32.IsWindowVisible(h) and user32.GetWindowTextLengthW(h) > 0:
                p = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(h, ctypes.byref(p))
                visible.add(p.value)
            return True
        user32.EnumWindows(EnumWindowsProc(_fw), 0)

        for pid in visible:
            try:
                proc = psutil.Process(pid); pn = proc.name().lower()
                if pn in immune: continue
                try:
                    if _SELF_SCRIPT in " ".join(proc.cmdline()).lower(): continue
                except Exception: pass
                if any(b in pn for b in browsers): continue
                if any(a in pn for a in allowed_apps): continue
                if pn.endswith(".exe"):
                    log_queue.append(("blocker", f"[BLOCKER] Closed: {pn}"))
                    _record("app", pn)
                    proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied): pass

    _status_blocked_sites = []   # clear when session ends
    log_queue.append(("system", "[SYSTEM] Session ended."))

# ══════════════════════════════════════════════════════════════════════════════
# SHARED WIDGETS
# ══════════════════════════════════════════════════════════════════════════════
class AppChip(ctk.CTkFrame):
    def __init__(self, parent, label, on_remove):
        super().__init__(parent, fg_color=BG_RAISED, border_color=ACCENT,
                         border_width=1, corner_radius=99)
        self.label_text = label
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(padx=10, pady=4)
        ctk.CTkLabel(inner, text="●", font=("DM Mono",8),
                     text_color=ACCENT, width=10).pack(side="left", padx=(0,5))
        ctk.CTkLabel(inner, text=label, font=("DM Sans",12),
                     text_color="#7a7aff").pack(side="left")
        ctk.CTkButton(inner, text="×", width=16, height=16,
                      fg_color="transparent", hover_color=BG_RAISED,
                      text_color=TEXT_MUT, font=("DM Sans",13),
                      corner_radius=99, command=lambda: on_remove(label)
                      ).pack(side="left", padx=(4,0))

class BlockedChip(ctk.CTkFrame):
    def __init__(self, parent, label, on_remove):
        super().__init__(parent, fg_color="#1e0e10", border_color="#3a1820",
                         border_width=1, corner_radius=99)
        self.label_text = label
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(padx=10, pady=4)
        ctk.CTkLabel(inner, text="⊘", font=("DM Mono", 8),
                     text_color="#aa4455", width=10).pack(side="left", padx=(0, 5))
        ctk.CTkLabel(inner, text=label, font=("DM Sans", 12),
                     text_color="#aa4455").pack(side="left")
        ctk.CTkButton(inner, text="×", width=16, height=16,
                      fg_color="transparent", hover_color="#1e0e10",
                      text_color="#3a1820", font=("DM Sans", 13),
                      corner_radius=99, command=lambda: on_remove(label)
                      ).pack(side="left", padx=(4, 0))
        
class WrapFrame(tk.Frame):
    def __init__(self, parent, h_gap=6, v_gap=6, **kw):
        super().__init__(parent, **kw)
        self.h_gap = h_gap; self.v_gap = v_gap
        self._reflow_job = None
        self.bind("<Configure>", self._schedule_reflow)

    def _schedule_reflow(self, _=None):
        if self._reflow_job:
            self.after_cancel(self._reflow_job)
        self._reflow_job = self.after(30, self._reflow)

    def _reflow(self, _=None):
        self._reflow_job = None
        w = self.winfo_width()
        if w < 2: return
        x = y = 0; rh = 0
        for c in self.winfo_children():
            c.update_idletasks()
            cw = c.winfo_reqwidth(); ch = c.winfo_reqheight()
            if x + cw > w and x > 0:
                x = 0; y += rh + self.v_gap; rh = 0
            c.place(x=x, y=y)
            x += cw + self.h_gap; rh = max(rh, ch)
        self.config(height=max(y+rh, 30))

class Tooltip:
    def __init__(self, widget, text):
        self._w = widget; self._text = text; self._tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)
    def _show(self, _=None):
        if self._tip: return
        x = self._w.winfo_rootx() + self._w.winfo_width() // 2
        y = self._w.winfo_rooty() + self._w.winfo_height() + 4
        self._tip = tw = tk.Toplevel(self._w)
        tw.wm_overrideredirect(True); tw.wm_geometry(f"+{x}+{y}")
        tw.configure(bg=BG_RAISED)
        tk.Label(tw, text=self._text, bg=BG_RAISED, fg=TEXT_SEC,
                 font=("DM Sans",10), padx=8, pady=4).pack()
    def _hide(self, _=None):
        if self._tip: self._tip.destroy(); self._tip = None

def _divider(parent, pady=(0,0)):
    ctk.CTkFrame(parent, fg_color=BORDER, height=1,
                 corner_radius=0).pack(fill="x", pady=pady)

def _section_label(parent, text, pady=(16,6)):
    ctk.CTkLabel(parent, text=text, font=("DM Mono",9),
                 text_color=TEXT_MUT).pack(anchor="w", padx=24, pady=pady)

# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM TRAY
# ══════════════════════════════════════════════════════════════════════════════
def _make_tray_icon(active):
    size = 64
    img  = Image.new("RGBA", (size,size), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    fill = (0,230,118) if active else (58,58,255)
    draw.ellipse([4,4,size-4,size-4], fill=fill)
    draw.ellipse([18,18,46,46], outline=(0,0,0,180), width=4)
    draw.line([20,44,44,20], fill=(0,0,0,180), width=4)
    return img

class TrayManager:
    def __init__(self, app):
        self.app = app; self._icon = None
    def start(self):
        if not _HAS_TRAY: return
        menu = pystray.Menu(
            pystray.MenuItem("Open",          self._on_open, default=True),
            pystray.MenuItem("Start session", self._on_toggle,
                             checked=lambda _: self.app.session_active),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )
        self._icon = pystray.Icon("NothingAlternative",
                                  _make_tray_icon(False), "Nothing Alternative", menu)
        threading.Thread(target=self._icon.run, daemon=True).start()
    def update(self, active):
        if self._icon:
            self._icon.icon  = _make_tray_icon(active)
            self._icon.title = "Nothing Alternative — active" if active else "Nothing Alternative"
    def stop(self):
        if self._icon: self._icon.stop()
    def _on_open(self, *_):
        self.app.after(0, self.app.deiconify); self.app.after(0, self.app.lift)
    def _on_toggle(self, *_): self.app.after(0, self.app._toggle_session)
    def _on_quit(self, *_):   self.app.after(0, self.app._quit)

# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS PANEL
# ══════════════════════════════════════════════════════════════════════════════
class SettingsPanel(ctk.CTkToplevel):
    def __init__(self, parent, cfg, on_change):
        super().__init__(parent)
        self.cfg = cfg; self.on_change = on_change
        self._all_apps = []; self._rows = []
        self.title("App Settings"); self.geometry("460x600")
        self.resizable(True,True); self.configure(fg_color=BG_BASE)
        self.grab_set(); self._build(); self._load_async()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=BG_BASE, corner_radius=0)
        hdr.pack(fill="x", padx=20, pady=(18,0))
        ctk.CTkLabel(hdr, text="Allowed Apps", font=("DM Sans",15,"bold"),
                     text_color=TEXT_PRI).pack(side="left")
        ctk.CTkLabel(hdr, text="  toggle to allow", font=("DM Sans",11),
                     text_color=TEXT_MUT).pack(side="left", pady=(2,0))
        ctk.CTkButton(hdr, text="✕", width=28, height=28,
                      fg_color="transparent", hover_color=BG_RAISED,
                      text_color=TEXT_MUT, font=("DM Sans",14),
                      corner_radius=99, command=self.destroy).pack(side="right")
        sf = ctk.CTkFrame(self, fg_color=BG_SURFACE, border_color=BORDER,
                          border_width=1, corner_radius=10)
        sf.pack(fill="x", padx=20, pady=14)
        ctk.CTkLabel(sf, text="⌕", font=("DM Sans",15),
                     text_color=TEXT_MUT).pack(side="left", padx=(12,0))
        self._sv = tk.StringVar(); self._sv.trace_add("write", self._search)
        ctk.CTkEntry(sf, textvariable=self._sv,
                     placeholder_text="Search installed apps…",
                     font=("DM Sans",13), fg_color="transparent",
                     border_width=0, text_color=TEXT_PRI,
                     placeholder_text_color=TEXT_MUT, height=40
                     ).pack(side="left", fill="x", expand=True, padx=(6,12))
        self.status_lbl = ctk.CTkLabel(self, text="Scanning…",
                                       font=("DM Mono",10), text_color=TEXT_MUT)
        self.status_lbl.pack(anchor="w", padx=20, pady=(0,6))
        self.lf = ctk.CTkScrollableFrame(self, fg_color=BG_BASE,
                                         scrollbar_button_color=BORDER,
                                         scrollbar_button_hover_color=TEXT_MUT)
        self.lf._scrollbar.configure(width=4)
        self.lf.pack(fill="both", expand=True)
        _divider(self)
        foot = ctk.CTkFrame(self, fg_color=BG_BASE, corner_radius=0)
        foot.pack(fill="x", padx=20, pady=14)
        ctk.CTkLabel(foot, text="Can't find it? Add manually:",
                     font=("DM Sans",11), text_color=TEXT_MUT).pack(anchor="w", pady=(0,6))
        mr = ctk.CTkFrame(foot, fg_color="transparent"); mr.pack(fill="x")
        self._me = ctk.CTkEntry(mr, placeholder_text="e.g. figma, slack",
                                font=("DM Sans",12), fg_color=BG_SURFACE,
                                border_color=BORDER, border_width=1,
                                text_color=TEXT_PRI, placeholder_text_color=TEXT_MUT,
                                height=36, corner_radius=8)
        self._me.pack(side="left", fill="x", expand=True, padx=(0,8))
        ctk.CTkButton(mr, text="Add", width=60, height=36,
                      fg_color=ACCENT, hover_color=ACCENT_HVR,
                      text_color=TEXT_PRI, font=("DM Sans",12),
                      corner_radius=8, command=self._manual_add).pack(side="left")

    def _load_async(self):
        threading.Thread(target=lambda: self.after(
            0, self._populate, get_installed_apps()), daemon=True).start()

    def _populate(self, apps):
        self._all_apps = apps; self._rows.clear()
        for w in self.lf.winfo_children(): w.destroy()
        allowed = set(active_profile(self.cfg).get("allowed_apps",[]))
        self.status_lbl.configure(text=f"{len(apps)} apps found  ·  {len(allowed)} allowed")
        for app in apps: self._make_row(app, allowed)

    def _make_row(self, app, allowed):
        hint  = app["exe_hint"]
        is_on = hint in allowed or any(hint in a or a in hint for a in allowed)
        row = ctk.CTkFrame(self.lf, fg_color="transparent", corner_radius=0)
        row.pack(fill="x", padx=16, pady=1)
        row.bind("<Enter>", lambda _,r=row: r.configure(fg_color=BG_RAISED))
        row.bind("<Leave>", lambda _,r=row: r.configure(fg_color="transparent"))
        bc = "#1a1a2e" if app["source"]=="registry" else "#0e1e0e"
        tc = "#4444aa" if app["source"]=="registry" else "#336633"
        b = ctk.CTkFrame(row, fg_color=bc, border_color=tc, border_width=1, corner_radius=4)
        b.pack(side="left", padx=(8,10), pady=8)
        ctk.CTkLabel(b, text="installed" if app["source"]=="registry" else "running",
                     font=("DM Mono",9), text_color=tc).pack(padx=6, pady=2)
        nc = ctk.CTkFrame(row, fg_color="transparent")
        nc.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(nc, text=app["display_name"], font=("DM Sans",12),
                     text_color=TEXT_PRI, anchor="w").pack(anchor="w")
        ctk.CTkLabel(nc, text=hint, font=("DM Mono",9),
                     text_color=TEXT_MUT, anchor="w").pack(anchor="w")
        var = tk.BooleanVar(value=is_on)
        ctk.CTkSwitch(row, variable=var, text="", width=40,
                      onvalue=True, offvalue=False,
                      fg_color=BORDER, progress_color=ACCENT,
                      button_color=TEXT_PRI, button_hover_color="#ccccff",
                      command=lambda a=app, v=var: self._toggle(a,v)
                      ).pack(side="right", padx=(0,12), pady=8)
        self._rows.append({"app":app,"row":row,"var":var})

    def _toggle(self, app, var):
        hint = app["exe_hint"]
        allowed = active_profile(self.cfg)["allowed_apps"]
        if var.get():
            if hint not in allowed: allowed.append(hint)
        else:
            active_profile(self.cfg)["allowed_apps"] = [a for a in allowed if a != hint]
        save_config(self.cfg, touched_profile=self.cfg.get("active_profile", "Default")); self.on_change()
        self.status_lbl.configure(
            text=f"{len(self._all_apps)} apps found  ·  "
                 f"{len(active_profile(self.cfg)['allowed_apps'])} allowed")

    def _search(self, *_):
        q = self._sv.get().lower().strip()
        for item in self._rows:
            a = item["app"]
            hit = not q or q in a["display_name"].lower() or q in a["exe_hint"].lower()
            (item["row"].pack if hit else item["row"].pack_forget)(
                **({"fill":"x","padx":16,"pady":1} if hit else {}))

    def _manual_add(self):
        name = self._me.get().strip().lower()
        if not name: return
        prof = active_profile(self.cfg)
        if name not in prof["allowed_apps"]:
            prof["allowed_apps"].append(name)
            save_config(self.cfg, touched_profile=self.cfg.get("active_profile", "Default")); self.on_change()
        self._me.delete(0,"end")

class BlockedPanel(ctk.CTkToplevel):
    def __init__(self, parent, cfg, on_change):
        super().__init__(parent)
        self.cfg = cfg; self.on_change = on_change
        self.title("Blocked Sites"); self.geometry("420x500")
        self.resizable(True, True); self.configure(fg_color=BG_BASE)
        self.grab_set(); self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=BG_BASE, corner_radius=0)
        hdr.pack(fill="x", padx=20, pady=(18, 0))
        ctk.CTkLabel(hdr, text="Blocked Sites & Keywords",
                     font=("DM Sans", 15, "bold"),
                     text_color=TEXT_PRI).pack(side="left")
        ctk.CTkButton(hdr, text="✕", width=28, height=28,
                      fg_color="transparent", hover_color=BG_RAISED,
                      text_color=TEXT_MUT, font=("DM Sans", 14),
                      corner_radius=99, command=self.destroy).pack(side="right")

        ctk.CTkLabel(self,
                     text="Any tab whose title or URL contains these words gets closed.",
                     font=("DM Sans", 11), text_color=TEXT_MUT,
                     wraplength=360).pack(anchor="w", padx=20, pady=(8, 14))

        # Scrollable list of current keywords
        self.sf = ctk.CTkScrollableFrame(self, fg_color=BG_BASE,
                                         scrollbar_button_color=BORDER,
                                         scrollbar_button_hover_color=TEXT_MUT)
        self.sf._scrollbar.configure(width=4)
        self.sf.pack(fill="both", expand=True)
        self._render()

        _divider(self)

        # Add new keyword
        foot = ctk.CTkFrame(self, fg_color=BG_BASE, corner_radius=0)
        foot.pack(fill="x", padx=20, pady=14)
        ctk.CTkLabel(foot, text="Add a site or keyword:",
                     font=("DM Sans", 11), text_color=TEXT_MUT
                     ).pack(anchor="w", pady=(0, 6))
        row = ctk.CTkFrame(foot, fg_color="transparent"); row.pack(fill="x")
        self._entry = ctk.CTkEntry(
            row, placeholder_text="e.g. twitch.tv, hacker news, gmail",
            font=("DM Sans", 12), fg_color=BG_SURFACE,
            border_color=BORDER, border_width=1,
            text_color=TEXT_PRI, placeholder_text_color=TEXT_MUT,
            height=36, corner_radius=8)
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._entry.bind("<Return>", lambda _: self._add())
        ctk.CTkButton(row, text="Add", width=60, height=36,
                      fg_color=RED, hover_color="#cc2233",
                      text_color=TEXT_PRI, font=("DM Sans", 12),
                      corner_radius=8, command=self._add).pack(side="left")

    def _render(self):
        for w in self.sf.winfo_children():
            w.destroy()
        keywords = active_profile(self.cfg).get("banned_keywords", [])
        if not keywords:
            ctk.CTkLabel(self.sf, text="No sites blocked yet.",
                         font=("DM Sans", 13), text_color=TEXT_MUT).pack(pady=40)
            return
        for kw in keywords:
            self._make_row(kw)

    def _make_row(self, kw):
        row = ctk.CTkFrame(self.sf, fg_color=BG_SURFACE,
                           border_color=BORDER, border_width=1,
                           corner_radius=8)
        row.pack(fill="x", padx=16, pady=3)
        ctk.CTkLabel(row, text=f"⊘  {kw}", font=("DM Mono", 11),
                     text_color="#aa4455", anchor="w").pack(
            side="left", padx=14, pady=10, fill="x", expand=True)
        ctk.CTkButton(row, text="Remove", width=70, height=28,
                      fg_color=BG_RAISED, hover_color="#2a1018",
                      border_color=RED, border_width=1,
                      text_color=RED, font=("DM Sans", 11),
                      corner_radius=6,
                      command=lambda k=kw: self._remove(k)
                      ).pack(side="right", padx=10)

    def _add(self):
        raw = self._entry.get().strip().lower()
        if not raw:
            return
        # Strip https://, www. so "https://www.youtube.com" → "youtube"
        raw = raw.replace("https://", "").replace("http://", "")
        raw = raw.replace("www.", "")
        raw = raw.split("/")[0].strip()   # drop paths
        if not raw:
            return
        prof = active_profile(self.cfg)
        if raw not in prof["banned_keywords"]:
            prof["banned_keywords"].append(raw)
            save_config(self.cfg, touched_profile=self.cfg.get("active_profile", "Default"))
            self.on_change()
        self._entry.delete(0, "end")
        self._render()

    def _remove(self, kw):
        prof = active_profile(self.cfg)
        if kw in prof["banned_keywords"]:
            prof["banned_keywords"].remove(kw)
            save_config(self.cfg, touched_profile=self.cfg.get("active_profile", "Default"))
            self.on_change()
        self._render()
        
# ══════════════════════════════════════════════════════════════════════════════
# HISTORY PANEL
# ══════════════════════════════════════════════════════════════════════════════
class HistoryPanel(ctk.CTkToplevel):
    def __init__(self, parent, cfg):
        super().__init__(parent)
        self.cfg = cfg
        self.title("Session History"); self.geometry("620x660")
        self.resizable(True,True); self.configure(fg_color=BG_BASE)
        self.grab_set(); self._build()

    def _build(self):
        history = self.cfg.get("history",[])
        hdr = ctk.CTkFrame(self, fg_color=BG_BASE, corner_radius=0)
        hdr.pack(fill="x", padx=20, pady=(18,0))
        ctk.CTkLabel(hdr, text="Session History", font=("DM Sans",15,"bold"),
                     text_color=TEXT_PRI).pack(side="left")
        ctk.CTkButton(hdr, text="✕", width=28, height=28,
                      fg_color="transparent", hover_color=BG_RAISED,
                      text_color=TEXT_MUT, font=("DM Sans",14),
                      corner_radius=99, command=self.destroy).pack(side="right")
        if history:
            total_s = sum(e.get("duration",0) for e in history)
            total_b = sum(e.get("blocked",0)  for e in history)
            avg_s   = total_s // max(len(history),1)
            all_blocks = []
            for e in history: all_blocks.extend(e.get("block_log",[]))
            tab_counts = Counter(ev["name"] for ev in all_blocks if ev["type"]=="tab")
            app_counts = Counter(ev["name"] for ev in all_blocks if ev["type"]=="app")
            cards = ctk.CTkFrame(self, fg_color="transparent")
            cards.pack(fill="x", padx=20, pady=(16,0))
            for label, val in [("Sessions",str(len(history))),
                                ("Total focus",fmt_dur(total_s)),
                                ("Avg session",fmt_dur(avg_s)),
                                ("Total blocked",str(total_b))]:
                card = ctk.CTkFrame(cards, fg_color=BG_SURFACE, border_color=BORDER,
                                    border_width=1, corner_radius=10)
                card.pack(side="left", expand=True, fill="x", padx=(0,6))
                ctk.CTkLabel(card, text=val, font=("DM Sans",16,"bold"),
                             text_color=TEXT_PRI).pack(pady=(10,2))
                ctk.CTkLabel(card, text=label, font=("DM Mono",9),
                             text_color=TEXT_MUT).pack(pady=(0,10))
            if tab_counts or app_counts:
                _divider(self, pady=(14,0))
                _section_label(self, "ALL-TIME MOST BLOCKED", pady=(12,6))
                charts = ctk.CTkFrame(self, fg_color="transparent")
                charts.pack(fill="x", padx=20, pady=(0,4))
                if tab_counts: self._mini_chart(charts,"🔴  Sites",tab_counts,RED,"left")
                if app_counts: self._mini_chart(charts,"🟡  Apps", app_counts,AMBER,"right")
        _divider(self, pady=(12,0))
        _section_label(self, "SESSIONS", pady=(12,6))
        sf = ctk.CTkScrollableFrame(self, fg_color=BG_BASE,
                                    scrollbar_button_color=BORDER,
                                    scrollbar_button_hover_color=TEXT_MUT)
        sf._scrollbar.configure(width=4)
        sf.pack(fill="both", expand=True)
        if not history:
            ctk.CTkLabel(sf, text="No sessions recorded yet.",
                         font=("DM Sans",13), text_color=TEXT_MUT).pack(pady=40)
            return
        for e in history: self._make_row(sf, e)

    def _mini_chart(self, parent, title, counts, bar_color, side):
        frame = ctk.CTkFrame(parent, fg_color=BG_SURFACE, border_color=BORDER,
                             border_width=1, corner_radius=10)
        frame.pack(side=side, fill="both", expand=True,
                   padx=(0,8) if side=="left" else (0,0))
        ctk.CTkLabel(frame, text=title, font=("DM Sans",11,"bold"),
                     text_color=TEXT_SEC).pack(anchor="w", padx=12, pady=(10,6))
        top5 = counts.most_common(5)
        max_val = top5[0][1] if top5 else 1
        for name, count in top5:
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(row, text=name[:18], font=("DM Mono",9),
                         text_color=TEXT_PRI, width=110, anchor="w").pack(side="left")
            bf = ctk.CTkFrame(row, fg_color=BG_RAISED, corner_radius=4, height=10)
            bf.pack(side="left", fill="x", expand=True, padx=(6,6))
            bf.pack_propagate(False)
            ctk.CTkFrame(bf, fg_color=bar_color, corner_radius=4, height=10,
                         width=int(120*(count/max_val))).place(x=0,y=0,relheight=1.0)
            ctk.CTkLabel(row, text=str(count), font=("DM Mono",9),
                         text_color=TEXT_MUT, width=24).pack(side="left")
        ctk.CTkFrame(frame, height=8, fg_color="transparent").pack()

    def _make_row(self, parent, e):
        blk_log  = e.get("block_log",[])
        tab_cnt  = Counter(ev["name"] for ev in blk_log if ev["type"]=="tab")
        app_cnt  = Counter(ev["name"] for ev in blk_log if ev["type"]=="app")
        outer = ctk.CTkFrame(parent, fg_color=BG_SURFACE, border_color=BORDER,
                             border_width=1, corner_radius=10)
        outer.pack(fill="x", padx=20, pady=5)
        top = ctk.CTkFrame(outer, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10,4))
        ctk.CTkLabel(top, text=e.get("goal","—"), font=("DM Sans",12,"bold"),
                     text_color=TEXT_PRI, anchor="w").pack(side="left")
        ctk.CTkLabel(top, text=e.get("ts","")[:16].replace("T","  "),
                     font=("DM Mono",9), text_color=TEXT_MUT).pack(side="right")
        pills = ctk.CTkFrame(outer, fg_color="transparent")
        pills.pack(fill="x", padx=14, pady=(0,6))
        for icon, val in [("⏱",fmt_dur(e.get("duration",0))),
                           ("⊘",f"{e.get('blocked',0)} blocked"),
                           ("◈",e.get("profile","Default"))]:
            pill = ctk.CTkFrame(pills, fg_color=BG_RAISED, corner_radius=6)
            pill.pack(side="left", padx=(0,6))
            ctk.CTkLabel(pill, text=f"{icon}  {val}", font=("DM Mono",9),
                         text_color=TEXT_SEC).pack(padx=8, pady=3)
        if tab_cnt or app_cnt:
            detail = ctk.CTkFrame(outer, fg_color=BG_RAISED, corner_radius=8)
            detail.pack(fill="x", padx=10, pady=(0,10))
            cols = ctk.CTkFrame(detail, fg_color="transparent")
            cols.pack(fill="x", padx=10, pady=8)
            if tab_cnt:
                col = ctk.CTkFrame(cols, fg_color="transparent")
                col.pack(side="left", fill="x", expand=True, padx=(0,8))
                ctk.CTkLabel(col, text="Sites blocked", font=("DM Mono",9),
                             text_color=RED).pack(anchor="w", pady=(0,4))
                for name, count in tab_cnt.most_common():
                    r = ctk.CTkFrame(col, fg_color="transparent"); r.pack(fill="x", pady=1)
                    ctk.CTkLabel(r, text=name, font=("DM Sans",11),
                                 text_color=TEXT_PRI, anchor="w").pack(side="left")
                    b = ctk.CTkFrame(r, fg_color="#2a1018", border_color="#3a1820",
                                     border_width=1, corner_radius=4)
                    b.pack(side="right")
                    ctk.CTkLabel(b, text=f"×{count}", font=("DM Mono",9),
                                 text_color=RED).pack(padx=6, pady=2)
            if tab_cnt and app_cnt:
                ctk.CTkFrame(cols, fg_color=BORDER, width=1,
                             corner_radius=0).pack(side="left", fill="y", padx=8)
            if app_cnt:
                col = ctk.CTkFrame(cols, fg_color="transparent")
                col.pack(side="left", fill="x", expand=True)
                ctk.CTkLabel(col, text="Apps closed", font=("DM Mono",9),
                             text_color=AMBER).pack(anchor="w", pady=(0,4))
                for name, count in app_cnt.most_common():
                    r = ctk.CTkFrame(col, fg_color="transparent"); r.pack(fill="x", pady=1)
                    ctk.CTkLabel(r, text=name, font=("DM Sans",11),
                                 text_color=TEXT_PRI, anchor="w").pack(side="left")
                    b = ctk.CTkFrame(r, fg_color="#1e1a00", border_color="#3a3000",
                                     border_width=1, corner_radius=4)
                    b.pack(side="right")
                    ctk.CTkLabel(b, text=f"×{count}", font=("DM Mono",9),
                                 text_color=AMBER).pack(padx=6, pady=2)

# ══════════════════════════════════════════════════════════════════════════════
# PROFILES PANEL
# ══════════════════════════════════════════════════════════════════════════════
class ProfilesPanel(ctk.CTkToplevel):
    def __init__(self, parent, cfg, on_change):
        super().__init__(parent)
        self.cfg = cfg; self.on_change = on_change
        self.title("Profiles"); self.geometry("400x500")
        self.resizable(True,True); self.configure(fg_color=BG_BASE)
        self.grab_set(); self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=BG_BASE, corner_radius=0)
        hdr.pack(fill="x", padx=20, pady=(18,0))
        ctk.CTkLabel(hdr, text="Focus Profiles", font=("DM Sans",15,"bold"),
                     text_color=TEXT_PRI).pack(side="left")
        ctk.CTkButton(hdr, text="✕", width=28, height=28,
                      fg_color="transparent", hover_color=BG_RAISED,
                      text_color=TEXT_MUT, font=("DM Sans",14),
                      corner_radius=99, command=self.destroy).pack(side="right")
        ctk.CTkLabel(self, text="Each profile stores its own allowed-app list.",
                     font=("DM Sans",11), text_color=TEXT_MUT
                     ).pack(anchor="w", padx=20, pady=(6,14))
        self.sf = ctk.CTkScrollableFrame(self, fg_color=BG_BASE,
                                         scrollbar_button_color=BORDER,
                                         scrollbar_button_hover_color=TEXT_MUT)
        self.sf._scrollbar.configure(width=4)
        self.sf.pack(fill="both", expand=True)
        self._render()
        _divider(self)
        foot = ctk.CTkFrame(self, fg_color=BG_BASE, corner_radius=0)
        foot.pack(fill="x", padx=20, pady=14)
        ctk.CTkLabel(foot, text="New profile name:", font=("DM Sans",11),
                     text_color=TEXT_MUT).pack(anchor="w", pady=(0,6))
        nr = ctk.CTkFrame(foot, fg_color="transparent"); nr.pack(fill="x")
        self._ne = ctk.CTkEntry(nr, placeholder_text="e.g. Deep Work, Study…",
                                font=("DM Sans",12), fg_color=BG_SURFACE,
                                border_color=BORDER, border_width=1,
                                text_color=TEXT_PRI, placeholder_text_color=TEXT_MUT,
                                height=36, corner_radius=8)
        self._ne.pack(side="left", fill="x", expand=True, padx=(0,8))
        ctk.CTkButton(nr, text="Create", width=70, height=36,
                      fg_color=ACCENT, hover_color=ACCENT_HVR,
                      text_color=TEXT_PRI, font=("DM Sans",12),
                      corner_radius=8, command=self._create).pack(side="left")

    def _render(self):
        for w in self.sf.winfo_children(): w.destroy()
        active = self.cfg.get("active_profile","Default")
        for name in list(self.cfg["profiles"].keys()):
            self._make_row(name, name==active)

    def _make_row(self, name, is_active):
        row = ctk.CTkFrame(self.sf,
                           fg_color=BG_RAISED if is_active else BG_SURFACE,
                           border_color=ACCENT if is_active else BORDER,
                           border_width=1, corner_radius=10)
        row.pack(fill="x", padx=20, pady=4)
        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=14, pady=10)
        nr = ctk.CTkFrame(left, fg_color="transparent"); nr.pack(anchor="w")
        ctk.CTkLabel(nr, text=name, font=("DM Sans",13,"bold"),
                     text_color=TEXT_PRI if is_active else TEXT_SEC).pack(side="left")
        if is_active:
            p = ctk.CTkFrame(nr, fg_color="#1a2a1a", border_color="#336633",
                             border_width=1, corner_radius=4)
            p.pack(side="left", padx=(8,0))
            ctk.CTkLabel(p, text="active", font=("DM Mono",8),
                         text_color="#44aa44").pack(padx=6, pady=2)
        n_apps = len(self.cfg["profiles"][name].get("allowed_apps",[]))
        ctk.CTkLabel(left, text=f"{n_apps} app{'s' if n_apps!=1 else ''} allowed",
                     font=("DM Mono",9), text_color=TEXT_MUT).pack(anchor="w")
        right = ctk.CTkFrame(row, fg_color="transparent"); right.pack(side="right", padx=10)
        if not is_active:
            ctk.CTkButton(right, text="Switch", width=64, height=30,
                          fg_color=ACCENT, hover_color=ACCENT_HVR,
                          text_color=TEXT_PRI, font=("DM Sans",11),
                          corner_radius=8, command=lambda n=name: self._switch(n)
                          ).pack(side="left", padx=(0,6))
        if name != "Default":
            ctk.CTkButton(right, text="Delete", width=60, height=30,
                          fg_color=BG_RAISED, hover_color="#2a1018",
                          border_color=RED, border_width=1, text_color=RED,
                          font=("DM Sans",11), corner_radius=8,
                          command=lambda n=name: self._delete(n)).pack(side="left")

    def _switch(self, name):
        self.cfg["active_profile"] = name
        save_config(self.cfg, touched_profile=self.cfg.get("active_profile", "Default")); self.on_change(); self._render()

    def _delete(self, name):
        if name == self.cfg.get("active_profile"): self.cfg["active_profile"] = "Default"
        del self.cfg["profiles"][name]
        save_config(self.cfg, touched_profile=self.cfg.get("active_profile", "Default")); self.on_change(); self._render()

    def _create(self):
        name = self._ne.get().strip()
        if not name:
            return

        # Check profile limit for free users
        current_profiles = len(self.cfg["profiles"])
        # Get subscription status from the main app if available
        is_premium = True  # default to allowing, server will enforce the real limit
        try:
            import __main__
            app = __main__.app if hasattr(__main__, "app") else None
            if app and hasattr(app, "_last_sub_status"):
                is_premium = app._last_sub_status in ("active", "trialing", "lifetime")
        except Exception:
            pass

        if not is_premium and current_profiles >= 1:
            # Show upgrade prompt instead of silently doing nothing
            dlg = ctk.CTkToplevel(self)
            dlg.title(""); dlg.geometry("320x150")
            dlg.resizable(False, False)
            dlg.configure(fg_color=BG_SURFACE)
            dlg.grab_set()
            ctk.CTkLabel(dlg, text="Premium feature",
                        font=("DM Sans", 13, "bold"),
                        text_color=TEXT_PRI).pack(pady=(22, 4))
            ctk.CTkLabel(dlg, text="Free accounts support up to 1 profile.\nUpgrade to create unlimited profiles.",
                        font=("DM Sans", 11), text_color=TEXT_MUT,
                        justify="center").pack()
            br = ctk.CTkFrame(dlg, fg_color="transparent"); br.pack(pady=16)
            ctk.CTkButton(br, text="Maybe later", width=100, height=34,
                        fg_color=BG_RAISED, hover_color=BORDER,
                        text_color=TEXT_SEC, font=("DM Sans", 12),
                        corner_radius=8, command=dlg.destroy
                        ).pack(side="left", padx=(0, 10))
            ctk.CTkButton(br, text="Upgrade →", width=110, height=34,
                        fg_color=ACCENT, hover_color=ACCENT_HVR,
                        text_color=TEXT_PRI, font=("DM Sans", 12, "bold"),
                        corner_radius=8,
                        command=lambda: [dlg.destroy(),
                                        self.master._open_upgrade() if hasattr(self.master, "_open_upgrade") else None]
                        ).pack(side="left")
            return

        if name not in self.cfg["profiles"]:
            self.cfg["profiles"][name] = json.loads(json.dumps(_DEFAULT_PROFILE))
        self.cfg["active_profile"] = name
        save_config(self.cfg, touched_profile=self.cfg.get("active_profile", "Default")); self.on_change()
        self._ne.delete(0, "end"); self._render()

# ══════════════════════════════════════════════════════════════════════════════
# WALKTHROUGH PANEL
# ══════════════════════════════════════════════════════════════════════════════
_STEPS = [
    {"title":"Welcome to Nothing Alternative","icon":"∅","body":(
        "This app gives you one choice: work on what you came here to do, "
        "or do nothing at all. No distractions make it through.\n\n"
        "This walkthrough covers everything in about 60 seconds.")},
    {"title":"① Session Goal","icon":"✎","body":(
        "Type your goal in the text field at the top — 'Finish the edit', "
        "'Chapter 3 draft', whatever you're here to do.\n\n"
        "It's saved automatically so it pre-fills next time. "
        "The character counter on the right shows how much you've written.")},
    {"title":"② Focus Profiles","icon":"◈","body":(
        "Profiles let you save different app sets for different work modes. "
        "'Editing' (DaVinci Resolve only), 'Study' (Notion + browser), etc.\n\n"
        "Click  switch →  next to the profile badge to manage them.")},
    {"title":"③ Allowed Apps","icon":"●","body":(
        "Only apps listed here are allowed to run during a session. "
        "Anything else with a visible window gets terminated automatically.\n\n"
        "Click  manage →  or ⚙ to open App Settings, which scans your "
        "installed apps so you can toggle them on/off.")},
    {"title":"④ Always Blocked","icon":"⊘","body":(
        "Social media sites are blocked two ways:\n\n"
        "  • Browser extension — blocks tabs before they load (Chrome/Edge/Brave)\n"
        "  • Tab sniper — closes any matching tab via Ctrl+W using the keyboard\n    "
        "    library, which works at driver level with no focus stealing needed.\n\n"
        "Install the browser extension from the nothing_alternative/browser_extension\n"
        "folder for the strongest protection.")},
    {"title":"⑤ Session Log","icon":"▸","body":(
        "The log shows live activity during a session:\n\n"
        "  🔵  SYSTEM — status messages\n"
        "  🔴  SNIPER — a distracting tab was closed\n"
        "  🟡  BLOCKER — an unapproved app was terminated\n\n"
        "Elapsed time and blocked count update every second at the bottom.")},
    {"title":"⑥ History","icon":"🕐","body":(
        "Every session is saved automatically. Click 🕐 to open History, "
        "which shows summary cards, an all-time chart of your most-blocked "
        "sites and apps, and a per-session breakdown with exact counts.")},
    {"title":"⑦ Keyboard Shortcuts","icon":"⌨","body":(
        "A few shortcuts to speed things up:\n\n"
        "  Enter  — start a session (when goal field is focused)\n"
        "  Escape — stop an active session\n\n"
        "The app minimises automatically when the session starts. "
        "Use the system tray icon to reopen it.")},
    {"title":"Ready to focus","icon":"▶","body":(
        "That's everything. Here's the quick version:\n\n"
        "  1. Type your goal\n"
        "  2. Choose your profile (or use Default)\n"
        "  3. Hit  Start session  (or press Enter)\n"
        "  4. Work — or do nothing\n\n"
        "Close this window and hit the button whenever you're ready.")},
]

class WalkthroughPanel(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Quick Walkthrough"); self.geometry("460x400")
        self.resizable(False,False); self.configure(fg_color=BG_BASE)
        self.grab_set(); self._step = 0; self._build(); self._render()

    def _build(self):
        self.dot_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.dot_frame.pack(pady=(20,0))
        self.icon_lbl  = ctk.CTkLabel(self, text="", font=("DM Sans",36), text_color=ACCENT)
        self.icon_lbl.pack(pady=(16,0))
        self.title_lbl = ctk.CTkLabel(self, text="", font=("DM Sans",16,"bold"),
                                      text_color=TEXT_PRI, wraplength=380)
        self.title_lbl.pack(pady=(8,0), padx=24)
        self.body_lbl  = ctk.CTkLabel(self, text="", font=("DM Sans",12),
                                      text_color=TEXT_SEC, wraplength=390, justify="left")
        self.body_lbl.pack(pady=(10,0), padx=28, fill="x", expand=True)
        _divider(self, pady=(16,0))
        nav = ctk.CTkFrame(self, fg_color=BG_BASE, corner_radius=0)
        nav.pack(fill="x", padx=20, pady=14)
        self.back_btn = ctk.CTkButton(nav, text="← Back", width=90, height=36,
                                      fg_color=BG_RAISED, hover_color=BORDER,
                                      text_color=TEXT_SEC, font=("DM Sans",12),
                                      corner_radius=8, command=self._back)
        self.back_btn.pack(side="left")
        self.step_lbl = ctk.CTkLabel(nav, text="", font=("DM Mono",10), text_color=TEXT_MUT)
        self.step_lbl.pack(side="left", expand=True)
        self.next_btn = ctk.CTkButton(nav, text="Next →", width=90, height=36,
                                      fg_color=ACCENT, hover_color=ACCENT_HVR,
                                      text_color=TEXT_PRI, font=("DM Sans",12,"bold"),
                                      corner_radius=8, command=self._next)
        self.next_btn.pack(side="right")

    def _render(self):
        step = _STEPS[self._step]; n = len(_STEPS)
        for w in self.dot_frame.winfo_children(): w.destroy()
        for i in range(n):
            color = ACCENT if i==self._step else (BG_RAISED if i<self._step else BORDER)
            c = tk.Canvas(self.dot_frame, width=8, height=8,
                          bg=BG_BASE, highlightthickness=0)
            c.pack(side="left", padx=3)
            c.create_oval(0,0,7,7, fill=color, outline="")
        self.icon_lbl.configure(text=step["icon"])
        self.title_lbl.configure(text=step["title"])
        self.body_lbl.configure(text=step["body"])
        self.step_lbl.configure(text=f"{self._step+1} / {n}")
        self.back_btn.configure(
            state="normal" if self._step>0 else "disabled",
            text_color=TEXT_SEC if self._step>0 else TEXT_MUT)
        if self._step == n-1:
            self.next_btn.configure(text="Done ✓", fg_color=GREEN,
                                    hover_color="#00bb55", text_color="#0a0a0f",
                                    command=self.destroy)
        else:
            self.next_btn.configure(text="Next →", fg_color=ACCENT,
                                    hover_color=ACCENT_HVR, text_color=TEXT_PRI,
                                    command=self._next)

    def _next(self):
        if self._step < len(_STEPS)-1: self._step += 1; self._render()
    def _back(self):
        if self._step > 0:             self._step -= 1; self._render()

class PricingPanel(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Upgrade to Premium")
        self.geometry("720x520")
        self.resizable(False, False)
        self.configure(fg_color=BG_BASE)
        self.grab_set()
        self._loading = False
        self._build()

    def _build(self):
        # ── Header ────────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=BG_BASE, corner_radius=0)
        hdr.pack(fill="x", padx=24, pady=(24, 0))
        ctk.CTkButton(hdr, text="✕", width=28, height=28,
                      fg_color="transparent", hover_color=BG_RAISED,
                      text_color=TEXT_MUT, font=("DM Sans", 14),
                      corner_radius=99, command=self.destroy).pack(side="right")
        ctk.CTkLabel(hdr, text="Upgrade to Premium",
                     font=("DM Sans", 18, "bold"),
                     text_color=TEXT_PRI).pack(side="left")

        ctk.CTkLabel(self,
                     text="Unlock cross-device sync, unlimited profiles, and full session history.",
                     font=("DM Sans", 12), text_color=TEXT_SEC,
                     wraplength=500).pack(pady=(8, 24))

        # ── Plan cards ────────────────────────────────────────────────────────
        cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        cards_frame.pack(fill="x", padx=20)

        plans = [
            {
                "plan":     "monthly",
                "name":     "Monthly",
                "price":    "$4.99",
                "period":   "per month",
                "detail":   "Billed monthly.\nCancel anytime.",
                "badge":    None,
                "color":    BORDER,
                "btn_color": ACCENT,
            },
            {
                "plan":     "yearly",
                "name":     "Yearly",
                "price":    "$29.99",
                "period":   "per year",
                "detail":   "Just $2.50/month.\nSave 50% vs monthly.",
                "badge":    "BEST VALUE",
                "color":    ACCENT,
                "btn_color": ACCENT,
            },
            {
                "plan":     "lifetime",
                "name":     "Lifetime",
                "price":    "$89.99",
                "period":   "one-time",
                "detail":   "Pay once, own forever.\nNo recurring charges.",
                "badge":    None,
                "color":    BORDER,
                "btn_color": "#336633",
            },
        ]

        for p in plans:
            self._make_card(cards_frame, p)

        # ── Footer note ───────────────────────────────────────────────────────
        ctk.CTkLabel(self,
                     text="All plans include a 7-day free trial · Secure payment via Stripe",
                     font=("DM Mono", 9), text_color=TEXT_MUT
                     ).pack(pady=(20, 0))

        # Status label for loading/error feedback
        self._status = ctk.CTkLabel(self, text="",
                                    font=("DM Mono", 10),
                                    text_color=TEXT_MUT)
        self._status.pack(pady=(6, 0))

    def _make_card(self, parent, plan):
        is_featured = plan["badge"] is not None

        card = ctk.CTkFrame(parent,
                            fg_color=BG_RAISED if is_featured else BG_SURFACE,
                            border_color=plan["color"],
                            border_width=2 if is_featured else 1,
                            corner_radius=14)
        card.pack(side="left", fill="both", expand=True,
                  padx=(0, 10) if plan["plan"] != "lifetime" else (0, 0))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(padx=10, pady=12, fill="both", expand=True)

        # Badge
        if plan["badge"]:
            badge = ctk.CTkFrame(inner, fg_color=ACCENT,
                                 corner_radius=6)
            badge.pack(anchor="w", pady=(0, 10))
            ctk.CTkLabel(badge, text=plan["badge"],
                         font=("DM Mono", 8, "bold"),
                         text_color=TEXT_PRI).pack(padx=8, pady=3)
        else:
            # Spacer so cards align
            ctk.CTkFrame(inner, fg_color="transparent",
                         height=27).pack(anchor="w", pady=(0, 10))

        # Plan name
        ctk.CTkLabel(inner, text=plan["name"],
                     font=("DM Sans", 14, "bold"),
                     text_color=TEXT_PRI).pack(anchor="w")

        # Price
        ctk.CTkLabel(inner, text=plan["price"],
                     font=("DM Sans", 28, "bold"),
                     text_color=TEXT_PRI).pack(anchor="w", pady=(6, 0))

        # Period
        ctk.CTkLabel(inner, text=plan["period"],
                     font=("DM Mono", 10),
                     text_color=TEXT_MUT).pack(anchor="w")

        # Divider
        ctk.CTkFrame(inner, fg_color=BORDER, height=1,
                     corner_radius=0).pack(fill="x", pady=12)

        # Detail text
        ctk.CTkLabel(inner, text=plan["detail"],
                     font=("DM Sans", 11),
                     text_color=TEXT_SEC,
                     justify="left").pack(anchor="w")

        # Spacer to push button to bottom
        ctk.CTkFrame(inner, fg_color="transparent",
                     height=12).pack(expand=True)

        # Choose button
        btn_text = f"Choose {plan['name']}"
        ctk.CTkButton(inner, text=btn_text,
                      font=("DM Sans", 12, "bold"),
                      fg_color=plan["btn_color"],
                      hover_color=ACCENT_HVR if plan["btn_color"] == ACCENT else "#225522",
                      text_color=TEXT_PRI,
                      corner_radius=8, height=36,
                      command=lambda pl=plan["plan"]: self._choose(pl)
                      ).pack(fill="x", pady=(8, 0))

    def _choose(self, plan: str):
        if self._loading:
            return
        self._loading = True
        self._status.configure(text="Opening checkout…", text_color=TEXT_MUT)

        def _fetch():
            data = _api_post("/billing/checkout", {"plan": plan})
            if data and "checkout_url" in data:
                import webbrowser
                webbrowser.open(data["checkout_url"])
                self.after(0, self.destroy)
            else:
                self._loading = False
                self.after(0, self._status.configure,
                           {"text": "⚠  Could not open checkout. Try again.",
                            "text_color": AMBER})

        threading.Thread(target=_fetch, daemon=True).start()
# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE OAUTH — local-redirect flow
# Opens the browser → user signs in → Google redirects to localhost:59285/callback
# We capture the code, exchange it for tokens, send the id_token to our backend.
# ══════════════════════════════════════════════════════════════════════════════
class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """One-shot handler: captures ?code=… and signals the waiting thread."""
    code:  str | None = None
    state: str | None = None
    error: str | None = None
    _server_ref = None      # set by GoogleOAuthFlow before starting

    def do_GET(self):
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        _OAuthCallbackHandler.code  = (params.get("code",  [None])[0])
        _OAuthCallbackHandler.error = (params.get("error", [None])[0])
        _OAuthCallbackHandler.state = (params.get("state", [None])[0])

        body = b"""<!doctype html><html><head>
<meta charset="utf-8">
<style>
  body{margin:0;display:flex;align-items:center;justify-content:center;
       min-height:100vh;background:#0e0e0f;font-family:'DM Sans',sans-serif;color:#fff}
  .box{text-align:center;max-width:340px}
  .icon{font-size:48px;margin-bottom:16px}
  h2{margin:0 0 8px;font-size:20px}
  p{color:#8888aa;font-size:14px;margin:0}
</style></head><body>
<div class="box">
  <div class="icon">&#x2713;</div>
  <h2>Signed in</h2>
  <p>You can close this tab and return to Nothing Alternative.</p>
</div></body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

        # Shut the server down from a separate thread so do_GET can return first
        threading.Thread(target=self._server_ref.shutdown, daemon=True).start()

    def log_message(self, *_):
        pass


class GoogleOAuthFlow:
    """
    Runs a full Google OAuth 2.0 Authorization Code flow (PKCE-free, secret-based).
    Call `start(callback)` — callback receives (token_data: dict | None, error: str | None).
    token_data shape matches /auth/google response: {access_token, user_id, email, display_name}.
    Works on Windows, macOS, Linux — no platform-specific SDK required.
    """
    _GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
    _GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

    def __init__(self):
        self._state = secrets.token_urlsafe(16)

    def _build_auth_url(self) -> str:
        params = {
            "client_id":     GOOGLE_CLIENT_ID,
            "redirect_uri":  OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope":         "openid email profile",
            "state":         self._state,
            "access_type":   "online",
            "prompt":        "select_account",
        }
        return self._GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)

    def start(self, callback):
        if not GOOGLE_CLIENT_ID:
            callback(None, "Google client ID not configured.")
            return

        _OAuthCallbackHandler.code  = None
        _OAuthCallbackHandler.error = None
        _OAuthCallbackHandler.state = None

        try:
            srv = HTTPServer(("localhost", OAUTH_REDIRECT_PORT), _OAuthCallbackHandler)
        except OSError as e:
            callback(None, f"Could not open OAuth redirect listener: {e}")
            return

        _OAuthCallbackHandler._server_ref = srv
        webbrowser.open(self._build_auth_url())

        def _run():
            srv.serve_forever()   # blocks until handler calls shutdown()
            code  = _OAuthCallbackHandler.code
            err   = _OAuthCallbackHandler.error
            state = _OAuthCallbackHandler.state

            if err:
                callback(None, f"Google sign-in cancelled or denied: {err}")
                return
            if not code:
                callback(None, "No authorisation code received from Google.")
                return
            if state != self._state:
                callback(None, "OAuth state mismatch — possible CSRF. Please try again.")
                return

            # Send the raw auth code to the backend — the backend holds the
            # client secret and does the exchange + sign-in in one call.
            try:
                if not _HAS_HTTPX:
                    import urllib.request
                    body = json.dumps({
                        "code": code,
                        "redirect_uri": OAUTH_REDIRECT_URI,
                    }).encode()
                    req = urllib.request.Request(
                        f"{API_BASE}/auth/google/exchange", data=body, method="POST",
                        headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=10) as r:
                        resp = json.loads(r.read())
                else:
                    r = _httpx.post(
                        f"{API_BASE}/auth/google/exchange",
                        json={"code": code, "redirect_uri": OAUTH_REDIRECT_URI},
                        timeout=10,
                    )
                    resp = r.json()
            except Exception as e:
                callback(None, f"Backend sign-in failed: {e}")
                return
            if "access_token" not in resp:
                callback(None, f"Backend error: {resp.get('detail', resp)}")
                return
            callback(resp, None)

        threading.Thread(target=_run, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
# SIGN-IN FRAME
# Fills the window on first launch.  On success it destroys itself and calls
# on_success(token_data) so the main app can build its UI.
# ══════════════════════════════════════════════════════════════════════════════
class SignInFrame(ctk.CTkFrame):
    def __init__(self, parent, on_success):
        super().__init__(parent, fg_color=BG_BASE, corner_radius=0)
        self.on_success = on_success
        self._flow: GoogleOAuthFlow | None = None
        self._build()

    def _build(self):
        self.place(relx=0, rely=0, relwidth=1, relheight=1)

        # ── Logo area ─────────────────────────────────────────────────────────
        logo_frame = ctk.CTkFrame(self, fg_color="transparent")
        logo_frame.place(relx=0.5, rely=0.30, anchor="center")

        icon_box = ctk.CTkFrame(logo_frame, width=52, height=52,
                                fg_color="transparent",
                                border_color=ACCENT, border_width=1,
                                corner_radius=14)
        icon_box.pack(pady=(0, 14)); icon_box.pack_propagate(False)
        ctk.CTkLabel(icon_box, text="∅", font=("DM Mono", 24, "bold"),
                     text_color=ACCENT).place(relx=.5, rely=.5, anchor="center")

        ctk.CTkLabel(logo_frame, text="Nothing Alternative",
                     font=("DM Sans", 22, "bold"),
                     text_color=TEXT_PRI).pack()
        ctk.CTkLabel(logo_frame, text="Sign in to sync sessions across devices",
                     font=("DM Sans", 12),
                     text_color=TEXT_SEC).pack(pady=(4, 0))

        # ── Card ──────────────────────────────────────────────────────────────
        card = ctk.CTkFrame(self, fg_color=BG_SURFACE,
                            border_color=BORDER, border_width=1,
                            corner_radius=14, width=340)
        card.place(relx=0.5, rely=0.58, anchor="center")
        card.pack_propagate(False)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(padx=28, pady=28, fill="both", expand=True)

        # Google sign-in button
        g_btn = ctk.CTkFrame(inner, fg_color=BG_RAISED,
                              border_color=BORDER, border_width=1,
                              corner_radius=10, cursor="hand2")
        g_btn.pack(fill="x", pady=(0, 14))
        g_inner = ctk.CTkFrame(g_btn, fg_color="transparent")
        g_inner.pack(padx=16, pady=13)

        # Google "G" logo drawn in pure tkinter (no image dependency)
        g_canvas = tk.Canvas(g_inner, width=20, height=20,
                             bg=BG_RAISED, highlightthickness=0)
        g_canvas.pack(side="left", padx=(0, 10))
        g_canvas.create_arc(2, 2, 18, 18, start=0, extent=360,
                            outline="#4285F4", width=3, style="arc")
        g_canvas.create_line(11, 10, 18, 10, fill="#4285F4", width=3)
        g_canvas.create_arc(2, 2, 18, 18, start=-45, extent=-135,
                            outline="#EA4335", width=3, style="arc")
        g_canvas.create_arc(2, 2, 18, 18, start=90, extent=90,
                            outline="#34A853", width=3, style="arc")
        g_canvas.create_arc(2, 2, 18, 18, start=180, extent=90,
                            outline="#FBBC05", width=3, style="arc")

        self._g_lbl = ctk.CTkLabel(g_inner, text="Continue with Google",
                                   font=("DM Sans", 13, "bold"),
                                   text_color=TEXT_PRI)
        self._g_lbl.pack(side="left")

        # Bind click to whole button area
        for w in [g_btn, g_inner, g_canvas, self._g_lbl]:
            w.bind("<Button-1>", lambda _: self._start_google())
            w.bind("<Enter>", lambda _: g_btn.configure(fg_color="#222228"))
            w.bind("<Leave>", lambda _: g_btn.configure(fg_color=BG_RAISED))

        # Divider
        div_row = ctk.CTkFrame(inner, fg_color="transparent")
        div_row.pack(fill="x", pady=(0, 14))
        ctk.CTkFrame(div_row, fg_color=BORDER, height=1,
                     corner_radius=0).pack(side="left", fill="x",
                                           expand=True, pady=7)
        ctk.CTkLabel(div_row, text="  or  ", font=("DM Mono", 9),
                     text_color=TEXT_MUT).pack(side="left")
        ctk.CTkFrame(div_row, fg_color=BORDER, height=1,
                     corner_radius=0).pack(side="left", fill="x",
                                           expand=True, pady=7)

        # Offline / skip
        ctk.CTkButton(inner, text="Use offline (no sync)",
                      font=("DM Sans", 12),
                      fg_color="transparent", hover_color=BG_RAISED,
                      border_color=BORDER, border_width=1,
                      text_color=TEXT_MUT, corner_radius=10, height=40,
                      command=self._skip).pack(fill="x")

        # Status label
        self._status = ctk.CTkLabel(self, text="",
                                    font=("DM Mono", 10),
                                    text_color=TEXT_MUT, wraplength=300)
        self._status.place(relx=0.5, rely=0.85, anchor="center")

        # Fine print
        ctk.CTkLabel(self,
                     text="Your data stays on your device in offline mode.\n"
                          "Sign in to sync profiles & history across all devices.",
                     font=("DM Sans", 10), text_color=TEXT_MUT,
                     justify="center").place(relx=0.5, rely=0.93, anchor="center")

    # ── Actions ───────────────────────────────────────────────────────────────
    def _start_google(self):
        self._g_lbl.configure(text="Opening browser…")
        self._status.configure(text="Sign in with your Google account in the browser window.",
                                text_color=TEXT_MUT)
        self._flow = GoogleOAuthFlow()
        self._flow.start(self._on_auth_result)

    def _on_auth_result(self, token_data: dict | None, error: str | None):
        # Called from a daemon thread — must schedule back onto the Tk event loop
        self.after(0, self._apply_result, token_data, error)

    def _apply_result(self, token_data: dict | None, error: str | None):
        if error:
            self._g_lbl.configure(text="Continue with Google")
            self._status.configure(
                text=f"⚠  {error}", text_color=AMBER)
            return
        if token_data:
            self._status.configure(text="✓  Signed in — loading…", text_color=GREEN)
            self.after(400, lambda: self.on_success(token_data))

    def _skip(self):
        self.on_success(None)   # None = offline mode


# ══════════════════════════════════════════════════════════════════════════════
# MAIN APP
# ══════════════════════════════════════════════════════════════════════════════
class NothingAlternative(ctk.CTk):
    def __init__(self):
        super().__init__()
        global API_TOKEN

        self.cfg              = load_config()
        self.session_active   = False
        self.elapsed          = 0
        self._session_goal    = ""
        self._timer_id        = None
        self._log_poll_id     = None
        self._title_clock_id  = None
        self._settings_panel  = None
        self._history_panel   = None
        self._profiles_panel  = None
        self._walkthrough_panel = None
        self._user_info: dict | None = None   # set after sign-in
        self._poll_stop     = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._poll_interval = 10
        self._sync_debounce_id = None

        self._break_active   = False
        self._break_timer_id = None
        
        self.title("Nothing Alternative")
        self.geometry("480x700")
        self.minsize(400, 560)
        self.resizable(True, True)
        self.configure(fg_color=BG_BASE)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.tray = TrayManager(self)
        self.tray.start()

        # ── Auth gate ─────────────────────────────────────────────────────────
        saved = load_saved_token()
        if saved and saved.get("access_token"):
            # Validate the saved token in the background; if it fails, show sign-in
            API_TOKEN = saved["access_token"]
            self._user_info = saved
            self._finish_init()
            # Validate asynchronously — revoke & re-auth if expired
            threading.Thread(target=self._validate_saved_token,
                             daemon=True).start()
        else:
            self._sign_in_frame = SignInFrame(self, self._on_sign_in)

    def _on_sign_in(self, token_data: dict | None):
        """Called by SignInFrame on success (token_data) or skip (None)."""
        global API_TOKEN
        if hasattr(self, "_sign_in_frame"):
            self._sign_in_frame.destroy()
            del self._sign_in_frame

        if token_data:
            API_TOKEN = token_data["access_token"]
            self._user_info = token_data
            save_token(token_data)
        else:
            API_TOKEN = None
            self._user_info = None

        self._finish_init()

    def _finish_init(self):
        """Builds the main UI — called once after auth is resolved."""
        self._build_ui()
        self._load_chips()
        self.after(100, self._reflow_chips)
        self.bind("<Escape>",
                  lambda _: self._stop_session() if self.session_active else None)
        self.goal_entry.bind("<Return>",
                             lambda _: self._start_session() if not self.session_active else None)
        # Pull profiles from the backend after sign-in (offline-safe)
        if API_TOKEN:
            threading.Thread(target=self._fetch_profiles_from_backend,
                             daemon=True).start()
            self._start_poll_thread(interval=10)
        threading.Thread(target=self._flush_pending_sync, daemon=True).start()

    def _validate_saved_token(self):
        """Background thread: hits /auth/me to confirm the JWT is still valid."""
        if not _HAS_HTTPX:
            return  # can't validate without httpx; trust the saved token
        try:
            r = _httpx.get(f"{API_BASE}/auth/me",
                           headers=api_headers(), timeout=8)
            if r.status_code == 401:
                # Token expired or revoked — ask user to sign in again
                self.after(0, self._force_reauth)
        except Exception:
            pass   # network unreachable; stay offline, keep using local config

    def _force_reauth(self):
        """Clears the saved token and shows the sign-in frame over the existing UI."""
        global API_TOKEN
        API_TOKEN = None
        self._user_info = None
        clear_token()
        # Teardown existing UI so sign-in frame has a clean slate
        for child in self.winfo_children():
            child.destroy()
        self._sign_in_frame = SignInFrame(self, self._on_sign_in)

    def _sign_out(self):
        global API_TOKEN
        API_TOKEN = None
        self._user_info = None
        clear_token()
        self._stop_poll_thread()
        for child in self.winfo_children():
            child.destroy()
        self._sign_in_frame = SignInFrame(self, self._on_sign_in)

    def _start_poll_thread(self, interval: int = 10) -> None:
        self._stop_poll_thread()
        self._poll_stop.clear()
        self._poll_interval = interval
        def _loop():
            while not self._poll_stop.wait(timeout=self._poll_interval):
                data = _api_get("/sessions/status")
                if data:
                    self.after(0, self._apply_remote_status, data)
        self._poll_thread = threading.Thread(target=_loop, daemon=True)
        self._poll_thread.start()

    def _stop_poll_thread(self) -> None:
        self._poll_stop.set()

    def _set_poll_interval(self, interval: int) -> None:
        self._poll_interval = interval

    # ── UI BUILD ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        pad = {"padx":24, "fill":"x"}

        # Header
        hdr = ctk.CTkFrame(self, fg_color=BG_BASE, corner_radius=0)
        hdr.pack(fill="x", padx=24, pady=(20,0))
        logo = ctk.CTkFrame(hdr, fg_color="transparent"); logo.pack(side="left")
        lb = ctk.CTkFrame(logo, width=28, height=28, fg_color="transparent",
                          border_color=ACCENT, border_width=1, corner_radius=8)
        lb.pack(side="left"); lb.pack_propagate(False)
        ctk.CTkLabel(lb, text="∅", font=("DM Mono",13,"bold"),
                     text_color=ACCENT).place(relx=.5,rely=.5,anchor="center")
        ctk.CTkLabel(logo, text="  Nothing Alternative",
                     font=("DM Sans",13,"bold"), text_color=TEXT_PRI).pack(side="left")
        ctk.CTkLabel(logo, text=" v5", font=("DM Mono",10),
                     text_color=TEXT_MUT).pack(side="left")
        hr = ctk.CTkFrame(hdr, fg_color="transparent"); hr.pack(side="right")
        for icon, cmd, tip in [
            ("?",  self._open_walkthrough, "Quick walkthrough"),
            ("🕐", self._open_history,     "Session history"),
            ("⚙",  self._open_settings,    "App settings"),
        ]:
            btn = ctk.CTkButton(hr, text=icon, width=28, height=28,
                                fg_color="transparent", hover_color=BG_RAISED,
                                text_color=TEXT_MUT, font=("DM Sans",15),
                                corner_radius=8, command=cmd)
            btn.pack(side="left", padx=(4,0))
            Tooltip(btn, tip)
            if icon == "?": self._walkthrough_btn = btn

        # User pill (sign-out)
        if self._user_info:
            name = (self._user_info.get("display_name") or
                    self._user_info.get("email", "")).split()[0][:12]
            user_pill = ctk.CTkFrame(hr, fg_color=BG_RAISED,
                                     border_color=BORDER, border_width=1,
                                     corner_radius=99, cursor="hand2")
            user_pill.pack(side="left", padx=(8, 0))
            ctk.CTkLabel(user_pill, text=f"⬤  {name}",
                         font=("DM Mono", 9), text_color=TEXT_MUT
                         ).pack(padx=8, pady=3)
            Tooltip(user_pill, f"Signed in as {self._user_info.get('email','')}\nClick to sign out")
            user_pill.bind("<Button-1>", lambda _: self._sign_out())
            for child in user_pill.winfo_children():
                child.bind("<Button-1>", lambda _: self._sign_out())
        sf = ctk.CTkFrame(hr, fg_color="transparent"); sf.pack(side="left", padx=(10,0))
        self.dot_canvas = tk.Canvas(sf, width=8, height=8,
                                    bg=BG_BASE, highlightthickness=0)
        self.dot_canvas.pack(side="left", padx=(0,5))
        self.dot_oval = self.dot_canvas.create_oval(1,1,7,7,fill=TEXT_MUT,outline="")
        self.status_lbl = ctk.CTkLabel(sf, text="idle",
                                       font=("DM Mono",10), text_color=TEXT_MUT)
        self.status_lbl.pack(side="left")

        _divider(self, pady=(16,0))

        self.main = ctk.CTkScrollableFrame(self, fg_color=BG_BASE,
                                           scrollbar_button_color=BORDER,
                                           scrollbar_button_hover_color=TEXT_MUT)
        self.main.pack(fill="both", expand=True)
        self.main._scrollbar.configure(width=4)
        
        # Subscription indicator
        self._sub_indicator = ctk.CTkLabel(
            hr,
            text="Trial · 7d left",
            font=("DM Mono", 9),
            text_color="#5555cc",
            cursor="hand2"
        )
        self._sub_indicator.pack(side="left", padx=(8, 0))
        self._sub_indicator.bind("<Button-1>", lambda _: self._open_upgrade())

        # Streak badge — only shown when streak > 0
        streak = self.cfg.get("streak_days", 0)
        if streak > 0:
            sb = ctk.CTkFrame(self.main, fg_color="transparent")
            sb.pack(fill="x", padx=24, pady=(16, 0))
            badge = ctk.CTkFrame(sb, fg_color="#1a1a0e", border_color="#3a3a00",
                                 border_width=1, corner_radius=8)
            badge.pack(side="left")
            ctk.CTkLabel(badge, text=f"🔥  {streak} day streak",
                         font=("DM Mono", 10), text_color=AMBER
                         ).pack(padx=10, pady=5)
            
        # Goal
        _section_label(self.main, "SESSION GOAL", pady=(20,6))
        gf = ctk.CTkFrame(self.main, fg_color=BG_SURFACE, border_color=BORDER,
                          border_width=1, corner_radius=10)
        gf.pack(**pad)
        # Templates dropdown — shown only when templates exist
        self._templates_frame = ctk.CTkFrame(self.main, fg_color="transparent")
        self._templates_frame.pack(fill="x", padx=24, pady=(4, 0))
        self._render_templates()
        ctk.CTkLabel(gf, text="✎", font=("DM Sans",13),
                     text_color=TEXT_MUT).pack(side="left", padx=(14,0))
        self.goal_entry = ctk.CTkEntry(gf, placeholder_text="What are you working on?",
                                       font=("DM Sans",13), fg_color="transparent",
                                       border_width=0, text_color=TEXT_PRI,
                                       placeholder_text_color=TEXT_MUT, height=44)
        self.goal_entry.pack(side="left", fill="x", expand=True, padx=(6,6))
        if self.cfg.get("last_goal"): self.goal_entry.insert(0, self.cfg["last_goal"])
        self._char_lbl = ctk.CTkLabel(gf, text=f"{len(self.cfg.get('last_goal',''))}/80",
                                      font=("DM Mono",9), text_color=TEXT_MUT, width=36)
        self._char_lbl.pack(side="right", padx=(0,10))
        self.goal_entry.bind("<KeyRelease>", self._update_char_count)

        # Profile badge
        ph = ctk.CTkFrame(self.main, fg_color="transparent")
        ph.pack(fill="x", padx=24, pady=(16,4))
        ctk.CTkLabel(ph, text="PROFILE", font=("DM Mono",9),
                     text_color=TEXT_MUT).pack(side="left")
        self.profile_badge_frame = ctk.CTkFrame(ph, fg_color="transparent")
        self.profile_badge_frame.pack(side="left", padx=(10,0))
        self._render_profile_badge()

        # Allowed apps
        ah = ctk.CTkFrame(self.main, fg_color="transparent")
        ah.pack(fill="x", padx=24, pady=(16,6))
        ctk.CTkLabel(ah, text="ALLOWED APPS", font=("DM Mono",9),
                     text_color=TEXT_MUT).pack(side="left")
        ctk.CTkButton(ah, text="manage →", font=("DM Mono",9),
                      fg_color="transparent", hover_color=BG_RAISED,
                      text_color=ACCENT, width=70, height=16,
                      corner_radius=4, command=self._open_settings).pack(side="right")
        self.chips_outer = ctk.CTkFrame(self.main, fg_color="transparent")
        self.chips_outer.pack(**pad)
        self.chips_wrap = WrapFrame(self.chips_outer, bg=BG_BASE, bd=0, highlightthickness=0)
        self.chips_wrap.pack(fill="x", expand=True)

        _divider(self.main, pady=(20,0))

        # Always blocked
        bh = ctk.CTkFrame(self.main, fg_color="transparent")
        bh.pack(fill="x", padx=24, pady=(16,6))
        ctk.CTkLabel(bh, text="ALWAYS BLOCKED", font=("DM Mono",9),
                    text_color=TEXT_MUT).pack(side="left")
        ctk.CTkButton(bh, text="manage →", font=("DM Mono",9),
                    fg_color="transparent", hover_color=BG_RAISED,
                    text_color=ACCENT, width=70, height=16,
                    corner_radius=4, command=self._open_blocked).pack(side="right")

        self.blocked_outer = ctk.CTkFrame(self.main, fg_color="transparent")
        self.blocked_outer.pack(**pad)
        self.blocked_wrap = WrapFrame(self.blocked_outer, bg=BG_BASE, bd=0, highlightthickness=0)
        self.blocked_wrap.pack(fill="x", expand=True)
        self._load_blocked_chips()

        # Extension status indicator
        _section_label(self.main, "BLOCKING METHODS", pady=(20,6))
        mf = ctk.CTkFrame(self.main, fg_color=BG_SURFACE, border_color=BORDER,
                          border_width=1, corner_radius=10)
        mf.pack(**pad, pady=(0,4))
        # keyboard lib row
        kb_color = GREEN if _HAS_KEYBOARD else AMBER
        kb_text  = "keyboard lib  ·  driver-level Ctrl+W" if _HAS_KEYBOARD \
                   else "keyboard lib missing  ·  pip install keyboard"
        kb_row = ctk.CTkFrame(mf, fg_color="transparent"); kb_row.pack(fill="x", padx=14, pady=(10,4))
        dot1 = tk.Canvas(kb_row, width=8, height=8, bg=BG_SURFACE, highlightthickness=0)
        dot1.pack(side="left", padx=(0,8)); dot1.create_oval(0,0,7,7, fill=kb_color, outline="")
        ctk.CTkLabel(kb_row, text=kb_text, font=("DM Mono",10),
                     text_color=TEXT_SEC, anchor="w").pack(side="left")
        # extension row
        ext_row = ctk.CTkFrame(mf, fg_color="transparent"); ext_row.pack(fill="x", padx=14, pady=(0,10))
        dot2 = tk.Canvas(ext_row, width=8, height=8, bg=BG_SURFACE, highlightthickness=0)
        dot2.pack(side="left", padx=(0,8)); dot2.create_oval(0,0,7,7, fill=ACCENT, outline="")
        ctk.CTkLabel(ext_row, text="browser extension  ·  blocks before page loads",
                     font=("DM Mono",10), text_color=TEXT_SEC, anchor="w").pack(side="left")

        # Log
        _section_label(self.main, "SESSION LOG", pady=(16,6))
        self.log_box = ctk.CTkTextbox(self.main, height=110, fg_color="#0a0a0c",
                                      border_color=BORDER, border_width=1,
                                      font=("DM Mono",10), text_color=TEXT_MUT,
                                      corner_radius=8, state="disabled", wrap="word")
        self.log_box.pack(**pad, pady=(0,20))
        self.log_box.tag_config("system", foreground=ACCENT)
        self.log_box.tag_config("sniper", foreground=RED)
        self.log_box.tag_config("blocker", foreground=AMBER)

        # Bottom bar
        _divider(self)
        bottom = ctk.CTkFrame(self, fg_color=BG_BASE, corner_radius=0)
        bottom.pack(fill="x", padx=24, pady=16)
        meta = ctk.CTkFrame(bottom, fg_color="transparent"); meta.pack(fill="x", pady=(0,10))
        self.elapsed_lbl = ctk.CTkLabel(meta, text="elapsed  00:00",
                                        font=("DM Mono",10), text_color=TEXT_MUT)
        self.elapsed_lbl.pack(side="left")
        self.blocked_lbl = ctk.CTkLabel(meta, text="blocked  0",
                                        font=("DM Mono",10), text_color=TEXT_MUT)
        self.blocked_lbl.pack(side="right")
        self.progress = ctk.CTkProgressBar(bottom, height=2, fg_color=BORDER,
                                           progress_color=ACCENT, corner_radius=99)
        self.progress.pack(fill="x", pady=(0,14)); self.progress.set(0)
        self.start_btn = ctk.CTkButton(bottom, text="▶  Start session",
                                       font=("DM Sans",13,"bold"),
                                       fg_color=ACCENT, hover_color=ACCENT_HVR,
                                       text_color=TEXT_PRI, corner_radius=10,
                                       height=46, command=self._toggle_session)
        self.start_btn.pack(fill="x")
        self.break_btn = ctk.CTkButton(bottom, text="Take a break",
                                       font=("DM Sans", 11),
                                       fg_color="transparent", hover_color=BG_RAISED,
                                       border_color=BORDER, border_width=1,
                                       text_color=TEXT_MUT, corner_radius=8,
                                       height=34, command=self._open_break_picker)
        self.break_btn.pack(fill="x", pady=(8, 0))
        self.break_btn.pack_forget()  # hidden until session starts

    def _render_templates(self):
        for w in self._templates_frame.winfo_children(): w.destroy()
        templates = self.cfg.get("goal_templates", [])
        if not templates: return
        ctk.CTkLabel(self._templates_frame, text="RECENT GOALS",
                     font=("DM Mono", 9), text_color=TEXT_MUT).pack(anchor="w", pady=(0, 4))
        row = ctk.CTkFrame(self._templates_frame, fg_color="transparent")
        row.pack(fill="x")
        for t in templates[:5]:  # show max 5
            btn = ctk.CTkFrame(row, fg_color=BG_SURFACE, border_color=BORDER,
                               border_width=1, corner_radius=6, cursor="hand2")
            btn.pack(side="left", padx=(0, 6))
            lbl = ctk.CTkLabel(btn, text=t[:24], font=("DM Sans", 11),
                               text_color=TEXT_SEC)
            lbl.pack(padx=8, pady=4)
            for w in [btn, lbl]:
                w.bind("<Button-1>", lambda _, goal=t: self._apply_template(goal))

    def _apply_template(self, goal: str):
        self.goal_entry.delete(0, "end")
        self.goal_entry.insert(0, goal)
        self._update_char_count()

    def _save_goal_as_template(self, goal: str):
        templates = self.cfg.setdefault("goal_templates", [])
        if goal in templates:
            templates.remove(goal)
        templates.insert(0, goal)
        self.cfg["goal_templates"] = templates[:10]  # keep last 10
        save_config(self.cfg)
        self._render_templates()

    # ── HELPERS ───────────────────────────────────────────────────────────────
    def _update_char_count(self, _=None):
        n = len(self.goal_entry.get())
        color = RED if n>80 else (AMBER if n>60 else TEXT_MUT)
        self._char_lbl.configure(text=f"{n}/80", text_color=color)

    def _render_profile_badge(self):
        for w in self.profile_badge_frame.winfo_children(): w.destroy()
        name = self.cfg.get("active_profile","Default")
        badge = ctk.CTkFrame(self.profile_badge_frame, fg_color="#1a1a2e",
                             border_color="#3333aa", border_width=1, corner_radius=6)
        badge.pack(side="left")
        ctk.CTkLabel(badge, text=f"◈  {name}", font=("DM Mono",9),
                     text_color="#5555cc").pack(padx=10, pady=4)
        ctk.CTkButton(self.profile_badge_frame, text="switch →", font=("DM Mono",9),
                      fg_color="transparent", hover_color=BG_RAISED,
                      text_color=TEXT_MUT, width=60, height=16,
                      corner_radius=4, command=self._open_profiles
                      ).pack(side="left", padx=(8,0))

    def _schedule_sync_profiles(self):
        if self._sync_debounce_id:
            self.after_cancel(self._sync_debounce_id)
        self._sync_debounce_id = self.after(
            800, lambda: threading.Thread(
                target=self._sync_profiles_to_backend, daemon=True).start())
        
    # ── PANEL OPENERS ─────────────────────────────────────────────────────────
    def _open_settings(self):
        if self._settings_panel and self._settings_panel.winfo_exists():
            self._settings_panel.focus(); return
        self._settings_panel = SettingsPanel(self, self.cfg, self._refresh_chips)

    def _open_walkthrough(self):
        if self.session_active: return
        if self._walkthrough_panel and self._walkthrough_panel.winfo_exists():
            self._walkthrough_panel.focus(); return
        self._walkthrough_panel = WalkthroughPanel(self)

    def _open_history(self):
        if self._history_panel and self._history_panel.winfo_exists():
            self._history_panel.focus(); return
        self._history_panel = HistoryPanel(self, self.cfg)

    def _open_profiles(self):
        if self._profiles_panel and self._profiles_panel.winfo_exists():
            self._profiles_panel.focus(); return
        self._profiles_panel = ProfilesPanel(self, self.cfg, self._on_profile_change)

    def _on_profile_change(self):
        self._render_profile_badge()
        self._refresh_chips()
        self._refresh_blocked_chips()    # ← add this line
        self._schedule_sync_profiles()

    # ── CHIPS ─────────────────────────────────────────────────────────────────
    def _load_chips(self):
        for app in active_profile(self.cfg).get("allowed_apps",[]): self._place_chip(app)

    def _place_chip(self, name):
        AppChip(self.chips_wrap, name, on_remove=self._remove_app).place(x=0,y=0)
        self.after(50, self._reflow_chips)

    def _reflow_chips(self): self.chips_wrap._reflow()

    def _refresh_chips(self):
        for w in self.chips_wrap.winfo_children(): w.destroy()
        for app in active_profile(self.cfg).get("allowed_apps",[]): self._place_chip(app)
        self.after(80, self._reflow_chips)
        # Push the updated profile to the backend
        self._schedule_sync_profiles()

    def _remove_app(self, name):
        prof = active_profile(self.cfg)
        if name in prof["allowed_apps"]: prof["allowed_apps"].remove(name); save_config(self.cfg, touched_profile=self.cfg.get("active_profile", "Default"))
        for c in self.chips_wrap.winfo_children():
            if isinstance(c, AppChip) and c.label_text == name: c.destroy(); break
        self.after(50, self._reflow_chips)
        # Push the updated profile to the backend
        self._schedule_sync_profiles()

    def _load_blocked_chips(self):
        for kw in active_profile(self.cfg).get("banned_keywords", []):
            self._place_blocked_chip(kw)

    def _place_blocked_chip(self, name):
        BlockedChip(self.blocked_wrap, name,
                    on_remove=self._remove_blocked).place(x=0, y=0)
        self.after(50, self._reflow_blocked)

    def _reflow_blocked(self):
        self.blocked_wrap._reflow()

    def _refresh_blocked_chips(self):
        for w in self.blocked_wrap.winfo_children():
            w.destroy()
        for kw in active_profile(self.cfg).get("banned_keywords", []):
            self._place_blocked_chip(kw)
        self.after(80, self._reflow_blocked)
        self._schedule_sync_profiles()

    def _remove_blocked(self, name):
        prof = active_profile(self.cfg)
        if name in prof["banned_keywords"]:
            prof["banned_keywords"].remove(name)
            save_config(self.cfg, touched_profile=self.cfg.get("active_profile", "Default"))
        for c in self.blocked_wrap.winfo_children():
            if isinstance(c, BlockedChip) and c.label_text == name:
                c.destroy()
                break
        self.after(50, self._reflow_blocked)
        self._schedule_sync_profiles()

    def _open_blocked(self):
        if hasattr(self, "_blocked_panel") and self._blocked_panel and \
        self._blocked_panel.winfo_exists():
            self._blocked_panel.focus()
            return
        self._blocked_panel = BlockedPanel(self, self.cfg, self._refresh_blocked_chips)
        
    # ── SESSION ───────────────────────────────────────────────────────────────
    def _toggle_session(self):
        if not self.session_active:
            self._start_session()
        else:
            self._confirm_stop_session()

    def _confirm_stop_session(self):
        # No friction for short sessions
        if self.elapsed < 300: # ARBITRARY 5-MINUTE THRESHOLD PLACEHOLDER YOU CAN CHANGE <<>>
            self._stop_session(); return
        dlg = ctk.CTkToplevel(self)
        dlg.title(""); dlg.geometry("320x160")
        dlg.resizable(False, False); dlg.configure(fg_color=BG_SURFACE); dlg.grab_set()
        m, s = divmod(self.elapsed, 60)
        ctk.CTkLabel(dlg, text="End session?",
                     font=("DM Sans", 13, "bold"), text_color=TEXT_PRI).pack(pady=(20, 4))
        ctk.CTkLabel(dlg, text=f"You've focused for {m}m {s:02d}s.\nAre you done?",
                     font=("DM Sans", 11), text_color=TEXT_MUT, justify="center").pack()
        br = ctk.CTkFrame(dlg, fg_color="transparent"); br.pack(pady=16)
        ctk.CTkButton(br, text="Keep going", width=100, height=34,
                      fg_color=ACCENT, hover_color=ACCENT_HVR,
                      text_color=TEXT_PRI, font=("DM Sans", 12, "bold"),
                      corner_radius=8, command=dlg.destroy
                      ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(br, text="End session", width=100, height=34,
                      fg_color=BG_RAISED, hover_color="#2a1018",
                      border_color=RED, border_width=1,
                      text_color=RED, font=("DM Sans", 12),
                      corner_radius=8,
                      command=lambda: [dlg.destroy(), self._stop_session()]
                      ).pack(side="left")

    def _start_session(self):
        global session_active
        goal = self.goal_entry.get().strip()
        if not goal:
            self.goal_entry.configure(border_color=RED, border_width=1)
            self.after(1200, lambda: self.goal_entry.configure(border_color=BORDER,border_width=0))
            return
        self._session_goal = goal; self.cfg["last_goal"] = goal
        self._save_goal_as_template(goal)
        self.session_active = True; session_active = True
        self.start_btn.configure(text="■  Stop session", fg_color=BG_RAISED,
                                 hover_color="#2a1018", border_color=RED,
                                 border_width=1, text_color=RED)
        self.break_btn.pack(fill="x", pady=(8, 0))
        self.dot_canvas.itemconfig(self.dot_oval, fill=GREEN)
        self.status_lbl.configure(text="active", text_color=GREEN)
        self.tray.update(True)
        self._walkthrough_btn.configure(text_color="#2a2a2e")
        self.elapsed = 0; self.iconify()
        prof = active_profile(self.cfg)
        threading.Thread(target=enforce_gatekeeper,
                         args=(list(prof["allowed_apps"]),
                               list(prof["banned_keywords"])),
                         daemon=True).start()
        # ── Backend sync: notify all devices this session has started ─────────
        threading.Thread(target=self._sync_start_session,
                         args=(goal, prof), daemon=True).start()
        self._tick(); self._poll_log(); self._update_title_clock()
        self._set_poll_interval(2)

    def _stop_session(self):
        global session_active
        self.session_active = False; session_active = False
        snap_elapsed      = self.elapsed
        snap_blocked      = blocked_count
        snap_block_log    = list(block_log)
        record_session(self.cfg, self._session_goal, snap_elapsed,
                       snap_blocked, self.cfg.get("active_profile","Default"),
                       snap_block_log)
        # ── Backend sync: inform all devices the session has stopped ──────────
        threading.Thread(target=self._sync_stop_session,
                         args=(snap_elapsed, snap_blocked, snap_block_log),
                         daemon=True).start()
        self.start_btn.configure(text="▶  Start session", fg_color=ACCENT,
                                 hover_color=ACCENT_HVR, border_width=0, text_color=TEXT_PRI)
        self.break_btn.pack_forget()
        self._end_break()
        self.dot_canvas.itemconfig(self.dot_oval, fill=TEXT_MUT)
        self.status_lbl.configure(text="idle", text_color=TEXT_MUT)
        self.progress.set(0); self.tray.update(False)
        self._walkthrough_btn.configure(text_color=TEXT_MUT)
        self.title("Nothing Alternative")
        if self._timer_id:              self.after_cancel(self._timer_id)
        if self._log_poll_id:           self.after_cancel(self._log_poll_id)
        if self._title_clock_id:        self.after_cancel(self._title_clock_id)
        self._set_poll_interval(10)

    def _open_break_picker(self):
        if self._break_active:
            self._end_break(); return
        dlg = ctk.CTkToplevel(self)
        dlg.title(""); dlg.geometry("280x180")
        dlg.resizable(False, False); dlg.configure(fg_color=BG_SURFACE); dlg.grab_set()
        ctk.CTkLabel(dlg, text="Take a break",
                     font=("DM Sans", 13, "bold"), text_color=TEXT_PRI).pack(pady=(20, 4))
        ctk.CTkLabel(dlg, text="Blocking pauses. Session keeps running.",
                     font=("DM Sans", 11), text_color=TEXT_MUT).pack()
        row = ctk.CTkFrame(dlg, fg_color="transparent"); row.pack(pady=16)
        for mins in [5, 10, 15]:
            ctk.CTkButton(row, text=f"{mins}m", width=64, height=34,
                          fg_color=ACCENT, hover_color=ACCENT_HVR,
                          text_color=TEXT_PRI, font=("DM Sans", 12, "bold"),
                          corner_radius=8,
                          command=lambda m=mins: [dlg.destroy(), self._start_break(m * 60)]
                          ).pack(side="left", padx=4)

    def _start_break(self, seconds: int) -> None:
        global session_active
        self._break_active = True
        session_active = False  # pauses the gatekeeper loop
        self.break_btn.configure(text=f"End break early", text_color=AMBER,
                                 border_color=AMBER)
        self.status_lbl.configure(text="on break", text_color=AMBER)
        self.dot_canvas.itemconfig(self.dot_oval, fill=AMBER)
        log_queue.append(("system", f"[SYSTEM] Break started — {seconds // 60}m"))
        self._break_timer_id = self.after(seconds * 1000, self._end_break)

    def _end_break(self) -> None:
        global session_active
        if not self._break_active: return
        self._break_active = False
        if self._break_timer_id:
            self.after_cancel(self._break_timer_id)
            self._break_timer_id = None
        if self.session_active:
            session_active = True  # resumes gatekeeper
            self.break_btn.configure(text="Take a break", text_color=TEXT_MUT,
                                     border_color=BORDER)
            self.status_lbl.configure(text="active", text_color=GREEN)
            self.dot_canvas.itemconfig(self.dot_oval, fill=GREEN)
            log_queue.append(("system", "[SYSTEM] Break ended — blocking resumed"))

    # ── BACKEND SYNC METHODS ──────────────────────────────────────────────────
    # All run on daemon threads or as lightweight Tk after-loops.
    # Failures are swallowed silently — local behaviour is never interrupted.

    def _fetch_profiles_from_backend(self) -> None:
        data = _api_get("/profiles")
        if not data or not isinstance(data, list) or len(data) == 0:
            return
        local_times = self.cfg.get("profiles_updated_at", {})
        merged = dict(self.cfg.get("profiles", {}))  # start from local
        changed = False
        for p in data:
            name = p.get("name")
            if not name:
                continue
            server_ts = p.get("updated_at", "")
            local_ts  = local_times.get(name, "")
            if name not in merged:
                # New profile from server — take it
                merged[name] = {
                    "allowed_apps":    p.get("allowed_apps", []),
                    "banned_keywords": p.get("banned_keywords", []),
                }
                changed = True
            elif server_ts and server_ts > local_ts:
                # Server is newer — take server version
                merged[name] = {
                    "allowed_apps":    p.get("allowed_apps", []),
                    "banned_keywords": p.get("banned_keywords", []),
                }
                changed = True
            # else: local is newer or same — keep local, it'll sync up on next PUT
        if not changed:
            return
        current_active = self.cfg.get("active_profile", "Default")
        if current_active not in merged:
            current_active = next(iter(merged))
        self.cfg["profiles"]       = merged
        self.cfg["active_profile"] = current_active
        save_config(self.cfg)
        self.after(0, self._on_profile_change)

    def _sync_profiles_to_backend(self) -> None:
        """
        Background thread: PUT /profiles with the full local profile list.
        Called whenever the user adds/removes an app, switches or creates a
        profile, or removes a profile — i.e. anywhere save_config() is called
        from a profile-related action.
        """
        profiles_payload = []
        for name, prof in self.cfg.get("profiles", {}).items():
            profiles_payload.append({
                "name":            name,
                "allowed_apps":    list(prof.get("allowed_apps", [])),
                "banned_keywords": list(prof.get("banned_keywords", [])),
                "is_active":       (name == self.cfg.get("active_profile", "Default")),
            })
        if not profiles_payload:
            return
        _api_put("/profiles/", {
            "profiles":       profiles_payload,
            "active_profile": self.cfg.get("active_profile", "Default"),
        })

    def _sync_start_session(self, goal: str, prof: dict) -> None:
        payload = {
            "goal":            goal,
            "profile_name":    self.cfg.get("active_profile", "Default"),
            "allowed_apps":    list(prof.get("allowed_apps", [])),
            "banned_keywords": list(prof.get("banned_keywords", [])),
            "device_id":       _DEVICE_ID,
        }
        result = _api_post("/sessions/start", payload)
        if result is None:
            # Network failed — queue it for retry
            self.cfg["pending_sync"] = {"action": "start", "payload": payload}
            save_config(self.cfg)
        else:
            self.cfg["pending_sync"] = None
            save_config(self.cfg)

    def _sync_stop_session(self, duration_s: int, blocked: int, b_log: list) -> None:
        payload = {
            "duration_s":    duration_s,
            "blocked_count": blocked,
            "block_log":     b_log,
            "device_id":     _DEVICE_ID,
            "goal":          self._session_goal,
            "profile_name":  self.cfg.get("active_profile", "Default"),
        }
        result = _api_post("/sessions/stop", payload)
        if result is None:
            self.cfg["pending_sync"] = {"action": "stop", "payload": payload}
            save_config(self.cfg)
        else:
            self.cfg["pending_sync"] = None
            save_config(self.cfg)

    def _flush_pending_sync(self) -> None:
        """Replay any queued start/stop that failed while offline."""
        pending = self.cfg.get("pending_sync")
        if not pending or not API_TOKEN:
            return
        action  = pending.get("action")
        payload = pending.get("payload", {})
        path = "/sessions/start" if action == "start" else "/sessions/stop"
        result = _api_post(path, payload)
        if result is not None:
            self.cfg["pending_sync"] = None
            save_config(self.cfg)
            print(f"[SYNC] Flushed pending {action}")

    def _prompt_join_session(self, data: dict) -> None:
        """Called when another device has an active session and this one doesn't."""
        # Don't show the prompt if it's already open
        if hasattr(self, "_join_dlg") and self._join_dlg and self._join_dlg.winfo_exists():
            return
        goal       = data.get("goal", "")
        started_by = data.get("started_by") or "another device"
        blocked    = data.get("blocked", [])
        allowed    = data.get("allowed_apps", [])

        dlg = ctk.CTkToplevel(self)
        self._join_dlg = dlg
        dlg.title(""); dlg.geometry("340x180")
        dlg.resizable(False, False); dlg.configure(fg_color=BG_SURFACE); dlg.grab_set()
        ctk.CTkLabel(dlg, text=f"Session active on {started_by}",
                     font=("DM Sans", 13, "bold"), text_color=TEXT_PRI).pack(pady=(20, 4))
        ctk.CTkLabel(dlg, text=f'"{goal}"' if goal else "A focus session is running.",
             font=("DM Sans", 11), text_color=TEXT_SEC,
             wraplength=290).pack()
        ctk.CTkLabel(dlg, text="Start blocking on this device too?",
                     font=("DM Sans", 11), text_color=TEXT_MUT).pack(pady=(6, 0))
        br = ctk.CTkFrame(dlg, fg_color="transparent"); br.pack(pady=16)

        def _join():
            dlg.destroy()
            # Start gatekeeper locally with the remote session's profile
            self._session_goal  = goal
            self.session_active = True
            global session_active
            session_active = True
            self.start_btn.configure(text="■  Stop session", fg_color=BG_RAISED,
                                     hover_color="#2a1018", border_color=RED,
                                     border_width=1, text_color=RED)
            self.dot_canvas.itemconfig(self.dot_oval, fill=GREEN)
            self.status_lbl.configure(text="active (joined)", text_color=GREEN)
            self.tray.update(True)
            self.elapsed = 0
            threading.Thread(target=enforce_gatekeeper,
                             args=(allowed, blocked), daemon=True).start()
            self._set_poll_interval(2)
            self._tick(); self._poll_log(); self._update_title_clock()

        ctk.CTkButton(br, text="Ignore", width=90, height=34,
                      fg_color=BG_RAISED, hover_color=BORDER,
                      text_color=TEXT_SEC, font=("DM Sans", 12),
                      corner_radius=8, command=dlg.destroy
                      ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(br, text="Join session", width=110, height=34,
                      fg_color=ACCENT, hover_color=ACCENT_HVR,
                      text_color=TEXT_PRI, font=("DM Sans", 12, "bold"),
                      corner_radius=8, command=_join).pack(side="left")
        
    def _apply_remote_status(self, data: dict) -> None:
        global _status_blocked_sites
        if data.get("active"):
            _status_blocked_sites = data.get("blocked", _status_blocked_sites)
            # If a remote device started a session and we aren't running one, ask to join
            if not self.session_active and data.get("started_by") != _DEVICE_ID:
                self.after(0, self._prompt_join_session, data)

        new_status = data.get("subscription_status", "free")
        new_premium = data.get("is_premium", False)
        self._trial_ends_at = data.get("trial_ends_at")

        if not hasattr(self, "_last_sub_status") or self._last_sub_status != new_status:
            self._last_sub_status = new_status
            self.after(0, self._refresh_subscription_ui, new_status, new_premium)

    def _refresh_subscription_ui(self, status: str, is_premium: bool):
        if not hasattr(self, "_sub_indicator"):
            return

        trial_ends = getattr(self, "_trial_ends_at", None)

        if status == "lifetime":
            self._sub_indicator.configure(
                text="Lifetime ✓",
                text_color=GREEN,
                cursor=""
            )
        elif status == "active":
            self._sub_indicator.configure(
                text="Premium ✓",
                text_color=GREEN,
                cursor=""
            )
        elif status == "trialing" and trial_ends:
            try:
                # Parse the ISO timestamp from the server
                ends = datetime.fromisoformat(trial_ends.replace("Z", "+00:00"))
                days_left = (ends.replace(tzinfo=None) - datetime.now(timezone.utc).replace(tzinfo=None)).days + 1
                days_left = max(0, days_left)
                color = RED if days_left <= 2 else AMBER if days_left <= 4 else "#5555cc"
                self._sub_indicator.configure(
                    text=f"Trial · {days_left}d left",
                    text_color=color,
                    cursor="hand2"
                )
            except Exception:
                self._sub_indicator.configure(
                    text="Trial",
                    text_color="#5555cc",
                    cursor="hand2"
                )
        elif status in ("expired", "cancelled", "past_due", "free"):
            self._sub_indicator.configure(
                text="Upgrade →",
                text_color=AMBER,
                cursor="hand2"
            )

    def _open_upgrade(self):
        if hasattr(self, "_pricing_panel") and self._pricing_panel and \
        self._pricing_panel.winfo_exists():
            self._pricing_panel.focus()
            return
        self._pricing_panel = PricingPanel(self)
        
    # ── TICK / LOG / TITLE ────────────────────────────────────────────────────
    def _tick(self):
        if not self.session_active: return
        self.elapsed += 1
        m, s = divmod(self.elapsed, 60)
        self.elapsed_lbl.configure(text=f"elapsed  {m:02d}:{s:02d}")
        self.blocked_lbl.configure(text=f"blocked  {blocked_count}")
        phase = (self.elapsed % 20) / 20.0
        self.progress.set((phase if phase<0.5 else 1.0-phase)*2)
        self._timer_id = self.after(1000, self._tick)

    def _update_title_clock(self):
        if not self.session_active: return
        m, s = divmod(self.elapsed, 60)
        self.title(f"Nothing Alternative  ·  {m:02d}:{s:02d}  ·  {blocked_count} blocked")
        self._title_clock_id = self.after(1000, self._update_title_clock)

    def _poll_log(self):
        global log_queue
        while log_queue:
            tag, msg = log_queue.pop(0)
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg+"\n", tag)
            self.log_box.see("end"); self.log_box.configure(state="disabled")
        if self.session_active: self._log_poll_id = self.after(300, self._poll_log)

    # ── WINDOW LIFECYCLE ──────────────────────────────────────────────────────
    def _on_close(self):
        if self.session_active:
            dlg = ctk.CTkToplevel(self)
            dlg.title(""); dlg.geometry("320x140")
            dlg.resizable(False,False); dlg.configure(fg_color=BG_SURFACE); dlg.grab_set()
            self.update_idletasks()
            x = self.winfo_x()+(self.winfo_width()-320)//2
            y = self.winfo_y()+(self.winfo_height()-140)//2
            dlg.geometry(f"320x140+{x}+{y}")
            ctk.CTkLabel(dlg, text="Session is active",
                         font=("DM Sans",13,"bold"), text_color=TEXT_PRI).pack(pady=(22,4))
            ctk.CTkLabel(dlg, text="Stop the session and quit?",
                         font=("DM Sans",11), text_color=TEXT_MUT).pack()
            br = ctk.CTkFrame(dlg, fg_color="transparent"); br.pack(pady=16)
            ctk.CTkButton(br, text="Cancel", width=100, height=34,
                          fg_color=BG_RAISED, hover_color=BORDER,
                          text_color=TEXT_SEC, font=("DM Sans",12),
                          corner_radius=8, command=dlg.destroy
                          ).pack(side="left", padx=(0,10))
            ctk.CTkButton(br, text="Stop & Quit", width=110, height=34,
                          fg_color=RED, hover_color="#cc2233",
                          text_color=TEXT_PRI, font=("DM Sans",12,"bold"),
                          corner_radius=8,
                          command=lambda: [dlg.destroy(), self._quit()]
                          ).pack(side="left")
        else:
            self._quit()

    def _quit(self):
        if self.session_active: self._stop_session()
        self._stop_poll_thread()
        self.tray.stop(); self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if sys.platform == "darwin":
        sys.exit("This file is for Windows only. Use nothing_alternative_mac.py on macOS.") 
    _start_status_server()   # Option 1: start HTTP server for browser extension
    app = NothingAlternative()
    app.mainloop()