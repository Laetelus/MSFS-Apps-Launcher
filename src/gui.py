"""Config editor GUI for the MSFS app launcher.

    pip install pywebview pystray pillow
    python gui.py [--config path\to\apps.json]

The window is an HTML page (ui/index.html) talking to the Api class below.
It edits the same apps.json the launcher reads; changes apply the next time
the sim starts.

Features:
    - Minimizes to system tray (closes window to tray instead of taskbar)
    - Monitors MSFS process; disables/closes GUI if MSFS is not running
    - Launch with launcher.py when MSFS starts, close when MSFS exits
"""
import argparse
import ctypes
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import webview

try:
    from PIL import Image, ImageDraw
    import pystray
    HAS_SYSTRAY = True
except ImportError:
    HAS_SYSTRAY = False

import config
import exe_xml

log = logging.getLogger("launcher")


# Setup logging if not already configured
if not log.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
    )

log.info("System tray support available: %s", HAS_SYSTRAY)

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if getattr(sys, "frozen", False):
    HERE = Path(sys.executable).resolve().parent
    UI_DIR = BASE / "ui"          # bundled data lives next to the exe (or in _internal)
else:
    HERE = Path(__file__).resolve().parent.parent  # running as a script (src/), go up to root
    UI_DIR = HERE / "ui"

GUI_LOCK_FILE = HERE / ".gui_running"
GUI_PORT = 54321  # Port used for GUI singleton detection

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


SHOW_MESSAGE = b"show"
WINDOW_BG = "#0a1628"          # matches --bg in ui/style.css (shown before the page paints)
SHOW_FALLBACK_SECONDS = 8      # show the window even if the page never reports "loaded"
LOG_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2},\d+)\s+(.*)$")
LOG_TAIL_BYTES = 64 * 1024   # only the end of launcher.log is ever read


def create_gui_lock_socket():
    """Create a socket listener to indicate this GUI instance is running.
    Returns the socket if successful, None if another instance is already running."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Exclusive: on Windows SO_REUSEADDR would let a second instance bind the same port
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(('127.0.0.1', GUI_PORT))
        sock.listen(5)
        log.info("GUI lock socket created on port %d", GUI_PORT)
        return sock
    except OSError as e:
        log.info("GUI lock socket in use (another instance is running): %s", e)
        return None


def signal_running_instance():
    """Ask the GUI that is already running to show its window. True if it answered."""
    try:
        # Let the running instance take focus (we were just launched, so we may grant it)
        ctypes.windll.user32.AllowSetForegroundWindow(-1)   # ASFW_ANY
    except Exception:
        pass
    try:
        with socket.create_connection(('127.0.0.1', GUI_PORT), timeout=2) as sock:
            sock.sendall(SHOW_MESSAGE)
        return True
    except OSError as e:
        log.error("Could not reach the running GUI: %s", e)
        return False


def listen_for_show(lock_socket, on_show):
    """Background thread: a second launch connects and sends "show".
    (launcher.py also connects, sending nothing, just to see if we are running.)"""
    while True:
        try:
            conn, _ = lock_socket.accept()
        except OSError:
            return   # socket closed: the app is exiting
        try:
            conn.settimeout(1)
            if conn.recv(16).strip() == SHOW_MESSAGE:
                log.info("Another launch asked to show the GUI")
                on_show()
        except OSError:
            pass
        finally:
            conn.close()


def is_running(exe_name):
    """True if a process with this image name is running."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, creationflags=NO_WINDOW, timeout=5
        ).stdout
        return out.lstrip().startswith('"')
    except Exception:
        return False


def create_tray_icon():
    """Create a system tray icon image (red circle with 'M' for MSFS)."""
    if not HAS_SYSTRAY:
        return None
    try:
        # Create a 64x64 icon image
        img = Image.new('RGB', (64, 64), color=(50, 50, 50))  # Dark gray background
        draw = ImageDraw.Draw(img)
        # Draw red circle
        draw.ellipse([10, 10, 54, 54], fill=(220, 20, 60), outline=(255, 255, 255))
        # Draw white "M" text
        draw.text((20, 16), "M", fill=(255, 255, 255))
        log.info("Tray icon image created successfully")
        return img
    except Exception as e:
        log.error("Failed to create tray icon image: %s", e)
        return None


