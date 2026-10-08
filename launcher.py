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
import subprocess
import sys
import time
import os
import argparse   # put this with your other imports at the top
from window_ctrl import start_window_watcher
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--config", help="path to apps.json")
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
    if app.get("skipIfRunning", True) and is_running(proc_name):
        log.info("%s already running, skipping", app["name"])
        return None
    # "requires administrator" prompt that would otherwise cause WinError 740
    env = {**os.environ, "__COMPAT_LAYER": "RunAsInvoker"} if app.get("runAsInvoker", True) else None
    subprocess.Popen([str(path), *app.get("args", [])], cwd=path.parent, env=env)
    start_window_watcher(app["name"], proc_name, app.get("window", "minimized"))
    log.info("launched %s", app["name"])
    return (app["name"], proc_name, app.get("closeOnExit", True))


def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    sim = cfg["sim"]
    apps = [a for a in cfg["apps"] if a.get("enabled", True)]
    apps.sort(key=lambda a: a.get("delay", 0))  # stable: keeps list order

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

    while is_running(sim):
        elapsed = time.time() - start
        while apps and apps[0].get("delay", 0) <= elapsed:
            app = apps.pop(0)
            try:
                result = launch(app)
                if result:
                    launched.append(result)
            except Exception as exc:  # one bad path shouldn't stop the rest
                log.info("failed to launch %s: %s", app["name"], exc)
        time.sleep(1)

    log.info("sim exited, closing apps")
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