import os
from pathlib import Path
import shutil
import traceback
import re
import requests
import subprocess
import json
import requests
from colorama import Fore, Style
from utils import *


def get_stream_info(input_path: Path):
    cmd_probe = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(input_path)]
    result = subprocess.run(cmd_probe, capture_output=True, text=True)
    info = VideoInfo(json.loads(result.stdout + result.stderr), input_path)
    return info


def handle_audio_conflicts(info: VideoInfo, target_file: Path):
    audio_idx = 0
    all_codes_audio = []
    for v in info.get_audio_tracks():
        language = v["tags"]["language"]
        title = v["tags"]["title"]
        code = tryMagnet(language)
        if language not in supported_lang_codes:
            while code not in supported_lang_codes + ["d"]:
                msg = f"   Type a valid code for the audio track \"{audio_idx}: {language} - {title}\".\n   Alternatively, drop it (d), test it (t) or open folder (o): "
                code = print_console(msg, Fore.YELLOW).strip()
                perform = open_or_test(code, target_file)
                if perform:
                    continue
            if code in supported_lang_codes:
                v["tags"]["language"] = code
                info.remux_audio = True
            elif code == "d":
                v["tags"]["language"] = None
                info.remux_audio = True
        
        extended_languages = [lang for lang, codes in full_language_codes.items() if code in codes]
        extended_language = extended_languages[0] if len(extended_languages) else code
        if v["tags"]["title"] != extended_language:
            v["tags"]["title"] = extended_language
            info.remux_audio = True

        audio_idx += 1
        all_codes_audio.append(v["tags"]["language"])

    all_codes_audio = set([x for x in all_codes_audio if x in supported_lang_codes])
    for c in all_codes_audio:
        candidates = []
        for e in info.get_audio_tracks():
            if e["tags"]["language"] == c:
                candidates.append(e)
        if len(candidates) > 1:
            print("   More than 1 audio track with the same language code. Please select only one of them:")
            for i, candidate in enumerate(candidates):
                print(f'\t{i}: {candidate["tags"]["language"]} - {candidate["tags"]["title"]}')
            selection = None
            while selection is None:
                selection = print_console("Press 't' to test, 'o' to open folder.\n   Insert a number: ", Fore.YELLOW).strip()
                perform = open_or_test(selection, target_file)
                if perform:
                    selection = None
                    continue
                try:
                    selection = int(selection)
                    if selection < 0 or selection >= len(candidates):
                        selection = None
                except:
                    print(traceback.format_exc())
                    selection = None
            for i, candidate in enumerate(candidates):
                if selection != i:
                    info.remux_audio = True
                    candidate["tags"]["language"] = None


def handle_subs_conflicts(info: VideoInfo, target_file: Path):
    sub_idx = 0
    all_codes_srt = []
    for v in info.get_sub_tracks():
        language = v["tags"]["language"]
        title = v["tags"]["title"]
        if language not in supported_lang_codes:
            code = tryMagnet(language)
            while code not in supported_lang_codes + ["d"]:
                msg = f"   Type a valid code for the sub \"{sub_idx}: {language} - {title}\".\n   Alternatively, drop it (d), test it (t) or open folder (o): "
                code = print_console(msg, Fore.YELLOW).strip()
                perform = open_or_test(code, target_file)
                if perform:
                    continue
            if code in supported_lang_codes:
                v["tags"]["language"] = code
            elif code == "d":
                v["tags"]["language"] = None
        sub_idx += 1
        all_codes_srt.append(v["tags"]["language"])

    all_codes_srt += [x["tags"]["language"] for x in info.get_external_subs() if x["extension"] == "srt"]
    all_codes_srt = set([x for x in all_codes_srt if x in supported_lang_codes])
    for c in all_codes_srt:
        candidates = []
        for e in info.get_sub_tracks():
            if e["tags"]["language"] == c:
                candidates.append(e)
        for e in info.get_external_subs():
            if e["tags"]["language"] == c:
                candidates.append(e)
        if len(candidates) > 1:
            print("   More than 1 subtitle with the same language code. Please select only one of them:")
            for i, candidate in enumerate(candidates):
                print(f'\t{i}: {candidate["tags"]["language"]} - {candidate["tags"]["title"]}')
            selection = None
            while selection is None:
                selection = print_console("Press 't' to test, 'o' to open folder.\n   Insert a number: ", Fore.YELLOW).strip()
                perform = open_or_test(selection, target_file)
                if perform:
                    selection = None
                    continue
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
                url = f"https://api.themoviedb.org/3/movie/{r['id']}"
                r = requests.get(url, params=params).json()
                return [sr], r
            if len(simple_results) > 10:
                break

        results = data.get("results", [])
        if not results or page > 2 or page >= data.get("total_pages", 0):
            break
        page += 1
    
    return simple_results, None


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
    candidates, details = check_on_imdb(name, year)
    if details:
        print(f"{Fore.GREEN}   Movie found on IMDB: {candidates[0][0]} ({candidates[0][1]}){Style.RESET_ALL}")
        print(f"{Fore.GREEN}   Genres: " + ", ".join([x["name"] for x in details["genres"]]) + Style.RESET_ALL)
        print(f"{Fore.GREEN}   Original language: {details['original_language']}" + Style.RESET_ALL)
        print(f"{Fore.GREEN}   Revenue: {round(details['revenue']/10**6, 1)}M€" + Style.RESET_ALL)
        print(f"{Fore.GREEN}   Runtime: {details['runtime']}min" + Style.RESET_ALL)
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


