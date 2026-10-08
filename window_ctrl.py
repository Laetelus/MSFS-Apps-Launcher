
"""Window control for launched apps (Windows only, standard library only).

Public API:
    start_window_watcher(name, proc_name, mode="minimized", timeout=30)
        Starts a background thread that finds the app's windows and sets them
        to "minimized" or "maximized". Returns the thread.
    enforce_window(...)
        Same thing, but blocking. Useful for tests.

Standalone test against an app that is already running:
    python window_ctrl.py SomeApp.exe minimized
"""
import csv
import ctypes
import logging
import subprocess
import sys
import threading
import time
from ctypes import wintypes

log = logging.getLogger("launcher")  # same logger as launcher.py, so one log file
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

SW_MAXIMIZE = 3
SW_SHOWMINNOACTIVE = 7   # minimize without stealing focus from the sim
GW_OWNER = 4

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]


def pids_for(exe_name):
    """PIDs of all running processes with this image name."""
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, creationflags=NO_WINDOW,
    ).stdout
    return {int(r[1]) for r in csv.reader(out.splitlines())
            if len(r) > 1 and r[1].isdigit()}


def windows_for(pids):
    """Visible, top-level (unowned) windows belonging to these PIDs."""
    found = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, GW_OWNER):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids:
                found.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def enforce_window(name, proc_name, mode="minimized", timeout=30):
    """Watch for the app's windows and set each new one once. Blocks."""
    flag = SW_MAXIMIZE if mode == "maximized" else SW_SHOWMINNOACTIVE
    handled = set()
    deadline = time.time() + timeout
    while time.time() < deadline:
        for hwnd in windows_for(pids_for(proc_name)):
            if hwnd not in handled:
                user32.ShowWindow(hwnd, flag)
                handled.add(hwnd)
                log.info("%s: window set to %s", name, mode)
        time.sleep(0.5)
    if not handled:
        log.info("%s: no window found within %ss", name, timeout)


def start_window_watcher(name, proc_name, mode="minimized", timeout=30):
    """Run enforce_window in a background thread."""
    t = threading.Thread(
        target=enforce_window, args=(name, proc_name, mode, timeout), daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python window_ctrl.py ProcessName.exe [minimized|maximized]")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
    enforce_window(sys.argv[1], sys.argv[1],
                   sys.argv[2] if len(sys.argv) > 2 else "minimized", timeout=10)