# MSFS App Launcher

Starts your Microsoft Flight Simulator companion apps automatically when the sim starts, minimizes them, and closes them when the sim exits.

This is an early version. It is configured by editing a JSON file; a GUI is planned.

# Setup

1. **Put the folder somewhere permanent**, for example `C:\MSFS Launcher\`. If you move it later, update exe.xml (step 3).
2. **Edit `apps.json`** in that folder and list your apps (see below). The file ships with placeholder entries that you replace.
3. **Point MSFS at the launcher** by adding an entry to your `exe.xml`:

## apps.json

```json
{
  "sim": "FlightSimulator2024.exe",
  "apps": [
    {
      "name": "My App",
      "path": "C:/Program Files/MyApp/MyApp.exe",
      "delay": 0,
      "closeOnExit": true
    }
  ]
}
```

Use forward slashes in paths (`C:/like/this`). For `"sim"`, use `FlightSimulator2024.exe` for MSFS 2024 or `FlightSimulator.exe` for MSFS 2020.

Per app:

| Field | Default | Meaning |
|---|---|---|
| `name` | required | Label used in the log. |
| `path` | required | Full path to the app's exe. |
| `delay` | `0` | Seconds after the sim starts before this app launches. |
| `window` | `"minimized"` | `"minimized"` or `"maximized"`. |
| `closeOnExit` | `true` | Close the app when the sim exits. |
| `enabled` | `true` | Set `false` to skip the app without deleting it. |
| `skipIfRunning` | `true` | Don't launch the app if it is already running. Apps that were already open are not closed later. |
| `process` | exe file name | Process name to close. Set this if the exe you launch starts a different process and quits. |
| `args` | none | List of command-line arguments, for example `["--flag"]`. |

## exe.xml

```xml
<Launch.Addon>
  <Name>App Launcher</Name>
  <Disabled>False</Disabled>
  <ManualLoad>False</ManualLoad>
  <Path>C:\MSFS Launcher\MSFSLauncher.exe</Path>
  <CommandLine>--config "C:\MSFS Launcher\apps.json"</CommandLine>
</Launch.Addon>
```

   Change both paths to where you put the files. If you already have other entries in `exe.xml`, add this one next to them and leave theirs alone. Make a backup of `exe.xml` first.

   Where `exe.xml` lives depends on how you installed MSFS (Microsoft Store or Steam) and which version you run. If you don't know, search your PC for `exe.xml`. Note, `exe.xml` is only read when the sim starts, so restart the sim after any change.

## Build the exe

1. **Install Python** from the official site: <https://www.python.org/downloads/>. On the first screen of the installer, **tick "Add python.exe to PATH"** before clicking Install. If you skip this, the build will not find Python. (If you already installed Python without it, run the installer again and choose Modify, or reinstall.)
2. **Double-click `build.bat`.** It checks for Python, installs the build tool (PyInstaller), and builds the exe.
3. When it finishes, the exe is in `dist\MSFSLauncher\`. Keep the `_internal` folder next to `MSFSLauncher.exe`, and point exe.xml at that exe (see Setup).

Built and tested with Python 3.12. The launcher itself uses only the standard library.

# Things to know

- **Editing `apps.json` does not require rebuilding the exe.** The launcher reads the file named by `--config` each time it starts, so changes take effect the next time you start the sim. Rebuild only when the code changes.
- **Some apps may need a delay.** Apps launched the moment the sim starts can fail if they expect the sim to be ready, and quit right away. If an app starts and immediately closes, increase its `delay` (try 20, then higher). Longer sim load times need longer delays.
- **Log:** `launcher.log` is written next to `MSFSLauncher.exe`. If something doesn't launch or close, check there first. Lines like `closed X` or `COULD NOT close X` show what happened at shutdown.
- **Antivirus** may flag the exe, as it does with many programs built with PyInstaller. The source is in this repo.
- Tray-only apps may never show a window. The log will say `no window found`, which is not an error.

# Known limitations

- **No window, taskbar icon, or tray icon yet.** The launcher runs in the background only while the sim runs. To see it, look for `MSFSLauncher.exe` in Task Manager. To stop it early, end that process there. It exits on its own after the sim closes and the apps are shut down.
- Configuration is by editing `apps.json` by hand.
- Window control is limited to minimized or maximized, and some apps may restore their own window after being minimized.

# Roadmap

Done:

- [x] Launch apps when the sim starts (via exe.xml, no manual step)
- [x] Per-app delay
- [x] Start apps minimized (or maximized)
- [x] Close apps when the sim exits
- [x] Runs as administrator so elevated apps can be closed

Planned updates:

- [ ] Tray icon so it is visible while running, with a menu to open the log or quit
- [ ] "Start when session loaded" option, so apps start when a flight is ready and not after a fixed delay
- [ ] GUI to add, remove, reorder, and configure apps (this will also provide the taskbar icon)
- [ ] Explanatory text for every option, so nothing in the GUI is confusing
- [ ] First-run setup that finds `exe.xml` and adds the launcher entry for you
- [ ] Option to turn administrator mode on or off
- [ ] Support for MSFS 2020 and 2024 side by side
- [ ] Clearer logging, for example a warning when an app quits right after launching

# Testing without the sim

The launcher treats whatever `"sim"` names as the sim. To try it with Notepad:

1. In `apps.json`, set `"sim": "notepad.exe"` and add an app to launch, for example another program you have installed.
2. Open Notepad.
3. In a terminal opened as administrator, run `python launcher.py --config apps.json`.
4. Close Notepad. The launcher treats that as the sim exiting and closes the apps it started.

Check `launcher.log` for what happened. Set `"sim"` back before using it for real.