def process_movie(info: VideoInfo):
    pattern = re.compile(r"^(?P<name>.+?)(?:\s*\((?P<year>\d{4})\))?$")
    file_path = info.video_path
    match = pattern.match(file_path.stem)
    name = sanitize_filename(match.group("name").strip()) if match else sanitize_filename(file_path.stem)
    year = sanitize_filename(match.group("year")) or "" if match else ""

    name, year = prompt_imdb(name, year)
    fullname = f"{name} ({year})" if year else name

    print()
    target_folder_path = file_path.parent.parent.joinpath(fullname)
    target_file = target_folder_path.joinpath(f"{fullname}.mkv")
    
    if target_file != file_path:
        shutil.move(file_path, file_path.parent.joinpath(f"{target_file.stem}.mkv"))
        shutil.move(file_path.parent, target_folder_path)

    folder_path = target_file.parent
    if not folder_path.exists():
        os.mkdir(folder_path)

    recompute = True
    while recompute:
        recompute = False
        info.external_subs = []
        for x in os.listdir(target_file.parent):
            if x.split(".")[-1] in supported_external_subs_ext:
                code = tryMagnet(x)
                if not code:
                    while True:
                        code = print_console(f"   Insert a language code for External SUB: {x};\nRecompute (r), drop it (d), test it (t), open folder (o) or mark it as multi-lang (multi): ", Fore.YELLOW).strip()
                        perform = open_or_test(code, target_file)
                        if perform:
                            continue
                        if code == "r":
                            recompute = True
                            break
                        if code in supported_lang_codes + ["d", "multi"]:
                            if code == "d":
                                code = None
                            break
                if recompute:
                    break
                if code:
                    info.add_external_sub(path=target_file.parent.joinpath(x), extension=x.split(".")[-1], title=x, language=code)

    handle_audio_conflicts(info, target_file)
    handle_subs_conflicts(info, target_file)
    
    for sub in info.get_external_subs():
        if sub["tags"]["language"]:
            new_path = sub["path"].parent.joinpath(target_file.stem + '.' + sub["tags"]["language"] + f'.{sub["extension"]}')
            subprocess.run(["attrib", "-H", sub["path"]])
            if new_path != sub["path"]:
                shutil.move(sub["path"], new_path)
                sub["path"] = new_path
                if sub["tags"]["language"] == "multi":
                    sub["tags"]["title"] = target_file.stem
    info.video_path = target_file
    return info


def remux(info: VideoInfo):
    # remux_subs = len(info.get_sub_tracks()) != 0 and any([(x["tags"]["language"] is None) for x in info.get_sub_tracks()])
    target_file = info.video_path
    folder_path = target_file.parent
    temp_file = folder_path.joinpath("temp__" + target_file.stem + ".mkv")
    cmd_grps = []

    cmd_grps.append(["mkvmerge", "-o", str(temp_file)])
    cmd_grps.append(["--title", target_file.stem])
    cmd_grps.append(["--video-tracks", "0"])

    couples = [
        ("--audio-tracks", info.get_audio_tracks),
        ("--subtitle-tracks", info.get_sub_tracks),
    ]
    for kw, get_e in couples:
        tracks = {}
        for e in get_e():
            if e["tags"]["language"] is not None:
                default = e["tags"]["language"] == "eng"
                tracks[e["index"]] = [
                    '--language', f'{e["index"]}:{e["tags"]["language"]}',
                    '--track-name', f'{e["index"]}:{e["tags"]["language"]}',
                    '--default-track', f'{e["index"]}:{"yes" if default else "no"}',
                    '--forced-track', f'{e["index"]}:no',
                    '--sync', f'{e["index"]}:{e["offset"]}'
                    ]
                
        if len(tracks):
            cmd_grps.append([kw, ",".join([str(x) for x in tracks.keys()])])
            for e in tracks.values():
                cmd_grps.append(e)

    cmd_grps.append([str(target_file)])
    cmd = [s for x in cmd_grps for s in x]
    
    res = execute(cmd, errorMsg=f"Error during mkvmerge execution to extract subs")
    if not res:
        msg = f"\n"
        msg += " ---------------------------------------------------------------------\n"
        msg += "|                         MKVMERGE error!                             |\n"
        msg += " ---------------------------------------------------------------------\n\n"
        print("\nCommand:")
        for g in cmd_grps:
            print(" ".join(g) + " `")
        safe_remove_file(temp_file)
        print(f"{Fore.RED}{msg}{Style.RESET_ALL}")
        return False
    else:
        safe_remove_file(target_file)
        shutil.move(temp_file, target_file)
    
    return True
