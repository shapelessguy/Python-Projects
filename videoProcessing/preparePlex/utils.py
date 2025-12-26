import sys
import os
import subprocess
import re
import stat
import ctypes
import json
import shutil
import time
from dotenv import dotenv_values
from colorama import init, Fore, Style
from pathlib import Path
import paramiko
from shift_srt import shift_srt_subs
init(autoreset=True)


if sys.platform == "win32":
    kernel32 = ctypes.windll.kernel32
    hStdOut = kernel32.GetStdHandle(-11)
    mode = ctypes.c_uint()
    kernel32.GetConsoleMode(hStdOut, ctypes.byref(mode))
    kernel32.SetConsoleMode(hStdOut, mode.value | 0x0004)


config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".config")
API_KEY = dotenv_values(os.path.join(os.path.dirname(__file__), ".env"))["IMDB_KEY"]
FINAL_MOVIE_HOLDER_PATH = dotenv_values(config_path)["FINAL_MOVIE_HOLDER_PATH"]
PURGATORY_FOLDER = dotenv_values(config_path)["PURGATORY_FOLDER"]
VLC_PATH = r"C:\Program Files\VideoLAN\VLC\vlc.exe"


TRASH_FOLDER_NAME = ".trash"
WORKING_FOLDER_NAME = ".working"
READY_FOLDER_NAME = ".ready"
sftp = None


supported_video_ext = [
    "mp4",
    "m4v",
    "mkv",
    "avi",
]


supported_external_subs_ext = [
    "srt",
    "idx",
    "sub",
]


full_language_codes = {
    "French": ["fr", "fre", "fra"],
    "Spanish": ["es", "spa"],
    "Korean": ["ko", "kor"],
    "English": ["en", "eng"],
    "German": ["de", "ger", "deu"],
    "Italian": ["it", "ita"],
    "Portuguese": ["pt", "por"],
    "Russian": ["ru", "rus"],
    "Chinese": ["zh", "chi", "zho"],
    "Japanese": ["ja", "jpn"],
    "Arabic": ["ar", "ara"],
    "Dutch": ["nl", "dut", "nld"],
    "Swedish": ["sv", "swe"],
    "Norwegian": ["no", "nor"],
    "Danish": ["da", "dan"],
    "Finnish": ["fi", "fin"],
    "Polish": ["pl", "pol"],
    "Turkish": ["tr", "tur"],
    "Greek": ["el", "gre", "ell"],
    "Czech": ["cs", "cze", "ces"],
    "Hungarian": ["hu", "hun"],
    "Hebrew": ["he", "heb"],
    "Romanian": ["ro", "rum", "ron"],
    "Ukrainian": ["uk", "ukr"],
    "Thai": ["th", "tha"]
}


supported_lang_codes = [e for x in full_language_codes.values() for e in x]


def get_extended(language_code: str):
    for v in full_language_codes.values():
        if language_code in v:
            return v[-1]
    return language_code


def initialize_sftp():
    global sftp
    if "@" in FINAL_MOVIE_HOLDER_PATH:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(
                hostname=FINAL_MOVIE_HOLDER_PATH.split("@")[1].split(":")[0],
                username=FINAL_MOVIE_HOLDER_PATH.split("@")[0],
                look_for_keys=True,
                allow_agent=True,
                timeout=1
            )
            sftp = client.open_sftp()
        except Exception:
            print(f"{Fore.RED}Address {FINAL_MOVIE_HOLDER_PATH} unavailable{Style.RESET_ALL}\n")
    else:
        sftp = None


def print_console(msg, color: str = None):
    if color:
        print(f"{color}{msg}{Style.RESET_ALL}", end="")
    else:
        print(msg, end="")
    return input()


def tryMagnet(language_str: str):
    return_value = None
    if not language_str:
        return None
    for k, v_ in {**full_language_codes, "multi": ["multi"]}.items():
        pattern = re.compile(rf"(?<![A-Za-z ])(?:{'|'.join(v_ + [k])})(?![A-Za-z ])",re.IGNORECASE)
        match = pattern.search(language_str)
        if match:
            if return_value is not None:
                print(match.group(0).lower(), return_value)
                return None
            return_value = v_[0]
    return return_value


class VideoInfo:
    def __init__(self, data, video_path):
        self.video_path = video_path
        self.data = data
        self.external_subs = []
        self.remux_audio = False
        self.to_trash = False
        self.standardize()
    
    def standardize(self):
        for s in self.get_audio_tracks() + self.get_sub_tracks():
            s["offset"] = 0
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
    
    def get_video_tracks(self):
        return [x for x in self.data["streams"] if x["codec_type"] == "video"]
    
    def get_audio_tracks(self):
        return [x for x in self.data["streams"] if x["codec_type"] == "audio"]

    def get_sub_tracks(self):
        return [x for x in self.data["streams"] if x["codec_type"] == "subtitle"]

    def get_external_subs(self):
        return self.external_subs
    
    def add_external_sub(self, path, extension, title, language):
        self.external_subs.append({
            "path": path,
            "offset": 0,
            "extension": extension,
            "codec_name": "subrip",
            "tags": {
                "title": f"External SUB: {title}",
                "language": language
            }
        })
                

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


def open_or_test(usr_input: str, video_path: Path):
    usr_input = usr_input.replace("\n", "").strip().lower()
    if usr_input == "o":
        os.startfile(video_path.parent)
        return True
    elif usr_input == "t":
        open_video(video_path)
        return True
    return False


def open_video(path):
    print(f"Opening video: {path}")
    subprocess.Popen([VLC_PATH, path])


