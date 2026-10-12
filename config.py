"""Load and save apps.json. Shared by the launcher and the GUI."""
import copy
import json
import os
import shutil
from pathlib import Path

DEFAULT = {"sim": "", "apps": []}


def load(path):
    """Read the config, or return an empty default if the file is missing."""
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(DEFAULT)
    return json.loads(path.read_text(encoding="utf-8"))


def validate(cfg):
    """Raise ValueError with a readable message if the config is unusable."""
    if not isinstance(cfg.get("sim"), str) or not cfg["sim"].strip():
        raise ValueError("The sim executable name is empty.")
    if not isinstance(cfg.get("apps"), list):
        raise ValueError("The app list is missing.")
    for i, app in enumerate(cfg["apps"], 1):
        for key in ("name", "path"):
            if not isinstance(app.get(key), str) or not app[key].strip():
                raise ValueError(f"App #{i} has no {key}.")


def save(path, cfg):
    """Validate, back up the old file to .bak, then write atomically."""
    validate(cfg)
    path = Path(path)
    if path.exists():
        shutil.copyfile(path, path.with_suffix(path.suffix + ".bak"))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)