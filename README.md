# MSFS App Launcher

> ⚠️ **In Development** — This project is still under development. Bugs and issues are expected.

Starts your Microsoft Flight Simulator companion apps automatically when the sim starts, minimizes them, and closes them when the sim exits. Apps can also be held back until a flight is actually loaded (cockpit or external view) instead of starting in the main menu.

Configure your apps using the built-in GUI, which includes system tray support for convenient access. Or edit `apps.json` manually for advanced use.

# Requirements

- Windows
- Python from the official site: <https://www.python.org/downloads/>. In the installer, **tick "Add python.exe to PATH"** on the first screen. It is needed to run `build.bat`, even if you only use the built exe afterwards.

`build.bat` installs the Python packages it needs by itself.

# Install

1. Make sure Python is installed (see Requirements).
2. Clone this repository (or download it as a zip and unzip it).
3. Double-click `build.bat`. It installs what it needs and creates `dist\MSFSLauncher\MSFSLauncher.exe`.
4. Run `dist\MSFSLauncher\MSFSLauncher.exe`. Keep the `_internal` folder next to the exe. Your settings (`apps.json`) are saved next to the exe.
5. On first run, the app asks whether to add itself to MSFS's `exe.xml`, which is how MSFS starts the launcher with the sim. Press **Add to exe.xml** to accept, or **Not now** to skip it. Skipping is fine: you can add it later, or repair it if something goes wrong or you move the folder, in **Settings > MSFS integration** (**Add**, **Fix**, **Remove**).
6. Add your apps in the GUI. Changes apply the next time you start the sim.

Note: you can move the `dist\MSFSLauncher` folder wherever you like (keep it somewhere you can write to). If you do, open the app and press **Fix** in **Settings > MSFS integration** so `exe.xml` points at the new location.

Windows may show "Windows protected your PC" because the exe is not code-signed: click **More info**, then **Run anyway**. Running `build.bat` again after you update the code rebuilds the exe and keeps your `apps.json`.

# Running from source (for development)

For working on the code or understanding how it works, you can run it without building the exe. Besides Python (see Requirements), install:

- The SimConnect package (only needed for apps that use `"start": "session"`):

```
pip install SimConnect
```

If SimConnect is not installed, session apps start immediately instead of waiting for a flight, and the log says `SimConnect not available`.

- For GUI system tray support (optional but recommended), install pystray and dependencies:

```
pip install pywebview pystray pillow
```

If pystray is not installed, the GUI will still work but without system tray minimize and menu features.

# Source setup

1. **Keep the folder somewhere permanent**, for example `C:\MSFS Launcher\`. If you move it, press **Fix** in **Settings > MSFS integration**.
2. **Run the GUI**: `python src\gui.py`. On first run it creates `apps.json` and asks whether to add the launcher to your `exe.xml` (**Add to exe.xml** or **Not now**). You can do it later, or repair it, in **Settings > MSFS integration**.
   - The GUI minimizes to the system tray (if pystray is installed) for easy access when in game.
   - Click the tray icon to show the window, or right-click for a menu.
3. **Add your games and apps** in the GUI. For each game, select the sim executable, then add your companion apps. You can configure launch behavior (delay, window state, close on exit, etc.) for each app.
4. **Changes are saved automatically** and apply the next time you start the sim.

## Adding the exe.xml entry by hand

Only needed if you don't use the GUI button. Add an entry to your `exe.xml`:

```xml
<Launch.Addon>
  <Name>MSFS App Launcher</Name>
  <Disabled>False</Disabled>
  <ManualLoad>False</ManualLoad>
  <Path>C:\Users\YOU\AppData\Local\Programs\Python\Python312\pythonw.exe</Path>
  <CommandLine>"C:\MSFS Launcher\src\launcher.py"</CommandLine>
