import sys
import os
import shutil
import tkinter as tk
from tkinter import filedialog
from dotenv import dotenv_values
from pathlib import Path
from PIL import Image
import configparser
import ctypes
config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".config")
ICON_FOLDER = dotenv_values(config_path)["ICON_FOLDER"]
SYSTEM_ICON_FOLDER = Path(dotenv_values(config_path)["SYSTEM_ICON_FOLDER"])


def refresh_explorer():
    SHCNE_ASSOCCHANGED = 0x08000000
    SHCNF_IDLIST = 0x0000

    ctypes.windll.shell32.SHChangeNotify(
        SHCNE_ASSOCCHANGED,
        SHCNF_IDLIST,
        None,
        None
    )


def set_folder_icon(folder: Path, icon_path: Path):
    desktop_ini = folder / "desktop.ini"

    config = configparser.ConfigParser()
    config.optionxform = str  # Preserve case of keys

    # Read existing desktop.ini if it exists
    if desktop_ini.exists():
        os.system(f'attrib -r -h -s "{desktop_ini}"')
        config.read(desktop_ini, encoding="utf-8")

    # Ensure [.ShellClassInfo] section exists
    if not config.has_section(".ShellClassInfo"):
        config.add_section(".ShellClassInfo")

    # Ensure [ViewState] exists
    if not config.has_section("ViewState"):
        config.add_section("ViewState")

    # Set/update icon
    config[".ShellClassInfo"]["IconResource"] = f"{icon_path},0"
    config[".ShellClassInfo"]["IconFile"] = str(icon_path)
    config[".ShellClassInfo"]["IconIndex"] = "0"

    config["ViewState"]["Mode"] = ""
    config["ViewState"]["Vid"] = ""
    config["ViewState"]["FolderType"] = "Generic"

    # Write back to desktop.ini
    with open(desktop_ini, "w", encoding="utf-8") as f:
        config.write(f)

    # Make desktop.ini hidden + system
    os.system(f'attrib +h +s "{desktop_ini}"')

    # Folder must be system for the icon to take effect
    os.system(f'attrib +s "{folder}"')


def ensure_icon(icon_filepath: Path, system_ico_filepath: Path):
    if icon_filepath.suffix.lower() == ".ico":
        shutil.copy(icon_filepath, system_ico_filepath)
        return

    img = Image.open(icon_filepath).convert("RGBA")
    img = img.resize((256, 256), Image.LANCZOS)
    img.save(
        system_ico_filepath,
        format="ICO",
        sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)]
    )


if __name__ == "__main__":
    targeted_folder = Path(sys.argv[1])
    if not SYSTEM_ICON_FOLDER.exists():
        os.mkdir(SYSTEM_ICON_FOLDER)
        os.system(f'attrib +s "{SYSTEM_ICON_FOLDER}"')

    root = tk.Tk()
    root.withdraw()

    icon_filepath = filedialog.askopenfilename(
        initialdir=ICON_FOLDER,
        title="Select a PNG file",
        filetypes=[("Image", "*.png *.jpg *.jpeg *.ico"), ("PNG", "*.png"), ("JPEG", "*.jpeg"), ("JPG", "*.jpg"), ("ICO", "*.ico"), ("ALL", "*.*")]
    )

    root.destroy()
    if icon_filepath:
        icon_filepath = Path(icon_filepath)
        icon_name = str(targeted_folder).replace(":", "").replace("\\", "_") + ".ico"
        system_ico_filepath = SYSTEM_ICON_FOLDER.joinpath(icon_name)
        ensure_icon(icon_filepath, system_ico_filepath)
        set_folder_icon(targeted_folder, system_ico_filepath)
        refresh_explorer()