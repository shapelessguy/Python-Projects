import os
from pathlib import Path
import shutil
import traceback
import re
import requests
import subprocess
import re
import json
import requests
from colorama import Fore, Style
from utils import *


def get_stream_info(input_path: Path):
    cmd_probe = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(input_path)]
    result = subprocess.run(cmd_probe, capture_output=True, text=True)
    info = VideoInfo(json.loads(result.stdout + result.stderr))
    return info


def handle_subs_conflicts(info: VideoInfo):
    print()
    sub_idx = 0
    all_codes_srt = []
    for v in info.get_sub_tracks():
        language = v["tags"].get("language", "")
        title = v["tags"].get("title", "")
        if language not in supported_lang_codes:
            code = None
            while code not in supported_lang_codes + ["d"]:
                msg = f"   Type a valid code for the sub \"{sub_idx}: {language} - {title}\".\n   Alternatively, drop it (d) or keep it (any other key): "
                code = print_console(msg, Fore.YELLOW).strip()
            if code in supported_lang_codes:
                v["tags"]["language"] = code
            elif code == "d":
                v["tags"]["language"] = None
        sub_idx += 1
        all_codes_srt.append(v["tags"]["language"])

    all_codes_srt += [x["tags"]["language"] for x in info.external_subs if x["extension"] == "srt"]
    all_codes_srt = set([x for x in all_codes_srt if x in supported_lang_codes])
    for c in all_codes_srt:
        candidates = []
        for e in info.get_sub_tracks():
            if e["tags"]["language"] == c:
                candidates.append(e)
        for e in info.external_subs:
            if e["tags"]["language"] == c:
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
        if x.split(".")[-1] in supported_external_subs_ext:
            pattern = re.compile(rf"(?<![A-Za-z])(?:{'|'.join(supported_lang_codes)})(?![A-Za-z])",re.IGNORECASE)
            match = pattern.search(x)
            code = match.group(0).lower() if match else None
            if not code or x.split(".")[-1] != "srt":
                code_match = False
                while not code_match:
                    code = print_console(f"   Insert a language code for External SUB: {x}, drop it (d) or mark it as multi-lang (multi): ", Fore.YELLOW).strip()
                    if code in supported_lang_codes + ["d", "multi"]:
                        if code == "d":
                            code = None
                        break
            info.external_subs.append({
                "path": target_file.parent.joinpath(x),
                "extension": x.split(".")[-1],
                "codec_name": "subrip",
                "tags": {
                    "title": f"External SUB: {x}",
                    "language": code
                }
            })

    handle_subs_conflicts(info)
    
    for sub in info.external_subs:
        if sub["tags"]["language"]:
            new_path = sub["path"].parent.joinpath(target_file.stem + '.' + sub["tags"]["language"] + f'.{sub["extension"]}')
            subprocess.run(["attrib", "-H", sub["path"]])
            if new_path != sub["path"]:
                shutil.move(sub["path"], new_path)
                sub["path"] = new_path
                if sub["tags"]["language"] == "multi":
                    sub["tags"]["title"] = target_file.stem
    
    if len(info.get_sub_tracks()) != 0 and any([(x["tags"]["language"] is None) for x in info.get_sub_tracks()]):
        temp_file = folder_path.joinpath("temp__" + target_file.stem + ".mkv")
        cmd = ["ffmpeg", "-y", "-i", str(target_file), "-map", "0:v", "-map", "0:a"]
        output_sub_index = 0
        for index, s in enumerate(info.get_sub_tracks()):
            if s["tags"]["language"] is not None:
                cmd += ["-map", f"0:s:{index}"]
                cmd += [f"-metadata:s:s:{output_sub_index}", f'title={s["tags"]["language"]}']
                cmd += [f"-metadata:s:s:{output_sub_index}", f'language={s["tags"]["language"]}']
                output_sub_index += 1
        cmd += ["-c", "copy", str(temp_file)]
        res = execute(cmd, errorMsg=f"Error during ffmpeg execution to extract subs")
        if not res:
            raise
        
        safe_remove_file(target_file)
        shutil.move(temp_file, target_file)
    
    return target_file, info
