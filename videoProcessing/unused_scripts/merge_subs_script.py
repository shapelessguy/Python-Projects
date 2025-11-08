import sys
import os
import subprocess
from pathlib import Path
import shutil
import traceback
import stat


def print_console(msg):
    input(f"{msg}\n\nPress Enter to continue...")


def remove_readonly(func, path, excinfo):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def process_folder(folder_path: Path):
    print(f"Remuxing {folder_path}...")
    all_files = os.listdir(folder_path)
    mkv_files = [x for x in all_files if x.endswith(".mkv")]
    srt_files = [x for x in all_files if x.endswith(".srt")]
    if len(mkv_files) != 1:
        print_console(f"The number of mkv files in {folder_path} expected is 1. Found {len(mkv_files)}")
        return
    mkv_filename = mkv_files[0]
    if len(srt_files) == 0:
        print_console(f"No srt files for {mkv_filename} found!")
        return

    print(f"\tMerging subs for {mkv_filename}...")
    mkv_input_file = folder_path.joinpath(mkv_filename)
    mkv_outer_file = folder_path.parent.joinpath(mkv_filename)
    mkv_temp_file = folder_path.parent.joinpath("output_" + mkv_filename)
    cmd = [
        "C:\Program Files (x86)\SVP 4\extensions\code\mkvmerge",
        "-o", str(mkv_temp_file),
        str(mkv_input_file)
    ]
    for sub in srt_files:
        parts = sub.split(".")
        sub_name = parts[0]
        sub_lang = parts[1] if len(parts) > 1 else parts[0]
        cmd += ["--language", f"0:{sub_lang}"]
        cmd += ["--track-name", f"0:{sub_name}", str(folder_path.joinpath(sub))]

    try:
        result = subprocess.Popen(cmd, text=True, shell=True)
        result.wait()
    except subprocess.CalledProcessError as e:
        print(f"Error during mkvmerge execution (check log file for details):\n{e.stderr}")
        return
    except Exception as e:
        print(f"Error: {e}")
        return

    try:
        shutil.move(mkv_temp_file, mkv_outer_file)
        shutil.rmtree(folder_path, onerror=remove_readonly)
    except:
        print_console(traceback.format_exc())
        try:
            os.remove(str(mkv_temp_file))
        except:
            return
        return


def main():
    if len(sys.argv) > 1:
        target_path = Path(sys.argv[1].replace("\n", ""))
    else:
        return

    process_folder(target_path)


if __name__ == "__main__":
    main()