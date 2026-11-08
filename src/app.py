"""Entry point of the packaged build (MSFSLauncher.exe).

    MSFSLauncher.exe            opens the GUI
    MSFSLauncher.exe --service  runs the launcher (this is what exe.xml starts)

When running from source you don't need this file: run gui.py for the GUI, and exe.xml
starts launcher.py directly.
"""
import sys

if "--service" in sys.argv:
    import launcher
    launcher.run()
else:
    import gui
    gui.main()