def move(src, dst):
    exception = True
    while exception:
        exception = False
        try:
            os.makedirs(Path(dst).parent, exist_ok=True)
            shutil.move(src, dst)
        except PermissionError:
            print_console(f"Access denied on {src}. Release it and try again", Fore.RED)
            exception = True
        except Exception:
            print_console(f"Error while moving: retrying every second", Fore.RED)
            time.sleep(1)


def safe_remove_file(path):
    if os.path.exists(path):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except PermissionError:
            os.chmod(path, stat.S_IWRITE)
            os.remove(path)
        except Exception:
            time.sleep(0.5)


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


def offset_interface(tracks, type_, shift_now=False):
    if len(tracks) > 0:
        print(f"\nInsert a delay (and extension in s) - i.e. -1400 +10 - in MS for the following {type_} TRACKS:")
    for t in tracks:
        t["offset"] = 0
        delay = None
        extension = None
        while delay is None:
            delay = input(f'   {t["tags"]["title"]} - {t["tags"]["language"]}: ').lower().strip()
            if delay == "":
                delay = None
                break
            numbers = delay.split(" ")
            try:
                delay = int(numbers[0])
                if len(numbers) > 1 and shift_now:
                    extension = int(numbers[1])
            except:
                delay = None
                extension = None
        if (delay is not None and delay != 0) or (extension is not None and extension != 0):
            delay = 0 if delay is None else delay
            extension = 0 if extension is None else extension
            if shift_now:
                exception = True
                while exception:
                    exception = False
                    try:
                        src = t["path"]
                        os.chmod(src, stat.S_IWRITE)
                        shift_srt_subs(src, src, delay, extend_s=extension)
                    except PermissionError:
                        print_console(f"Access denied on {src}. Release it and try again", Fore.RED)
                        exception = True
                    except Exception as e:
                        print(f"{Fore.RED}{e}{Style.RESET_ALL}")
                        time.sleep(0.5)
            else:
                t["offset"] = delay


def execute(cmd, errorMsg):
    try:
        result = subprocess.Popen(cmd, text=True, shell=True)
        result.wait()
        if result.returncode != 0:
            print(f"{errorMsg}")
            return False
        return True
    except subprocess.CalledProcessError as e:
        print(f"Command: {' '.join(cmd)}\n{errorMsg}:\n{e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False


def seconds_to_mmss(seconds):
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    return f"{minutes:02}:{remaining_seconds:02}"


def sftp_mkdir_p(sftp, remote_directory):
    """
    Recursively create remote directories like mkdir -p.
    """
    dirs = []
    path = remote_directory

    while len(path) > 1:
        dirs.append(path)
        path = os.path.dirname(path)
    dirs.reverse()

    for d in dirs:
        try:
            sftp.stat(d)
        except IOError:
            sftp.mkdir(d)


def list_ready_dirs(files):
    ready_dir_path = Path(PURGATORY_FOLDER).joinpath(READY_FOLDER_NAME)
    files += os.listdir(ready_dir_path)


def list_holder_dirs(files):
    global sftp
    if "@" in FINAL_MOVIE_HOLDER_PATH:
        if sftp:
            files += sftp.listdir(FINAL_MOVIE_HOLDER_PATH.split(":")[1])
    else:
        files += os.listdir(FINAL_MOVIE_HOLDER_PATH)


def copy_via_hhd(root, files, src, dst, callback, copied_in_folder=0, chunk_size=10*1024*1024):
    rel_path = Path(root).relative_to(src)
    target_root = dst / rel_path
    target_root.mkdir(parents=True, exist_ok=True)
    for file in files:
        src_file = Path(root) / file
        dst_file = target_root / file
        file_size = src_file.stat().st_size
        copied = 0
        with open(src_file, 'rb') as fsrc, open(dst_file, 'wb') as fdst:
            while True:
                buf = fsrc.read(chunk_size)
                if not buf:
                    break
                fdst.write(buf)
                copied += len(buf)
                copied_in_folder += len(buf)
                if callback:
                    callback(copied_in_folder, file_size)
        shutil.copystat(src_file, dst_file)
    return copied_in_folder


def copy_via_paramiko(root, files, src, dst, callback, copied_in_folder=0, chunk_size=1024*1024):
    global sftp

    if sftp is None:
        print(f"{Fore.RED}Upload to {FINAL_MOVIE_HOLDER_PATH} not possible{Style.RESET_ALL}", end="")
        return
    rel_path = Path(root).relative_to(src)
    remote_root = dst / rel_path
    sftp_mkdir_p(sftp, str(remote_root))

    for file in files:
        local_file = Path(root) / file
        remote_file = remote_root / file
        file_size = local_file.stat().st_size

        with open(local_file, "rb") as fsrc, sftp.open(str(remote_file), "wb") as fdst:

            while True:
                buf = fsrc.read(chunk_size)
                if not buf:
                    break
                fdst.write(buf)
                copied_in_folder += len(buf)

                if callback:
                    callback(copied_in_folder, file_size)

        st = local_file.stat()
        sftp.utime(str(remote_file), (st.st_atime, st.st_mtime))
    return copied_in_folder


def copy_folder_with_progress(src, dst, callback=None):
    """
    Copy a folder recursively with progress.
    - src, dst: folders (Path or str)
    - callback(bytes_copied, total_bytes)
    """
    global sftp

    src = Path(src)
    dst = Path(dst)

    copied_in_folder = 0
    for root, _, files in os.walk(src):
        if "@" in FINAL_MOVIE_HOLDER_PATH:
            copied_in_folder = copy_via_paramiko(root, files, src, dst, callback, copied_in_folder)
        else:
            copied_in_folder = copy_via_hhd(root, files, src, dst, callback, copied_in_folder)

    if sftp:
        sftp.close()
    if copied_in_folder > 0:
        shutil.rmtree(src, onerror=remove_readonly)
