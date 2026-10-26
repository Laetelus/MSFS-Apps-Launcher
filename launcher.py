"""MSFS app launcher - proof of concept.

Run by exe.xml when the sim starts. Reads apps.json (same folder), launches
each enabled app (after its delay, counted from when this script starts),
waits for the sim to exit, then closes the apps it launched.

Windows only, standard library only. Writes launcher.log next to this file,
because there is no console window when exe.xml runs it.

"""
import ctypes
import json
import logging
import socket
import subprocess
import sys
import time
import os
import argparse  
from session_watch import start_session_watch
from window_ctrl import start_window_watcher
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--config", help="path to apps.json")
parser.add_argument("--sim", help="override sim executable name (for development/testing)")
ARGS = parser.parse_args()

if getattr(sys, "frozen", False):
    HERE = Path(sys.executable).resolve().parent   # running as an exe
else:
    HERE = Path(__file__).resolve().parent         # running as a script

CONFIG = Path(ARGS.config) if ARGS.config else HERE / "apps.json"
LOG = HERE / "launcher.log"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

logging.basicConfig(
    filename=LOG,
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
)
log = logging.getLogger("launcher")
log.info("args: %s", sys.argv)
log.info("config path: %s", CONFIG)


def is_gui_running():
    """Check if GUI is already running by attempting to connect to its lock socket."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', 54321))
        sock.close()
        if result == 0:
            log.info("GUI already running (detected on port 54321)")
            return True
        return False
    except Exception as exc:
        log.info("error checking if GUI is running: %s", exc)
        return False


def is_running(exe_name):
    """True if a process with this image name is running."""
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, creationflags=NO_WINDOW,
    ).stdout
    # Found processes print as CSV rows starting with a quote; the "no match"
    # message does not. This avoids depending on the Windows language.
    return out.lstrip().startswith('"')


def close_all(launched, grace=3.0):
    """Close every app flagged closeOnExit, in parallel."""
    targets = {proc: name for name, proc, close in launched if close}
    if not targets:
        return

    def kill(proc, force):
        cmd = ["taskkill", "/IM", proc, "/T"] + (["/F"] if force else [])
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                creationflags=NO_WINDOW)

    for proc in targets:                      # polite request to all, at once
        kill(proc, False)

    deadline = time.time() + grace            # one shared grace period
    remaining = list(targets)
    while remaining and time.time() < deadline:
        remaining = [p for p in remaining if is_running(p)]
        if remaining:
            time.sleep(0.25)

    for proc in remaining:                    # force survivors, all at once
        kill(proc, True)

    for _ in range(8):                        # brief wait, then verify
        if not any(is_running(p) for p in targets):
            break
        time.sleep(0.25)

    for proc, name in targets.items():
        if is_running(proc):
            log.info("COULD NOT close %s (process %s)", name, proc)
        else:
            log.info("closed %s", name)


def launch(app):
    """Start one app. Returns (name, process_name, close_on_exit) or None."""
    path = Path(app["path"])
    proc_name = app.get("process", path.name)
    if is_running(proc_name):
        log.info("%s already running, skipping", app["name"])
        return (app["name"], proc_name, app.get("closeOnExit", True))
    
    env = {**os.environ, "__COMPAT_LAYER": "RunAsInvoker"} if app.get("runAsInvoker", True) else None
    subprocess.Popen([str(path), *app.get("args", [])], cwd=path.parent, env=env)
    start_window_watcher(app["name"], proc_name, app.get("window", "minimized"))
    log.info("launched %s", app["name"])
    return (app["name"], proc_name, app.get("closeOnExit", True))


def launch_due(pending, elapsed, launched):
    """Launch every app in `pending` whose delay has passed (removes them)."""
    while pending and pending[0].get("delay", 0) <= elapsed:
        app = pending.pop(0)
        try:
            result = launch(app)
            if result:
                launched.append(result)
        except Exception as exc:  # one bad path shouldn't stop the rest
            log.info("failed to launch %s: %s", app["name"], exc)


def main():
    if not CONFIG.exists():
        log.info("No config at %s. Open the GUI, add a game and apps, and save.", CONFIG)
        return
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    
    # Allow override via environment variable or command-line argument (useful for development)
    sim = ARGS.sim or os.environ.get("MSFS_LAUNCHER_SIM")
    
    if not sim:
        # Auto-detect which game is running
        profiles = cfg.get("profiles", {})
        if not profiles:
            log.info("No games configured. Open the GUI and add a game.")
            return
        
        # Check which game process is running
        for game_exe in profiles.keys():
            if is_running(game_exe):
                sim = game_exe
                break
        else:
            log.info("No configured game is currently running. Available: %s", list(profiles.keys()))
            return
    
    log.info("using sim: %s (source: %s)", sim, 
             "CLI arg" if ARGS.sim else ("env var" if os.environ.get("MSFS_LAUNCHER_SIM") else "auto-detect"))
    
    # Load the profile for this game
    profile = cfg.get("profiles", {}).get(sim)
    if not profile:
        log.info("No profile for %s. Configure it in the GUI.", sim)
        return
    
    apps = [a for a in profile.get("apps", []) if a.get("enabled", True)]
    session_apps = sorted((a for a in apps if a.get("start") == "session"),
                          key=lambda a: a.get("delay", 0))
    apps = sorted((a for a in apps if a.get("start") != "session"),
                  key=lambda a: a.get("delay", 0))

    # exe.xml starts us with the sim, but give it a minute to show up.
    for _ in range(30):
        if is_running(sim):
            break
        time.sleep(2)
    else:
        log.info("%s never appeared, exiting", sim)
        return

    log.info("%s detected, starting", sim)
    start = time.time()
    launched = []
    
    # Launch the GUI app (minimized to tray) - but only if not already running
    gui_proc = None
    try:
        if not is_gui_running():
            gui_path = HERE / "gui.py"
            if gui_path.exists():
                cmd = [sys.executable, str(gui_path), "--config", str(CONFIG), "--sim", sim, "--minimized"]
                gui_proc = subprocess.Popen(cmd, cwd=HERE, creationflags=NO_WINDOW)
                log.info("launched GUI (pid %s) minimized to tray", gui_proc.pid)
            else:
                log.info("GUI not found at %s", gui_path)
        else:
            log.info("GUI already running, not launching another instance")
    except Exception as exc:
        log.info("failed to launch GUI: %s", exc)
    
    session_ready = start_session_watch(lambda: is_running(sim)) if session_apps else None
    session_start = None

    while is_running(sim):
        elapsed = time.time() - start
        launch_due(apps, elapsed, launched)

        if session_ready is not None and session_ready.is_set():
            if session_start is None:
                session_start = time.time()
            launch_due(session_apps, time.time() - session_start, launched)
        time.sleep(1)

    log.info("sim exited, closing apps")
    
    # Only close GUI if we launched it (gui_proc is not None)
    if gui_proc:
        try:
            gui_proc.terminate()
            gui_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            gui_proc.kill()
        except Exception as exc:
            log.info("error closing GUI: %s", exc)
    else:
        log.info("GUI was already running, leaving it open")
    
    close_all(launched)
    
    
def is_admin():
    return bool(ctypes.windll.shell32.IsUserAnAdmin())

if __name__ == "__main__":
    try:
        if not is_admin():
            log.info("not elevated, relaunching as administrator")
            if getattr(sys, "frozen", False):
                params = subprocess.list2cmdline(sys.argv[1:])          # exe: pass the same args
            else:
                params = subprocess.list2cmdline(
                    [str(Path(__file__).resolve()), *sys.argv[1:]])     # script: path + args
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, params or None, None, 0)
            if result <= 32:  # ShellExecute returns <= 32 on failure
                log.info("elevation failed or was declined (code %s)", result)
            sys.exit()
        log.info("running elevated")
        main()
    except Exception:
        log.exception("launcher crashed")
        sys.exit(1)