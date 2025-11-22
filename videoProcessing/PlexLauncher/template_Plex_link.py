
#  ----------------------------------------------------------------------------------------------
# | This script is not supposed to be launched manually!                                         |
# | Use pyinstaller to create an executable to replace the normal Plex link.                     |
# | Use plex_launch.bat for a complete installation                                              |
#  ----------------------------------------------------------------------------------------------


import os
import subprocess

# Set environment variables for this process
os.environ["PATH"] = r"C:\Program Files\SVP 4\mpv64;" + os.environ["PATH"]
os.environ["PYTHONHOME"] = r"C:\Program Files\SVP 4\mpv64"

# Path to Plex executable
plex_exe = r"C:\Program Files\Plex\Plex\Plex.exe"

# Launch Plex
subprocess.run([plex_exe])