class Api:
    """Methods here are callable from the page as pywebview.api.<name>()."""

    def __init__(self, path, sim_exe="FlightSimulator.exe"):
        self._path = Path(path)
        self._window = None   # underscore: not exposed to the page
        self._cfg = None
        self._sim_exe = sim_exe
        self._monitor_thread = None
        self._running = True
        self._tray_icon = None
        self._sim_running = False
        self._quitting = False   # True when the app is really exiting (not just hiding to tray)
        self._log_cache = (None, [])   # ((mtime, size), parsed entries) of launcher.log

    def _setting(self, key, default=None):
        """Read one GUI setting (the page and this object share the same config)."""
        try:
            if not self._cfg:
                self._cfg = config.load(self._path)
            return self._cfg.get("settings", {}).get(key, default)
        except Exception:
            return default

    def get_config(self):
        """Load full config with all profiles."""
        self._cfg = config.load(self._path)
        return self._cfg

    def config_path(self):
        return str(self._path)

    def save_config(self, cfg):
        """Save the updated config."""
        try:
            self._cfg = cfg
            config.save(self._path, cfg)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_settings(self):
        """Get current GUI settings."""
        if not self._cfg:
            self._cfg = config.load(self._path)
        return self._cfg.get("settings", {})

    def save_settings(self, settings):
        """Save GUI settings."""
        try:
            if not self._cfg:
                self._cfg = config.load(self._path)
            self._cfg["settings"] = settings
            config.save(self._path, self._cfg)
            log.info("Settings saved: %s", settings)
            return {"ok": True}
        except Exception as exc:
            log.error("Error saving settings: %s", exc)
            return {"ok": False, "error": str(exc)}

    # ---- exe.xml integration (the page only ever passes an install id, never a path) ----

    @staticmethod
    def _describe(install):
        return {"id": install["id"], "sim": install["sim"], "store": install["store"],
                **exe_xml.inspect(install["folder"])}

    @staticmethod
    def _find_install(install_id):
        for install in exe_xml.installs():
            if install["id"] == install_id:
                return install
        raise exe_xml.ExeXmlError("That MSFS installation was not found.")

    def exe_xml_status(self):
        """State of exe.xml for every MSFS installation found on this PC."""
        return [self._describe(i) for i in exe_xml.installs()]

    def _exe_xml_change(self, install_id, change):
        try:
            install = self._find_install(install_id)
        except exe_xml.ExeXmlError as exc:
            return {"ok": False, "error": str(exc), "status": None}
        try:
            result = change(install["folder"])
            log.info("exe.xml (%s): %s%s", install_id, result["message"],
                     f" backup: {result['backup']}" if result["backup"] else "")
            return {"ok": True, **result, "status": self._describe(install)}
        except exe_xml.ExeXmlError as exc:
            log.error("exe.xml (%s) failed: %s", install_id, exc)
            return {"ok": False, "error": str(exc), "status": self._describe(install)}
        except Exception as exc:   # never let the page see a crash
            log.exception("exe.xml (%s) unexpected error", install_id)
            return {"ok": False, "error": f"Unexpected error: {exc}", "status": self._describe(install)}

    def exe_xml_add(self, install_id):
        return self._exe_xml_change(install_id, exe_xml.add)

    def exe_xml_remove(self, install_id):
        return self._exe_xml_change(install_id, exe_xml.remove)

    def exe_xml_open_folder(self, install_id):
        try:
            exe_xml.open_folder(self._find_install(install_id)["folder"])
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def browse_exe(self, folder=None):
        kwargs = {"file_types": ("Programs (*.exe)",)}
        if folder and Path(folder).is_dir():
            kwargs["directory"] = folder
        result = self._window.create_file_dialog(webview.FileDialog.OPEN, **kwargs)
        return result[0] if result else None

    def check_path_exists(self, path):
        """Check if a file path exists."""
        if not path:
            return False
        return Path(path).exists()

    def get_launcher_logs(self, lines=50):
        """Recent entries from launcher.log as [{date, time, msg}], oldest first.

        The page polls this every second, so the file is only re-read when its
        size or modified time changes, and only its last LOG_TAIL_BYTES are read.
        Lines without a timestamp (e.g. traceback lines) belong to the entry above.
        """
        log_file = self._path.parent / "launcher.log"
        try:
            st = log_file.stat()
        except OSError:
            return []
        key = (st.st_mtime_ns, st.st_size)
        if self._log_cache[0] == key:
            return self._log_cache[1][-lines:]

        try:
            with open(log_file, "rb") as f:
                start = max(0, st.st_size - LOG_TAIL_BYTES)
                f.seek(start)
                text = f.read().decode("utf-8", errors="replace")
            raw = text.splitlines()
            if start > 0 and raw:
                raw = raw[1:]   # first line was probably cut in half by the seek

            logs = []
            for line in raw:
                if not line.strip():
                    continue
                m = LOG_LINE.match(line)
                if m:
                    logs.append({"date": m[1], "time": m[2], "msg": m[3]})
                elif logs:
                    logs[-1]["msg"] += "\n" + line   # continuation of the previous entry
                # else: continuation whose entry was cut off by the tail; skip it

            self._log_cache = (key, logs)
            return logs[-lines:]
        except Exception as e:
            return [{"date": "N/A", "time": "ERROR", "msg": str(e)}]

    def is_msfs_running(self):
        """Check if MSFS is currently running."""
        return is_running(self._sim_exe)

    def _monitor_msfs(self):
        """Background thread: monitor MSFS and optionally close GUI if it stops."""
        prev_running = None
        while self._running:
            sim_running = is_running(self._sim_exe)
            if sim_running != prev_running:
                self._sim_running = sim_running
                if not sim_running and prev_running:  # MSFS just stopped
                    log.info("MSFS stopped")
                    if self._setting("closeWithMSFS", False):
                        log.info("Closing GUI because MSFS exited")
                        self._close_app()
                        return
                elif sim_running and not prev_running:  # MSFS just started
                    log.info("MSFS started")
                prev_running = sim_running
            time.sleep(2)

    def _close_app(self):
        """Really exit the application (bypasses hide-to-tray)."""
        self._quitting = True
        self._running = False
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        if self._window:
            self._window.destroy()

    def _center_window(self):
        """Move the window to the middle of the screen it is on (primary as fallback)."""
        w = self._window
        screens = webview.screens or []
        if not screens:
            return
        primary = next((s for s in screens if s.x == 0 and s.y == 0), screens[0])
        screen = next((s for s in screens
                       if s.x <= w.x < s.x + s.width and s.y <= w.y < s.y + s.height),
                      primary)
        x = screen.x + max(0, (screen.width - w.width) // 2)
        y = screen.y + max(0, (screen.height - w.height) // 2)
        w.move(x, y)

    def _show_window(self, center=False):
        """Bring the window back from the tray / taskbar, optionally centered."""
        if not self._window:
            return
        try:
            self._window.show()
            try:
                self._window.restore()   # in case it was minimized
            except Exception:
                pass
            if center:
                self._center_window()
            log.info("GUI shown%s", " (centered)" if center else "")
        except Exception as e:
            log.error("Error showing window: %s", e)

    def start_monitor(self):
        """Start MSFS monitoring thread."""
        if not self._monitor_thread or not self._monitor_thread.is_alive():
            self._monitor_thread = threading.Thread(target=self._monitor_msfs, daemon=True)
            self._monitor_thread.start()

    def _setup_tray_icon(self):
        """Setup system tray icon with menu."""
        if not HAS_SYSTRAY or self._tray_icon:
            log.info("Tray icon setup skipped (systray: %s, already_created: %s)", HAS_SYSTRAY, self._tray_icon is not None)
            return

        log.info("Creating tray icon image...")
        icon_image = create_tray_icon()
        if not icon_image:
            log.error("Failed to create tray icon image")
            return

        def show_window(icon=None, item=None):
            """Show window from tray menu."""
            self._show_window()

        def quit_app(icon=None, item=None):
            """Quit app from tray menu."""
            log.info("Quit selected from tray menu")
            self._running = False
            self._quitting = True
            try:
                if icon:
                    icon.stop()
            except Exception as e:
                log.error("Error stopping icon: %s", e)
            try:
                if self._window:
                    self._window.destroy()
            except Exception as e:
                log.error("Error destroying window: %s", e)

        # Create menu with Show as default (will be triggered on left-click)
        menu = pystray.Menu(
            pystray.MenuItem("Show", show_window, default=True),
            pystray.MenuItem("Quit", quit_app),
        )

        try:
            self._tray_icon = pystray.Icon(
                "msfs_launcher",
                icon_image,
                "MSFS App Launcher",
                menu=menu
            )
            
            log.info("Tray icon created, starting in background thread...")
            # Run tray icon in background thread
            tray_thread = threading.Thread(target=self._tray_icon.run, daemon=True)
            tray_thread.start()
            log.info("Tray icon thread started successfully")
        except Exception as e:
            log.error("Failed to setup tray icon: %s", e)
            self._tray_icon = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="path to apps.json")
    parser.add_argument("--sim", help="override sim executable name")
    parser.add_argument("--minimized", action="store_true", help="start hidden (tray) or minimized")
    args = parser.parse_args()
    path = Path(args.config) if args.config else HERE / "apps.json"

    # Without --sim, watch the game that was last selected in the GUI
    sim_exe = args.sim
    if not sim_exe:
        try:
            sim_exe = config.load(path).get("lastGame") or "FlightSimulator.exe"
        except Exception:
            sim_exe = "FlightSimulator.exe"

    # Only one GUI at a time: if one is already running, bring it forward and exit
    lock_socket = create_gui_lock_socket()
    if not lock_socket:
        if signal_running_instance():
            log.info("GUI already running; asked it to show its window. Exiting.")
        else:
            log.error("Port %d is in use but the running GUI did not answer. Exiting.", GUI_PORT)
        return

    api = Api(path, sim_exe=sim_exe)

    # Create the window hidden: it is only shown (centered) once the page has rendered,
    # so you never see the blank/black frame WebView2 paints while it starts up.
    api._window = webview.create_window(
        "MSFS App Launcher", str(UI_DIR / "index.html"),
        js_api=api, width=1160, height=720, min_size=(1160, 720),
        hidden=True, background_color=WINDOW_BG)

    # Setup tray icon first (if available)
    if HAS_SYSTRAY:
        api._setup_tray_icon()

    first_show = threading.Lock()
    shown = []

    def show_first_time():
        """Runs once: when the page has loaded, or after a timeout as a fallback."""
        with first_show:
            if shown:
                return
            shown.append(True)
        try:
            if not args.minimized:
                api._show_window(center=True)
            elif api._tray_icon:
                log.info("GUI started hidden in system tray")
            else:
                api._show_window(center=True)
                api._window.minimize()
                log.info("GUI started minimized to taskbar")
        except Exception as e:
            log.error("Error showing the window at startup: %s", e)

    api._window.events.loaded += show_first_time
    # Fallback in case the page never reports "loaded" (it should within a second or two)
    fallback = threading.Timer(SHOW_FALLBACK_SECONDS, show_first_time)
    fallback.daemon = True
    fallback.start()

    # Setup event handlers
    def on_minimized(window):
        """Minimize button: hide to tray or stay on the taskbar, per settings."""
        if api._tray_icon and api._setting("minimizeButtonAction", "tray") == "tray":
            window.hide()
            log.info("GUI minimized to system tray")
        # "taskbar": the window is already minimized, nothing more to do

    def on_closing():
        """Close button: hide to tray or exit, per settings."""
        if (not api._quitting and api._tray_icon
                and api._setting("closeButtonAction", "tray") == "tray"):
            api._window.hide()
            log.info("GUI hidden to system tray (close button)")
            return False   # cancel the close, keep running in the tray
        api._running = False
        if api._tray_icon:
            try:
                api._tray_icon.stop()
            except Exception:
                pass
        # Close lock socket
        try:
            lock_socket.close()
            log.info("GUI lock socket closed")
        except Exception as e:
            log.error("Error closing lock socket: %s", e)
        return True
    
    api._window.events.closing += on_closing
    api._window.events.minimized += on_minimized

    # A second launch of the GUI shows (and centers) this window instead of opening another
    threading.Thread(target=listen_for_show,
                     args=(lock_socket, lambda: api._show_window(center=True)),
                     daemon=True).start()

    # Start MSFS monitoring (doesn't block GUI, just monitors)
    api.start_monitor()

    # Run the window
    webview.start()


if __name__ == "__main__":
    main()