</Launch.Addon>
```

   - Change both paths to match your PC. `Path` must be the Python install that has SimConnect installed. `pythonw.exe` runs without a console window. For the built exe, use `Path` = the full path to `MSFSLauncher.exe` and `CommandLine` = `--service`.
   - Use the name `MSFS App Launcher` so the GUI recognizes the entry.
   - The launcher reads `apps.json` from its own folder by default. To use another file, add `--config "C:\path\to\apps.json"` after the script path in `CommandLine`.
   - If you already have other entries in `exe.xml`, add this one next to them and leave theirs alone. Make a backup of `exe.xml` first.
   - Where `exe.xml` lives depends on how you installed MSFS (Microsoft Store or Steam) and which version you run. `exe.xml` is only read when the sim starts, so restart the sim after any change.

   Only one launcher entry should be active at a time. If two are, or an old one is left over, the second copy exits (see "Things to know").

## apps.json

The launcher supports **separate profiles for each game** (MSFS 2024 and MSFS 2020). You can configure different apps for each game using the GUI.

```json
{
  "lastGame": "FlightSimulator2024.exe",
  "profiles": {
    "FlightSimulator2024.exe": {
      "apps": [
        {
          "name": "TouchdownFX",
          "path": "C:/Program Files/TouchdownFX/TouchdownFX.exe",
          "delay": 0,
          "closeOnExit": true,
          "enabled": true
        },
        {
          "name": "My Weather Tool",
          "path": "C:/Program Files/Weather/Weather.exe",
          "delay": 5,
          "closeOnExit": true,
          "start": "session",
          "enabled": true
        }
      ]
    },
    "FlightSimulator.exe": {
      "apps": []
    }
  }
}
```

Use forward slashes in paths (`C:/like/this`). Game executables are:
- `FlightSimulator2024.exe` for MSFS 2024
- `FlightSimulator.exe` for MSFS 2020

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

- **The launcher runs in the background while the sim runs.** The launcher itself has no visible window, only the apps it launches appear. MSFS starts it through `exe.xml` (`MSFSLauncher.exe --service`, or `pythonw.exe` when running from source). To monitor or stop it early, look for that process in Task Manager. It exits on its own after the sim closes and the apps are shut down.
- **The GUI and the launcher are separate processes.** The window you configure things in (`MSFSLauncher.exe` opened normally) does not start your apps, and the launcher does not need it open. If **Launch with MSFS** is on, the launcher opens the GUI for you when the sim starts. So during a flight you may see two `MSFSLauncher.exe` entries in Task Manager: one is the launcher, the other is the GUI.
- Window control is limited to minimized or maximized, and some apps may restore their own window after being minimized.
- Session apps start once per sim run (see above).
- The camera-state values used to detect a flight were observed on MSFS 2024 and are not all verified. If an app starts too early, check the `camera state` lines in the log.

# Development

## Testing with the real MSFS

Point `exe.xml` at `src\launcher.py` (the GUI's **Fix** button does this when you run it from source). MSFS then starts your current code every time the sim launches: edit, save, start the sim, read `launcher.log`.

If `exe.xml` instead points at a built `MSFSLauncher.exe`, that exe runs whatever code it was built with, not your latest edits. Run `build.bat` again to update it, or press **Fix** in the GUI from source to switch back. The status in Settings shows which one `exe.xml` points to.

You can also override the sim name without editing `apps.json`:

```
python src\launcher.py --config apps.json --sim FlightSimulator2024.exe
```

or with an environment variable:

```
set MSFS_LAUNCHER_SIM=FlightSimulator2024.exe
python src\launcher.py --config apps.json
```

Run these in a terminal opened as administrator, since the launcher needs elevated privileges to close apps. Disable the `exe.xml` entry (`<Disabled>True</Disabled>`) while you do this, or the single-instance guard will make your manual copy exit.

## Testing without the sim

The launcher treats whatever `"sim"` names as the sim. To try it with Notepad:

1. In `apps.json`, set `"sim": "notepad.exe"` and add an app to launch, for example another program you have installed.
2. Open Notepad.
3. In a terminal opened as administrator, run `python src\launcher.py --config apps.json`.
4. Close Notepad. The launcher treats that as the sim exiting and closes the apps it started.

SimConnect never connects in this setup, so `"start": "session"` apps fall back to the timer. Test the camera-state logic with the real sim.

Check `launcher.log` for what happened. Set `"sim"` back before using it for real.e