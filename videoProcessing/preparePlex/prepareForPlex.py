import sys
import os
import subprocess
from pathlib import Path
import shutil
import traceback
from datetime import datetime
import re
import stat
import ctypes
import json
from dotenv import dotenv_values
try:
    import colorama
except ImportError:
    print("colorama not found, installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "colorama"])
    import colorama
try:
    import requests
except ImportError:
    print("requests not found, installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

API_KEY = dotenv_values(os.path.join(os.path.dirname(__file__), ".env"))["IMDB_KEY"]

if sys.platform == "win32":
    kernel32 = ctypes.windll.kernel32
    hStdOut = kernel32.GetStdHandle(-11)
    mode = ctypes.c_uint()
    kernel32.GetConsoleMode(hStdOut, ctypes.byref(mode))
    kernel32.SetConsoleMode(hStdOut, mode.value | 0x0004)


from colorama import init, Fore, Style
init(autoreset=True)


FINAL_MOVIE_HOLDER_PATH = dotenv_values(os.path.join(os.path.dirname(__file__), ".config"))["FINAL_MOVIE_HOLDER_PATH"]
PURGATORY_FOLDER = dotenv_values(os.path.join(os.path.dirname(__file__), ".config"))["PURGATORY_FOLDER"]

TRASH_FOLDER_NAME = ".trash"
WORKING_FOLDER_NAME = ".working"
READY_FOLDER_NAME = ".ready"
SKIP_KWS = ["skip", "s"]


video_extensions = [
    "mp4",
    "mkv",
    "avi",
]


def print_console(msg, color: str = None):
    if color:
        print(f"{color}{msg}{Style.RESET_ALL}", end="")
    else:
        print(msg, end="")
    return input()


language_codes = [
    "fr", "fre", "fra",   # French
    "es", "spa",          # Spanish
    "ko", "kor",          # Korean
    "en", "eng",          # English
    "de", "ger", "deu",   # German
    "it", "ita"           # Italian
]


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


def get_stream_info(input_path: Path):
    # cmd_probe = ["mkvmerge", "-J", str(input_path)]
    # result = subprocess.run(cmd_probe, capture_output=True, text=True)
    # output = json.loads(result.stdout + result.stderr)
    # info = {
    #     "video": [t for t in output["tracks"] if t["type"] == "video"], 
    #     "audio": [t for t in output["tracks"] if t["type"] == "audio"],
    #     "sub": [t for t in output["tracks"] if t["type"] == "subtitles"],
    #     "ext_srt": []
    # }
    
    cmd_probe = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(input_path)]
    result = subprocess.run(cmd_probe, capture_output=True, text=True)
    info = VideoInfo(json.loads(result.stdout + result.stderr))
    return info


def handle_subs_conflicts(info: VideoInfo):
    print()
    sub_idx = 0
    all_codes = []
    for v in info.get_sub_tracks():
        language = v["tags"].get("language", "")
        title = v["tags"].get("title", "")
        if language not in language_codes:
            code = None
            while code not in language_codes + SKIP_KWS:
                code = print_console(f"   Type a valid code for the sub {sub_idx}: {language} - {title} or just skip: ", Fore.YELLOW).strip()
            if code not in SKIP_KWS:
                v["tags"]["language"] = code
            else:
                v["tags"]["language"] = None
        sub_idx += 1
        all_codes.append(v["tags"]["language"])

    all_codes += [x["tags"]["language"] for x in info.external_subs]
    all_codes = set([x for x in all_codes if x in language_codes])
    for c in all_codes:
        candidates = []
        for e in info.get_sub_tracks():
            if e["tags"]["language"] == c:
                candidates.append(e)
        for e in info.external_subs:
            if e["tags"]["language"] == c and e["path"].suffix not in [".idx"]:
                candidates.append(e)
        if len(candidates) > 1:
            print(candidates)
            print("   More than 1 subtitle with the same language code. Please select only one of them:")
            for i, candidate in enumerate(candidates):
                print(f'\t{i}: {candidate["tags"]["language"]} - {candidate["tags"]["title"]}')
            selection = None
            while selection is None:
                selection = print_console("   Insert a number: ", Fore.YELLOW).strip()
                try:
                    selection = int(selection)
                    if selection < 0 or selection >= len(candidates):
                        selection = None
                except:
                    print(traceback.format_exc())
                    selection = None
            for i, candidate in enumerate(candidates):
                if selection != i:
                    candidate["tags"]["language"] = None

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


def sanitize_filename(name: str) -> str:
    if not name:
        return name
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', name)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.strip().rstrip(' .')
    return cleaned or name


def check_on_imdb(name, year):
    page = 1
    simple_results = []
    while True:
        url = f"https://api.themoviedb.org/3/search/movie"
        params = {
            "api_key": API_KEY,
            "query": name,
            "page": page
        }
        response = requests.get(url, params=params)
        data = response.json()
        for r in data["results"]:
            sr = (r["title"].replace(":", " -"), r["release_date"][:4])
            simple_results.append(sr)
            if name == sr[0] and (not year or year == sr[1]):
                return True, [sr]
            if len(simple_results) > 10:
                break

        results = data.get("results", [])
        if not results or page > 2 or page >= data.get("total_pages", 0):
            break
        page += 1
    
    return False, simple_results


def get_name_year(name, year, up_to_index: None):
    index_option = f" or insert a number of one of the alternatives" if up_to_index > 0 else ""
    name_ = sanitize_filename(print_console(f"   Rename movie (default '{name}'){index_option}: ", Fore.YELLOW).strip())
    try:
        index = int(name_)
        if index >= 0 and index < up_to_index:
            return None, None, index
    except:
        pass
    year_ = year
    first_ask = False
    while not first_ask or year_ is None:
        first_ask = True
        try:
            year_ = sanitize_filename(print_console(f"   Insert the year (default '{year}'): ", Fore.YELLOW).strip())
            if year_.strip() == "":
                break
            int_year = int(year_)
            year_ = str(int_year)
            if int_year < 1900 or int_year > 2050:
                raise
        except:
            print(f"   {Fore.RED}Insert a valid year.{Style.RESET_ALL}")
            year_ = None
    name = name_ if name_ else name
    year = year_ if year_ else year
    return name, year, None


def prompt_imdb(name, year):
    found, candidates = check_on_imdb(name, year)
    if found:
        print(f"{Fore.GREEN}   Movie found on IMDB: {candidates[0][0]} ({candidates[0][1]}){Style.RESET_ALL}")
        name, year = candidates[0][0], candidates[0][1]
    else:
        print(f"{Fore.RED}   Movie not found on IMDB. Alternatives:\n{Style.RESET_ALL}")
        for i, c in enumerate(candidates):
            print(f"{Fore.RED}\t- ({i}) {c[0]} ({c[1]}){Style.RESET_ALL}")
        name, year, index = get_name_year(name, year, len(candidates))
        if index is not None:
            name, year = candidates[index]
        return prompt_imdb(name, year)
    return name, year


def process_movie(info: VideoInfo, file_path: Path):
    print(f"   Extracting subs from {file_path}")
    pattern = re.compile(r"^(?P<name>.+?)(?:\s*\((?P<year>\d{4})\))?$")
    match = pattern.match(file_path.stem)
    name = sanitize_filename(match.group("name").strip()) if match else sanitize_filename(file_path.stem)
    year = sanitize_filename(match.group("year")) or "" if match else ""

    name, year = prompt_imdb(name, year)
    fullname = f"{name} ({year})" if year else name

    target_folder_path = file_path.parent.parent.joinpath(fullname)
    target_file = target_folder_path.joinpath(f"{fullname}{file_path.suffix}")
    if target_file != file_path:
        shutil.move(file_path, file_path.parent.joinpath(target_file.stem + file_path.suffix))
        shutil.move(file_path.parent, target_folder_path)

    folder_path = target_file.parent
    if not folder_path.exists():
        os.mkdir(folder_path)

    for x in os.listdir(target_file.parent):
        if x.split(".")[-1] == 'srt':
            pattern = re.compile(rf"(?<![A-Za-z])(?:{'|'.join(language_codes)})(?![A-Za-z])",re.IGNORECASE)
            match = pattern.search(x)
            code_found = match.group(0).lower() if match else None
            info.external_subs.append({
                "path": target_file.parent.joinpath(x),
                "codec_name": "subrip",
                "tags": {
                    "title": f"External SUB: {x}",
                    "language": code_found
                }
            })

    handle_subs_conflicts(info)
    
    for sub in info.external_subs:
        if sub["tags"]["language"]:
            new_path = sub["path"].parent.joinpath(target_file.stem + '.' + sub["tags"]["language"] + '.srt')
            if new_path != sub["path"]:
                shutil.move(sub["path"], new_path)
        else:
            safe_remove_file(sub["path"])
    
    if len(info.get_sub_tracks()) != 0 and any([(x["tags"]["language"] not in language_codes) for x in info.get_sub_tracks()]):
        temp_file = folder_path.joinpath("temp__" + target_file.stem + ".mkv")
        # cmd = ["mkvextract", "tracks", str(target_file)]
        # for track in info.get_sub_tracks():
        #     code = track["properties"]["language"]
        #     if code:
        #         srt_path = folder_path.joinpath(target_file.stem + '.' + code + '.srt')
        #         cmd += [f'{track["id"]}:{srt_path}']

        # res = execute(cmd, errorMsg=f"Error during ffmpeg execution to extract subs")
        # if not res:
        #     return
        cmd = ["ffmpeg", "-y", "-i", str(target_file), "-map", "0:v", "-map", "0:a"]
        output_sub_index = 0
        for index, s in enumerate(info.get_sub_tracks()):
            if s["tags"]["language"] in language_codes:
                cmd += ["-map", f"0:s:{index}"]
                cmd += [f"-metadata:s:s:{output_sub_index}", f'title={s["tags"]["language"]}']
                cmd += [f"-metadata:s:s:{output_sub_index}", f'language={s["tags"]["language"]}']
                output_sub_index += 1
        cmd += ["-c", "copy", str(temp_file)]
        res = execute(cmd, errorMsg=f"Error during ffmpeg execution to extract subs")
        if not res:
            return
        
        safe_remove_file(target_file)
        shutil.move(temp_file, target_file)
    
    return target_folder_path, info
    


class Folder:
    def __init__(self, path: Path):
        self.path = path
        self.sub_folders: list[Folder] = []
        self.video_paths = []
        self.video_path: Path = None
        self.subs_paths = []
        self.others_paths = []
        self.get_paths()
    
    def get_paths(self):
        files_and_folders = os.listdir(self.path)
        files = [x for x in files_and_folders if self.path.joinpath(x).is_file()]
        self.video_paths = [self.path.joinpath(x) for x in files if x.split(".")[-1] in video_extensions]
        if len(self.video_paths):
            self.video_path = self.video_paths[0]
        self.subs_paths = [self.path.joinpath(x) for x in files if x.split(".")[-1] == 'srt']
        self.other_paths = [self.path.joinpath(x) for x in files if x.split(".")[-1] not in (video_extensions + ['srt'])]
        self.sub_folders = [Folder(self.path.joinpath(x)) for x in files_and_folders
                            if not self.path.joinpath(x).is_file() and x not in [TRASH_FOLDER_NAME, WORKING_FOLDER_NAME, READY_FOLDER_NAME]]
    
    def is_valid(self):
        return len(self.video_paths) == 1
    
    def to_working_dir(self, working_dir_path: Path, trash_path: Path):
        new_folder_path = working_dir_path.joinpath(self.path.stem)
        os.mkdir(new_folder_path)
        shutil.move(self.video_path, new_folder_path.joinpath(self.video_path.stem + self.video_path.suffix))
        for sub in self.subs_paths:
            shutil.move(sub, new_folder_path.joinpath(sub.stem + sub.suffix))
        if not len(os.listdir(self.path)):
            os.rmdir(self.path)
        else:
            shutil.move(self.path, trash_path.joinpath(self.path.stem))
        
    
    def process(self, move_to: Path):
        if self.is_valid():
            info = get_stream_info(self.video_path)
            new_folder_path, info = process_movie(info, self.video_path)

            msg = f"\n ----------------------------------------\n"
            msg += f"|                RECAP                   |\n"
            msg += f"|----------------------------------------\n"
            msg += f"|  Title: {new_folder_path.stem}\n"
            msg += f"|----------------------------------------\n"

            for vs in info.get_video_tracks():
                video_attr = {"codec": vs["codec_name"], "pixel_dim": f'{vs["width"]}x{vs["height"]}'}
                msg += f"|  Video track {vs['index']}:\n"
                for k, v in video_attr.items():
                    msg += f"|     {k}: {v}\n"
            msg += f"|----------------------------------------\n"
            for aus in info.get_audio_tracks():
                audio_attr = {"codec": aus["codec_name"]}
                msg += f"|  Audio track {aus['index']}:\n"
                for k, v in audio_attr.items():
                    msg += f"|     {k}: {v}\n"
            msg += f"|----------------------------------------\n"
            if (len(info.get_sub_tracks())):
                for ss in info.get_sub_tracks():
                    if ss["tags"].get("language", ""):
                        ss["tags"]["language"] = ss["tags"].get("language", "")
                        ss["tags"]["title"] = ss["tags"].get("title", "")
                        sub_attr = {"codec": ss["codec_name"], "language": ss["tags"]["language"], "title": ss["tags"]["title"]}
                        msg += f"|  Subtitle {ss['index']}:\n"
                        for k, v in sub_attr.items():
                            msg += f"|     {k}: {v}\n"
            else:
                msg += f"|  {Fore.LIGHTRED_EX}NO SUBTITLES{Fore.LIGHTCYAN_EX}\n"
            msg += f"|----------------------------------------\n"
            if (len(info.external_subs)):
                for ss in info.external_subs:
                    if ss["tags"].get("language", ""):
                        ss["tags"]["language"] = ss["tags"].get("language", "")
                        ss["tags"]["title"] = ss["tags"].get("title", "")
                        sub_attr = {"language": ss["tags"]["language"], "title": ss["tags"]["title"]}
                        msg += f"|  Subtitle {ss.get('index', 'extra')}:\n"
                        for k, v in sub_attr.items():
                            msg += f"|     {k}: {v}\n"
            else:
                msg += f"|  {Fore.LIGHTRED_EX}NO EXTERNAL SUBTITLES{Fore.LIGHTCYAN_EX}\n"
            msg += f"|----------------------------------------\n"

            msg += f"\n\nPress any key to mark as 'ready' \n"
            print_console(msg, Fore.LIGHTCYAN_EX)
            if new_folder_path:
                try:
                    to_path = move_to.joinpath(new_folder_path.stem)
                    if to_path.exists():
                        print(f"{Fore.LIGHTYELLOW_EX}   Folder {to_path} already exists. Overwriting now.{Style.RESET_ALL}")
                        shutil.rmtree(to_path, onerror=remove_readonly)
                    shutil.move(new_folder_path, to_path)
                except:
                    print(f"Error while moving folder from working dir to ready dir:\n{traceback.format_exc()}")
                    return


def clean_dirs(path):
    sub_folders = [path.joinpath(x) for x in os.listdir(path)]
    if not sub_folders:
        os.rmdir(path)
    else:
        for f in sub_folders:
            if not len(os.listdir(f)):
                os.rmdir(f)
        if not len(os.listdir(path)):
            os.rmdir(path)


def prepare_plex(target_path):
    if target_path != Path(PURGATORY_FOLDER):
        print_console(f"You must be on the predefined location: {str(PURGATORY_FOLDER)}\n\nPress Enter to exit", Fore.RED)
        return

    # Setting up the environment
    main_folder = Folder(target_path)
    trash_path = target_path.joinpath(TRASH_FOLDER_NAME)
    cur_trash_path = trash_path.joinpath(datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    working_dir_path = target_path.joinpath(WORKING_FOLDER_NAME)
    ready_dir_path = target_path.joinpath(READY_FOLDER_NAME)
    for folder in [trash_path, cur_trash_path, working_dir_path, ready_dir_path]:
        if not folder.exists():
            os.mkdir(folder)
    
    try:
        # Handling top-most folders
        invalid_folders: list[Folder] = []
        for folder in main_folder.sub_folders:
            if folder.is_valid():
                folder.to_working_dir(working_dir_path, trash_path=cur_trash_path)
            else:
                invalid_folders.append(folder)

        # Handling top-most files
        for file in main_folder.video_paths:
            new_folder_path = working_dir_path.joinpath(file.stem)
            os.mkdir(new_folder_path)
            shutil.move(file, new_folder_path.joinpath(file.stem + file.suffix))

        # Sharing info about skipped folders/files
        if len(invalid_folders):
            msg = f"The following containers have been skipped because invalid folders:\n\nPress Enter to continue..."
            for f in invalid_folders:
                msg += f"\t- {f.path.stem}\n"
            print_console(msg, Fore.LIGHTYELLOW_EX)
        if len(main_folder.other_paths):
            msg = f"The following files have been skipped because invalid video:\n\nPress Enter to continue..."
            for f in main_folder.other_paths:
                msg += f"\t- {f.path.stem}\n"
            print_console(msg, Fore.LIGHTYELLOW_EX)
        
        # The structure of the working_path is fixed at this point
        working_folder = Folder(working_dir_path)
        for folder in working_folder.sub_folders:
            folder.process(move_to=ready_dir_path)
    
    except Exception:
        print(traceback.format_exc())

    clean_dirs(working_dir_path)
    clean_dirs(trash_path)
    
    print(f"{Fore.GREEN}Preparation to Plex completed.{Style.RESET_ALL}")
    ready_folder = Folder(ready_dir_path)
    if len(ready_folder.sub_folders):
        print_console("Press Enter to send files to the server...", Fore.YELLOW)

        for folder in ready_folder.sub_folders:
            if "@" in FINAL_MOVIE_HOLDER_PATH:
                print(f"Uploading {folder.path} to the server...")
                cmd = ["scp", "-r", str(folder.path), f"{FINAL_MOVIE_HOLDER_PATH}/{folder.path.stem + folder.path.suffix}"]
                res = execute(cmd, errorMsg=f"Error during scp execution to upload movie")
                if res:
                    shutil.rmtree(folder.path, onerror=remove_readonly)
            else:
                print(f"Moving {folder.path} into {FINAL_MOVIE_HOLDER_PATH}...")
                shutil.move(folder.path, f"{FINAL_MOVIE_HOLDER_PATH}/{folder.path.stem + folder.path.suffix}")
    
    clean_dirs(ready_dir_path)
    print(f"{Fore.GREEN}Preparation to Plex completed.{Style.RESET_ALL}")
    print_console("Press Enter to exit")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_path = Path(sys.argv[1].replace("\n", ""))
        prepare_plex(target_path)
    else:
        print_console("No path target\n\nPress Enter to exit", Fore.RED)