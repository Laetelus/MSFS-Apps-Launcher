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
import logging
import os
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
else:
    HERE = Path(__file__).resolve().parent

GUI_LOCK_FILE = HERE / ".gui_running"
GUI_PORT = 54321  # Port used for GUI singleton detection

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def create_gui_lock_socket():
    """Create a socket listener to indicate this GUI instance is running.
    Returns the socket if successful, None if another instance is already running."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', GUI_PORT))
        sock.listen(1)
        log.info("GUI lock socket created on port %d", GUI_PORT)
        return sock
    except OSError as e:
        log.error("GUI lock socket failed (another instance may be running): %s", e)
        return None


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
        """Read recent logs from launcher.log file."""
        log_file = self._path.parent / "launcher.log"
        if not log_file.exists():
            return []
        
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
            
            # Get the last N lines
            recent_lines = all_lines[-lines:] if all_lines else []
            
            # Parse each line into timestamp and message
            logs = []
            for line in recent_lines:
                line = line.rstrip('\n')
                if not line.strip():
                    continue
                
                # Format: "2026-10-12 17:40:29,531  message"
                date, time_part, message = line.split(' ', 2)
                logs.append({"date": date, "time": time_part, "msg": message})
            
            return logs
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
                    log.info("MSFS stopped, GUI remains open (user can still edit)")
                elif sim_running and not prev_running:  # MSFS just started
                    log.info("MSFS started")
                prev_running = sim_running
            time.sleep(2)

    def _close_app(self):
        """Close the application."""
        if self._window:
            self._window.destroy()
        self._running = False

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
            try:
                if self._window:
                    self._window.show()
                    # Restore from minimized state if needed
                    try:
                        self._window.restore()
                    except Exception:
                        pass
                    log.info("GUI shown from tray")
            except Exception as e:
                log.error("Error showing window: %s", e)

        def quit_app(icon=None, item=None):
            """Quit app from tray menu."""
            log.info("Quit selected from tray menu")
            self._running = False
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
    parser.add_argument("--sim", help="override sim executable name", default="FlightSimulator.exe")
    parser.add_argument("--minimized", action="store_true", help="start minimized to system tray")
    args = parser.parse_args()
    path = Path(args.config) if args.config else HERE / "apps.json"

    api = Api(path, sim_exe=args.sim)

    # Try to create lock socket to indicate this instance is running
    lock_socket = create_gui_lock_socket()
    if not lock_socket:
        log.error("Another GUI instance is already running. Exiting.")
        print("Error: Another GUI instance is already running.")
        return

    # Create window
    api._window = webview.create_window(
        "MSFS App Launcher", str(BASE / "ui" / "index.html"),
        js_api=api, width=1160, height=720, min_size=(1160, 720))
    
    # Setup tray icon first (if available)
    if HAS_SYSTRAY:
        api._setup_tray_icon()
        time.sleep(0.5)  # Give tray icon time to initialize
    
    # Start minimized to tray if requested (delay to ensure window is ready)
    if args.minimized and HAS_SYSTRAY:
        def hide_to_tray():
            try:
                time.sleep(1)  # Wait for webview to fully initialize
                api._window.hide()
                log.info("GUI minimized to system tray (launched by MSFS)")
            except Exception as e:
                log.error("Error hiding window to tray: %s", e)
        
        hide_thread = threading.Thread(target=hide_to_tray, daemon=True)
        hide_thread.start()
    
    # Setup event handlers
    def on_minimized(window):
        """Hide window to tray on minimize."""
        if HAS_SYSTRAY and api._tray_icon:
            window.hide()
            log.info("GUI minimized to system tray")
        else:
            window.minimize()

    def on_closing():
        """Handle window close."""
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
    
    # Only use tray minimize if pystray is available
    if HAS_SYSTRAY:
        api._window.events.minimized += on_minimized

    # Start MSFS monitoring (doesn't block GUI, just monitors)
    api.start_monitor()

    # Run the window
    webview.start()


if __name__ == "__main__":
    main()
