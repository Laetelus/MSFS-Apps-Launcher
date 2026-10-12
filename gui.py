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

    def get_config(self):
        return config.load(self._path)

    def config_path(self):
        return str(self._path)

    def save_config(self, cfg):
        try:
            config.save(self._path, cfg)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def browse_exe(self, folder=None):
        folder = Path(folder) if folder and Path(folder).is_dir() else None
        result = self._window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=("Programs (*.exe)",), directory=str(folder) if folder else None)
        return result[0] if result else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="path to apps.json")
    args = parser.parse_args()
    path = Path(args.config) if args.config else HERE / "apps.json"

    api = Api(path)
    api._window = webview.create_window(
        "MSFS App Launcher", str(BASE / "ui" / "index.html"),
        js_api=api, width=1300, height=720, min_size=(900, 600))
    webview.start()


if __name__ == "__main__":
    main()
