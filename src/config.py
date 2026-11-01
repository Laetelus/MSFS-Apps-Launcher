"""Load and save apps.json. Shared by the launcher and the GUI."""
import copy
import json
import os
import shutil
from pathlib import Path

# Default structure with per-game profiles
DEFAULT_PROFILE = {"apps": []}
DEFAULT = {"lastGame": "", "profiles": {}}


def load(path):
    """Read the config, or return an empty default if the file is missing.
    Handles backward compatibility by migrating old flat structure to profiles."""
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(DEFAULT)
    
    cfg = json.loads(path.read_text(encoding="utf-8"))
    
    # Migrate old format (flat "sim" and "apps") to new format (profiles)
    if "profiles" not in cfg:
        profiles = {}
        sim = cfg.get("sim", "").strip()
        apps = cfg.get("apps", [])
        
        if sim:
            profiles[sim] = {"apps": apps}
        
        cfg = {"lastGame": sim, "profiles": profiles}
    
    return cfg


def get_profile(cfg, game_exe):
    """Get profile for a specific game, or None if it doesn't exist."""
    return cfg.get("profiles", {}).get(game_exe)


def validate(cfg):
    """Raise ValueError with a readable message if the config is unusable."""
    if not isinstance(cfg.get("profiles"), dict):
        raise ValueError("The profiles section is missing or invalid.")
    
    for game_exe, profile in cfg["profiles"].items():
        if not isinstance(game_exe, str) or not game_exe.strip():
            raise ValueError("A profile has an empty game executable name.")
        if not isinstance(profile.get("apps"), list):
            raise ValueError(f"Profile for {game_exe} has no app list.")
        
        for i, app in enumerate(profile["apps"], 1):
            for key in ("name", "path"):
                if not isinstance(app.get(key), str) or not app[key].strip():
                    raise ValueError(f"In {game_exe}, app #{i} has no {key}.")


def save(path, cfg):
    """Validate, back up the old file to .bak, then write atomically."""
    validate(cfg)
    path = Path(path)
    if path.exists():
        shutil.copyfile(path, path.with_suffix(path.suffix + ".bak"))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)