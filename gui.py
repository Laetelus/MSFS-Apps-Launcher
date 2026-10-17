"""Config editor GUI for the MSFS app launcher.

    pip install pywebview
    python gui.py [--config path\to\apps.json]

The window is an HTML page (ui/index.html) talking to the Api class below.
It edits the same apps.json the launcher reads; changes apply the next time
the sim starts.
"""
import argparse
import sys
from pathlib import Path

import webview

import config

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if getattr(sys, "frozen", False):
    HERE = Path(sys.executable).resolve().parent
else:
    HERE = Path(__file__).resolve().parent


class Api:
    """Methods here are callable from the page as pywebview.api.<name>()."""

    def __init__(self, path):
        self._path = Path(path)
        self._window = None   # underscore: not exposed to the page
        self._cfg = None

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
                parts = line.split('  ', 1)
                if len(parts) == 2:
                    timestamp, message = parts
                    # Extract just time from timestamp
                    time_part = timestamp.split(' ')[1] if ' ' in timestamp else timestamp
                    logs.append({"time": time_part, "msg": message})
            
            return logs
        except Exception as e:
            return [{"time": "ERROR", "msg": str(e)}]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="path to apps.json")
    args = parser.parse_args()
    path = Path(args.config) if args.config else HERE / "apps.json"

    api = Api(path)
    # Adjust window size 
    api._window = webview.create_window(
        "MSFS App Launcher", str(BASE / "ui" / "index.html"),
        js_api=api, width=1120, height=720, min_size=(1120, 720))
    webview.start()


if __name__ == "__main__":
    main()
