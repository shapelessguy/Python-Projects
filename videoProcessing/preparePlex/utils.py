import sys
import os
import subprocess
import re
import stat
import ctypes
import json
from dotenv import dotenv_values
from shift_srt import shift_srt_subs
from colorama import init, Style
init(autoreset=True)


if sys.platform == "win32":
    kernel32 = ctypes.windll.kernel32
    hStdOut = kernel32.GetStdHandle(-11)
    mode = ctypes.c_uint()
    kernel32.GetConsoleMode(hStdOut, ctypes.byref(mode))
    kernel32.SetConsoleMode(hStdOut, mode.value | 0x0004)


API_KEY = dotenv_values(os.path.join(os.path.dirname(__file__), ".env"))["IMDB_KEY"]
FINAL_MOVIE_HOLDER_PATH = dotenv_values(os.path.join(os.path.dirname(__file__), ".config"))["FINAL_MOVIE_HOLDER_PATH"]
PURGATORY_FOLDER = dotenv_values(os.path.join(os.path.dirname(__file__), ".config"))["PURGATORY_FOLDER"]
VLC_PATH = r"C:\Program Files\VideoLAN\VLC\vlc.exe"


TRASH_FOLDER_NAME = ".trash"
WORKING_FOLDER_NAME = ".working"
READY_FOLDER_NAME = ".ready"


supported_video_ext = [
    "mp4",
    "mkv",
    "avi",
]


supported_external_subs_ext = [
    "srt",
    "idx",
    "sub",
]


supported_lang_codes = [
    "fr", "fre", "fra",   # French
    "es", "spa",          # Spanish
    "ko", "kor",          # Korean
    "en", "eng",          # English
    "de", "ger", "deu",   # German
    "it", "ita"           # Italian
]


def print_console(msg, color: str = None):
    if color:
        print(f"{color}{msg}{Style.RESET_ALL}", end="")
    else:
        print(msg, end="")
    return input()


class VideoInfo:
    def __init__(self, data):
        self.data = data
        self.external_subs = []
        self.clean_tags()
    
    def get_video_tracks(self):
        return [x for x in self.data["streams"] if x["codec_type"] == "video"]
    
    def get_audio_tracks(self):
        return [x for x in self.data["streams"] if x["codec_type"] == "audio"]

    def get_sub_tracks(self):
        return [x for x in self.data["streams"] if x["codec_type"] == "subtitle"]
    
    def clean_tags(self):
        for s in self.get_sub_tracks():
            tags = s.get("tags", {})
            s["tags"] = tags
            keys = list(tags.keys())
            key_map = {
                "language": ["lang", "language", "language_code", "code"],
                "title": ["title", "name", "track_name"]
            }
            for forced, aliases in key_map.items():
                for k in keys:
                    if k.lower() in aliases and k != forced:
                        tags[forced] = tags[k]
                        del tags[k]
                tags[forced] = tags.get(forced, "unknown")
                

    def __str__(self):
        return json.dumps(self.data, indent=4)


def remove_readonly(func, path, excinfo):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def sanitize_filename(name: str) -> str:
    if not name:
        return name
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', name)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.strip().rstrip(' .')
    return cleaned or name


def safe_remove_file(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)
        os.remove(path)


def convert_hms_to_seconds(time_string: str) -> float:
    """
    Converts a time string in HH:MM:SS.fractional_seconds format 
    (e.g., '02:15:19.028000000') into a total number of seconds (float).
    """
    try:
        h_str, m_str, s_f_str = time_string.split(':')
        hours = int(h_str)
        minutes = int(m_str)
        seconds_and_fraction = float(s_f_str)
        total_seconds = (hours * 3600) + (minutes * 60) + seconds_and_fraction
        
        return total_seconds
        
    except ValueError as e:
        raise ValueError(f"Invalid time string format. Expected HH:MM:SS.fraction, got '{time_string}'. Error: {e}")


def sub_delay_interface(external_subs):
    print("\nInsert a delay (i.e. +100, -1400) in MS for the following subtitles:")
    for sub in external_subs:
        delay = None
        while delay is None:
            delay = input(f'   {sub["tags"]["title"]} - {sub["tags"]["language"]}: ').lower().strip()
            try:
                delay = int(delay)
            except:
                delay = None
        if delay != 0:
            shift_srt_subs(sub["path"], sub["path"], delay)


def execute(cmd, errorMsg):
    try:
        result = subprocess.Popen(cmd, text=True, shell=True)
        result.wait()
        if result.returncode != 0:
            print(f"{errorMsg}")
            return False
        return True
    except subprocess.CalledProcessError as e:
        print(f"{errorMsg}:\n{e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False
