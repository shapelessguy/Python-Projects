import sys
import os
from dotenv import dotenv_values
from pathlib import Path
import shutil


config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".config")
PURGATORY_FOLDER = Path(dotenv_values(config_path)["PURGATORY_FOLDER"])
if not PURGATORY_FOLDER:
    print("Error: PURGATORY_FOLDER not found in config")
    sys.exit(1)


def move_to_purgatory(src_path_str: str):
    src = Path(src_path_str).resolve()
    
    if not src.exists():
        print(f"Error: Path does not exist: {src}")
        return False
    
    dest = PURGATORY_FOLDER / src.name
    
    if dest.exists():
        stem = src.stem
        suffix = src.suffix
        counter = 1
        while dest.exists():
            new_name = f"{stem} ({counter}){suffix}" if src.is_file() else f"{stem} ({counter})"
            dest = PURGATORY_FOLDER / new_name
            counter += 1
        print(f"Destination existed → using {dest.name}")
    
    try:
        shutil.move(src, dest)
        print(f"Moved: {src}")
        print(f"     → {dest}")
        return True
    except shutil.Error as e:
        print(f"Move failed (maybe cross-device or permission): {e}")
        return False
    except PermissionError:
        print(f"Permission denied: {src}")
        return False
    except Exception as e:
        print(f"Unexpected error moving {src}: {e}")
        return False


if __name__ == "__main__":
    input_path = Path(sys.argv[1])
    move_to_purgatory(input_path)
    
    
