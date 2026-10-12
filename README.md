# MSFS App Launcher

Starts your Microsoft Flight Simulator companion apps automatically when the sim starts, minimizes them, and closes them when the sim exits. Apps can also be held back until a flight is actually loaded (cockpit or external view) instead of starting in the main menu.

Configure your apps using the built-in GUI, or edit `apps.json` manually for advanced use.

# Requirements

- Windows
- Python 3.12 from the official site: <https://www.python.org/downloads/>. On the first screen of the installer, **tick "Add python.exe to PATH"** before clicking Install.
- The SimConnect package (only needed for apps that use `"start": "session"`):

```
pip install SimConnect
```

If SimConnect is not installed, session apps start immediately instead of waiting for a flight, and the log says `SimConnect not available`.

# Setup

1. **Put the folder somewhere permanent**, for example `C:\MSFS Launcher\`. If you move it later, update exe.xml (step 2).
2. **Point MSFS at the launcher** by adding an entry to your `exe.xml`:

```xml
<Launch.Addon>
  <Name>App Launcher</Name>
  <Disabled>False</Disabled>
  <ManualLoad>False</ManualLoad>
  <Path>C:\Users\YOU\AppData\Local\Programs\Python\Python312\pythonw.exe</Path>
  <CommandLine>"C:\MSFS Launcher\launcher.py"</CommandLine>
</Launch.Addon>
```

   - Change both paths to match your PC. `Path` must be the Python install that has SimConnect installed. `pythonw.exe` runs without a console window.
   - The launcher reads `apps.json` from its own folder by default. To use another file, add `--config "C:\path\to\apps.json"` after the script path in `CommandLine`.
   - If you already have other entries in `exe.xml`, add this one next to them and leave theirs alone. Make a backup of `exe.xml` first.
   - Where `exe.xml` lives depends on how you installed MSFS (Microsoft Store or Steam) and which version you run. If you don't know, search your PC for `exe.xml`. `exe.xml` is only read when the sim starts, so restart the sim after any change.

   Only one launcher entry should be active at a time. If two are, or an old one is left over, the second copy exits (see "Things to know").

3. **Run the GUI** by double-clicking `GUI.py` in your launcher folder. On first run, it will create `apps.json`.
4. **Add your games and apps** in the GUI. For each game, select the sim executable, then add your companion apps. You can configure launch behavior (delay, window state, close on exit, etc.) for each app.
5. **Save your configuration** in the GUI. Changes apply the next time you start the sim.

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
    },
    {
      "name": "My Weather Tool",
      "path": "C:/Program Files/Weather/Weather.exe",
      "delay": 0,
      "closeOnExit": true,
      "start": "session"
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
| `delay` | `0` | Seconds before this app launches. Counted from when the sim starts, or from when the flight is ready if `start` is `"session"`. |
| `start` | at sim start | Set to `"session"` to wait until a flight is loaded (see below). |
| `window` | `"minimized"` | `"minimized"` or `"maximized"`. |
| `closeOnExit` | `true` | Close the app when the sim exits. |
| `enabled` | `true` | Set `false` to skip the app without deleting it. |
| `process` | exe file name | Process name to close. Set this if the exe you launch starts a different process and quits. |
| `args` | none | List of command-line arguments, for example `["--flag"]`. |

# Starting apps when a flight is loaded

Some apps (weather tools, for example) only make sense once a flight is loaded, and misbehave if they start in the main menu. Set `"start": "session"` on those apps.

The launcher watches the sim's camera state through SimConnect. When the camera has stayed in a flight view (cockpit or external) for a few seconds, the flight is considered ready and session apps launch, after their own `delay`.

- The check happens **once per sim run**. Restarting the flight, changing aircraft, or going back to the main menu does not restart or close the app.
- If SimConnect cannot connect at all for 3 minutes, session apps start anyway so they are not held back forever.
- The log shows every camera state change and a `session ready` line when the apps are released, which helps if something starts too early or too late.

# Things to know

- **Changes to `apps.json` take effect the next time you start the sim.** No rebuild needed, because the launcher reads the file each time it starts.
- **Only one launcher runs at a time.** If a second copy starts (for example, one from `exe.xml` and one you ran by hand), it logs `another launcher instance is already running` and exits. If your code changes seem to have no effect, check which copy is running.
- **Some apps may need a delay.** Apps launched the moment the sim starts can fail if they expect the sim to be ready, and quit right away. Use `"start": "session"`, or increase the app's `delay` (try 20, then higher).
- **Log:** `launcher.log` is written next to the launcher. If something doesn't launch or close, check there first. Lines like `closed X` or `COULD NOT close X` show what happened at shutdown.
- Tray-only apps may never show a window. The log will say `no window found`, which is not an error.

# Known limitations

- **No tray icon or launcher visibility while running.** The launcher runs in the background only while the sim runs. To see it, look for `pythonw.exe` (or `MSFSLauncher.exe`) in Task Manager. To stop it early, end that process there. It exits on its own after the sim closes and the apps are shut down.
- Window control is limited to minimized or maximized, and some apps may restore their own window after being minimized.
- Session apps start once per sim run (see above).
- The camera-state values used to detect a flight were observed on MSFS 2024 and are not all verified. If an app starts too early, check the `camera state` lines in the log.

# Roadmap

Done:

- [x] Launch apps when the sim starts (via exe.xml, no manual step)
- [x] Per-app delay
- [x] Start apps minimized (or maximized)
- [x] Close apps when the sim exits
- [x] Runs as administrator so elevated apps can be closed
- [x] "Start when session loaded" option
- [x] Single-instance guard
- [x] GUI to add, remove, reorder, and configure apps

Planned updates:

- [ ] Tray icon so it is visible while running, with a menu to open the log or quit
- [ ] Explanatory text for every option in the GUI (tooltips)
- [ ] First-run setup that finds `exe.xml` and adds the launcher entry for you
- [ ] Pre-built exe as a GitHub release (zip package with first-run setup, no Python required)
- [ ] Support for MSFS 2020 and 2024 side by side
- [ ] Clearer logging, for example a warning when an app quits right after launching

# Development

## Testing with the real MSFS

Point `exe.xml` at `launcher.py` as shown in Setup. MSFS then starts your current code every time the sim launches: edit, save, start the sim, read `launcher.log`.

If `exe.xml` instead points at a built `MSFSLauncher.exe`, that exe runs whatever code it was built with, not your latest edits. Make sure `exe.xml` points where you think it does before debugging.

You can also override the sim name without editing `apps.json`:

```
python launcher.py --config apps.json --sim FlightSimulator2024.exe
```

or with an environment variable:

```
set MSFS_LAUNCHER_SIM=FlightSimulator2024.exe
python launcher.py --config apps.json
```

Run these in a terminal opened as administrator, since the launcher needs elevated privileges to close apps. Disable the `exe.xml` entry (`<Disabled>True</Disabled>`) while you do this, or the single-instance guard will make your manual copy exit.

## Testing without the sim

The launcher treats whatever `"sim"` names as the sim. To try it with Notepad:

1. In `apps.json`, set `"sim": "notepad.exe"` and add an app to launch, for example another program you have installed.
2. Open Notepad.
3. In a terminal opened as administrator, run `python launcher.py --config apps.json`.
4. Close Notepad. The launcher treats that as the sim exiting and closes the apps it started.

SimConnect never connects in this setup, so `"start": "session"` apps fall back to the timer. Test the camera-state logic with the real sim.

Check `launcher.log` for what happened. Set `"sim"` back before using it for real.